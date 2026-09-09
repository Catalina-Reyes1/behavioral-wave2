import hashlib
import json
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

import numpy as np
import pandas as pd

from src.export_web_data import ROOT, build_web_data, export_web_data


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.references, self.bindings = [], [], []

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if "id" in attrs:
            self.ids.append(attrs["id"])
        for key in ("src", "href"):
            if key in attrs:
                self.references.append(attrs[key])
        if "data-bind" in attrs:
            self.bindings.append(attrs["data-bind"])


@unittest.skipUnless((ROOT / "results/backtest_summary.csv").exists(), "Requiere los CSV validados del proyecto")
class WebExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = build_web_data()

    def test_summary_is_copied_from_existing_results(self):
        summary = pd.read_csv(ROOT / "results/backtest_summary.csv", index_col="Sample")
        for row in self.data["overview"]["results"]:
            for key, value in row.items():
                if key != "Sample":
                    actual = summary.loc[row["Sample"], key]
                    self.assertTrue(pd.isna(actual)) if value is None else self.assertAlmostEqual(value, actual)

    def test_parameters_reconstruct_saved_outputs_without_new_fit(self):
        market = pd.read_csv(ROOT / "data/processed/market_model.csv")
        params = self.data["overview"]["market_model"]
        np.testing.assert_allclose(market.Expected_Return, params["alpha"] + params["beta"] * market.VOO_Return, atol=1e-12)
        np.testing.assert_allclose(market.CAR_Z, market.CAR_5 / (params["sigma_epsilon"] * np.sqrt(5)), equal_nan=True, atol=1e-12)

    def test_signal_dates_and_market_prices_are_preserved(self):
        signals = pd.read_csv(ROOT / "data/processed/behavioral_signals.csv")
        expected = signals.loc[signals.Signal.ne(0)]
        self.assertEqual([row["Date"] for row in self.data["events"]["signals"]], expected.Date.tolist())
        self.assertEqual([row["Signal"] for row in self.data["events"]["signals"]], expected.Signal.tolist())
        market = pd.read_csv(ROOT / "data/processed/market_model.csv")
        np.testing.assert_allclose([row["TSLA_Price"] for row in self.data["series"]["market"]], market.TSLA_Price)
        attention = pd.read_csv(ROOT / "data/processed/attention_wave.csv")
        self.assertEqual(len(self.data["series"]["attention"]), len(attention))
        self.assertIsNone(self.data["series"]["attention"][0]["IOC"])

    def test_export_is_deterministic_strict_json_and_leaves_inputs_unchanged(self):
        sources = self.data["overview"]["sources"]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            export_web_data(output_dir=output)
            first = {path.name: path.read_bytes() for path in output.iterdir()}
            export_web_data(output_dir=output)
            self.assertEqual(first, {path.name: path.read_bytes() for path in output.iterdir()})
            for key in ["overview", "series", "events"]:
                parsed = json.loads((output / f"{key}.json").read_text(encoding="utf-8"), parse_constant=lambda value: self.fail(f"JSON no estándar: {value}"))
                self.assertEqual(parsed, self.data[key])
            snapshot = (output / "snapshot.js").read_text(encoding="utf-8")
            self.assertEqual(json.loads(snapshot.removeprefix("window.BEHAVIORAL_WAVE_DATA = ").removesuffix(";\n")), self.data)
        for source in sources:
            self.assertEqual(hashlib.sha256((ROOT / source["path"]).read_bytes()).hexdigest(), source["sha256"])

    def test_html_links_assets_sections_and_exported_data_exist(self):
        parser = PageParser()
        parser.feed((ROOT / "app/index.html").read_text(encoding="utf-8"))
        self.assertEqual(len(parser.ids), len(set(parser.ids)))
        for section in ["inicio", "la-ola", "ioc", "analisis", "mercado", "senales", "resultados", "metodologia", "manual"]:
            self.assertIn(section, parser.ids)
        for reference in parser.references:
            if reference.startswith("#"):
                self.assertIn(reference[1:], parser.ids)
            elif not reference.startswith("data:"):
                self.assertFalse(reference.startswith("http"), "La página debe ser autosuficiente")
                self.assertTrue((ROOT / "app" / reference).is_file(), reference)
        for key in ["overview", "series", "events"]:
            self.assertEqual(json.loads((ROOT / "app/data" / f"{key}.json").read_text(encoding="utf-8")), self.data[key])


if __name__ == "__main__":
    unittest.main()
