import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch
from urllib.error import URLError

from dashboard_danzer import (
    DISCHARGE_HISTORY_URL,
    DISCHARGE_URL,
    HISTORY_URL,
    SOURCE_URL,
    fetch_water_level,
    fetch_water_level_history,
    fetch_discharge,
    fetch_notices,
    main,
    parse_water_level,
    parse_water_levels,
    parse_discharge,
    parse_notices,
)


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
    def setUp(self) -> None:
        weather_patch = patch("dashboard_danzer.fetch_weather", return_value={"status": "unavailable"})
        self.mock_weather = weather_patch.start()
        self.addCleanup(weather_patch.stop)
        discharge_patch = patch("dashboard_danzer.fetch_discharge", return_value={
            "id": "eisbach_discharge", "status": "ok", "value": 15,
        })
        self.mock_discharge = discharge_patch.start()
        self.addCleanup(discharge_patch.stop)
        notices_patch = patch("dashboard_danzer.fetch_notices", return_value={
            "status": "unavailable", "access_status": "unverified",
        })
        self.mock_notices = notices_patch.start()
        self.addCleanup(notices_patch.stop)

    def test_notices_are_relevant_official_and_deduplicated(self) -> None:
        html = """<h1>Rathaus Umschau</h1>
        <a href="/2026/eisbach">Eisbachwelle update</a>
        <a href="/2026/eisbach">Eisbachwelle update</a>
        <a href="https://example.com/">Eisbach unverified</a>
        <a href="javascript:alert(1)">Eisbach unsafe link</a>
        <a href="/other">Unrelated city news</a>"""
        self.assertEqual(parse_notices(html), [{
            "title": "Eisbachwelle update", "url": "https://ru.muenchen.de/2026/eisbach",
        }])
        self.assertEqual(parse_notices("<h1>Rathaus Umschau</h1>"), [])
        with self.assertRaises(ValueError):
            parse_notices("<h1>Service unavailable</h1>")

    @patch("dashboard_danzer._fetch_html", return_value="<h1>Rathaus Umschau</h1>")
    def test_empty_notices_never_means_open(self, _mock_html: MagicMock) -> None:
        notices = fetch_notices()
        self.assertEqual(notices["access_status"], "unverified")
        self.assertEqual(notices["coverage"], "latest_issue_only")
        self.assertEqual(notices["items"], [])

    @patch("dashboard_danzer.fetch_water_level_history")
    @patch("dashboard_danzer.fetch_water_level")
    def test_notices_failure_does_not_block_gauge_export(
        self, mock_fetch: MagicMock, mock_history: MagicMock
    ) -> None:
        mock_fetch.return_value = parse_water_level(PAGE)
        mock_history.return_value = parse_water_levels(PAGE)
        self.mock_notices.side_effect = URLError("city offline")
        with TemporaryDirectory() as directory:
            output = Path(directory) / "latest.json"
            with patch("sys.argv", ["main.py", "--output", str(output)]), patch("sys.stderr"):
                main()
            snapshot = json.loads(output.read_text())
            self.assertEqual(snapshot["notices"]["access_status"], "unverified")
            self.assertEqual(snapshot["notices"]["status"], "unavailable")
            self.assertEqual(snapshot["metrics"][0]["value"], 116)

    def test_discharge_parser_uses_correct_quantity_and_decimal_comma(self) -> None:
        page = PAGE.replace("Wasserstand", "Abfluss").replace(">116<", ">14,7<")
        readings = parse_discharge(page + page)
        self.assertEqual([point.value for point in readings], [117, 14.7])
        with self.assertRaises(ValueError):
            parse_discharge(PAGE)
        for invalid in ("NaN", "inf", "-1"):
            with self.subTest(invalid=invalid):
                self.assertEqual(len(parse_discharge(page.replace(">14,7<", f">{invalid}<"))), 1)

    @patch("dashboard_danzer._fetch_html")
    def test_discharge_fetch_merges_current_and_history(self, mock_html: MagicMock) -> None:
        page = PAGE.replace("Wasserstand", "Abfluss").replace(">116<", ">14,7<")
        mock_html.side_effect = [page.replace("20:45", "21:15"), page]
        metric = fetch_discharge()
        self.assertEqual(metric["unit"], "m\u00b3/s")
        self.assertEqual(metric["value"], 14.7)
        self.assertEqual(len(metric["history"]), 3)
        self.assertEqual(mock_html.call_args_list[0].args[0], DISCHARGE_URL)
        self.assertEqual(mock_html.call_args_list[1].args[0], DISCHARGE_HISTORY_URL)

    @patch("dashboard_danzer.fetch_water_level_history")
    @patch("dashboard_danzer.fetch_water_level")
    def test_discharge_failure_does_not_block_water_level(
        self, mock_fetch: MagicMock, mock_history: MagicMock
    ) -> None:
        mock_fetch.return_value = parse_water_level(PAGE)
        mock_history.return_value = parse_water_levels(PAGE)
        self.mock_discharge.side_effect = URLError("discharge offline")
        with TemporaryDirectory() as directory:
            output = Path(directory) / "latest.json"
            with patch("sys.argv", ["main.py", "--output", str(output)]), patch("sys.stderr"):
                main()
            snapshot = json.loads(output.read_text())
            self.assertEqual(snapshot["discharge"]["status"], "unavailable")
            self.assertEqual(len(snapshot["metrics"]), 1)

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

    def test_history_is_sorted_and_deduplicated(self) -> None:
        readings = parse_water_levels(PAGE + PAGE)
        self.assertEqual([point.level_cm for point in readings], [117, 116])
        self.assertLess(readings[0].measured_at, readings[1].measured_at)

    @patch("dashboard_danzer.fetch_water_level_history")
    @patch("dashboard_danzer.fetch_water_level")
    def test_dashboard_export(self, mock_fetch: MagicMock, mock_history: MagicMock) -> None:
        mock_fetch.return_value = parse_water_level(PAGE)
        mock_history.return_value = parse_water_levels(PAGE)
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
            self.assertEqual(len(snapshot["metrics"][0]["history"]), 2)
            self.assertEqual(snapshot["metrics"][0]["history"][0]["value"], 117)
            self.assertEqual(snapshot["metrics"][0]["history_source_url"], HISTORY_URL)
            self.assertFalse(output.with_suffix(".json.tmp").exists())

    @patch("dashboard_danzer.fetch_water_level_history")
    @patch("dashboard_danzer.fetch_water_level")
    def test_weather_failure_does_not_block_gauge_export(
        self, mock_fetch: MagicMock, mock_history: MagicMock
    ) -> None:
        mock_fetch.return_value = parse_water_level(PAGE)
        mock_history.return_value = parse_water_levels(PAGE)
        self.mock_weather.side_effect = URLError("weather offline")
        with TemporaryDirectory() as directory:
            output = Path(directory) / "latest.json"
            with patch("sys.argv", ["main.py", "--output", str(output)]), patch("sys.stderr"):
                main()
            snapshot = json.loads(output.read_text())
            self.assertEqual(snapshot["weather"]["status"], "unavailable")
            self.assertEqual(snapshot["metrics"][0]["value"], 116)

    @patch("dashboard_danzer.fetch_water_level_history")
    @patch("dashboard_danzer.fetch_water_level")
    def test_export_merges_latest_and_history_updates(
        self, mock_fetch: MagicMock, mock_history: MagicMock
    ) -> None:
        for latest_is_newer in (True, False):
            with self.subTest(latest_is_newer=latest_is_newer), TemporaryDirectory() as directory:
                older = parse_water_level(PAGE)
                newer = parse_water_level(PAGE.replace("20:45", "21:15"))
                mock_fetch.return_value = newer if latest_is_newer else older
                mock_history.return_value = [older if latest_is_newer else newer]
                output = Path(directory) / "latest.json"
                with patch("sys.argv", ["main.py", "--output", str(output)]):
                    main()
                metric = json.loads(output.read_text())["metrics"][0]
                self.assertEqual(len(metric["history"]), 2)
                self.assertEqual(metric["measured_at"], newer.measured_at.isoformat())
                self.assertEqual(metric["history"][-1]["measured_at"], metric["measured_at"])

    @patch("dashboard_danzer.fetch_water_level_history", side_effect=URLError("offline"))
    @patch("dashboard_danzer.fetch_water_level")
    def test_failed_history_fetch_preserves_snapshot(
        self, mock_fetch: MagicMock, _mock_history: MagicMock
    ) -> None:
        mock_fetch.return_value = parse_water_level(PAGE)
        with TemporaryDirectory() as directory:
            output = Path(directory) / "latest.json"
            output.write_text("previous snapshot")
            with patch("sys.argv", ["main.py", "--output", str(output)]):
                with self.assertRaises(SystemExit):
                    main()
            self.assertEqual(output.read_text(), "previous snapshot")

    @patch("dashboard_danzer.urlopen")
    def test_history_fetch_uses_historical_table(self, mock_urlopen: MagicMock) -> None:
        response = mock_urlopen.return_value.__enter__.return_value
        response.headers.get_content_charset.return_value = "utf-8"
        response.read.return_value = PAGE.encode()
        self.assertEqual(len(fetch_water_level_history()), 2)
        self.assertEqual(mock_urlopen.call_args.args[0].full_url, HISTORY_URL)
        self.assertEqual(mock_urlopen.call_args.kwargs["timeout"], 30)

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