# City Surf

A personal city-surf conditions dashboard, starting with the Eisbach water level.
Python collects current and historical observations into a versioned JSON snapshot;
GitHub Pages serves the dashboard. This is an observations dashboard, not yet a
forecast or an assessment of wave quality, surf safety, or access.

## Local Dashboard

```sh
uv run main.py --output dashboard/data/latest.json
uv run python -m http.server 8000 --directory dashboard --bind 127.0.0.1
```

Open http://127.0.0.1:8000. The dashboard needs an HTTP server to load JSON.
Refresh reloads the deployed snapshot, not the upstream gauge. It also checks for
new snapshots every five minutes. Readings older than 90 minutes are marked stale.
Times are displayed in Europe/Berlin, including daylight-saving adjustments.
The chart is rendered locally from historical readings in the same snapshot as the
current value. It offers 24-hour, 3-day, and 7-day ranges, hover values, minimum,
maximum, net change, and a measurements table. Windows end at the newest observation,
not the browser clock, so stale data remains visible and explicitly marked stale.
Missing intervals longer than 30 minutes are not joined by a continuous line.

## GitHub Pages

1. Push these changes to the `main` branch of `bendanzer/dashboard_danzer`.
2. In repository **Settings > Pages > Build and deployment**, select **GitHub Actions**.
3. In **Actions > Publish Dashboard**, select **Run workflow** if needed.
4. After a successful deployment, visit https://bendanzer.github.io/dashboard_danzer/.

The workflow tests pull requests without publishing. Pushes to `main`, manual runs,
and the schedule (17 and 47 minutes past each hour, UTC) collect data and deploy.
GitHub schedules can be delayed; on public repositories they can be disabled after
60 days without repository activity. This is not a real-time alerting service.
Pages must be available for your repository visibility and GitHub plan.

Collection or validation failures stop publication, leaving the previous deployment
online. The dashboard recomputes staleness even while open. All deployed data is
public. No tokens or secrets belong in the JSON. The workflow uses GitHub's built-in
deployment token and does not require a personal access token.

## Snapshot Contract

`--output` writes `schema_version: 1`, `collected_at` (UTC), and a `metrics` array.
Each metric has `id`, `name`, `location`, `value`, `unit`, `status`, `measured_at`,
`station_id`, `source_name`, and `source_url`. The UI accepts `status: "ok"` and
determines staleness from `measured_at`, not collection time. Future collectors can
append metrics using this contract. Failed sources currently block deployment;
partial-success behavior should be defined when adding another source.

The Eisbach metric additionally includes `history_source_url` and `history`, a
chronological array of `{ "measured_at": "<ISO 8601>", "value": 116 }` samples in cm.
HND's seven-day table is requested at 15-minute resolution. Invalid readings are
skipped, duplicate timestamps are collapsed, and the newest reading is merged into
the series. The current value always matches the newest observation in the series.
Missing history in an older snapshot shows an unavailable state, not invented data.

Generated JSON is ignored by Git and deployed as part of the Pages artifact.
Each run refetches the rolling seven-day history from HND, so charts work immediately
without accumulating samples in GitHub Actions. This is not a permanent archive:
retention beyond that window will need separate persistent storage. Failure to fetch
either current or historical data stops deployment and preserves the previous site.

Chart.js 4.4.8 is vendored under `dashboard/vendor/`, with its MIT license alongside
the distribution. No build tool or external chart service is required.

## Eisbach Collector

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
from dashboard_danzer import fetch_water_level, fetch_water_level_history

reading = fetch_water_level()
print(reading.level_cm, reading.measured_at)
history = fetch_water_level_history()
print(len(history), history[0].measured_at, history[-1].measured_at)
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
