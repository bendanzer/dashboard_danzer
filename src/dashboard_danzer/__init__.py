import argparse
import json
import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup


SOURCE_URL = (
    "https://www.hnd.bayern.de/pegel/isar/"
    "muenchen-himmelreichbruecke-16515005"
)
HISTORY_URL = SOURCE_URL + "/tabelle?methode=wasserstand&days=7&setdiskr=15"


@dataclass(frozen=True)
class WaterLevel:
    level_cm: float
    measured_at: datetime
    station_id: str = "16515005"
    source_url: str = SOURCE_URL


def parse_water_levels(html: str) -> list[WaterLevel]:
    """Extract valid readings in chronological order, deduplicated by timestamp."""
    soup = BeautifulSoup(html, "html.parser")
    readings: list[WaterLevel] = []
    for table in soup.select("table.tblsort"):
        header = table.select_one("thead")
        if header is None or "Wasserstand" not in header.get_text():
            continue
        for row in table.select("tbody tr"):
            cells = row.find_all("td", recursive=False)
            if len(cells) != 2:
                continue
            try:
                measured_at = datetime.strptime(
                    cells[0].get_text(strip=True), "%d.%m.%Y %H:%M"
                ).replace(tzinfo=ZoneInfo("Europe/Berlin"))
                level_cm = float(cells[1].get_text(strip=True).replace(",", "."))
            except ValueError:
                continue
            if not math.isfinite(level_cm):
                continue
            readings.append(WaterLevel(level_cm=level_cm, measured_at=measured_at))
    if not readings:
        raise ValueError("No valid water-level readings found on the HND page.")
    unique = {reading.measured_at: reading for reading in readings}
    return sorted(unique.values(), key=lambda reading: reading.measured_at)


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
        content = json.dumps(snapshot, indent=2, allow_nan=False) + "\n"
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(args.output)
    except (OSError, ValueError) as error:
        raise SystemExit(f"Could not fetch Eisbach water level: {error}") from error
