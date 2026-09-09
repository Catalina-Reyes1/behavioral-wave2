import unittest

import numpy as np
import pandas as pd
from scipy import stats

from src.capm_model import calculate_capm
from src.backtest import calculate_backtest, summarize_backtest


def market_sample():
    dates = pd.bdate_range("2019-01-01", periods=20, name="Date")
    market_return = np.array([.01, -.02, .03, .01, -.01] * 4)
    asset_return = .001 + 1.3 * market_return + np.sin(np.arange(20)) * .003
    market = pd.DataFrame({"Sample": ["Train"] * 10 + ["Test"] * 10,
                           "TSLA_Return": asset_return, "VOO_Return": market_return,
                           "Expected_Return": .001 + 1.3 * market_return}, index=dates)
    irx = pd.DataFrame({"IRX_Annual_Percent": np.linspace(2, 4, 20)}, index=dates)
    return market, irx


def event_sample():
    market, irx = market_sample()
    capm, _ = calculate_capm(market, irx)
    signals = market[["Sample", "TSLA_Return", "VOO_Return"]].copy()
    signals["AR"] = market.TSLA_Return - market.Expected_Return
    signals["IOC"] = 50.0
    signals["CAR_Z"] = 1.0
    signals["Trade_Signal"] = 0.0
    signals.iloc[0, signals.columns.get_loc("Trade_Signal")] = np.nan
    return signals, capm


class CAPMTests(unittest.TestCase):
    def test_fit_matches_independent_train_covariance_and_sigma(self):
        market, irx = market_sample()
        result, summary = calculate_capm(market, irx)
        np.testing.assert_allclose(result.RF_Daily, irx.IRX_Annual_Percent / 100 / 252)
        train = result.iloc[:10]
        beta = train.TSLA_Excess.cov(train.Market_Excess) / train.Market_Excess.var()
        alpha = train.TSLA_Excess.mean() - beta * train.Market_Excess.mean()
        self.assertAlmostEqual(summary["Alpha_CAPM"], alpha)
        self.assertAlmostEqual(summary["Beta_CAPM"], beta)
        self.assertAlmostEqual(summary["Sigma_Epsilon_CAPM"], train.CAPM_AR.std(ddof=1))
        np.testing.assert_allclose(result.CAPM_Expected_Return, result.RF_Daily + alpha + beta * (market.VOO_Return - result.RF_Daily))

    def test_only_past_forward_fill_and_no_backfill(self):
        market, irx = market_sample()
        irx = irx.drop(irx.index[[0, 1, 4]])
        result, summary = calculate_capm(market, irx)
        self.assertTrue(result.RF_Daily.iloc[:2].isna().all())
        self.assertAlmostEqual(result.RF_Daily.iloc[4], result.RF_Daily.iloc[3])
        self.assertEqual(result.RF_Observation_Date.iloc[4], market.index[3])
        self.assertEqual(summary["Train_Observations"], 8)

    def test_rate_before_first_market_date_is_available(self):
        market, irx = market_sample()
        irx = irx.iloc[1:]
        irx.loc[pd.Timestamp("2018-12-31")] = 2.5
        result, _ = calculate_capm(market, irx)
        self.assertAlmostEqual(result.RF_Daily.iloc[0], .025 / 252)
        self.assertEqual(result.RF_Observation_Date.iloc[0], pd.Timestamp("2018-12-31"))

    def test_changes_to_test_cannot_change_fitted_parameters(self):
        market, irx = market_sample()
        result, summary = calculate_capm(market, irx)
        market.loc[market.Sample.eq("Test"), ["TSLA_Return", "VOO_Return"]] += .5
        irx.iloc[10:, 0] = 20
        changed, new_summary = calculate_capm(market, irx)
        self.assertEqual(summary, new_summary)
        pd.testing.assert_frame_equal(result.iloc[:10], changed.iloc[:10])


