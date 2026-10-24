import json
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from dashboard_danzer.weather import WEATHER_URL, fetch_weather, parse_weather


def weather_response() -> dict:
    timestamp = datetime(2026, 10, 24, 12, tzinfo=ZoneInfo("Europe/Berlin")).timestamp()
    return {
        "current": {"time": timestamp, "temperature_2m": 12, "apparent_temperature": 10,
                    "precipitation": 0, "weather_code": 2, "wind_speed_10m": 9,
                    "wind_direction_10m": 225},
        "daily": {"time": [timestamp], "temperature_2m_max": [15], "temperature_2m_min": [6],
                  "sunrise": [timestamp - 5 * 3600], "sunset": [timestamp + 6 * 3600]},
        "hourly": {"time": [timestamp, timestamp + 3600], "temperature_2m": [12, 13],
                   "precipitation_probability": [10, 30], "precipitation": [0, 0.2],
                   "weather_code": [2, 61], "wind_speed_10m": [9, 12]},
    }


class WeatherTests(unittest.TestCase):
    def test_normalizes_values_and_local_times(self) -> None:
        weather = parse_weather(weather_response())
        self.assertEqual(weather["current"]["temperature_c"], 12)
        self.assertEqual(weather["current"]["time"], "2026-10-24T12:00:00+02:00")
        self.assertEqual(weather["today"]["date"], "2026-10-24")
        self.assertEqual(weather["hourly"][1]["rain_probability_pct"], 30)
        self.assertEqual(weather["status"], "ok")

    def test_rejects_invalid_values_and_misaligned_arrays(self) -> None:
        for value in (None, float("nan"), float("inf"), True):
            response = weather_response()
            response["current"]["temperature_2m"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_weather(response)
        response = weather_response()
        response["hourly"]["temperature_2m"].pop()
        with self.assertRaises(ValueError):
            parse_weather(response)
        with self.assertRaises(ValueError):
            parse_weather({})

    def test_repeated_dst_hour_preserves_distinct_offsets(self) -> None:
        response = weather_response()
        first = datetime.fromisoformat("2026-10-25T02:00:00+02:00").timestamp()
        response["daily"]["time"] = [first]
        response["hourly"]["time"] = [first, first + 3600]
        weather = parse_weather(response)
        self.assertEqual(weather["hourly"][0]["time"], "2026-10-25T02:00:00+02:00")
        self.assertEqual(weather["hourly"][1]["time"], "2026-10-25T02:00:00+01:00")

    @patch("dashboard_danzer.weather.urlopen")
    def test_fetch_requests_expected_location_and_timeout(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value.__enter__.return_value.read.return_value = json.dumps(weather_response()).encode()
        self.assertEqual(fetch_weather(timeout=4)["status"], "ok")
        self.assertEqual(mock_urlopen.call_args.args[0].full_url, WEATHER_URL)
        self.assertEqual(mock_urlopen.call_args.kwargs["timeout"], 4)