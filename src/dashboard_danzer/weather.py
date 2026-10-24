import json
import math
from datetime import datetime
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


WEATHER_SOURCE_URL = "https://open-meteo.com/"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast?" + urlencode({
    "latitude": 48.1435,
    "longitude": 11.5877,
    "current": "temperature_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m,wind_direction_10m",
    "hourly": "temperature_2m,precipitation_probability,precipitation,weather_code,wind_speed_10m",
    "daily": "temperature_2m_max,temperature_2m_min,sunrise,sunset",
    "temperature_unit": "celsius",
    "wind_speed_unit": "kmh",
    "precipitation_unit": "mm",
    "timezone": "Europe/Berlin",
    "forecast_days": 1,
    "timeformat": "unixtime",
})


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("Missing or invalid weather value.")
    return float(value)


def _time(value: object) -> str:
    return datetime.fromtimestamp(_number(value), ZoneInfo("Europe/Berlin")).isoformat()


def parse_weather(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize Open-Meteo's model output, preserving timezone-aware valid times."""
    try:
        current = payload["current"]
        daily = payload["daily"]
        hourly = payload["hourly"]
        day = _time(daily["time"][0])[:10]
        columns = ("time", "temperature_2m", "precipitation_probability", "precipitation", "weather_code", "wind_speed_10m")
        if not hourly["time"] or any(len(hourly[key]) != len(hourly["time"]) for key in columns):
            raise ValueError("Weather forecast arrays are empty or misaligned.")
        forecast = []
        for index, timestamp in enumerate(hourly["time"]):
            valid_at = _time(timestamp)
            if valid_at[:10] != day:
                continue
            probability = _number(hourly["precipitation_probability"][index])
            if not 0 <= probability <= 100:
                raise ValueError("Invalid precipitation probability.")
            forecast.append({
                "time": valid_at,
                "temperature_c": _number(hourly["temperature_2m"][index]),
                "rain_probability_pct": probability,
                "precipitation_mm": _number(hourly["precipitation"][index]),
                "weather_code": _number(hourly["weather_code"][index]),
                "wind_kmh": _number(hourly["wind_speed_10m"][index]),
            })
        if not forecast:
            raise ValueError("No weather forecast for the requested day.")
        return {
            "status": "ok",
            "source_name": "Open-Meteo",
            "source_url": WEATHER_SOURCE_URL,
            "location": "Munich / Eisbach",
            "current": {
                "time": _time(current["time"]),
                "temperature_c": _number(current["temperature_2m"]),
                "feels_like_c": _number(current["apparent_temperature"]),
                "precipitation_mm": _number(current["precipitation"]),
                "weather_code": _number(current["weather_code"]),
                "wind_kmh": _number(current["wind_speed_10m"]),
                "wind_direction_deg": _number(current["wind_direction_10m"]),
            },
            "today": {
                "date": day,
                "high_c": _number(daily["temperature_2m_max"][0]),
                "low_c": _number(daily["temperature_2m_min"][0]),
                "sunrise": _time(daily["sunrise"][0]),
                "sunset": _time(daily["sunset"][0]),
            },
            "hourly": forecast,
        }
    except (KeyError, IndexError, TypeError, OverflowError) as error:
        raise ValueError("Invalid Open-Meteo weather response.") from error


def fetch_weather(*, timeout: float = 20) -> dict[str, Any]:
    """Fetch current model conditions and today's hourly Munich forecast."""
    request = Request(WEATHER_URL, headers={"User-Agent": "dashboard-danzer/0.1"})
    with urlopen(request, timeout=timeout) as response:
        return parse_weather(json.load(response))