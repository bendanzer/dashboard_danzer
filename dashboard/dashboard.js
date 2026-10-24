const refreshButton = document.querySelector("#refresh");
const notice = document.querySelector("#notice");
const metrics = document.querySelector("#metrics");
const template = document.querySelector("#metric-template");
const staleAfterMs = 90 * 60 * 1000;
const dateFormat = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Europe/Berlin", dateStyle: "medium", timeStyle: "short",
});
let snapshot = null;
let refreshFailed = false;
let historyChart = null;
let temperatureArchive = null;
let temperatureFailed = false;
let temperatureChart = null;

function renderTemperature() {
  const archive = temperatureArchive;
  const status = document.querySelector("#temperature-status");
  const average = document.querySelector("#temperature-average");
  const badge = document.querySelector("#temperature-badge");
  const section = document.querySelector("#temperature-history");
  if (!archive?.observations.length) {
    status.textContent = temperatureFailed ? "Temperature archive unavailable." : "No daily temperature snapshots yet.";
    badge.textContent = "Unavailable";
    badge.classList.add("stale");
    average.hidden = true;
    section.hidden = true;
    return;
  }
  average.hidden = false;
  section.hidden = false;
  const latest = archive.observations.at(-1);
  const overdue = Date.now() - Date.parse(latest.collected_at) > 36 * 3600000;
  const failed = temperatureFailed || archive.collection_status === "unavailable";
  average.textContent = `${latest.value_c.toLocaleString("en-GB", { maximumFractionDigits: 1 })} \u00b0C`;
  badge.textContent = overdue ? "Archive overdue" : "72h average";
  badge.classList.toggle("stale", overdue || failed || latest.source_update_unchanged === true);
  status.textContent = `Collected ${dateFormat.format(new Date(latest.collected_at))} Berlin${failed ? " / Collection unavailable; showing saved history" : ""}${overdue ? " / Daily collection overdue" : ""}${latest.source_update_unchanged ? " / Source update unchanged since previous collection" : ""}`;
}

