import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from dashboard_danzer.weather import WEATHER_SOURCE_URL, fetch_weather


SOURCE_URL = (
    "https://www.hnd.bayern.de/pegel/isar/"
    "muenchen-himmelreichbruecke-16515005"
)
HISTORY_URL = SOURCE_URL + "/tabelle?methode=wasserstand&days=7&setdiskr=15"
DISCHARGE_URL = SOURCE_URL + "/abfluss"
DISCHARGE_HISTORY_URL = SOURCE_URL + "/tabelle?methode=abfluss&days=7&setdiskr=15"
NOTICES_URL = "https://ru.muenchen.de/"


@dataclass(frozen=True)
class WaterLevel:
    level_cm: float
    measured_at: datetime
    station_id: str = "16515005"
    source_url: str = SOURCE_URL


@dataclass(frozen=True)
class GaugeReading:
    value: float
    measured_at: datetime


def _parse_gauge_readings(html: str, quantity: str) -> list[GaugeReading]:
    soup = BeautifulSoup(html, "html.parser")
    readings: list[GaugeReading] = []
    for table in soup.select("table.tblsort"):
        header = table.select_one("thead")
        if header is None or quantity not in header.get_text():
            continue
        for row in table.select("tbody tr"):
            cells = row.find_all("td", recursive=False)
            if len(cells) != 2:
                continue
            try:
                measured_at = datetime.strptime(
                    cells[0].get_text(strip=True), "%d.%m.%Y %H:%M"
                ).replace(tzinfo=ZoneInfo("Europe/Berlin"))
                value = float(cells[1].get_text(strip=True).replace(",", "."))
            except ValueError:
                continue
            if not math.isfinite(value) or (quantity == "Abfluss" and value < 0):
                continue
            readings.append(GaugeReading(value=value, measured_at=measured_at))
    if not readings:
        raise ValueError(f"No valid {quantity} readings found on the HND page.")
    unique = {reading.measured_at: reading for reading in readings}
    return sorted(unique.values(), key=lambda reading: reading.measured_at)


def parse_water_levels(html: str) -> list[WaterLevel]:
    """Extract valid water levels in chronological order, deduplicated by timestamp."""
    return [WaterLevel(level_cm=point.value, measured_at=point.measured_at)
            for point in _parse_gauge_readings(html, "Wasserstand")]


def parse_discharge(html: str) -> list[GaugeReading]:
    """Extract discharge readings in cubic metres per second."""
    return _parse_gauge_readings(html, "Abfluss")


def parse_water_level(html: str) -> WaterLevel:
    """Extract the newest valid water-level reading from the HND page."""
    return parse_water_levels(html)[-1]


def _fetch_html(url: str, timeout: float) -> str:
    request = Request(url, headers={"User-Agent": "dashboard-danzer/0.1"})
    with urlopen(request, timeout=timeout) as response:
        encoding = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(encoding)


def fetch_water_level(*, timeout: float = 15) -> WaterLevel:
    """Fetch the latest Eisbach reading; network and parsing errors propagate."""
    return parse_water_level(_fetch_html(SOURCE_URL, timeout))


def fetch_water_level_history(*, timeout: float = 30) -> list[WaterLevel]:
    """Fetch HND's rolling seven-day table of 15-minute water levels."""
    return parse_water_levels(_fetch_html(HISTORY_URL, timeout))


def fetch_discharge(*, timeout: float = 30) -> dict:
    """Fetch current discharge and seven-day history for the same Eisbach gauge."""
    latest = parse_discharge(_fetch_html(DISCHARGE_URL, timeout))[-1]
    history = parse_discharge(_fetch_html(DISCHARGE_HISTORY_URL, timeout))
    unique = {point.measured_at: point for point in [*history, latest]}
    history = sorted(unique.values(), key=lambda point: point.measured_at)
    latest = history[-1]
    return {
        "id": "eisbach_discharge",
        "name": "Eisbach discharge",
        "location": "Munich / Himmelreichbruecke",
        "value": latest.value,
        "unit": "m\u00b3/s",
        "status": "ok",
        "measured_at": latest.measured_at.isoformat(),
        "station_id": "16515005",
        "source_name": "HND Bayern",
        "source_url": DISCHARGE_URL,
        "history_source_url": DISCHARGE_HISTORY_URL,
        "history": [{"value": point.value, "measured_at": point.measured_at.isoformat()}
                    for point in history],
    }


