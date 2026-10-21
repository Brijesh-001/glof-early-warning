// GEWS Watch Console — frontend. Every number here comes from the backend API (/api/*),
// which reads the pipeline's committed outputs; nothing is recomputed in the browser.

const BAND_LABEL = { high: "High", concern: "Concern", watch: "Watch", ok: "Low", cannot_assess: "Cannot assess" };
const SIGNALS = ["lake_area_km2", "velocity_trend", "velocity_accel", "sar_backscatter_change", "thermal_index"];
const SIGNAL_LABEL = {
  lake_area_km2: "Lake area (km²)", velocity_trend: "Glacier speed", velocity_accel: "Glacier accel.",
  sar_backscatter_change: "Radar change", thermal_index: "Thermal index",
};

const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const bandColor = (b) => css({ high: "--high", concern: "--concern", watch: "--watch", ok: "--ok" }[b] || "--abst");

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error(`${path}: ${r.status} ${await r.text()}`);
  return r.json();
}

const fmt = (v, d = 3) => (v === null || v === undefined || Number.isNaN(v)) ? "—"
  : typeof v === "number" ? (Number.isInteger(v) ? v.toLocaleString() : v.toFixed(d)) : v;
const pill = (cls, text) => `<span class="pill ${cls}">${text}</span>`;

function kpis(el, items) {
  document.getElementById(el).innerHTML = items.map(([v, l]) =>
    `<div class="kpi"><div class="v">${v}</div><div class="l">${l}</div></div>`).join("");
}

function table(el, rows, cols, opts = {}) {
  const head = `<thead><tr>${cols.map((c) => `<th>${c.label || c.key}</th>`).join("")}</tr></thead>`;
  const body = rows.map((r) => {
    const cells = cols.map((c) => `<td>${c.render ? c.render(r[c.key], r) : fmt(r[c.key], c.digits)}</td>`).join("");
    return `<tr ${opts.onClick ? `class="clickable" data-key="${r[opts.key]}"` : ""}>${cells}</tr>`;
  }).join("");
  const t = document.getElementById(el);
  t.innerHTML = head + `<tbody>${body}</tbody>`;
  if (opts.onClick) t.querySelectorAll("tr.clickable").forEach((tr) =>
    tr.addEventListener("click", () => opts.onClick(tr.dataset.key)));
}

function layout(extra = {}) {
  return Object.assign({
    paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
    font: { color: css("--ink"), size: 12 },
    margin: { l: 55, r: 20, t: 10, b: 45 },
    xaxis: { gridcolor: css("--line"), zerolinecolor: css("--line") },
    yaxis: { gridcolor: css("--line"), zerolinecolor: css("--line") },
    legend: { orientation: "h", y: -0.18 },
  }, extra);
}
// plotly.js v3 only accepts title objects, so expand any `title: "text"` shorthand;
// automargin keeps long category labels (lake / test names) from being clipped
function titles(lay) {
  for (const [k, v] of Object.entries(lay)) {
    if (!/^[xy]axis\d*$/.test(k)) continue;
    if (typeof v.title === "string") v.title = { text: v.title };
    v.automargin = true;
  }
  return lay;
}
const plot = (el, data, lay) => {
  data.forEach((t) => { if (t.colorbar && typeof t.colorbar.title === "string") t.colorbar.title = { text: t.colorbar.title }; });
  return Plotly.react(el, data, titles(layout(lay)), { responsive: true, displaylogo: false });
};

let STATE = { thresholds: { watch: 0.5, concern: 0.7, high: 0.85 } };

function thresholdShapes(axis = "y") {
  return Object.entries(STATE.thresholds).map(([b, v]) => ({
    type: "line", xref: "paper", x0: 0, x1: 1, yref: axis, y0: v, y1: v,
    line: { color: bandColor(b), width: 1, dash: "dot" },
  }));
}