function renderTemperatureChart() {
  if (temperatureChart) temperatureChart.destroy();
  temperatureChart = null;
  const container = document.querySelector("#temperature-chart-container");
  container.hidden = true;
  if (!temperatureArchive?.observations.length) return;
  const all = temperatureArchive.observations;
  const last = Date.parse(all.at(-1).collected_at);
  const range = document.querySelector('[name="temperature-range"]:checked').value;
  const points = all.filter((point) => range === "all" || Date.parse(point.collected_at) >= last - Number(range) * 86400000);
  document.querySelector("#temperature-history-status").textContent = `${points.length} daily ${points.length === 1 ? "snapshot / No trend yet" : "snapshots"} / reported 72-hour averages`;
  document.querySelector("#temperature-source-update").textContent = all.at(-1).source_updated_text
    ? `Latest source page update text (not a measurement time): ${all.at(-1).source_updated_text}`
    : "Source measurement time is not provided.";
  const rows = document.createDocumentFragment();
  for (const point of [...points].reverse()) {
    const row = document.createElement("tr");
    const collected = document.createElement("td");
    const value = document.createElement("td");
    collected.textContent = dateFormat.format(new Date(point.collected_at));
    value.textContent = point.value_c.toLocaleString("en-GB", { maximumFractionDigits: 1 });
    row.append(collected, value);
    rows.append(row);
  }
  document.querySelector("#temperature-rows").replaceChildren(rows);
  if (typeof window.Chart !== "function") return;
  container.hidden = false;
  const canvas = document.querySelector("#temperature-chart");
  canvas.setAttribute("aria-label", `${points.length} daily snapshots of reported 72-hour average water temperature, latest ${all.at(-1).value_c} degrees Celsius`);
  temperatureChart = new window.Chart(canvas, {
    type: "line",
    data: { datasets: [{ label: "Reported 72h average", data: points.map((point) => ({ x: Date.parse(point.collected_at), y: point.value_c })),
      parsing: false, borderColor: "#ad4864", borderWidth: 2, pointRadius: points.length === 1 ? 5 : 2,
      pointHitRadius: 14, tension: 0, spanGaps: 36 * 3600000 }] },
    options: { responsive: true, maintainAspectRatio: false, animation: false,
      plugins: { legend: { display: false }, tooltip: { displayColors: false, callbacks: {
        title: (items) => `Collected ${dateFormat.format(new Date(items[0].parsed.x))} Berlin`,
        label: (item) => `${item.parsed.y} \u00b0C / reported 72h average`,
      } } },
      scales: {
        x: { type: "linear", ...(points.length === 1 ? { min: last - 12 * 3600000, max: last + 12 * 3600000 } : {}),
          grid: { display: false }, ticks: { maxTicksLimit: 5, maxRotation: 0, callback: (value) => new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/Berlin", day: "numeric", month: "short" }).format(new Date(value)) } },
        y: { title: { display: true, text: "Reported 72h average / \u00b0C" }, ticks: { maxTicksLimit: 6 } },
      },
    },
  });
}

async function loadTemperature() {
  try {
    const response = await fetch("data/water-temperature.json", { cache: "no-store" });
    if (!response.ok) throw new Error("Temperature archive unavailable");
    const archive = await response.json();
    if (archive.schema_version !== 1 || archive.statistic !== "reported_72h_average" || archive.unit !== "celsius" ||
        !Array.isArray(archive.observations) || !archive.observations.every((point, index, points) => point &&
          Number.isFinite(point.value_c) && Number.isFinite(Date.parse(point.collected_at)) &&
          typeof point.source_updated_text === "string" && (index === 0 || Date.parse(point.collected_at) - Date.parse(points[index - 1].collected_at) >= 86400000))) {
      throw new Error("Invalid temperature archive");
    }
    temperatureArchive = archive;
    temperatureFailed = false;
  } catch {
    temperatureFailed = true;
  }
  renderTemperature();
  renderTemperatureChart();
}

function renderNotices() {
  const notices = snapshot?.notices;
  const status = document.querySelector("#notices-status");
  const list = document.querySelector("#official-notices");
  list.replaceChildren();
  if (notices?.status !== "ok" || !Array.isArray(notices.items) || !Number.isFinite(Date.parse(notices.fetched_at))) {
    status.textContent = "City bulletin unavailable. Access status is not verified.";
    return;
  }
  const items = notices.items.filter((item) => typeof item?.title === "string" && typeof item.url === "string" && item.url.startsWith("https://ru.muenchen.de/"));
  const stale = Date.now() - Date.parse(notices.fetched_at) > staleAfterMs;
  status.textContent = `${stale ? "Outdated bulletin snapshot" : "Latest city bulletin"} / fetched ${dateFormat.format(new Date(notices.fetched_at))} Berlin${items.length ? "" : " / No Eisbach mentions in this issue"}`;
  for (const item of items.slice(0, 5)) {
    const row = document.createElement("li");
    const link = document.createElement("a");
    link.href = item.url;
    link.textContent = item.title;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    row.append(link);
    list.append(row);
  }
}

const weatherCodes = {
  0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
  45: "Fog", 48: "Freezing fog", 51: "Light drizzle", 53: "Drizzle", 55: "Dense drizzle",
  56: "Freezing drizzle", 57: "Freezing drizzle", 61: "Light rain", 63: "Rain", 65: "Heavy rain",
  66: "Freezing rain", 67: "Heavy freezing rain", 71: "Light snow", 73: "Snow", 75: "Heavy snow",
  77: "Snow grains", 80: "Rain showers", 81: "Rain showers", 82: "Heavy showers",
  85: "Snow showers", 86: "Heavy snow showers", 95: "Thunderstorm", 96: "Thunderstorm / hail",
  97: "Heavy thunderstorm", 99: "Thunderstorm / hail",
};
const hourFormat = new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/Berlin", hour: "2-digit", minute: "2-digit", timeZoneName: "short" });
const dayFormat = new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Berlin", year: "numeric", month: "2-digit", day: "2-digit" });

function validWeather(weather) {
  const current = weather?.current;
  const today = weather?.today;
  return weather?.status === "ok" && current && today &&
    ["temperature_c", "feels_like_c", "wind_kmh", "wind_direction_deg", "precipitation_mm", "weather_code"].every((key) => Number.isFinite(current[key])) &&
    Number.isFinite(Date.parse(current.time)) && [today.sunrise, today.sunset].every((value) => Number.isFinite(Date.parse(value))) &&
    [today.high_c, today.low_c].every(Number.isFinite) && typeof today.date === "string" &&
    Array.isArray(weather.hourly) && weather.hourly.length > 0 && weather.hourly.every((point) => point &&
      Number.isFinite(Date.parse(point.time)) && ["temperature_c", "rain_probability_pct", "precipitation_mm", "wind_kmh", "weather_code"].every((key) => Number.isFinite(point[key])));
}

function renderWeather() {
  const weather = snapshot?.weather;
  const status = document.querySelector("#weather-status");
  const badge = document.querySelector("#weather-badge");
  const details = document.querySelector("#weather-details");
  const forecast = document.querySelector("#weather-forecast");
  if (!validWeather(weather)) {
    status.textContent = "Weather unavailable. Gauge observations are still shown.";
    badge.textContent = "Unavailable";
    badge.classList.add("stale");
    details.hidden = true;
    forecast.hidden = true;
    return;
  }
  details.hidden = false;
  forecast.hidden = false;
  const current = weather.current;
  const today = weather.today;
  const age = Date.now() - Date.parse(current.time);
  const isToday = today.date === dayFormat.format(new Date());
  const stale = age > staleAfterMs || age < -5 * 60 * 1000 || !isToday;
  badge.textContent = stale ? "Stale model data" : "Model data";
  badge.classList.toggle("stale", stale);
  status.textContent = `Valid ${dateFormat.format(new Date(current.time))} Berlin${stale ? " / Weather may be outdated" : ""}`;
  const number = (value) => new Intl.NumberFormat("en-GB", { maximumFractionDigits: 1 }).format(value);
  const compass = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][Math.round(current.wind_direction_deg / 45) % 8];
  document.querySelector("#weather-temperature").textContent = number(current.temperature_c);
  document.querySelector("#weather-description").textContent = weatherCodes[current.weather_code] || "Unknown conditions";
  document.querySelector("#weather-feels").textContent = `${number(current.feels_like_c)} \u00b0C`;
  document.querySelector("#weather-wind").textContent = `${number(current.wind_kmh)} km/h ${compass}`;
  document.querySelector("#weather-rain").textContent = `${number(current.precipitation_mm)} mm`;
  document.querySelector("#weather-range").textContent = `${number(today.low_c)} / ${number(today.high_c)} \u00b0C`;
  document.querySelector("#weather-sunrise").textContent = hourFormat.format(new Date(today.sunrise));
  document.querySelector("#weather-sunset").textContent = hourFormat.format(new Date(today.sunset));
  document.querySelector("#forecast-heading").textContent = isToday ? "Today's forecast" : `Forecast / ${today.date}`;
  const fullDay = document.querySelector('[name="forecast-range"]:checked').value === "all";
  const nextHour = Math.ceil(Date.now() / 3600000) * 3600000;
  const hours = weather.hourly.filter((point) => fullDay || Date.parse(point.time) >= nextHour);
  document.querySelector("#forecast-status").textContent = `${today.date} / ${stale ? "Stale model data" : "Hourly model forecast"}${hours.length ? "" : " / No forecast hours remain for this day"}`;
  const rows = document.createDocumentFragment();
  for (const point of hours) {
    const row = document.createElement("tr");
    const values = [hourFormat.format(new Date(point.time)), weatherCodes[point.weather_code] || "Unknown",
      number(point.temperature_c), `${number(point.rain_probability_pct)}%`, number(point.precipitation_mm), number(point.wind_kmh)];
    for (const value of values) {
      const cell = document.createElement("td");
      cell.textContent = value;
      row.append(cell);
    }
    rows.append(row);
  }
  document.querySelector("#forecast-rows").replaceChildren(rows);
}

function renderHistory() {
  const selected = document.querySelector('[name="history-metric"]:checked').value;
  const metric = snapshot?.metrics.find((entry) => entry.id === selected);
  const isDischarge = selected === "eisbach_discharge";
  const label = isDischarge ? "Discharge" : "Water level";
  const unit = isDischarge ? "m\u00b3/s" : "cm";
  document.querySelector("#history-heading").textContent = `${label} history`;
  document.querySelector("#history-value-heading").textContent = `${label} / ${unit}`;
  document.querySelector("#history-caption").textContent = `${isDischarge ? "Discharge is the volume passing the gauge per second." : "Water level is height above gauge datum, not depth."} Gauge measurements do not assess wave quality, safety, or access.`;
  document.querySelector("#history-source").href = `https://www.hnd.bayern.de/pegel/isar/muenchen-himmelreichbruecke-16515005/tabelle?methode=${isDischarge ? "abfluss" : "wasserstand"}&days=7&setdiskr=15`;
  const status = document.querySelector("#history-status");
  const container = document.querySelector("#chart-container");
  const summary = document.querySelector(".history-summary");
  const table = document.querySelector("#history-table");
  if (historyChart) historyChart.destroy();
  historyChart = null;
  container.hidden = true;
  summary.hidden = true;
  table.hidden = true;
  const valid = Array.isArray(metric?.history) && metric.history.length > 0 &&
    metric.history.every((point) => Number.isFinite(point?.value) && Number.isFinite(Date.parse(point.measured_at)));
  if (!valid) {
    status.textContent = `${label} history unavailable for this snapshot.`;
    return;
  }
  const unique = new Map(metric.history.map((point) => [Date.parse(point.measured_at), point.value]));
  const points = [...unique].sort((first, second) => first[0] - second[0]).map(([time, value]) => ({ x: time, y: value }));
  const rangeDays = Number(document.querySelector('[name="history-range"]:checked').value);
  const end = points.at(-1).x;
  const start = end - rangeDays * 24 * 60 * 60 * 1000;
  const visible = points.filter((point) => point.x >= start);
  const values = visible.map((point) => point.y);
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const change = visible.at(-1).y - visible[0].y;
  const format = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 1 });
  document.querySelector("#history-min").textContent = `${format.format(minimum)} ${unit}`;
  document.querySelector("#history-max").textContent = `${format.format(maximum)} ${unit}`;
  document.querySelector("#history-change").textContent = `${change > 0 ? "+" : ""}${format.format(change)} ${unit}`;
  status.textContent = `${visible.length} observations / ${dateFormat.format(new Date(visible[0].x))} to ${dateFormat.format(new Date(end))} / Berlin time`;
  summary.hidden = false;
  const rows = document.createDocumentFragment();
  for (const point of [...visible].reverse()) {
    const row = document.createElement("tr");
    const time = document.createElement("td");
    const value = document.createElement("td");
    time.textContent = dateFormat.format(new Date(point.x));
    value.textContent = format.format(point.y);
    row.append(time, value);
    rows.append(row);
  }
  table.querySelector("tbody").replaceChildren(rows);
  table.hidden = false;
  if (typeof window.Chart !== "function") {
    status.textContent += " / Chart unavailable";
    return;
  }
  container.hidden = false;
  const canvas = document.querySelector("#water-level-chart");
  canvas.setAttribute("aria-label", `Eisbach ${label.toLowerCase()}, ${visible.length} observations, minimum ${minimum} ${unit}, maximum ${maximum} ${unit}`);
  historyChart = new window.Chart(canvas, {
    type: "line",
    data: { datasets: [{
      label, data: visible, parsing: false, normalized: true,
      borderColor: isDischarge ? "#007b8a" : "#176448", backgroundColor: isDischarge ? "rgba(0, 123, 138, 0.08)" : "rgba(23, 100, 72, 0.08)",
      borderWidth: 2, fill: true, pointRadius: visible.length === 1 ? 4 : 0,
      pointHitRadius: 16, pointHoverRadius: 4, tension: 0, spanGaps: 30 * 60 * 1000,
    }] },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      interaction: { mode: "nearest", axis: "x", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: { displayColors: false, callbacks: {
          title: (items) => `${dateFormat.format(new Date(items[0].parsed.x))} Berlin`,
          label: (item) => `${format.format(item.parsed.y)} ${unit}`,
        } },
      },
      scales: {
        x: { type: "linear", min: start, max: end, grid: { display: false }, ticks: {
          count: rangeDays === 1 ? 5 : rangeDays + 1,
          maxTicksLimit: rangeDays === 1 ? 5 : 7, maxRotation: 0,
          callback: (value) => new Intl.DateTimeFormat("en-GB", rangeDays === 1
            ? { timeZone: "Europe/Berlin", hour: "2-digit", minute: "2-digit" }
            : { timeZone: "Europe/Berlin", day: "2-digit", month: "short" }).format(new Date(value)),
        } },
        y: { suggestedMin: isDischarge ? Math.max(0, minimum - 0.5) : minimum - 3, suggestedMax: maximum + (isDischarge ? 0.5 : 3),
          title: { display: true, text: `${label} / ${unit}` },
          grid: { color: "#e5eae6" }, ticks: { precision: isDischarge ? 1 : 0, maxTicksLimit: 6 },
        },
      },
    },
  });
}

