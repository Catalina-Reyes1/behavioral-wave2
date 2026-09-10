import json
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd
import requests
from contextlib import redirect_stdout

from src.gdelt_data import GDELTError, HistoricalRangeError, _Client, _combine, _parse_timeline, _windows, download_gdelt_data


def payload(dates, values):
    return {"timeline": [{"series": "test", "data": [
        {"date": date.strftime("%Y%m%dT%H%M%SZ"), "value": value}
        for date, value in zip(dates, values)
    ]}]}


class GDELTTests(unittest.TestCase):
    def test_daily_counts_duplicates_and_undefined_tone(self):
        dates = pd.to_datetime(["2019-01-01", "2019-01-01", "2019-01-02"])
        count = _parse_timeline(payload(dates, [5, 5, 0]), "TimelineVolRaw")
        tone = _parse_timeline(payload(dates, [-2, -2, 0]), "TimelineTone")
        frame = _combine(count, tone, "2019-01-01", "2019-01-02")
        self.assertEqual(len(frame), 2)
        self.assertEqual(frame.iloc[0]["News_Count"], 5)
        self.assertTrue(pd.isna(frame.iloc[1]["News_Tone"]))

    def test_reject_invalid_payloads(self):
        day = pd.to_datetime(["2019-01-01"])
        bad = [{}, {"timeline": []}, {"timeline": [{"data": [{"unexpected": 1}]}]},
               payload(day, [1.5]), payload(day, [-1]), payload(day, [float("nan")]),
               payload(pd.to_datetime(["2019-01-01 12:00"]), [1]),
               payload(pd.to_datetime(["2019-01-01", "2019-01-01"]), [1, 2])]
        for item in bad:
            with self.subTest(item=item), self.assertRaises(GDELTError):
                _parse_timeline(item, "TimelineVolRaw")

    def test_no_silent_alignment_or_intraday_mean(self):
        count = _parse_timeline(payload(pd.to_datetime(["2019-01-01"]), [2]), "TimelineVolRaw")
        tone = _parse_timeline(payload(pd.to_datetime(["2019-01-02"]), [-1]), "TimelineTone")
        with self.assertRaises(GDELTError):
            _combine(count, tone, "2019-01-01", "2019-01-02")

    def test_windows_cover_range_and_keep_daily_resolution(self):
        start, end = pd.Timestamp("2019-01-01"), pd.Timestamp("2020-01-02")
        windows = list(_windows(start, end))
        covered = set()
        for first, last in windows:
            self.assertGreater((last - first).days, 7)
            covered.update(pd.date_range(first, last))
        self.assertTrue(set(pd.date_range(start, end)).issubset(covered))

    @patch("src.gdelt_data.time.sleep")
    def test_http_timeout_empty_and_non_json_errors(self, sleep):
        with tempfile.TemporaryDirectory() as directory:
            for error in [requests.Timeout("timeout"), requests.ConnectionError("offline")]:
                session = Mock()
                session.get.side_effect = error
                with self.assertRaises(GDELTError):
                    _Client(session, Path(directory)).fetch("TimelineTone", {})
                self.assertEqual(session.get.call_count, 3)
            response = Mock(status_code=503, headers={})
            response.raise_for_status.side_effect = requests.HTTPError("503", response=response)
            session = Mock()
            session.get.return_value = response
            with self.assertRaises(GDELTError):
                _Client(session, Path(directory)).fetch("TimelineTone", {})
            self.assertEqual(session.get.call_count, 3)
            for content in ["", "API unavailable"]:
                response = Mock(text=content)
                response.json.side_effect = ValueError("not JSON")
                session.get.return_value = response
                with self.assertRaises(GDELTError):
                    _Client(session, Path(directory)).fetch("TimelineTone", {})

    @patch("src.gdelt_data.time.sleep")
    def test_csv_cache_and_reproducibility(self, sleep):
        def answer(url, params, timeout):
            first = pd.to_datetime(params["startdatetime"], format="%Y%m%d%H%M%S")
            last = pd.to_datetime(params["enddatetime"], format="%Y%m%d%H%M%S").normalize()
            dates = pd.date_range(first, last)
            value = 10 if params["mode"] == "TimelineVolRaw" else -1.25
            response = Mock(text="JSON", url=url)
            response.json.return_value = payload(dates, [value] * len(dates))
            return response

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "news.csv"
            with patch("src.gdelt_data.requests.Session") as factory:
                session = factory.return_value.__enter__.return_value
                session.get.side_effect = answer
                frame = download_gdelt_data("2019-01-01", "2020-01-03", path)
                self.assertEqual(len(frame), 368)
                self.assertEqual(session.get.call_count, 4)
                saved = pd.read_csv(path)
                self.assertEqual(list(saved), ["Date", "News_Count", "News_Tone"])
                self.assertEqual(saved.iloc[0]["Date"], "2019-01-01")
                self.assertTrue(json.loads(path.with_suffix(".metadata.json").read_text())["complete_requested_range"])
                session.get.reset_mock()
                again = download_gdelt_data("2019-01-01", "2020-01-03", path)
                pd.testing.assert_frame_equal(frame, again)
                session.get.assert_not_called()

    @patch("src.gdelt_data._Client.fetch", side_effect=GDELTError("offline"))
    def test_failed_download_preserves_previous_csv(self, fetch):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "news.csv"
            path.write_text("previous validated data", encoding="utf-8")
            with self.assertRaises(GDELTError):
                download_gdelt_data("2019-01-01", "2019-02-01", path)
            self.assertEqual(path.read_text(), "previous validated data")

    def test_explicit_historical_rejection_marks_partial_coverage(self):
        dates = pd.date_range("2019-12-01", "2019-12-31")
        count = pd.Series(5, index=dates, name="News_Count")
        tone = pd.Series(-1.0, index=dates, name="News_Tone")
        with tempfile.TemporaryDirectory() as directory:
            with patch("src.gdelt_data._Client.fetch", side_effect=[HistoricalRangeError("Start date too far in the past"), count, tone]):
                with self.assertWarns(UserWarning):
                    frame = download_gdelt_data("2019-01-01", "2019-12-31", Path(directory) / "news.csv")
            self.assertEqual(len(frame), 31)
            self.assertFalse(frame.attrs["metadata"]["complete_requested_range"])
            self.assertEqual(len(frame.attrs["metadata"]["missing_dates"]), 334)

    def test_main_runs_attention_after_financial_output_without_gdelt(self):
        import main

        dates = pd.date_range("2019-01-01", periods=10, name="Date")
        market = pd.DataFrame({"NVDA_Return": [.01, -.02, .04, .02, .01, -.01, .03, .02, -.01, .05],
                               "VOO_Return": [.01, -.01, .02, .01, -.01, .02, .01, .01, -.02, .03]}, index=dates)
        attention = pd.DataFrame({"Pageviews": 10, "IOC": 0.0}, index=dates)
        calls = []

        def save(frame, path):
            calls.append(path)

        def download(**kwargs):
            self.assertEqual(calls[-1], "data/processed/market_model.csv")
            return attention

        output = io.StringIO()
        period = {"analysis_start": str(dates[0].date()), "analysis_end": str(dates[-1].date())}
        with patch.object(main, "END_DATE", period["analysis_end"]), patch.object(main, "START_DATE", period["analysis_start"]), patch.object(main, "Path"), patch.object(main, "download_wikimedia_pageviews", return_value=attention), patch.object(main, "determine_common_period", return_value=period), patch.object(main, "export_web_data") as web, patch.object(main, "download_market_data", return_value=market), patch.object(main, "save_market_data", side_effect=save), patch.object(main, "run_wikimedia_attention", side_effect=download), patch.object(main, "run_signals") as signals, patch.object(main, "run_capm") as capm, patch.object(main, "run_backtest") as backtest, patch("src.gdelt_data.download_gdelt_data") as gdelt, redirect_stdout(output):
            main.main()
        web.assert_called_once_with()
        capm.assert_called_once_with()
        backtest.assert_called_once_with()
        signals.assert_called_once_with()
        gdelt.assert_not_called()
        text = output.getvalue()
        self.assertNotIn("GDELT:", text)
        self.assertLess(text.index("Alpha:"), text.index("WIKIMEDIA ATTENTION:"))
        for label in ["Primera fecha", "Última fecha", "Número de observaciones", "Promedio de Pageviews", "Máximo Pageviews", "Máximo IOC"]:
            self.assertIn(label, text)


if __name__ == "__main__":
    unittest.main()
