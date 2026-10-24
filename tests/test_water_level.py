import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch
from urllib.error import URLError

from dashboard_danzer import SOURCE_URL, fetch_water_level, main, parse_water_level


PAGE = """
<table class="tblsort">
  <thead><tr><th>Datum</th><th>Wasserstand <b>cm</b></th></tr></thead>
  <tbody>
    <tr><td>24.10.2026 20:30</td><td>117</td></tr>
    <tr><td>24.10.2026 20:45</td><td>116</td></tr>
    <tr><td>24.10.2026 21:00</td><td>---</td></tr>
    <tr><td colspan="3"><a>weitere Messwerte ...</a></td></tr>
  </tbody>
</table>
"""


class WaterLevelTests(unittest.TestCase):
    def test_latest_reading_and_local_timezone(self) -> None:
        reading = parse_water_level(PAGE)
        self.assertEqual(reading.level_cm, 116)
        self.assertEqual(reading.measured_at.isoformat(), "2026-10-24T20:45:00+02:00")
        self.assertEqual(reading.station_id, "16515005")

    def test_decimal_comma_and_winter_timezone(self) -> None:
        page = PAGE.replace("24.10.2026", "24.12.2026").replace(">116<", ">116,5<")
        reading = parse_water_level(page)
        self.assertEqual(reading.level_cm, 116.5)
        self.assertEqual(reading.measured_at.isoformat(), "2026-12-24T20:45:00+01:00")

    def test_missing_or_unrelated_data_raises(self) -> None:
        for page in ("<html></html>", PAGE.replace("Wasserstand", "Abfluss")):
            with self.subTest(page=page), self.assertRaisesRegex(ValueError, "No valid"):
                parse_water_level(page)

    def test_nonfinite_values_are_not_readings(self) -> None:
        for value in ("NaN", "inf", "-inf"):
            with self.subTest(value=value):
                reading = parse_water_level(PAGE.replace(">116<", f">{value}<"))
                self.assertEqual(reading.level_cm, 117)

    @patch("dashboard_danzer.fetch_water_level")
    def test_dashboard_export(self, mock_fetch: MagicMock) -> None:
        mock_fetch.return_value = parse_water_level(PAGE)
        with TemporaryDirectory() as directory:
            output = Path(directory) / "data" / "latest.json"
            with patch("sys.argv", ["main.py", "--output", str(output)]):
                main()
            snapshot = json.loads(output.read_text())
            self.assertEqual(snapshot["schema_version"], 1)
            self.assertIn("collected_at", snapshot)
            self.assertEqual(snapshot["metrics"][0]["value"], 116)
            self.assertEqual(snapshot["metrics"][0]["unit"], "cm")
            self.assertEqual(snapshot["metrics"][0]["status"], "ok")
            self.assertFalse(output.with_suffix(".json.tmp").exists())

    @patch("dashboard_danzer.fetch_water_level", side_effect=URLError("offline"))
    def test_failed_fetch_preserves_snapshot(self, _mock_fetch: MagicMock) -> None:
        with TemporaryDirectory() as directory:
            output = Path(directory) / "latest.json"
            output.write_text("previous snapshot")
            with patch("sys.argv", ["main.py", "--output", str(output)]):
                with self.assertRaises(SystemExit):
                    main()
            self.assertEqual(output.read_text(), "previous snapshot")

    @patch("dashboard_danzer.urlopen")
    def test_fetch_uses_timeout_and_parses_response(self, mock_urlopen: MagicMock) -> None:
        response = mock_urlopen.return_value.__enter__.return_value
        response.headers.get_content_charset.return_value = "utf-8"
        response.read.return_value = PAGE.encode("utf-8")
        self.assertEqual(fetch_water_level(timeout=3).level_cm, 116)
        self.assertEqual(mock_urlopen.call_args.args[0].full_url, SOURCE_URL)
        self.assertEqual(mock_urlopen.call_args.kwargs["timeout"], 3)

    @patch("dashboard_danzer.urlopen", side_effect=URLError("offline"))
    def test_network_errors_propagate(self, _mock_urlopen: MagicMock) -> None:
        with self.assertRaises(URLError):
            fetch_water_level()