function showNotice(message, state = "") {
  notice.textContent = message;
  notice.className = `notice ${state}`;
  notice.hidden = !message;
}

function isValidSnapshot(data) {
  return data?.schema_version === 1 && Number.isFinite(Date.parse(data.collected_at)) &&
    Array.isArray(data.metrics) && data.metrics.length > 0 &&
    data.metrics.every((metric) => metric && typeof metric.id === "string" &&
      typeof metric.name === "string" && typeof metric.location === "string" &&
      Number.isFinite(metric.value) && typeof metric.unit === "string" &&
      metric.status === "ok" && Number.isFinite(Date.parse(metric.measured_at)) &&
      typeof metric.station_id === "string" && typeof metric.source_name === "string" &&
      typeof metric.source_url === "string" && metric.source_url.startsWith("https://"));
}

function render() {
  if (!snapshot) return;
  const fragment = document.createDocumentFragment();
  let staleCount = 0;
  for (const metric of snapshot.metrics) {
    const item = template.content.firstElementChild.cloneNode(true);
    const age = Date.now() - Date.parse(metric.measured_at);
    const stale = age > staleAfterMs || age < -5 * 60 * 1000;
    if (stale) staleCount += 1;
    item.querySelector("h2").textContent = metric.name;
    item.querySelector(".location").textContent = metric.location;
    item.querySelector(".value").textContent = new Intl.NumberFormat("en-GB").format(metric.value);
    item.querySelector(".unit").textContent = metric.unit;
    const badge = item.querySelector(".badge");
    badge.textContent = stale ? "Stale reading" : "Recent reading";
    badge.classList.toggle("stale", stale);
    const measured = item.querySelector(".measured-at");
    measured.dateTime = metric.measured_at;
    measured.textContent = `${dateFormat.format(new Date(metric.measured_at))} Berlin`;
    item.querySelector(".station-id").textContent = metric.station_id;
    const datum = item.querySelector(".datum");
    datum.hidden = !["eisbach_water_level", "eisbach_discharge"].includes(metric.id);
    datum.textContent = metric.id === "eisbach_discharge" ? "Volume passing the gauge per second" : "Above gauge datum, not water depth";
    const source = item.querySelector(".source");
    source.href = metric.source_url;
    source.textContent = `Source: ${metric.source_name} \u2197`;
    fragment.append(item);
  }
  metrics.replaceChildren(fragment);
  const count = new Set(snapshot.metrics.map((metric) => metric.source_name)).size + (validWeather(snapshot.weather) ? 1 : 0) + (snapshot.notices?.status === "ok" ? 1 : 0);
  document.querySelector("#source-count").textContent = `${count} data ${count === 1 ? "source" : "sources"}`;
  const collected = document.querySelector("#collected-at");
  collected.dateTime = snapshot.collected_at;
  collected.textContent = `${dateFormat.format(new Date(snapshot.collected_at))} Berlin`;
  if (refreshFailed) {
    showNotice("Refresh failed. Showing the last loaded snapshot; check measurement times.", "warning");
  } else if (staleCount) {
    showNotice("Some readings are over 90 minutes old or have an unexpected timestamp. Check measurement times before relying on them.", "warning");
  } else {
    showNotice("");
  }
  document.querySelector("#station-record").hidden = !snapshot.metrics.some((metric) => metric.id === "eisbach_water_level");
  const dischargeMissing = !snapshot.metrics.some((metric) => metric.id === "eisbach_discharge");
  document.querySelector("#optional-notice").hidden = !dischargeMissing;
  document.querySelector("#optional-notice").textContent = dischargeMissing ? "Discharge data unavailable. Water level and other available sources are shown." : "";
  renderWeather();
  renderNotices();
  renderTemperature();
}

