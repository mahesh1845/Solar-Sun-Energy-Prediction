/* SolarCast front-end: shared by index.html, dashboard.html and about.html */
const $ = (id) => document.getElementById(id);

/* ---------- safe API helper (never throws "Unexpected end of JSON") ---------- */
async function api(url, options) {
  let res;
  try {
    res = await fetch(url, options);
  } catch (e) {
    throw new Error("Cannot reach the server. Start it with:  python app.py  and open http://127.0.0.1:5000");
  }
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch (e) { /* not JSON */ }
  if (!res.ok) throw new Error((data && data.error) || `Server returned ${res.status}. Make sure you opened the app via http://127.0.0.1:5000 (not as a file).`);
  if (data === null) throw new Error("Empty response from server. Make sure app.py is running.");
  return data;
}

const fmt = (n, d = 2) => Number(n).toLocaleString(undefined, { maximumFractionDigits: d, minimumFractionDigits: d });

/* ---------- tiny canvas chart (line / bar, no libraries) ---------- */
function drawChart(canvas, labels, series, opts = {}) {
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth, h = parseInt(canvas.getAttribute("height"), 10) || 220;
  canvas.width = w * dpr; canvas.height = h * dpr;
  canvas.style.height = h + "px";
  const c = canvas.getContext("2d");
  c.scale(dpr, dpr); c.clearRect(0, 0, w, h);

  const pad = { l: 46, r: 12, t: 12, b: 30 };
  const iw = w - pad.l - pad.r, ih = h - pad.t - pad.b;
  const all = series.flatMap((s) => s.data).filter((v) => v != null);
  if (!all.length) { c.fillStyle = "#64788a"; c.font = "14px sans-serif"; c.fillText("No data yet", pad.l, h / 2); return; }
  let max = Math.max(...all, opts.minMax || 0) * 1.1 || 1, min = 0;
  const n = labels.length;
  const x = (i) => pad.l + (n === 1 ? iw / 2 : (i / (n - 1)) * iw);
  const y = (v) => pad.t + ih - ((v - min) / (max - min)) * ih;

  c.strokeStyle = "#e3ebf1"; c.fillStyle = "#64788a"; c.font = "11px sans-serif"; c.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const v = min + ((max - min) * i) / 4, yy = y(v);
    c.beginPath(); c.moveTo(pad.l, yy); c.lineTo(w - pad.r, yy); c.stroke();
    c.textAlign = "right"; c.fillText(v.toFixed(max < 10 ? 1 : 0), pad.l - 6, yy + 4);
  }
  const step = Math.max(1, Math.ceil(n / 7));
  c.textAlign = "center";
  labels.forEach((l, i) => { if (i % step === 0 || i === n - 1) c.fillText(l, x(i), h - 10); });

  series.forEach((s, si) => {
    if (s.type === "bar") {
      const bw = Math.min(40, (iw / n) * 0.6);
      c.fillStyle = s.color;
      s.data.forEach((v, i) => { const xx = n === 1 ? pad.l + iw / 2 : pad.l + ((i + 0.5) / n) * iw; c.fillRect(xx - bw / 2, y(v), bw, y(0) - y(v)); });
      return;
    }
    c.strokeStyle = s.color; c.lineWidth = 2.5; c.lineJoin = "round";
    c.beginPath();
    s.data.forEach((v, i) => (i ? c.lineTo(x(i), y(v)) : c.moveTo(x(i), y(v))));
    c.stroke();
    if (s.fill) {
      c.lineTo(x(n - 1), y(0)); c.lineTo(x(0), y(0)); c.closePath();
      c.fillStyle = s.color + "22"; c.fill();
    }
    if (n <= 30) { c.fillStyle = s.color; s.data.forEach((v, i) => { c.beginPath(); c.arc(x(i), y(v), 3, 0, 7); c.fill(); }); }
  });
}