// ---------------- Watch-list ----------------
async function loadWatch() {
  const [s, wl] = await Promise.all([api("/api/summary"), api("/api/watchlist")]);
  STATE.thresholds = s.thresholds;
  document.getElementById("versions").innerHTML =
    `model <b>${s.model_version}</b> · data <b>${s.data_version}</b><br>outputs updated ${s.outputs_updated.models}`;
  const b = s.latest_bands;
  kpis("watch-kpis", [
    [s.n_lakes, "lakes monitored"], [b.high, "High (≥0.85)"], [b.concern, "Concern (≥0.70)"],
    [b.watch, "Watch (≥0.50)"], [b.ok, "Low"], [b.cannot_assess, "Cannot assess"],
    [s.n_windows.toLocaleString(), `windows ${s.date_range[0]} → ${s.date_range[1]}`],
  ]);
  table("watch-table", wl, [
    { key: "lake", label: "Lake" },
    { key: "band", label: "Status", render: (v) => pill(v, BAND_LABEL[v] || v) },
    { key: "risk_score", label: "Risk", digits: 2 },
    { key: "driver", label: "Driver (why)" },
    { key: "observability", label: "Visible", render: (v) => v == null ? "—" : `${Math.round(v * 100)}%` },
    { key: "date", label: "Window" },
  ], { key: "lake", onClick: (lake) => { document.getElementById("lake-select").value = lake; loadLake(lake); } });

  const sel = document.getElementById("lake-select");
  sel.innerHTML = wl.map((r) => `<option>${r.lake}</option>`).join("");
  sel.onchange = () => loadLake(sel.value);
  sel.value = wl[0].lake;
  loadLake(wl[0].lake);
}

async function loadLake(lake) {
  const rows = await api(`/api/lakes/${lake}/scores`);
  const assessed = rows.filter((r) => r.status === "assessed");
  const abst = rows.filter((r) => r.status !== "assessed");
  plot("lake-chart", [
    { x: assessed.map((r) => r.date), y: assessed.map((r) => r.risk_score), type: "scatter", mode: "lines",
      name: "risk", line: { color: css("--muted"), width: 1 }, hoverinfo: "skip" },
    { x: assessed.map((r) => r.date), y: assessed.map((r) => r.risk_score), type: "scatter", mode: "markers",
      name: "assessed window", marker: { size: 5, color: assessed.map((r) => bandColor(r.band)) },
      text: assessed.map((r) => `${BAND_LABEL[r.band]} · ${r.driver || ""}`),
      hovertemplate: "%{x|%d %b %Y}<br>risk %{y:.2f}<br>%{text}<extra></extra>" },
    { x: abst.map((r) => r.date), y: abst.map(() => -0.04), type: "scatter", mode: "markers",
      name: "cannot assess", marker: { symbol: "line-ns-open", size: 8, color: css("--abst") },
      text: abst.map((r) => r.reason), hovertemplate: "%{x|%d %b %Y}<br>cannot assess: %{text}<extra></extra>" },
  ], { yaxis: { range: [-0.08, 1.02], title: "risk score", gridcolor: css("--line") }, shapes: thresholdShapes() });
  const last = rows[rows.length - 1];
  document.getElementById("lake-meta").innerHTML =
    `<b>${rows.length}</b> windows · <b>${assessed.length}</b> assessed · <b>${abst.length}</b> cannot assess · ` +
    `peak risk <b>${fmt(Math.max(...assessed.map((r) => r.risk_score)), 2)}</b> · last window ${last.date.slice(0, 10)}`;
}

// ---------------- Data ----------------
async function loadData() {
  const ov = await api("/api/data/overview");
  const t = ov.totals;
  kpis("data-kpis", [
    [t.lakes, "lakes in data cube"], [t.windows.toLocaleString(), "10-day windows"], [t.dem_lakes, "lakes with DEM"],
    ...SIGNALS.map((s) => [`${t.signal_coverage_pct[s]}%`, `${SIGNAL_LABEL[s]} coverage`]),
  ]);
  const lakes = ov.lakes.map((r) => r.lake);
  plot("coverage-chart", [{
    type: "heatmap", y: lakes, x: SIGNALS.map((s) => SIGNAL_LABEL[s]).concat(["Observability"]),
    z: ov.lakes.map((r) => SIGNALS.map((s) => r[`${s}_coverage_pct`]).concat([Math.round(r.mean_observability * 100)])),
    colorscale: "Blues", zmin: 0, zmax: 100, colorbar: { title: "%" },
    hovertemplate: "%{y}<br>%{x}: %{z}%<extra></extra>",
  }], { margin: { l: 140, r: 10, t: 10, b: 70 }, yaxis: { autorange: "reversed", tickfont: { size: 10 } } });

  table("dem-table", ov.dem, Object.keys(ov.dem[0] || {}).map((k) => ({ key: k, digits: 1 })));
  table("inventory-table", ov.lakes, [
    { key: "lake" }, { key: "windows" }, { key: "start" }, { key: "end" },
    { key: "mean_observability", label: "mean obs.", digits: 2 },
    ...SIGNALS.map((s) => ({ key: `${s}_coverage_pct`, label: `${SIGNAL_LABEL[s]} %`, digits: 1 })),
  ]);

  const sel = document.getElementById("data-lake-select");
  sel.innerHTML = lakes.map((l) => `<option>${l}</option>`).join("");
  sel.value = lakes.includes("south_lhonak") ? "south_lhonak" : lakes[0];
  sel.onchange = () => loadDataLake(sel.value);
  loadDataLake(sel.value);
}

