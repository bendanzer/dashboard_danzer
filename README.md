# City Surf

A personal city-surf conditions dashboard for Eisbach water level, discharge,
weather, and relevant official city-bulletin mentions.
Python collects current and historical gauge observations and Munich weather into
a versioned JSON snapshot; GitHub Pages serves the dashboard. Weather forecasts are
not predictions of wave quality, surf safety, or access.

## Local Dashboard

```sh
uv run main.py --output dashboard/data/latest.json
uv run python -m dashboard_danzer.temperature --archive .temperature-archive/water-temperature.json --output dashboard/data/water-temperature.json
uv run python -m http.server 8000 --directory dashboard --bind 127.0.0.1
```

Open http://127.0.0.1:8000. The dashboard needs an HTTP server to load JSON.
Refresh reloads the deployed snapshot, not the upstream gauge. It also checks for
new snapshots every five minutes. Readings older than 90 minutes are marked stale.
Times are displayed in Europe/Berlin, including daylight-saving adjustments.
The chart is rendered locally from historical readings in the same snapshot as the
current value. Switch between water level and discharge, with 24-hour, 3-day,
and 7-day ranges, hover values, minimum,
maximum, net change, and a measurements table. Windows end at the newest observation,
not the browser clock, so stale data remains visible and explicitly marked stale.
Missing intervals longer than 30 minutes are not joined by a continuous line.

## GitHub Pages

1. Push these changes to the `main` branch of `bendanzer/dashboard_danzer`.
2. In repository **Settings > Pages > Build and deployment**, select **GitHub Actions**.
3. In **Actions > Publish Dashboard**, select **Run workflow** if needed.
4. After a successful deployment, visit https://bendanzer.github.io/dashboard_danzer/.

The workflow tests pull requests without publishing. Pushes to `main`, manual runs,
and the schedule (7, 22, 37, and 52 minutes past each hour, UTC) collect data and deploy.
The 15-minute schedule provides additional refresh opportunities, not a guaranteed
cadence. GitHub can delay or drop scheduled events; on public repositories schedules
can also be disabled after 60 days without repository activity.
This is not a real-time alerting service.
Pages must be available for your repository visibility and GitHub plan.

### Investigating Stale Data

First check the live site's `data/latest.json`: `collected_at` identifies pipeline
freshness, while each metric's `measured_at` identifies source freshness. Fresh
collection with old measurements points upstream; an old collection points to a
missed or failed refresh. The local preview uses local files and is not updated
by GitHub Actions. Regenerate its JSON with the local commands above.

On 25 October 2026 the workflow was active, the repository's default branch was
`main`, and its published cron was valid. Only three scheduled runs appeared
overnight, including a five-hour gap. Recorded runs started promptly and completed
successfully in under a minute, so those gaps were not explained by a stuck runner,
failed collection, or deployment lock. GitHub does not expose a diagnostic reason
for a schedule event that never creates a run; its internal cause is unverified.

The GitHub-only mitigation is more off-peak refresh opportunities and 10-minute job
timeouts to bound future blocked runs. Each test-job summary records trigger, cron,
start time, and commit. This cannot guarantee delivery of future schedule events,
and warnings still turn on after 90 minutes rather than disguising stale data.
Use **Actions > Publish Dashboard > Run workflow** for immediate manual recovery.
A dependable timing requirement needs an external scheduler; none is configured.

Water-level collection or validation failures stop publication, leaving the previous
deployment online. Discharge, weather, and city bulletins are optional: a failure
publishes fresh water-level data with the failed source explicitly unavailable.
Old optional-source data is not silently reused.
The dashboard recomputes staleness even while open. All deployed data is
public. No tokens or secrets belong in the JSON. The workflow uses GitHub's built-in
deployment token and does not require a personal access token.

## Snapshot Contract

