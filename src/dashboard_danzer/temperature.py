import argparse
import json
import math
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup


SOURCE_URL = "https://www.eisbachwetter.de/"


def parse_temperature_average(html: str) -> tuple[float, str]:
    """Read the explicitly labelled 72-hour average, never the current-value field."""
    soup = BeautifulSoup(html, "html.parser")
    cell = soup.select_one("h2#water.value-small")
    if cell is None or cell.parent is None:
        raise ValueError("No water-temperature average found.")
    label = cell.parent.select_one(".value-header-small")
    unit = cell.select_one("span")
    if label is None or "72" not in label.get_text() or unit is None or unit.get_text(strip=True) != "\u00b0C":
        raise ValueError("Water-temperature averaging window or unit not recognized.")
    value = float(str(cell.find(string=True, recursive=False)).strip().replace(",", "."))
    if not math.isfinite(value):
        raise ValueError("Invalid water-temperature average.")
    updated = soup.select_one("#timestamp")
    return value, updated.get_text(" ", strip=True) if updated else ""


def fetch_temperature_average(*, timeout: float = 20) -> tuple[float, str]:
    request = Request(SOURCE_URL, headers={"User-Agent": "dashboard-danzer/0.1"})
    with urlopen(request, timeout=timeout) as response:
        encoding = response.headers.get_content_charset() or "utf-8"
        return parse_temperature_average(response.read().decode(encoding))


def load_archive(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": 1, "source_url": SOURCE_URL,
                "statistic": "reported_72h_average", "unit": "celsius", "observations": []}
    archive = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(archive, dict) or archive.get("schema_version") != 1 or archive.get("statistic") != "reported_72h_average" or archive.get("unit") != "celsius" or archive.get("source_url") != SOURCE_URL or not isinstance(archive.get("observations"), list):
        raise ValueError("Temperature archive format not recognized; refusing to overwrite it.")
    previous = None
    for point in archive["observations"]:
        if not isinstance(point, dict):
            raise ValueError("Invalid archived temperature observation.")
        value = point.get("value_c")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("Invalid archived temperature value.")
        collected = datetime.fromisoformat(point["collected_at"])
        if collected.tzinfo is None or (previous is not None and collected - previous < timedelta(hours=24)):
            raise ValueError("Archive timestamps must be timezone-aware and at least 24 hours apart.")
        if not isinstance(point.get("source_updated_text"), str):
            raise ValueError("Missing archived source update text.")
        previous = collected
    return archive


def write_json(path: Path, payload: dict[str, Any]) -> None:
    content = json.dumps(payload, indent=2, allow_nan=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def collect_daily(archive_path: Path, *, now: datetime | None = None) -> dict[str, Any]:
    archive = load_archive(archive_path)
    now = (now or datetime.now(UTC)).astimezone(UTC)
    observations = archive["observations"]
    previous = observations[-1] if observations else None
    if previous:
        elapsed = now - datetime.fromisoformat(previous["collected_at"])
        if elapsed < timedelta(0):
            raise ValueError("Archive contains a future collection time.")
        if elapsed < timedelta(hours=24):
            return {**archive, "collection_status": "ok"}
    try:
        value, updated = fetch_temperature_average()
    except (OSError, ValueError) as error:
        print(f"Temperature collection unavailable; retaining archive: {error}", file=sys.stderr)
        return {**archive, "collection_status": "unavailable"}
    observations.append({
        "collected_at": now.isoformat(),
        "value_c": value,
        "source_updated_text": updated,
        "source_update_unchanged": bool(previous and updated and updated == previous["source_updated_text"]),
    })
    write_json(archive_path, archive)
    return {**archive, "collection_status": "ok"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Archive Eisbachwetter's reported 72-hour average once per 24 hours.")
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        write_json(args.output, collect_daily(args.archive))
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise SystemExit(f"Could not maintain temperature archive: {error}") from error


if __name__ == "__main__":
    main()