def parse_notices(html: str) -> list[dict[str, str]]:
    """Find Eisbach mentions in the latest city bulletin, without inferring access."""
    soup = BeautifulSoup(html, "html.parser")
    if "Rathaus Umschau" not in soup.get_text(" ", strip=True):
        raise ValueError("City bulletin format not recognized.")
    items: dict[str, dict[str, str]] = {}
    for anchor in soup.select("a[href]"):
        title = anchor.get_text(" ", strip=True)
        url = urljoin(NOTICES_URL, str(anchor.get("href")))
        parsed = urlsplit(url)
        if "eisbach" in title.casefold() and parsed.scheme == "https" and parsed.hostname == "ru.muenchen.de":
            items[url] = {"title": title, "url": url}
    return list(items.values())[:5]


def fetch_notices(*, timeout: float = 20) -> dict:
    items = parse_notices(_fetch_html(NOTICES_URL, timeout))
    return {
        "status": "ok",
        "access_status": "unverified",
        "coverage": "latest_issue_only",
        "fetched_at": datetime.now(UTC).isoformat(),
        "source_url": NOTICES_URL,
        "items": items,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch the latest Eisbach water level.")
    parser.add_argument("--output", type=Path, help="Write a dashboard JSON snapshot.")
    args = parser.parse_args()
    try:
        reading = fetch_water_level()
        payload = asdict(reading)
        payload["measured_at"] = reading.measured_at.isoformat()
        if args.output is None:
            print(json.dumps(payload, indent=2, allow_nan=False))
            return
        history = fetch_water_level_history()
        unique = {point.measured_at: point for point in [*history, reading]}
        history = sorted(unique.values(), key=lambda point: point.measured_at)
        reading = history[-1]
        snapshot = {
            "schema_version": 1,
            "collected_at": datetime.now(UTC).isoformat(),
            "metrics": [
                {
                    "id": "eisbach_water_level",
                    "name": "Eisbach water level",
                    "location": "Munich / Himmelreichbruecke",
                    "value": reading.level_cm,
                    "unit": "cm",
                    "status": "ok",
                    "measured_at": reading.measured_at.isoformat(),
                    "station_id": reading.station_id,
                    "source_name": "HND Bayern",
                    "source_url": reading.source_url,
                    "history_source_url": HISTORY_URL,
                    "history": [
                        {"value": point.level_cm, "measured_at": point.measured_at.isoformat()}
                        for point in history
                    ],
                }
            ],
        }
        try:
            snapshot["metrics"].append(fetch_discharge())
        except (OSError, ValueError) as error:
            snapshot["discharge"] = {"status": "unavailable", "source_url": DISCHARGE_URL}
            print(f"Discharge unavailable; publishing water level: {error}", file=sys.stderr)
        try:
            snapshot["notices"] = fetch_notices()
        except (OSError, ValueError) as error:
            snapshot["notices"] = {
                "status": "unavailable", "access_status": "unverified", "source_url": NOTICES_URL,
            }
            print(f"City notices unavailable: {error}", file=sys.stderr)
        try:
            snapshot["weather"] = fetch_weather()
        except (OSError, ValueError) as error:
            snapshot["weather"] = {
                "status": "unavailable",
                "source_name": "Open-Meteo",
                "source_url": WEATHER_SOURCE_URL,
            }
            print(f"Weather unavailable; publishing gauge data only: {error}", file=sys.stderr)
        content = json.dumps(snapshot, indent=2, allow_nan=False) + "\n"
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(args.output)
    except (OSError, ValueError) as error:
        raise SystemExit(f"Could not fetch Eisbach water level: {error}") from error
