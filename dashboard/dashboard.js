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
    item.querySelector(".datum").hidden = metric.id !== "eisbach_water_level";
    const source = item.querySelector(".source");
    source.href = metric.source_url;
    source.textContent = `Source: ${metric.source_name} \u2197`;
    fragment.append(item);
  }
  metrics.replaceChildren(fragment);
  const count = new Set(snapshot.metrics.map((metric) => metric.source_url)).size;
  document.querySelector("#source-count").textContent = `${count} ${count === 1 ? "source" : "sources"} / ${snapshot.metrics.length} ${snapshot.metrics.length === 1 ? "observation" : "observations"}`;
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
}

async function loadSnapshot() {
  refreshButton.disabled = true;
  metrics.setAttribute("aria-busy", "true");
  try {
    const response = await fetch("data/latest.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    if (!isValidSnapshot(data)) throw new Error("Invalid snapshot");
    snapshot = data;
    refreshFailed = false;
    render();
    const chart = document.querySelector("#station-chart");
    if (!chart.hasAttribute("src")) {
      chart.src = "https://www.hnd.bayern.de/webservices/graphik.php?cache=hnd&statnr=16515005&thema=hochwasser.meldestufen&wert=wasserstand&vhs=false&geber=0";
    }
  } catch {
    refreshFailed = true;
    if (snapshot) render();
    else showNotice("Observations are unavailable. Please try again later or check HND Bayern directly.", "error");
  } finally {
    refreshButton.disabled = false;
    metrics.setAttribute("aria-busy", "false");
  }
}

document.querySelector("#station-chart").addEventListener("error", () => {
  document.querySelector("#station-chart").hidden = true;
  document.querySelector("#chart-caption").textContent = "Chart unavailable. View the station record on HND Bayern.";
});
refreshButton.addEventListener("click", loadSnapshot);
setInterval(() => { if (snapshot) render(); }, 60 * 1000);
setInterval(loadSnapshot, 5 * 60 * 1000);
loadSnapshot();