async function loadSnapshot() {
  refreshButton.disabled = true;
  const temperatureTask = loadTemperature();
  metrics.setAttribute("aria-busy", "true");
  try {
    const response = await fetch("data/latest.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    if (!isValidSnapshot(data)) throw new Error("Invalid snapshot");
    snapshot = data;
    refreshFailed = false;
    render();
    renderHistory();
  } catch {
    refreshFailed = true;
    if (snapshot) render();
    else showNotice("Observations are unavailable. Please try again later or check HND Bayern directly.", "error");
  } finally {
    await temperatureTask;
    refreshButton.disabled = false;
    metrics.setAttribute("aria-busy", "false");
  }
}

document.querySelectorAll('[name="history-range"]').forEach((input) => input.addEventListener("change", renderHistory));
document.querySelectorAll('[name="history-metric"]').forEach((input) => input.addEventListener("change", renderHistory));
document.querySelectorAll('[name="forecast-range"]').forEach((input) => input.addEventListener("change", renderWeather));
document.querySelectorAll('[name="temperature-range"]').forEach((input) => input.addEventListener("change", renderTemperatureChart));
refreshButton.addEventListener("click", loadSnapshot);
setInterval(() => { if (snapshot) render(); }, 60 * 1000);
setInterval(loadSnapshot, 5 * 60 * 1000);
loadSnapshot();