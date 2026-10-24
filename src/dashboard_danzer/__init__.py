import json
from dataclasses import asdict, dataclass
from datetime import datetime
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup


SOURCE_URL = (
    "https://www.hnd.bayern.de/pegel/isar/"
    "muenchen-himmelreichbruecke-16515005"
)


@dataclass(frozen=True)
class WaterLevel:
    level_cm: float
    measured_at: datetime
    station_id: str = "16515005"
    source_url: str = SOURCE_URL


def parse_water_level(html: str) -> WaterLevel:
    """Extract the newest valid water-level reading from the HND page."""
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
            readings.append(WaterLevel(level_cm=level_cm, measured_at=measured_at))
    if not readings:
        raise ValueError("No valid water-level readings found on the HND page.")
    return max(readings, key=lambda reading: reading.measured_at)


def fetch_water_level(*, timeout: float = 15) -> WaterLevel:
    """Fetch the latest Eisbach reading; network and parsing errors propagate."""
    request = Request(SOURCE_URL, headers={"User-Agent": "dashboard-danzer/0.1"})
    with urlopen(request, timeout=timeout) as response:
        encoding = response.headers.get_content_charset() or "utf-8"
        html = response.read().decode(encoding)
    return parse_water_level(html)


def main() -> None:
    try:
        reading = fetch_water_level()
    except (OSError, ValueError) as error:
        raise SystemExit(f"Could not fetch Eisbach water level: {error}") from error
    payload = asdict(reading)
    payload["measured_at"] = reading.measured_at.isoformat()
    print(json.dumps(payload, indent=2))
