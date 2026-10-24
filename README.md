# City Surf

A personal city-surf conditions dashboard, starting with the Eisbach water level.
Python collects current and historical gauge observations and Munich weather into
a versioned JSON snapshot; GitHub Pages serves the dashboard. Weather forecasts are
not predictions of wave quality, surf safety, or access.

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

Gauge collection or validation failures stop publication, leaving the previous
deployment online. Weather is optional: an API or validation failure publishes fresh
gauge data with weather explicitly unavailable. No old weather is silently reused.
The dashboard recomputes staleness even while open. All deployed data is
public. No tokens or secrets belong in the JSON. The workflow uses GitHub's built-in
deployment token and does not require a personal access token.

## Snapshot Contract

`--output` writes `schema_version: 1`, `collected_at` (UTC), and a `metrics` array.
Each metric has `id`, `name`, `location`, `value`, `unit`, `status`, `measured_at`,
`station_id`, `source_name`, and `source_url`. The UI accepts `status: "ok"` and
determines staleness from `measured_at`, not collection time. Future collectors can
append metrics using this contract. Gauge failures block deployment; the separate
optional `weather` field uses `status: "ok"` or `status: "unavailable"`.

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

## Weather

Open-Meteo provides current model conditions and the current day's hourly weather
forecast near the Eisbach (48.1435 N, 11.5877 E). The weather model grid cell may
be several kilometres away; this is not an on-site station or a wave forecast.
Current weather is based on 15-minute model data, not direct local observations.

The panel includes air temperature, feels-like temperature, wind speed/direction,
recent precipitation, today's low/high, sunrise and sunset. The hourly table adds
precipitation probability, amount, and weather conditions. "From now" excludes
elapsed hours; "Full day" also shows earlier model values. Precipitation totals and
probabilities refer to the hour ending at the displayed time. All times use
Europe/Berlin; repeated daylight-saving hours retain distinct UTC offsets and zone
labels. Sunrise and sunset do not account for local tree or building shade.

The `weather` snapshot field contains `current`, `today`, and `hourly` objects with
ISO 8601 valid times. Temperatures are Celsius, wind is km/h, precipitation is mm,
and precipitation probability is percent. Weather older than 90 minutes or belonging
to a different calendar day is marked stale; an older forecast is labelled with its
actual date instead of "today". Unknown weather codes display "Unknown conditions".

No API key is needed for this personal, non-commercial use. The free API's limits
are documented in [Open-Meteo's terms](https://open-meteo.com/en/terms). The existing
schedule normally makes 48 weather requests per day, plus manual and push runs.
Weather data are attributed to [Open-Meteo](https://open-meteo.com/), under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); field names and timestamps
are normalized for this dashboard. Commercial use requires reviewing the API plan.

## Other Wave-Relevant Sources

- HND also publishes [discharge at this station](https://www.hnd.bayern.de/pegel/isar/muenchen-himmelreichbruecke-16515005/abfluss)
	in cubic metres per second. Together with level and recent changes, it is a useful
	next input, but cannot determine wave quality or safe access by itself.
- Water temperature would help with thermal exposure planning if a representative
	nearby source is available. Air temperature is not a substitute.
- Official wave closures, works, and access notices should override any inferred
	surf recommendation. These need a verified official source before integration.
- Wind, daylight, and rain help session planning. Local rainfall alone is not a
	reliable predictor of Eisbach flow, wave shape, or water quality.

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