async function loadDataLake(lake) {
  const d = await api(`/api/data/${lake}`);
  const x = d.windows.map((r) => r.window);
  const pal = ["#2f5fd0", "#c2185b", "#00897b", "#ef6c00", "#6a1b9a"];
  const traces = SIGNALS.map((s, i) => ({
    x, y: d.windows.map((r) => r[s]), type: "scatter", mode: "lines+markers", connectgaps: false,
    name: SIGNAL_LABEL[s], line: { color: pal[i], width: 1.2 }, marker: { size: 3 },
    xaxis: "x", yaxis: i ? `y${i + 1}` : "y",
  }));
  const axes = {};
  SIGNALS.forEach((s, i) => { axes[i ? `yaxis${i + 1}` : "yaxis"] = { title: { text: SIGNAL_LABEL[s], font: { size: 10 } }, gridcolor: css("--line") }; });
  plot("signals-chart", traces, Object.assign({ grid: { rows: 5, columns: 1, pattern: "coupled" }, showlegend: false,
    margin: { l: 70, r: 10, t: 10, b: 30 } }, axes));

  const px = d.per_signal.map((r) => r.date);
  plot("persignal-chart", SIGNALS.map((s, i) => ({
    x: px, y: d.per_signal.map((r) => r[`s_${s}`]), type: "scatter", mode: "lines",
    name: SIGNAL_LABEL[s], line: { color: pal[i], width: 1 },
  })), { yaxis: { title: "anomaly score 0–1", gridcolor: css("--line") } });

  table("stats-table", d.stats, Object.keys(d.stats[0]).map((k) => ({ key: k, digits: 3,
    render: k === "signal" ? (v) => SIGNAL_LABEL[v] || v : undefined })));
}

