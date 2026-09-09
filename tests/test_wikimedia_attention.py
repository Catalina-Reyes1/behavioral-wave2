import unittest
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd
import requests

from src.wikimedia_attention import WikimediaError, _parse_pageviews, calculate_attention_wave, download_wikimedia_pageviews


def sample():
    return pd.DataFrame({"Pageviews": 100 + (np.arange(160) * 17) % 121}, index=pd.date_range("2019-01-01", periods=160, name="Date"))


class WikimediaTests(unittest.TestCase):
    def test_past_only_reference_and_formulas(self):
        raw = sample()
        result = calculate_attention_wave(raw)
        self.assertTrue(result["IOC"].iloc[:60].isna().all())
        for i in range(60, len(raw)):
            history = np.log1p(raw["Pageviews"].iloc[i-60:i].to_numpy())
            z = (np.log1p(raw["Pageviews"].iloc[i]) - history.mean()) / history.std(ddof=1)
            self.assertAlmostEqual(result["Attention_Z"].iloc[i], z)
            self.assertAlmostEqual(result["IAA"].iloc[i], max(z, 0))
            self.assertAlmostEqual(result["IOC"].iloc[i], 100 * np.tanh(max(z, 0) / 2))
        np.testing.assert_allclose(result["IOC_Velocity"].iloc[61:], np.diff(result["IOC"].iloc[60:]))
        np.testing.assert_allclose(result["IOC_Acceleration"].iloc[62:], np.diff(result["IOC"].iloc[60:], n=2))
        self.assertTrue(result["IOC"].dropna().between(0, 100).all())

    def test_future_changes_cannot_change_past_indicators(self):
        raw = sample()
        original = calculate_attention_wave(raw)
        changed = raw.copy()
        changed.iloc[100:, 0] *= 1000
        altered = calculate_attention_wave(changed)
        pd.testing.assert_frame_equal(original.iloc[:100], altered.iloc[:100])
        history = np.log1p(raw["Pageviews"].iloc[40:100])
        expected = (np.log1p(changed["Pageviews"].iloc[100]) - history.mean()) / history.std(ddof=1)
        self.assertAlmostEqual(altered["Attention_Z"].iloc[100], expected)

    def test_missing_day_is_not_zero_or_a_shorter_window(self):
        raw = sample().drop(pd.Timestamp("2019-03-12"))  # posición 70
        result = calculate_attention_wave(raw)
        self.assertTrue(pd.isna(result.iloc[70]["Pageviews"]))
        self.assertTrue(result["IOC"].iloc[70:131].isna().all())
        self.assertTrue(pd.notna(result["IOC"].iloc[131]))

    def test_zero_variance_is_undefined_not_infinity(self):
        raw = sample()
        raw["Pageviews"] = 100
        raw.iloc[80, 0] = 100000
        result = calculate_attention_wave(raw)
        self.assertTrue(result["IOC"].iloc[:81].isna().all())
        self.assertFalse(np.isinf(result.to_numpy()).any())

    def test_parse_sorts_and_marks_missing_dates_without_filling(self):
        payload = {"items": [{"timestamp": "2019010300", "views": 20}, {"timestamp": "2019010100", "views": 10}]}
        result = _parse_pageviews(payload, pd.Timestamp("2019-01-01"), pd.Timestamp("2019-01-05"))
        self.assertEqual(len(result), 3)
        self.assertTrue(pd.isna(result.iloc[1, 0]))
        self.assertEqual(result.index.max(), pd.Timestamp("2019-01-03"))
        self.assertEqual(result.index.name, "Date")

    def test_invalid_payloads_fail_explicitly(self):
        for payload in [{}, {"items": []}, {"items": [{"other": 10}]},
                        {"items": [{"timestamp": "bad", "views": 1}]},
                        {"items": [{"timestamp": "2019010100", "views": -1}]},
                        {"items": [{"timestamp": "2019010100", "views": 1.5}]},
                        {"items": [{"timestamp": "2019010100", "views": None}]},
                        {"items": [{"timestamp": "2019010100", "views": 1, "agent": "all-agents"}]}]:
            with self.subTest(payload=payload), self.assertRaises(WikimediaError):
                _parse_pageviews(payload, pd.Timestamp("2019-01-01"), pd.Timestamp("2019-02-01"))

    @patch("src.wikimedia_attention.time.sleep")
    def test_timeouts_http_empty_and_invalid_json(self, sleep):
        with patch("src.wikimedia_attention.requests.Session") as factory:
            session = factory.return_value.__enter__.return_value
            session.get.side_effect = requests.Timeout("timeout")
            with self.assertRaises(WikimediaError):
                download_wikimedia_pageviews("2019-01-01", "2019-02-01")
            self.assertEqual(session.get.call_count, 3)
            session.get.side_effect = None
            for status, attempts in [(429, 3), (503, 3), (404, 1)]:
                session.get.reset_mock()
                response = Mock(status_code=status, headers={})
                response.raise_for_status.side_effect = requests.HTTPError(str(status), response=response)
                session.get.return_value = response
                with self.assertRaises(WikimediaError):
                    download_wikimedia_pageviews("2019-01-01", "2019-02-01")
                self.assertEqual(session.get.call_count, attempts)
            for content in ["", "unavailable"]:
                response = Mock(text=content)
                response.json.side_effect = ValueError("not JSON")
                session.get.return_value = response
                with self.assertRaises(WikimediaError):
                    download_wikimedia_pageviews("2019-01-01", "2019-02-01")


if __name__ == "__main__":
    unittest.main()