class BacktestTests(unittest.TestCase):
    def test_five_returns_include_entry_without_second_shift(self):
        signals, capm = event_sample()
        signals.iloc[2, signals.columns.get_loc("Trade_Signal")] = 1
        events = calculate_backtest(signals, capm)
        row = events.iloc[0]
        actual = np.prod(1 + capm.TSLA_Return.iloc[2:7]) - 1
        normal = np.prod(1 + capm.Expected_Return.iloc[2:7]) - 1
        normal_capm = np.prod(1 + capm.CAPM_Expected_Return.iloc[2:7]) - 1
        self.assertEqual(events.index[0], signals.index[2])
        self.assertEqual(row.Signal_Date, signals.index[1])
        self.assertEqual(row.Exit_Date, signals.index[6])
        self.assertAlmostEqual(row.Forward_Return_5D, actual)
        self.assertAlmostEqual(row.Strategy_Net_Return, actual - .002)
        self.assertAlmostEqual(row.MarketModel_Normal_5D, normal)
        self.assertAlmostEqual(row.Abnormal_Strategy_MarketModel, actual - .002 - normal)
        self.assertAlmostEqual(row.Abnormal_Strategy_CAPM, actual - .002 - normal_capm)

    def test_short_profit_and_cost_with_declining_asset(self):
        signals, capm = event_sample()
        capm.loc[:, "TSLA_Return"] = -.01
        signals.loc[:, "TSLA_Return"] = -.01
        signals["AR"] = signals.TSLA_Return - capm.Expected_Return
        signals.iloc[2, signals.columns.get_loc("Trade_Signal")] = -1
        row = calculate_backtest(signals, capm).iloc[0]
        self.assertAlmostEqual(row.Strategy_Gross_Return, 1 - .99 ** 5)
        self.assertAlmostEqual(row.Strategy_Net_Return, 1 - .99 ** 5 - .002)
        self.assertAlmostEqual(row.Abnormal_Strategy_CAPM, row.Strategy_Net_Return + row.CAPM_Normal_5D)

    def test_overlaps_independent_and_incomplete_event_retained(self):
        signals, capm = event_sample()
        signals.iloc[[2, 3, 19], signals.columns.get_loc("Trade_Signal")] = [1, -1, 1]
        events = calculate_backtest(signals, capm)
        self.assertEqual(len(events), 3)
        self.assertTrue(events.Status.iloc[:2].eq("Completed").all())
        self.assertEqual(events.Status.iloc[2], "Incomplete_Horizon")
        self.assertTrue(pd.isna(events.Strategy_Net_Return.iloc[2]))
        summary = summarize_backtest(events)
        self.assertEqual(summary.loc["Total", "Trades"], 2)
        self.assertEqual(summary.loc["Test", "Incomplete_Events"], 1)

    def test_boundary_events_not_mixed_into_train_test_statistics(self):
        signals, capm = event_sample()
        signals.iloc[[8, 10, 11], signals.columns.get_loc("Trade_Signal")] = 1
        events = calculate_backtest(signals, capm)
        self.assertEqual(events.Crosses_Sample_Boundary.tolist(), [True, True, False])
        summary = summarize_backtest(events)
        self.assertEqual(summary.loc["Train", "Trades"], 0)
        self.assertEqual(summary.loc["Test", "Trades"], 1)
        self.assertEqual(summary.loc["Total", "Trades"], 3)

    def test_summary_cost_wins_cumulative_and_two_sided_tests(self):
        signals, capm = event_sample()
        signals.iloc[[11, 12, 13], signals.columns.get_loc("Trade_Signal")] = [1, -1, 1]
        events = calculate_backtest(signals, capm)
        summary = summarize_backtest(events).loc["Test"]
        net = events.Strategy_Net_Return
        self.assertAlmostEqual(summary.Mean_Net_Return, net.mean())
        self.assertAlmostEqual(summary.Win_Rate_Pct, net.gt(0).mean() * 100)
        self.assertAlmostEqual(summary.Cumulative_Event_Net_Return, np.prod(1 + net) - 1)
        for name, column in [("Net", "Strategy_Net_Return"), ("MarketModel", "Abnormal_Strategy_MarketModel"), ("CAPM", "Abnormal_Strategy_CAPM")]:
            values = events[column]
            t = values.mean() / (values.std(ddof=1) / np.sqrt(len(values)))
            p = 2 * stats.t.sf(abs(t), len(values) - 1)
            self.assertAlmostEqual(summary[f"{name}_T_Statistic"], t)
            self.assertAlmostEqual(summary[f"{name}_P_Value"], p)

    def test_no_events_and_missing_normal_returns(self):
        signals, capm = event_sample()
        empty = calculate_backtest(signals, capm)
        self.assertTrue(empty.empty)
        self.assertEqual(summarize_backtest(empty).loc["Total", "Trades"], 0)
        signals.iloc[2, signals.columns.get_loc("Trade_Signal")] = 1
        capm.iloc[4, capm.columns.get_loc("CAPM_Expected_Return")] = np.nan
        self.assertEqual(calculate_backtest(signals, capm).iloc[0].Status, "Missing_Returns")

    def test_reject_mismatched_input_versions(self):
        signals, capm = event_sample()
        capm.iloc[0, capm.columns.get_loc("TSLA_Return")] += .01
        with self.assertRaises(ValueError):
            calculate_backtest(signals, capm)


if __name__ == "__main__":
    unittest.main()