// ---------------- Modelling ----------------
async function loadModel() {
  const m = await api("/api/model");
  const c = m.config, bc = m.band_counts;
  const total = Object.values(bc).reduce((a, b) => a + b, 0);
  kpis("model-kpis", [
    [c.detector.replace("_", " "), "production detector"], [c.n_assessed.toLocaleString(), "windows scored"],
    [`p = ${c.p_norm}`, "fusion p-norm"],
    ...Object.entries(bc).map(([b, n]) => [`${(100 * n / total).toFixed(1)}%`, `${BAND_LABEL[b]} windows`]),
  ]);

  const det = m.detector_comparison;
  plot("detector-chart", [
    { x: det.map((r) => r.detector), y: det.map((r) => r.peak_runup_southlhonak), type: "bar", name: "peak run-up (South Lhonak)",
      marker: { color: det.map((r) => r.detector === c.detector ? css("--accent") : "#9fb3e0") }, text: det.map((r) => r.peak_runup_southlhonak), textposition: "outside" },
    { x: det.map((r) => r.detector), y: det.map((r) => r.false_alarm_pct_other_lakes), type: "scatter", mode: "lines+markers+text",
      name: "false-alarm % (other lakes)", yaxis: "y2", line: { color: css("--high") }, text: det.map((r) => `${r.false_alarm_pct_other_lakes}%`), textposition: "top center" },
  ], { yaxis: { title: "peak run-up", range: [0, 1.1], gridcolor: css("--line") },
       yaxis2: { title: "false-alarm %", overlaying: "y", side: "right", range: [0, 50], showgrid: false }, margin: { l: 55, r: 55, t: 10, b: 45 } });

  const ab = m.ablation;
  plot("ablation-chart", [{
    y: ab.map((r) => r.config.replace("drop_", "drop ").replace("all_signals", "all signals")), x: ab.map((r) => r.peak_runup),
    type: "bar", orientation: "h", text: ab.map((r) => r.peak_runup), textposition: "outside",
    marker: { color: ab.map((r) => r.config === "all_signals" ? css("--accent") : "#9fb3e0") },
  }], { xaxis: { range: [0, 1], title: "peak run-up", gridcolor: css("--line") }, margin: { l: 170, r: 30, t: 10, b: 45 } });

  const h = m.risk_histogram, mids = h.edges.slice(0, -1).map((e, i) => (e + h.edges[i + 1]) / 2);
  const bandOf = (v) => v >= c.thresholds.high ? "high" : v >= c.thresholds.concern ? "concern" : v >= c.thresholds.watch ? "watch" : "ok";
  plot("hist-chart", [{ x: mids, y: h.counts, type: "bar", marker: { color: mids.map((v) => bandColor(bandOf(v))) },
    hovertemplate: "risk %{x:.3f}<br>%{y} windows<extra></extra>" }],
    { bargap: 0.05, xaxis: { title: "risk score", gridcolor: css("--line") }, yaxis: { title: "windows", gridcolor: css("--line") } });

  plot("year-chart", ["ok", "watch", "concern", "high", "cannot_assess"].map((b) => ({
    x: m.bands_by_year.map((r) => r.year), y: m.bands_by_year.map((r) => r[b]), type: "bar", name: BAND_LABEL[b],
    marker: { color: bandColor(b) },
  })), { barmode: "stack", yaxis: { title: "windows", gridcolor: css("--line") } });

  const dr = m.top_drivers.slice().reverse();
  plot("driver-chart", [{ y: dr.map((r) => r.driver), x: dr.map((r) => r.count), type: "bar", orientation: "h", marker: { color: css("--accent") } }],
    { margin: { l: 120, r: 20, t: 10, b: 40 }, xaxis: { title: "assessed windows naming this driver", gridcolor: css("--line") } });

  plot("weights-chart", [{ x: Object.keys(c.weights).map((k) => SIGNAL_LABEL[k]), y: Object.values(c.weights), type: "bar",
    marker: { color: "#00897b" }, text: Object.values(c.weights), textposition: "outside" }],
    { yaxis: { range: [0, 0.4], title: "weight", gridcolor: css("--line") }, margin: { l: 55, r: 10, t: 10, b: 40 } });
  document.getElementById("config").innerHTML =
    `Isolation Forest: <b>${c.if_params.n_estimators}</b> trees, max_samples <b>${c.if_params.max_samples}</b>, contamination <b>${c.if_params.contamination}</b> · ` +
    `thresholds watch <b>${c.thresholds.watch}</b> / concern <b>${c.thresholds.concern}</b> / high <b>${c.thresholds.high}</b> · ` +
    `abstain if observability &lt; <b>${c.abstain.obs_floor}</b> or history &lt; <b>${c.abstain.min_history}</b> windows · spec <b>${c.spec}</b>`;

  table("abstain-table", m.abstain_reasons, [{ key: "reason" }, { key: "count" }]);
}

