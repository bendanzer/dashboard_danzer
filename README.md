# Eisbach Water Level

Fetch the latest published water level for Munich's Himmelreichbruecke / Eisbach
gauge (station 16515005) from the Bavarian flood information service.

Requires Python 3.13+ and [uv](https://docs.astral.sh/uv/).

```sh
uv run main.py
# Or use the installed command:
uv run dashboard-danzer
```

The command prints JSON containing `level_cm`, `measured_at` (ISO 8601 with the
Europe/Berlin UTC offset), `station_id`, and `source_url`.
Network failures and missing readings produce a nonzero exit status.

To use it from Python:

```python
from dashboard_danzer import fetch_water_level

reading = fetch_water_level()
print(reading.level_cm, reading.measured_at)
```

Water levels are centimetres above the station's gauge datum, not water depth.
The function returns the newest valid reading on the page, which may be stale
if the station stops reporting. Check `measured_at` before relying on it.
This reads the site's HTML, so future layout changes may require parser updates.
Source: [Bayerisches Landesamt fuer Umwelt, HND Bayern](https://www.hnd.bayern.de/pegel/isar/muenchen-himmelreichbruecke-16515005).
Avoid polling more frequently than the readings update (currently every 15 minutes).

Run the offline tests:

```sh
uv run python -m unittest discover -s tests -v
```
