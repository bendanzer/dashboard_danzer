import json
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch
from urllib.error import URLError

from dashboard_danzer.temperature import collect_daily, load_archive, parse_temperature_average


PAGE = """<p id="timestamp">Aktualisiert am 24.10.2026 um 09:19pm</p>
<div><p class="value-header-small">Average last 72 hours:</p>
<h2 id="water" class="value-small">11,8<span>\u00b0C</span></h2></div>
<h1 id="water" class="value-big">99<span>\u00b0C</span></h1>"""


class TemperatureTests(unittest.TestCase):
    def test_reads_average_not_current_or_page_update_as_measurement_time(self) -> None:
        value, updated = parse_temperature_average(PAGE)
        self.assertEqual(value, 11.8)
        self.assertIn("09:19pm", updated)
        for page in (PAGE.replace("11,8", "--"), PAGE.replace("11,8", "NaN"),
                     PAGE.replace("72 hours", "24 hours"), PAGE.replace("\u00b0C", "\u00b0F"), "<html></html>"):
            with self.subTest(page=page), self.assertRaises(ValueError):
                parse_temperature_average(page)

    @patch("dashboard_danzer.temperature.fetch_temperature_average", return_value=(11.8, "source update"))
    def test_at_most_once_per_24_hours_and_persisted_between_runs(self, mock_fetch: MagicMock) -> None:
        now = datetime(2026, 10, 24, 10, tzinfo=UTC)
        with TemporaryDirectory() as directory:
            archive = Path(directory) / "archive.json"
            first = collect_daily(archive, now=now)
            self.assertEqual(first["observations"][0]["collected_at"], now.isoformat())
            collect_daily(archive, now=now + timedelta(hours=23, minutes=59))
            self.assertEqual(mock_fetch.call_count, 1)
            second = collect_daily(archive, now=now + timedelta(hours=24))
            self.assertEqual(mock_fetch.call_count, 2)
            self.assertEqual(len(load_archive(archive)["observations"]), 2)
            self.assertTrue(second["observations"][-1]["source_update_unchanged"])

    @patch("dashboard_danzer.temperature.fetch_temperature_average")
    def test_failed_fetch_preserves_history_and_can_retry(self, mock_fetch: MagicMock) -> None:
        now = datetime(2026, 10, 24, 10, tzinfo=UTC)
        with TemporaryDirectory() as directory:
            archive = Path(directory) / "archive.json"
            mock_fetch.return_value = (11.8, "first update")
            collect_daily(archive, now=now)
            previous = archive.read_text()
            mock_fetch.side_effect = URLError("offline")
            with patch("sys.stderr"):
                result = collect_daily(archive, now=now + timedelta(days=1))
            self.assertEqual(result["collection_status"], "unavailable")
            self.assertEqual(archive.read_text(), previous)
            mock_fetch.side_effect = None
            mock_fetch.return_value = (12.1, "new update")
            result = collect_daily(archive, now=now + timedelta(days=1, minutes=30))
            self.assertEqual(len(result["observations"]), 2)
            self.assertFalse(result["observations"][-1]["source_update_unchanged"])

    def test_invalid_archive_is_not_replaced(self) -> None:
        with TemporaryDirectory() as directory:
            archive = Path(directory) / "archive.json"
            archive.write_text('{"schema_version": 999}')
            with self.assertRaises(ValueError):
                collect_daily(archive)
            self.assertEqual(json.loads(archive.read_text())["schema_version"], 999)

    @patch("dashboard_danzer.temperature.fetch_temperature_average", side_effect=URLError("offline"))
    def test_failed_first_fetch_does_not_create_an_observation(self, _mock_fetch: MagicMock) -> None:
        with TemporaryDirectory() as directory:
            archive = Path(directory) / "archive.json"
            with patch("sys.stderr"):
                result = collect_daily(archive)
            self.assertEqual(result["observations"], [])
            self.assertEqual(result["collection_status"], "unavailable")
            self.assertFalse(archive.exists())

    @patch("dashboard_danzer.temperature.fetch_temperature_average", return_value=(11.8, "source update"))
    def test_future_archive_is_preserved_without_fetching(self, mock_fetch: MagicMock) -> None:
        now = datetime(2026, 10, 24, 10, tzinfo=UTC)
        with TemporaryDirectory() as directory:
            archive = Path(directory) / "archive.json"
            collect_daily(archive, now=now + timedelta(days=1))
            previous = archive.read_text()
            with self.assertRaisesRegex(ValueError, "future"):
                collect_daily(archive, now=now)
            self.assertEqual(mock_fetch.call_count, 1)
            self.assertEqual(archive.read_text(), previous)