// ---------------- Evaluation ----------------
async function loadEval() {
  const e = await api("/api/evaluation"), r = e.report, lk = e.leak_and_generalisation;
  const lt = r.sikkim_lead_time_weeks;
  kpis("eval-kpis", [
    [lt.watch == null ? "missed" : `${lt.watch} wk`, "lead time at Watch"],
    [lt.concern == null ? "missed" : `${lt.concern} wk`, "lead time at Concern"],
    [lt.high == null ? "never" : `${lt.high} wk`, "lead time at High"],
    [r.false_alarm.watch.per_lake_year, "false alarms / lake-year (Watch)"],
    [`${r.cannot_assess.overall_pct}%`, "windows cannot assess"],
    [lk.leak_check.causal_ok ? "PASS" : "FAIL", "leak check (causal)"],
    [lk.unseen_lake[0].peak_preburst_risk_unseen, "South Lhonak peak, held out"],
  ]);

  const tr = e.sikkim_trajectory;
  const as = tr.filter((x) => x.status === "assessed");
  plot("trajectory-chart", [
    { x: as.map((x) => x.weeks_before), y: as.map((x) => x.risk_score), type: "scatter", mode: "lines+markers", name: "risk",
      marker: { color: as.map((x) => bandColor(x.band)), size: 7 }, line: { color: css("--muted") },
      text: as.map((x) => `${x.date} · ${x.driver || ""}`), hovertemplate: "%{x} wk before<br>risk %{y:.2f}<br>%{text}<extra></extra>" },
    { x: tr.filter((x) => x.status !== "assessed").map((x) => x.weeks_before), y: tr.filter((x) => x.status !== "assessed").map(() => -0.04),
      type: "scatter", mode: "markers", name: "cannot assess", marker: { symbol: "line-ns-open", size: 9, color: css("--abst") } },
  ], { xaxis: { autorange: "reversed", title: "weeks before burst (4 Oct 2023)", gridcolor: css("--line") },
       yaxis: { range: [-0.08, 1.02], title: "risk score", gridcolor: css("--line") }, shapes: thresholdShapes() });

  const sw = e.threshold_sweep;
  plot("sweep-chart", [
    { x: sw.map((x) => x.threshold), y: sw.map((x) => x.sikkim_lead_weeks), type: "scatter", mode: "lines+markers", name: "South Lhonak lead (weeks)",
      line: { color: css("--accent") }, marker: { symbol: sw.map((x) => x.sikkim_detected ? "circle" : "x"), size: 9 } },
    { x: sw.map((x) => x.threshold), y: sw.map((x) => x.control_false_alarms_per_lake_year), type: "scatter", mode: "lines+markers",
      name: "false alarms / lake-year", yaxis: "y2", line: { color: css("--high") } },
  ], { xaxis: { title: "alert threshold", gridcolor: css("--line") }, yaxis: { title: "lead time (weeks)", gridcolor: css("--line") },
       yaxis2: { title: "false alarms / lake-year", overlaying: "y", side: "right", showgrid: false }, margin: { l: 55, r: 55, t: 10, b: 45 } });

  const rows = Object.entries(r.detection).map(([b, d]) => Object.assign({ band: b }, d, r.false_alarm[b],
    { lead: lt[b] }));
  table("detection-table", rows, [
    { key: "band", label: "Band", render: (v) => pill(v, BAND_LABEL[v]) },
    { key: "detected", label: "Event detected", render: (v) => v ? `<span class="good">yes</span>` : `<span class="bad">no</span>` },
    { key: "lead", label: "Lead (wk)", digits: 1 },
    { key: "recall", label: "Recall", digits: 2 }, { key: "precision", label: "Precision", digits: 4 },
    { key: "episodes", label: "FA episodes" }, { key: "per_lake_year", label: "FA / lake-yr", digits: 2 },
    { key: "pct_windows", label: "% windows ≥ band", digits: 1 },
  ]);

  plot("fa-chart", [
    { x: rows.map((x) => BAND_LABEL[x.band]), y: rows.map((x) => x.per_lake_year), type: "bar", name: "per lake-year",
      marker: { color: rows.map((x) => bandColor(x.band)) }, text: rows.map((x) => x.per_lake_year), textposition: "outside" },
    { x: rows.map((x) => BAND_LABEL[x.band]), y: rows.map((x) => x.pct_windows), type: "scatter", mode: "lines+markers",
      name: "% of control windows", yaxis: "y2", line: { color: css("--muted") } },
  ], { yaxis: { title: "false alarms / lake-year", gridcolor: css("--line") },
       yaxis2: { title: "% windows", overlaying: "y", side: "right", showgrid: false, range: [0, 100] }, margin: { l: 55, r: 55, t: 10, b: 45 } });

  const l = lk.leak_check;
  document.getElementById("leak").innerHTML =
    `<p>Pre-event windows compared: <b>${l.pre_event_windows}</b></p>` +
    `<p>Max score difference, full history vs. truncated at the event: <b>${l.max_diff_causal.toExponential(2)}</b></p>` +
    `<p>Causal (no future data leaked backward): ${l.causal_ok ? '<span class="good">PASS</span>' : '<span class="bad">FAIL</span>'}</p>` +
    `<p>Deliberate-leak demo: using future data would shift the mean pre-event score by <b>${l.deliberate_leak_mean_shift.toFixed(3)}</b>, so the check is sensitive enough to catch a real leak.</p>`;

  const ctrl = lk.unseen_lake.filter((x) => x.role === "control"), ev = lk.unseen_lake.find((x) => x.role === "event");
  plot("unseen-chart", [{ x: ctrl.map((x) => x.lake), y: ctrl.map((x) => x.pct_windows_concern_unseen), type: "bar",
    marker: { color: "#9fb3e0" }, text: ctrl.map((x) => `${x.pct_windows_concern_unseen}%`), textposition: "outside", name: "control lakes" }],
    { yaxis: { title: "% windows ≥ Concern (held out)", gridcolor: css("--line") }, showlegend: false,
      annotations: [{ xref: "paper", yref: "paper", x: 1, y: 1, xanchor: "right", showarrow: false,
        text: `<b>${ev.lake}</b> (event, held out): peak pre-burst risk <b>${ev.peak_preburst_risk_unseen}</b>` }] });

  table("failure-table", e.failure_cases, [
    { key: "lake" }, { key: "date" }, { key: "risk_score", label: "risk", digits: 2 },
    { key: "band", render: (v) => pill(v, BAND_LABEL[v]) }, { key: "driver" },
  ]);
}

