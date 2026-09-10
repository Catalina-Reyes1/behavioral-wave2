"""Regresiones sobre los artefactos congelados de la entrega final."""
import unittest
import io
from contextlib import redirect_stdout
from unittest.mock import patch

import pandas as pd

from src.audit_final import (ROOT, audit_backtest, audit_hashes, audit_ioc, audit_models,
                             audit_signals, audit_test_isolation, audit_web, read_csv)


class FinalAuditTests(unittest.TestCase):
    def test_incomplete_frozen_period_stops_before_writing(self):
        import main
        period = {"analysis_start": main.START_DATE, "analysis_end": "2026-09-07"}
        with patch.object(main, "download_market_data") as market, patch.object(main, "download_wikimedia_pageviews"), \
             patch.object(main, "determine_common_period", return_value=period), patch.object(main, "save_market_data") as save, \
             redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, "corte final congelado"):
                main.main()
        self.assertEqual(market.call_args.kwargs["end"], "2026-09-09")
        save.assert_not_called()

    def test_unique_dates_all_principal_csv(self):
        for path in (ROOT / "data").glob("*/*.csv"):
            frame = read_csv(path.relative_to(ROOT))
            self.assertTrue(frame.index.is_unique, str(path))

    def test_domain_mutual_exclusion_and_next_session(self):
        result = audit_signals()
        self.assertEqual(result["events"], 70)
        self.assertEqual(result["train_events"], 53)
        self.assertEqual(result["test_events"], 17)

    def test_first_shift_is_missing_not_an_order(self):
        signals = read_csv("data/processed/behavioral_signals.csv")
        self.assertTrue(pd.isna(signals.Trade_Signal.iloc[0]))
        self.assertEqual(signals.Trade_Signal.isna().sum(), 1)

    def test_independent_ioc_from_raw_daily_history(self):
        result = audit_ioc()
        self.assertEqual(len(result["cases"]), 5)
        for row in result["cases"]:
            self.assertLess(pd.Timestamp(row["Fin_Referencia"]), pd.Timestamp(row["Date"]))

    def test_independent_train_fit_and_ar_car_capm(self):
        result = audit_models()
        self.assertGreater(result["sigma_epsilon"], 0)
        self.assertEqual(len(result["cases"]), 5)

    def test_all_trades_and_summary_independently_compounded(self):
        result = audit_backtest()
        self.assertEqual(result["events_checked"], 70)
        self.assertAlmostEqual(result["test_statistics"]["Net"]["p"], .3428686008369948)

    def test_perturbed_test_cannot_change_train_parameters_or_signals(self):
        self.assertTrue(all(audit_test_isolation().values()))

    def test_csv_json_snapshot_and_tooltip_entries(self):
        result = audit_web()
        self.assertEqual(result["event_dates_checked"], 70)
        self.assertEqual([r["Date"] for r in result["tooltip_records"]], ["2021-11-03", "2021-11-09"])
        self.assertEqual([r["Signal"] for r in result["tooltip_records"]], [-1, 1])
        self.assertEqual([r["Entry_Date"] for r in result["tooltip_records"]], ["2021-11-04", "2021-11-10"])

    def test_november_fifth_is_not_a_signal(self):
        row = read_csv("data/processed/behavioral_signals.csv").loc["2021-11-05"]
        self.assertEqual(row.Signal, 0)
        self.assertEqual(row.Trade_Signal, 0)
        self.assertAlmostEqual(row.IOC, 32.468646907044274)

    def test_financial_data_models_archive_and_workflow_unchanged(self):
        self.assertEqual(len(audit_hashes()["unchanged_files"]), 25)

    def test_web_academic_sections_and_unicode(self):
        html = (ROOT / "app/index.html").read_text(encoding="utf-8")
        for phrase in ["¿Contradice la eficiencia", "20 → 45 → 72 → 91 → 80", 'id="valor"',
                       'id="robustez"', 'data-bind="train_events"', 'data-bind="test_events"']:
            self.assertIn(phrase, html)
        self.assertNotIn("atenci?n", html)
        self.assertNotIn("se?al", html)


if __name__ == "__main__":
    unittest.main()
