import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from src.signals import calculate_signals, run_signals


def sample():
    dates = pd.bdate_range("2019-01-01", periods=15, name="Date")
    market = pd.DataFrame({
        "Sample": ["Train"] * 10 + ["Test"] * 5,
        "TSLA_Return": .01, "VOO_Return": .005, "AR": .004, "CAR_5": .02,
        "CAR_Z": list(np.arange(10) - 5) + [10, 0, -10, np.nan, 10],
    }, index=dates)
    attention = pd.DataFrame({
        "Pageviews": 100, "Attention_Z": 1.0, "IOC_Velocity": 0.0,
        "IOC": list(np.arange(10) * 10) + [80, 90, 80, 70, 60],
    }, index=dates)
    return market, attention


class SignalTests(unittest.TestCase):
    def test_thresholds_directions_and_next_market_day(self):
        market, attention = sample()
        signals, thresholds = calculate_signals(market, attention)
        self.assertAlmostEqual(thresholds["IOC_Extreme_Threshold"], 81)
        self.assertAlmostEqual(thresholds["CAR_Positive_Threshold"], 3.1)
        self.assertAlmostEqual(thresholds["CAR_Negative_Threshold"], -4.1)
        self.assertEqual(signals["Signal"].iloc[10:].tolist(), [-1, 0, 1, 0, 0])
        pd.testing.assert_series_equal(signals["Trade_Signal"], signals["Signal"].shift(1), check_names=False)
        self.assertTrue(pd.isna(signals["Trade_Signal"].iloc[0]))
        self.assertEqual(signals["Trade_Signal"].iloc[11], -1)

    def test_test_changes_cannot_change_thresholds_or_train(self):
        market, attention = sample()
        original, thresholds = calculate_signals(market, attention)
        market.loc[market["Sample"].eq("Test"), "CAR_Z"] = 100000
        attention.iloc[10:, attention.columns.get_loc("IOC")] = 0
        changed, new_thresholds = calculate_signals(market, attention)
        self.assertEqual(thresholds, new_thresholds)
        pd.testing.assert_frame_equal(original.iloc[:10], changed.iloc[:10])

    def test_weekends_do_not_enter_join_or_thresholds(self):
        market, attention = sample()
        original, thresholds = calculate_signals(market, attention)
        attention.loc[pd.Timestamp("2019-01-05")] = [100, 1, 0, 100]
        changed, new_thresholds = calculate_signals(market.sample(frac=1, random_state=1), attention)
        pd.testing.assert_frame_equal(original, changed, check_freq=False)
        self.assertEqual(thresholds, new_thresholds)
        self.assertEqual(changed.index.tolist(), market.index.tolist())

    def test_missing_attention_retains_market_day_without_event(self):
        market, attention = sample()
        attention = attention.drop(market.index[10])
        with self.assertWarns(UserWarning):
            signals, _ = calculate_signals(market, attention)
        self.assertEqual(len(signals), len(market))
        self.assertTrue(pd.isna(signals["IOC"].iloc[10]))
        self.assertEqual(signals["Signal"].iloc[10], 0)
        self.assertFalse(signals["Wave_Exhaustion"].iloc[11])

    def test_shift_crosses_train_test_boundary(self):
        market, attention = sample()
        attention.iloc[8, attention.columns.get_loc("IOC")] = 100
        attention.iloc[9, attention.columns.get_loc("IOC")] = 90
        signals, _ = calculate_signals(market, attention)
        self.assertEqual(signals["Signal"].iloc[9], -1)
        self.assertEqual(signals["Trade_Signal"].iloc[10], -1)
        self.assertEqual(signals["Sample"].iloc[10], "Test")

    def test_nan_warmup_ignored_per_variable(self):
        market, attention = sample()
        attention.iloc[0, attention.columns.get_loc("IOC")] = np.nan
        market.iloc[1, market.columns.get_loc("CAR_Z")] = np.nan
        signals, thresholds = calculate_signals(market, attention)
        self.assertAlmostEqual(thresholds["IOC_Extreme_Threshold"], np.quantile(np.arange(1, 10) * 10, .9))
        self.assertAlmostEqual(thresholds["CAR_Positive_Threshold"], np.quantile(np.delete(np.arange(10) - 5, 1), .9))
        self.assertFalse(signals["Wave_Extreme"].iloc[0])
        self.assertEqual(signals["Signal"].iloc[1], 0)

    def test_csv_output_preserves_sample_and_dates(self):
        market, attention = sample()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            market.to_csv(root / "market.csv")
            attention.to_csv(root / "attention.csv")
            result = run_signals(root / "market.csv", root / "attention.csv", root / "signals.csv")
            saved = pd.read_csv(root / "signals.csv", index_col="Date", parse_dates=["Date"])
            pd.testing.assert_frame_equal(result, saved, check_freq=False)
            pd.testing.assert_series_equal(saved["Sample"], market["Sample"], check_freq=False)

    def test_invalid_train_or_duplicate_dates_fail(self):
        market, attention = sample()
        with self.assertRaises(ValueError):
            calculate_signals(pd.concat([market, market.iloc[:1]]), attention)
        attention.loc[market.index[:10], "IOC"] = np.nan
        with self.assertRaises(ValueError):
            calculate_signals(market, attention)


if __name__ == "__main__":
    unittest.main()