// ---------------- Testing ----------------
async function runTests() {
  const btn = document.getElementById("run-tests"), st = document.getElementById("tests-status");
  btn.disabled = true; st.textContent = "running pytest…";
  try {
    const t = await api("/api/tests/run", { method: "POST" });
    st.textContent = `finished ${new Date().toLocaleTimeString()}`;
    kpis("test-kpis", [
      [t.cases.length, "tests collected"], [`<span class="good">${t.passed}</span>`, "passed"],
      [`<span class="${t.failed ? "bad" : ""}">${t.failed}</span>`, "failed"],
      [`${t.cases.length ? Math.round(100 * t.passed / t.cases.length) : 0}%`, "pass rate"], [`${t.elapsed_s}s`, "wall time"],
    ]);
    table("tests-table", t.cases, [
      { key: "name", label: "Test" }, { key: "outcome", render: (v) => pill(v, v) },
      { key: "time", label: "ms", render: (v) => (v * 1000).toFixed(1) }, { key: "message", render: (v) => v || "" },
    ]);
    const cs = t.cases.slice().reverse();
    plot("tests-chart", [{ y: cs.map((c) => c.name.replace(/^test_/, "")), x: cs.map((c) => c.time * 1000), type: "bar", orientation: "h",
      marker: { color: cs.map((c) => c.outcome === "passed" ? css("--ok") : css("--high")) } }],
      { margin: { l: 260, r: 20, t: 10, b: 40 }, xaxis: { title: "ms", gridcolor: css("--line") } });
    document.getElementById("tests-log").textContent = t.stdout + (t.stderr ? "\n" + t.stderr : "");
  } catch (err) { st.textContent = String(err); }
  btn.disabled = false;
}

async function rerunEval() {
  const btn = document.getElementById("rerun-eval"), st = document.getElementById("rerun-status");
  btn.disabled = true; st.textContent = "running gews_evaluation.py + gews_leak_gen.py…";
  try { await api("/api/pipeline/evaluate", { method: "POST" }); st.textContent = "done, results reloaded"; await loadEval(); }
  catch (err) { st.textContent = String(err); }
  btn.disabled = false;
}

// ---------------- tabs ----------------
const loaders = { watch: loadWatch, data: loadData, model: loadModel, eval: loadEval, tests: runTests };
const loaded = {};
function show(tab) {
  document.querySelectorAll("nav button").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  document.querySelectorAll(".tab").forEach((s) => s.classList.toggle("active", s.id === `tab-${tab}`));
  if (!loaded[tab]) { loaded[tab] = true; loaders[tab]().catch((e) => alert(e)); }
  else window.dispatchEvent(new Event("resize"));
  history.replaceState(null, "", `#${tab}`);
}
document.querySelectorAll("nav button").forEach((b) => b.addEventListener("click", () => show(b.dataset.tab)));
document.getElementById("run-tests").addEventListener("click", runTests);
document.getElementById("rerun-eval").addEventListener("click", rerunEval);
show(location.hash.slice(1) in loaders ? location.hash.slice(1) : "watch");