`--output` writes `schema_version: 1`, `collected_at` (UTC), and a `metrics` array.
Each metric has `id`, `name`, `location`, `value`, `unit`, `status`, `measured_at`,
`station_id`, `source_name`, and `source_url`. The UI accepts `status: "ok"` and
determines staleness from `measured_at`, not collection time. Future collectors can
append metrics using this contract. Water-level failures block deployment; the
optional `weather` and `notices` fields use `status: "ok"` or `status: "unavailable"`.
On success discharge is an `eisbach_discharge` metric with unit `m\u00b3/s` and its own
history. If collection fails, the metric is omitted and a `discharge` object reports
`status: "unavailable"`. The UI does not substitute zero for missing discharge.

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
either current or historical water-level data stops deployment and preserves the
previous site. Discharge errors do not prevent water-level publication.

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
schedule targets 96 weather requests per day, plus manual and push runs.
Weather data are attributed to [Open-Meteo](https://open-meteo.com/), under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); field names and timestamps
are normalized for this dashboard. Commercial use requires reviewing the API plan.

## Discharge

HND publishes [discharge at the same station](https://www.hnd.bayern.de/pegel/isar/muenchen-himmelreichbruecke-16515005/abfluss)
in cubic metres per second. Each run fetches the current reading and seven-day
15-minute history, merges and deduplicates them, and exports them beside water level.
Invalid, negative, non-finite, or missing discharge values are skipped. This is a
station discharge value, not wave height or a direct measurement of wave quality.
No surfability or safety thresholds have been inferred from it.

## Official Mentions And Access

The collector reads the latest [Rathaus Umschau](https://ru.muenchen.de/), Munich's
official city bulletin, and extracts up to five distinct links with "Eisbach" in
their titles. Links must remain on the official HTTPS host. Collection includes
`fetched_at` and `coverage: "latest_issue_only"`, not a claim that all older notices
or closures have been searched. Headlines can include proposals and political
motions, not just operational notices; do not interpret them as access decisions.

Access is always `access_status: "unverified"`. No matching headlines, a failed
request, or stable gauge data never implies open access. The UI also links to the
[Englischer Garten authority](https://www.schloesser.bayern.de/deutsch/garten/objekte/mu_engl.htm).
Official restrictions and on-site signage take precedence. Bulletin fetches older
than 90 minutes are labelled outdated; fetched time is not article publication time.

## Water Temperature And Limitations

Current water temperature remains unavailable. The GKD service rejected requests,
so no direct station reading could be verified. Instead we archive the explicitly
labelled **reported 72-hour average** on [Eisbachwetter](https://www.eisbachwetter.de/).
This is a third-party summary, not a current measurement, daily mean, or direct
station feed. Consecutive 72-hour averages overlap. No historical samples are
invented, and the archive cannot reconstruct instantaneous water temperatures.

The collector checks the average field, its 72-hour label, and Celsius unit. It
never reads the separate current-value placeholder. Each observation stores
`collected_at` (UTC), `value_c`, the literal `source_updated_text`, and
`source_update_unchanged`. The source page's update text is not parsed or presented
as a sensor measurement time. An unchanged update text is flagged; a repeated value
does not imply the source has refreshed. Collection age alone cannot prove source
freshness. Attribution links to Eisbachwetter appear alongside the value.

### Persistent Daily Storage

The Pages workflow automatically creates a **`temperature-data` branch** on its
first run, initialized from the workflow's code commit. It checks out that branch
separately and changes only its root `water-temperature.json` archive. The branch's
code files are not used to run the collector or publish the dashboard.

The existing 15-minute workflow checks whether at least **24 elapsed hours** have
passed since the last successful collection. If not, no temperature request is
made and no observation or commit is added. Once due, a successful fetch adds one
observation and the workflow commits it to `temperature-data` with the built-in
GitHub token. Retries and manual deployments within 24 hours do not duplicate it.
This is approximately daily, not an exact-time service: schedules can be delayed,
and failed requests are retried on subsequent runs. Missed days are not backfilled.
UTC elapsed-time checks avoid daylight-saving calendar-day ambiguities.

The archive survives runner cleanup and Pages redeployments; it does not rely on
caches or temporary artifacts. Do not delete or rewrite `temperature-data` if you
want to retain the history. The archive is also published at
`data/water-temperature.json`, with `collection_status` added for the UI. Local
preview data under `.temperature-archive/` are ignored by Git; production history
starts with the first successful deployed collector run, not this local preview.

The build job now needs `contents: write` to create/update this data branch. Branch
rules must permit the workflow token to push to `temperature-data`. No personal
access token is needed. Bot commits do not start another workflow with the default
token, and the push trigger is restricted to `main`. Failed pushes stop the build
rather than risk publishing unpersisted history; a later run can retry. Existing
workflow concurrency serializes writers. Corrupt or future-dated archives stop the
build instead of being reset. A temperature-source outage preserves existing data
and does not prevent publication of other sources.

The UI plots daily snapshots with 30-day, 90-day, and all-history views, plus an
accessible table. A single real point is shown initially; a trend needs more than
one collection. Gaps exceeding 36 hours are not joined. The latest collection is
marked overdue after 36 hours; failed fetches keep old history visibly labelled.
No temperature is guessed from air, another river, or a model.

Wind, daylight, and rain help session planning. Local rainfall alone is not a
reliable predictor of Eisbach flow, wave shape, or water quality. This dashboard
does not provide safety clearance or water-quality assessments.

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