/* ---------- Predict page ---------- */
function initPredict() {
  const btn = $("predictBtn");
  const ARC = 377; // approx. length of the gauge arc (pi * 120)
  const fill = $("gaugeFill");
  fill.style.strokeDasharray = ARC; fill.style.strokeDashoffset = ARC;
  let lastHourly = null;

  async function run() {
    $("error").textContent = "";
    btn.disabled = true; btn.textContent = "Predicting…";
    const body = {};
    ["temperature", "humidity", "irradiation", "wind_speed", "sun_hours", "tariff"].forEach((k) => (body[k] = $(k).value));
    try {
      const r = await api("/api/predict", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      $("powerVal").textContent = fmt(r.power_kw, 2);
      $("hint").textContent = `${r.performance} output · system capacity ${r.capacity_kw} kW`;
      fill.style.strokeDashoffset = ARC * (1 - Math.min(1, r.power_kw / r.capacity_kw));
      $("energy").textContent = fmt(r.energy_kwh) + " kWh";
      $("eff").textContent = fmt(r.efficiency_pct, 1) + " %";
      $("savings").textContent = "₹ " + fmt(r.savings);
      $("co2").textContent = fmt(r.co2_kg) + " kg";
      $("best").textContent = r.best_hours;
      $("perf").textContent = r.performance;
      $("rec").textContent = r.recommendation;
      $("alerts").innerHTML = r.alerts.map((a) => `<div class="alert ${a.level}">${a.text}</div>`).join("");
      $("details").hidden = false;
      lastHourly = r.hourly;
      drawHourly();
    } catch (e) {
      $("error").textContent = e.message;
    } finally {
      btn.disabled = false; btn.textContent = "Predict power";
    }
  }
  function drawHourly() {
    if (!lastHourly) return;
    drawChart($("hourChart"), lastHourly.map((h) => h.hour.slice(0, 2)), [{ data: lastHourly.map((h) => h.power_kw), color: "#f59e0b", fill: true }]);
  }
  btn.addEventListener("click", run);
  document.querySelectorAll("input").forEach((i) => i.addEventListener("keydown", (e) => e.key === "Enter" && run()));
  window.addEventListener("resize", drawHourly);
}

/* ---------- Dashboard page ---------- */
function initDashboard() {
  let history = [], analytics = null, metrics = null, tab = "daily";

  async function load() {
    try {
      [history, analytics, metrics] = await Promise.all([api("/api/history"), api("/api/analytics"), api("/api/metrics")]);
    } catch (e) { alert(e.message); return; }
    render();
  }

  function render() {
    const asc = [...history].reverse();
    const last = history[0];
    $("sPower").textContent = last ? fmt(last.power_kw) + " kW" : "—";
    $("sEnergy").textContent = history.length ? fmt(history.reduce((s, r) => s + r.energy_kwh, 0), 1) + " kWh" : "—";
    $("sEff").textContent = history.length ? fmt(history.reduce((s, r) => s + r.efficiency_pct, 0) / history.length, 1) + " %" : "—";
    $("sWeather").textContent = last ? `${fmt(last.temperature, 0)}°C · ${fmt(last.irradiation, 0)}` : "—";

    const recent = asc.slice(-30);
    const lbl = recent.map((r) => r.time.slice(5, 10));
    drawChart($("powerChart"), lbl, [{ data: recent.map((r) => r.power_kw), color: "#f59e0b", fill: true }]);
    drawChart($("weatherChart"), lbl, [
      { data: recent.map((r) => r.temperature), color: "#f59e0b" },
      { data: recent.map((r) => r.irradiation / 10), color: "#1565a8" },
    ]);
    drawAnalytics();
    drawChart($("cmpChart"), metrics.compare.map((_, i) => i + 1), [
      { data: metrics.compare.map((r) => r.actual), color: "#1565a8" },
      { data: metrics.compare.map((r) => r.predicted), color: "#f59e0b" },
    ]);

    $("metrics").innerHTML = `
      <div class="kpi"><span>Model</span><b>${metrics.model}</b></div>
      <div class="kpi"><span>R² score</span><b>${(metrics.r2 * 100).toFixed(2)} %</b></div>
      <div class="kpi"><span>MAE</span><b>${metrics.mae} kW</b></div>
      <div class="kpi"><span>RMSE</span><b>${metrics.rmse} kW</b></div>
      <div class="kpi"><span>Training rows</span><b>${metrics.train_rows}</b></div>
      <div class="kpi"><span>Test rows</span><b>${metrics.test_rows}</b></div>`;

    $("historyBody").innerHTML = history.length
      ? history.slice(0, 100).map((r) => `<tr><td>${r.time.replace("T", " ")}</td><td>${r.temperature}</td><td>${r.humidity}</td><td>${r.irradiation}</td><td>${r.wind_speed}</td><td><b>${fmt(r.power_kw)}</b></td><td>${fmt(r.energy_kwh)}</td><td>${fmt(r.efficiency_pct, 1)} %</td><td>${fmt(r.savings)}</td><td>${fmt(r.co2_kg)}</td></tr>`).join("")
      : `<tr><td colspan="10" class="empty">No predictions yet. Make one on the Predict page, or add sample data.</td></tr>`;
  }

  function drawAnalytics() {
    const rows = analytics[tab];
    drawChart($("anaChart"), rows.map((r) => r.label.slice(tab === "daily" ? 5 : 0)), [{ data: rows.map((r) => r.energy_kwh), color: "#1565a8", type: "bar" }]);
  }

  document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((x) => x.classList.remove("on"));
    t.classList.add("on"); tab = t.dataset.k; if (analytics) drawAnalytics();
  }));
  $("sampleBtn").addEventListener("click", async () => { try { await api("/api/history/sample", { method: "POST" }); load(); } catch (e) { alert(e.message); } });
  $("clearBtn").addEventListener("click", async () => { if (confirm("Delete all prediction history?")) { try { await api("/api/history", { method: "DELETE" }); load(); } catch (e) { alert(e.message); } } });
  window.addEventListener("resize", () => history && metrics && render());
  load();
}

const page = document.body.dataset.page;
if (page === "predict") initPredict();
if (page === "dashboard") initDashboard();
