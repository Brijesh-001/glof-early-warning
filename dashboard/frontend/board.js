// GEWS triage board + watch surface. All numbers come from /api/board, /api/lakes/*, /api/data/*
// and /api/evaluation, which read the pipeline's outputs. The browser only draws and filters.
(function () {
  const $ = (id) => document.getElementById(id);
  const TIERS = ["clear", "watch", "concern", "high", "regional", "cannot_assess"];
  const TIER_LABEL = { clear: "Clear", watch: "Watch", concern: "Concern", high: "High", regional: "Regional", cannot_assess: "Cannot assess" };
  const SIG = [
    { k: "lake_area_km2", label: "lake area km²", c: "#4ff0a0" }, { k: "vv_db", label: "radar VV dB", c: "#5b8cff" },
    { k: "sar_backscatter_change", label: "radar change", c: "#b48cff" }, { k: "thermal_index", label: "thermal index", c: "#ff9b3d" },
    { k: "velocity_trend", label: "glacier speed", c: "#f5c542" }, { k: "velocity_accel", label: "glacier accel.", c: "#ff4d79" },
  ];
  const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const fd = (iso) => { const [y, m, d] = iso.split("-"); return `${+d} ${MON[+m - 1]} ${y}`; };
  const col = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const tierColor = (t) => ({ high: col("--high"), concern: col("--concern"), watch: col("--watch"), regional: col("--regional"),
    clear: "#2f8a5c", cannot_assess: "#3b4652" }[t]);

  let B = null, EV = null;
  const S = { win: 0, lake: 0, mode: "triage", sig: new Set(["lake_area_km2", "sar_backscatter_change"]), timer: null, yaw: 0.65 };
  const lakeCache = {};
  let started = null;

  // ---------- imagery links ----------
  const hasXY = (l) => l.lat != null && l.lon != null;
  const coordText = (l) => (hasXY(l) ? `${l.lat.toFixed(4)}, ${l.lon.toFixed(4)}` : null);   // "lat, lon": paste into a search bar
  const zoomFor = (l) => (l.half_km != null && l.half_km <= 1 ? 15 : l.half_km != null && l.half_km <= 2 ? 14 : 13);
  function planetUrl(l, iso) {            // Planet Insights Platform browser, centred on the lake, +-2 months around the window
    const d = new Date(iso + "T00:00:00Z"), from = new Date(d - 60 * 864e5), to = new Date(Math.min(Date.now(), +d + 70 * 864e5));
    const q = (x) => encodeURIComponent(x.toISOString());
    return `https://insights.planet.com/analyze/browser/?zoom=${zoomFor(l)}&lat=${l.lat}&lng=${l.lon}&themeId=PLANET_SANDBOX&fromTime=${q(from)}&toTime=${q(to)}`;
  }
  const copernicusUrl = (l) => `https://browser.dataspace.copernicus.eu/?zoom=${zoomFor(l)}&lat=${l.lat}&lng=${l.lon}&themeId=DEFAULT-THEME`;
  function copyText(text, btn) {
    const done = () => { const o = btn.dataset.label || btn.textContent; btn.dataset.label = o; btn.textContent = "Copied \u2713"; setTimeout(() => (btn.textContent = o), 1600); };
    if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(text).then(done, () => fallback());
    else fallback();
    function fallback() { const ta = document.createElement("textarea"); ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0"; document.body.appendChild(ta); ta.select();
      try { document.execCommand("copy"); done(); } catch (e) { btn.textContent = text; } ta.remove(); }
  }

  // ---------- helpers ----------
  const tierOf = (li, wi = S.win) => TIERS[B.code[li][wi]];
  const riskOf = (li, wi = S.win) => B.risk[li][wi];
  const nSignals = (li, wi) => { const d = B.drivers[B.driver[li][wi]]; return !d || d === "—" ? 0 : d.split(" · ").length; };
  function confidence(li, wi) {
    const o = B.obs[li][wi] ?? 0, n = nSignals(li, wi);
    return o >= 0.7 && n >= 2 ? "high" : o >= 0.45 ? "medium" : "low";
  }
  const pct = (v) => (v == null ? "-" : `${Math.round(v * 100)}%`);
  const sgn = (v) => `${v >= 0 ? "+" : ""}${Math.round(v * 100)}`;
  const medianAt = (wi) => B.median[wi];

  function fitCanvas(cv, h) {
    const r = window.devicePixelRatio || 1, w = cv.clientWidth || cv.parentElement.clientWidth || 600;
    const hh = h || cv.clientHeight || 200;
    if (cv.width !== Math.round(w * r) || cv.height !== Math.round(hh * r)) { cv.width = Math.round(w * r); cv.height = Math.round(hh * r); }
    const g = cv.getContext("2d"); g.setTransform(r, 0, 0, r, 0, 0);
    return { g, w, h: hh };
  }

  // ---------- load ----------
  window.loadBoard = async function () {
    if (started) return started;
    started = (async () => {
      B = await api("/api/board");
      S.win = B.latest_idx;
      S.lake = Math.max(0, B.lakes.findIndex((l) => l.id === B.event.lake));
      const sl = $("slider"); sl.max = B.dates.length - 1; sl.value = S.win;
      $("event-label").textContent = `GLOF ${fd(B.event.date)}`.replace(/(\d+ \w+) (\d+)$/, "$1 $2");
      sl.oninput = () => { stop(); setWin(+sl.value); };
      $("latest").onclick = () => { stop(); setWin(B.latest_idx); };
      $("event").onclick = () => { stop(); setWin(winAtOrBefore(B.event.date)); selectLake(B.lakes.findIndex((l) => l.id === B.event.lake)); };
      $("play").onclick = togglePlay;
      document.querySelectorAll("#modes button").forEach((b) => b.onclick = () => {
        S.mode = b.dataset.mode; document.querySelectorAll("#modes button").forEach((x) => x.classList.toggle("on", x === b)); drawHeat(); legend();
      });
      bindCanvas(); bindRefresh();
      header(); legend(); renderAll(); await loadLakeData(); drawWorkbench(); trust();
      window.addEventListener("resize", () => redraw());
      EV = EV || (await api("/api/evaluation").catch(() => null)); trust();
    })();
    return started;
  };
  window.boardShown = function (tab) { if (B) redraw(tab); };

  // ---------- keep it current: start an update, poll it, reload when done ----------
  let pollTimer = null, sawRunning = false;
  function bindRefresh() {
    $("refresh").onclick = async () => {
      if (!confirm("Fetch the newest finished windows for every lake, re-score and re-evaluate?\nThis takes several minutes and needs the collection requirements (pip install -r requirements-collect.txt).")) return;
      const r = await fetch("/api/pipeline/update", { method: "POST" });
      if (!r.ok && r.status !== 409) { setRefresh("bad", "could not start: " + (await r.text())); return; }
      poll();
    };
    pollStatus();                                    // resume if an update is already running
  }
  function setRefresh(cls, text, busy) {
    const s = $("refresh-status"); s.className = cls; s.textContent = text;
    $("refresh").disabled = !!busy; $("refresh").classList.toggle("spin", !!busy);
  }
  function poll() { if (!pollTimer) pollTimer = setInterval(pollStatus, 3000); pollStatus(); }
  async function pollStatus() {
    let s; try { s = await (await fetch("/api/pipeline/update/status")).json(); } catch (e) { return; }
    if (s.state === "running") {
      sawRunning = true;
      setRefresh("run", `updating since ${s.started.slice(11)} · ${s.stage || "starting"}`, true);
      if (!pollTimer) pollTimer = setInterval(pollStatus, 3000);
    } else {
      if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
      if (s.state === "done") { setRefresh("ok", `updated ${s.finished}`, false); if (sawRunning) { sawRunning = false; await reloadAll(); } }
      else if (s.state === "failed") setRefresh("bad", `update failed (exit ${s.returncode}): ${(s.tail.filter((x) => x.trim()).slice(-1)[0] || "").slice(0, 160)}`, false);
      else setRefresh("", "", false);
    }
  }
  async function reloadAll() {
    const lakeId = B.lakes[S.lake].id;
    B = await api("/api/board"); layout3d = null;
    Object.keys(lakeCache).forEach((k) => delete lakeCache[k]);
    EV = await api("/api/evaluation").catch(() => EV);
    S.win = B.latest_idx; S.lake = Math.max(0, B.lakes.findIndex((l) => l.id === lakeId));
    const sl = $("slider"); sl.max = B.dates.length - 1; sl.value = S.win;
    header(); legend(); renderAll(); await loadLakeData(); drawWorkbench(); trust();
  }

  function winAtOrBefore(iso) { let k = 0; B.dates.forEach((d, i) => { if (d <= iso) k = i; }); return k; }

  function header() {
    const m = B.meta, behind = m.n_behind, cur = m.n_current;
    $("h-n").textContent = m.n_lakes;
    const chip = (cls, t) => `<span class="chip ${cls}">${t}</span>`;
    $("chips").innerHTML = [
      chip("", `learned from ${m.learned_from}`), chip("", `newest window ends ${fd(m.newest_window_end)}`),
      chip("good", `refreshed ${m.refreshed}`),
      chip(cur < m.n_lakes ? "warn" : "good", `${cur} / ${m.n_lakes} lakes current for the window starting ${fd(m.newest_window)}`),
      behind ? chip("warn", `${behind} behind or failed`) : "",
      chip(m.days_behind > 20 ? "warn" : "", `feed ${m.days_behind} d behind`), chip("", `model: ${m.model}`),
      m.fetch ? `<span class="chip ${m.fetch.failed.length ? "warn" : "good"}" title="${m.fetch.failed.map((x) => x.lake + ": " + x.error).join("&#10;").replace(/"/g, "'")}">last fetch ${(m.fetch.finished || "").slice(0, 16).replace("T", " ")} · ${m.fetch.failed.length ? m.fetch.failed.length + " lake(s) failed or without coordinates" : "all lakes ok"}</span>` : "",
    ].join("");
  }

  function legend() {
    const sw = (c, t, cls = "") => `<span class="${cls}" style="--c:${c}">${t}</span>`;
    const th = B.thresholds;
    $("heat-legend").innerHTML = S.mode === "triage"
      ? [sw(col("--high"), `High ≥${th.high}`), sw(col("--concern"), `Concern ≥${th.concern}`), sw(col("--watch"), `Watch ≥${th.watch}`),
         sw(col("--regional"), "Regional (discounted)"), sw("#2f8a5c", "Clear"), sw("", "Cannot assess", "hatch"), sw("#fff", "recorded outburst")].join("")
      : S.mode === "risk"
        ? [sw("#143d2a", "0.0"), sw(col("--watch"), "0.5"), sw(col("--concern"), "0.7"), sw(col("--high"), "1.0"), sw("", "Cannot assess", "hatch")].join("")
        : [sw("#3b6fd6", "calmer than peers"), sw("#1b2733", "same as fleet median"), sw(col("--high"), "higher than peers"), sw("", "Cannot assess", "hatch")].join("");
    $("surf-legend").innerHTML = [sw(col("--high"), "High"), sw(col("--concern"), "Concern"), sw(col("--watch"), "Watch"),
      sw(col("--regional"), "Regional"), sw("#2f8a5c", "Clear"), sw("", "Cannot assess", "hatch")].join("");
  }

  // ---------- state changes ----------
  function setWin(i) { S.win = Math.max(0, Math.min(B.dates.length - 1, i)); $("slider").value = S.win; renderAll(); }
  async function selectLake(li) { S.lake = li; renderAll(); await loadLakeData(); drawWorkbench(); }
  function togglePlay() {
    if (S.timer) return stop();
    if (S.win >= B.dates.length - 1) setWin(0);
    $("play").innerHTML = "&#10074;&#10074; Pause";
    S.timer = setInterval(() => { if (S.win >= B.dates.length - 1) return stop(); setWin(S.win + 1); }, 80);
  }
  function stop() { if (S.timer) { clearInterval(S.timer); S.timer = null; } $("play").innerHTML = "&#9654; Play"; }

  function activeTab() { const b = document.querySelector("nav button.active"); return b ? b.dataset.tab : "board"; }
  function redraw(tab) { renderAll(tab || activeTab()); }

  function renderAll(tab) {
    tab = tab || activeTab();
    const iso = B.dates[S.win];
    $("when").firstChild.textContent = fd(iso);
    const mo = +iso.slice(5, 7); $("season").textContent = mo >= 6 && mo <= 9 ? "MONSOON WINDOW" : "DRY-SEASON WINDOW";
    $("surf-when").textContent = fd(iso);
    if (tab === "board") { kpis(); queue(); lakeCard(); sideGroups(); drawHeat(); drawWorkbench(); }
    if (tab === "surface") { draw3D(); rank(); }
  }

  // ---------- KPI cards ----------
  function counts(wi = S.win) {
    const c = Object.fromEntries(TIERS.map((t) => [t, 0]));
    B.lakes.forEach((_, li) => c[tierOf(li, wi)]++);
    return c;
  }
  function kpis() {
    const c = counts(), th = B.thresholds, rs = Math.round(B.regional_share * 100);
    const card = (t, title, v, d) => `<div class="kpi c-${t}"><div class="t">${title}</div><div class="v">${v}</div><div class="l">${d}</div></div>`;
    $("board-kpis").innerHTML = [
      card("high", "Look at imagery now", c.high, `high · ≥${th.high}, about the top 1% of calm-lake windows`),
      card("concern", "Look this window", c.concern, `concern · ≥${th.concern}, about the top 3%`),
      card("watch", "Keep an eye", c.watch, `watch · ≥${th.watch}, about the top 10%; weak evidence on its own`),
      card("regional", "Discounted (regional)", c.regional, `high or concern, but ${rs}%+ of lakes are at Concern at once`),
      card("cannot_assess", "Cannot assess", c.cannot_assess, "no usable reading (cloud, no data, short history). Never shown as clear"),
      card("clear", "Clear", c.clear, `assessed, below ${th.watch}, nothing unusual`),
    ].join("");
  }

  // ---------- attention queue ----------
  const PRIORITY = { high: 3, concern: 2, watch: 1 };
  function riskBar(li, wi) {
    const r = riskOf(li, wi), t = B.thresholds, m = medianAt(wi), c = tierColor(tierOf(li, wi));
    return `<div class="bar"><i style="width:${(r ?? 0) * 100}%;background:${c}"></i>` +
      [t.watch, t.concern, t.high].map((v) => `<u style="left:${v * 100}%"></u>`).join("") +
      (m != null ? `<em style="left:${m * 100}%"></em>` : "") + `</div>`;
  }
  function queue() {
    const rows = [];
    B.lakes.forEach((l, li) => { const t = tierOf(li); if (PRIORITY[t]) rows.push([li, t]); });
    rows.sort((a, b) => PRIORITY[b[1]] - PRIORITY[a[1]] || riskOf(b[0]) - riskOf(a[0]));
    $("q-count").textContent = `${rows.length} to review`;
    const m = medianAt(S.win);
    $("queue").innerHTML = rows.length ? rows.map(([li, t]) => {
      const r = riskOf(li), gap = m == null ? "" : `${sgn(r - m)} vs peers`;
      return `<div class="qrow t-${t} ${li === S.lake ? "sel" : ""}" data-li="${li}">
        <div><span class="n">${B.lakes[li].name}</span> <span class="pill ${t}">${TIER_LABEL[t]}</span></div>
        <div class="rk" style="color:${tierColor(t)}">${pct(r)}</div>
        <div class="s">${B.lakes[li].region} · ${B.lakes[li].id}</div><div class="gap">${gap}</div>${riskBar(li, S.win)}</div>`;
    }).join("") : `<div class="empty"><b>Nothing stands out from its peers this window.</b>
      That is a statement about unusualness only, not a guarantee that every lake is safe.</div>`;
    $("queue").querySelectorAll(".qrow").forEach((el) => el.onclick = () => selectLake(+el.dataset.li));
  }

  function whyList(li, wi) {
    const out = [], r = riskOf(li, wi), m = medianAt(wi), t = tierOf(li, wi);
    if (t === "cannot_assess") {
      const why = B.reasons[B.reason[li][wi]] || "no usable reading";
      return [`Cannot assess: ${why}.`, "A missing reading is not evidence of safety. Check the lake by other means."];
    }
    out.push(`Risk ${pct(r)} against this lake's own 2017-2024 history` + (m != null ? `; fleet median ${pct(m)} (${sgn(r - m)} points vs peers)` : ""));
    const d = B.drivers[B.driver[li][wi]];
    out.push(d && d !== "—" ? `Driven by: ${d}` : "No single signal stands out");
    out.push(`Visibility ${pct(B.obs[li][wi])} · ${nSignals(li, wi)} of 5 signals contributed`);
    if (t === "regional") out.push(`Discounted: ${pct(B.share_concern[wi])} of assessed lakes are at Concern or above at once, so this looks regional or seasonal.`);
    if (t === "clear") out.push("Within the normal range for this lake and its peers.");
    return out;
  }
  function lakeCard() {
    const li = S.lake, l = B.lakes[li], t = tierOf(li), conf = t === "cannot_assess" ? "" : confidence(li);
    const xy = hasXY(l), iso = B.dates[S.win];
    $("lakecard").innerHTML = `<div class="lakecard t-${t}"><div class="hd"><h3>${l.name}</h3><span class="pill ${t}">${TIER_LABEL[t]}</span>` +
      (conf ? `<span class="pill conf ${conf === "high" ? "" : conf === "medium" ? "med" : "low"}">confidence ${conf}</span>` : "") +
      (l.id === B.event.lake ? `<span class="pill high">event</span>` : "") +
      `</div><div class="s" style="color:var(--dim);font:11px var(--mono);margin-top:2px">${l.region} · ${l.id}` +
      (xy ? ` · <span title="seed point, latitude then longitude">${coordText(l)}</span>` : ` · no coordinates on file`) + `</div>` +
      (t === "cannot_assess" ? "" : riskBar(li, S.win).replace('class="bar"', 'class="bar" style="margin:10px 0 2px"')) +
      `<ul>${whyList(li, S.win).map((x) => `<li>${x}</li>`).join("")}</ul>` +
      `<div class="acts">` +
      (xy ? `<a class="btn sm primary" target="_blank" rel="noopener" href="${planetUrl(l, iso)}" title="Opens Planet Insights Platform centred on this lake, around ${fd(iso)}. Needs a Planet login.">Open imagery &#8599;</a>` +
            `<button class="btn sm" id="lc-copy" title="Copies 'latitude, longitude' to paste into any map search bar">Copy coords</button>` +
            `<a class="btn sm" target="_blank" rel="noopener" href="${copernicusUrl(l)}" title="Free Copernicus Browser (Sentinel-2) at the same spot">Copernicus &#8599;</a>`
          : `<button class="btn sm" disabled title="This lake has no coordinates in data/lake_coordinates.csv">Open imagery</button><button class="btn sm" disabled>Copy coords</button>`) +
      `<button class="btn sm" id="lc-wb">Open workbench</button></div></div>`;
    $("lc-wb").onclick = () => $("workbench").scrollIntoView();
    if (xy) $("lc-copy").onclick = (e) => copyText(coordText(l), e.target);
  }
  function sideGroups() {
    const g = { regional: [], cannot_assess: [], clear: [] };
    B.lakes.forEach((l, li) => { const t = tierOf(li); if (g[t]) g[t].push(li); });
    const chips = (arr, cls) => arr.map((li) => `<span class="mini ${cls}" data-li="${li}">${B.lakes[li].name}${riskOf(li) != null ? " " + pct(riskOf(li)) : ""}</span>`).join("");
    $("sidegroups").innerHTML =
      `<div class="s" style="color:var(--dim);font:10.5px var(--mono);letter-spacing:.08em;margin-bottom:4px">DISCOUNTED, HIGH BUT REGIONAL (${g.regional.length})</div><div class="chiprow">${chips(g.regional, "regional") || '<span class="hint">none</span>'}</div>` +
      `<div class="s" style="color:var(--dim);font:10.5px var(--mono);letter-spacing:.08em;margin-bottom:4px">CANNOT ASSESS (${g.cannot_assess.length})</div><div class="chiprow">${chips(g.cannot_assess, "") || '<span class="hint">none</span>'}</div>` +
      `<div class="s" style="color:var(--dim);font:10.5px var(--mono);letter-spacing:.08em;margin-bottom:4px">CLEAR (${g.clear.length})</div><div class="chiprow">${chips(g.clear, "") || '<span class="hint">none</span>'}</div>`;
    $("sidegroups").querySelectorAll(".mini").forEach((el) => el.onclick = () => selectLake(+el.dataset.li));
  }

  // ---------- heatmap ----------
  const LEFT = 128, STRIP = 46, ROW = 11, RHEAD = 17;
  function rowsLayout() {
    const rows = []; let last = null, y = STRIP + 10;
    B.lakes.forEach((l, li) => {
      if (l.region !== last) { rows.push({ head: l.region, y }); y += RHEAD; last = l.region; }
      rows.push({ li, y }); y += ROW;
    });
    return { rows, h: y + 6 };
  }
  const lerp = (a, b, t) => a + (b - a) * t;
  const hex = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
  function ramp(stops, v) {
    for (let i = 1; i < stops.length; i++) if (v <= stops[i][0]) {
      const [a, ca] = [stops[i - 1][0], hex(stops[i - 1][1])], [b, cb] = [stops[i][0], hex(stops[i][1])], t = (v - a) / (b - a || 1);
      return `rgb(${ca.map((x, k) => Math.round(lerp(x, cb[k], t))).join(",")})`;
    }
    return stops[stops.length - 1][1];
  }
  const RISK_RAMP = [[0, "#143d2a"], [0.5, "#f5c542"], [0.7, "#ff9b3d"], [1, "#ff4d79"]];
  const PEER_RAMP = [[-0.5, "#3b6fd6"], [0, "#1b2733"], [0.5, "#ff4d79"]];
  function cellColor(li, wi) {
    const code = B.code[li][wi];
    if (code === 5) return null;
    if (S.mode === "triage") return tierColor(TIERS[code]);
    const r = B.risk[li][wi];
    if (S.mode === "risk") return ramp(RISK_RAMP, r);
    const m = B.median[wi]; return ramp(PEER_RAMP, Math.max(-0.5, Math.min(0.5, r - (m ?? r))));
  }
  function drawHeat() {
    const cv = $("heat"), { rows, h } = rowsLayout(), { g, w } = fitCanvas(cv, h);
    g.clearRect(0, 0, w, h);
    const n = B.dates.length, cw = (w - LEFT - 6) / n, x0 = LEFT;
    // top strip: share at/above Concern
    g.fillStyle = "#0a1017"; g.fillRect(x0, 0, w - LEFT - 6, STRIP);
    for (let i = 0; i < n; i++) {
      const s = B.share_concern[i]; if (s == null) continue;
      g.fillStyle = s >= B.regional_share ? col("--regional") : "#4a6a86"; const bh = s * (STRIP - 4);
      g.fillRect(x0 + i * cw, STRIP - bh, Math.ceil(cw), bh);
    }
    g.setLineDash([3, 3]); g.strokeStyle = "#8aa0b3"; g.beginPath();
    const ty = STRIP - B.regional_share * (STRIP - 4); g.moveTo(x0, ty); g.lineTo(w - 6, ty); g.stroke(); g.setLineDash([]);
    g.font = "10px " + col("--mono"); g.fillStyle = col("--dim"); g.textBaseline = "top";
    g.fillText("lakes at Concern+", 0, 4); g.fillText(`${Math.round(B.regional_share * 100)}% = regional`, 0, 16);
    // rows
    rows.forEach((r) => {
      if (r.head) { g.fillStyle = "#8ea1b3"; g.font = "600 10px " + col("--mono"); g.textBaseline = "middle"; g.fillText(r.head.toUpperCase(), 0, r.y + RHEAD / 2 + 2); return; }
      const sel = r.li === S.lake;
      g.font = (sel ? "700 " : "") + "10px " + col("--mono"); g.textBaseline = "middle"; g.fillStyle = sel ? col("--accent") : "#9fb0bf";
      g.fillText(B.lakes[r.li].name.slice(0, 18), 8, r.y + ROW / 2);
      for (let i = 0; i < n; i++) {
        const c = cellColor(r.li, i), x = x0 + i * cw;
        if (c) { g.fillStyle = c; g.fillRect(x, r.y, Math.ceil(cw), ROW - 1); }
        else { g.fillStyle = "#171f27"; g.fillRect(x, r.y, Math.ceil(cw), ROW - 1); if (i % 2 === 0) { g.fillStyle = "#2a3540"; g.fillRect(x, r.y, 1, ROW - 1); } }
      }
      if (sel) { g.strokeStyle = col("--accent"); g.lineWidth = 1; g.strokeRect(x0 - 0.5, r.y - 0.5, w - LEFT - 5, ROW); }
    });
    // event marker + cursor + years
    const ev = B.lakes.findIndex((l) => l.id === B.event.lake), er = rows.find((r) => r.li === ev), ei = winAtOrBefore(B.event.date);
    if (er) { g.fillStyle = "#fff"; g.beginPath(); g.arc(x0 + ei * cw + cw / 2, er.y + ROW / 2 - 0.5, 3, 0, 7); g.fill(); }
    g.strokeStyle = "rgba(255,255,255,.85)"; g.lineWidth = 1; g.beginPath(); g.moveTo(x0 + S.win * cw + cw / 2, 0); g.lineTo(x0 + S.win * cw + cw / 2, h - 6); g.stroke();
    g.fillStyle = col("--dim"); g.textBaseline = "bottom"; g.font = "10px " + col("--mono");
    B.dates.forEach((d, i) => { if (d.slice(5, 7) === "01" && (i === 0 || B.dates[i - 1].slice(0, 4) !== d.slice(0, 4))) g.fillText(d.slice(0, 4), x0 + i * cw, h + 2); });
  }
  function heatPick(ev) {
    const cv = $("heat"), r = cv.getBoundingClientRect(), x = ev.clientX - r.left, y = ev.clientY - r.top;
    const n = B.dates.length, cw = (r.width - LEFT - 6) / n, wi = Math.floor((x - LEFT) / cw);
    const row = rowsLayout().rows.find((q) => q.li != null && y >= q.y && y < q.y + ROW);
    return { wi: wi >= 0 && wi < n ? wi : null, li: row ? row.li : null };
  }

  // ---------- workbench ----------
  async function loadLakeData() {
    const id = B.lakes[S.lake].id;
    if (!lakeCache[id]) {
      const [scores, data] = await Promise.all([api(`/api/lakes/${id}/scores`), api(`/api/data/${id}`)]);
      const idx = new Map(B.dates.map((d, i) => [d, i])), sig = {};
      SIG.forEach((s) => { sig[s.k] = new Array(B.dates.length).fill(null); });
      data.windows.forEach((w) => { const i = idx.get(String(w.window).slice(0, 10)); if (i != null) SIG.forEach((s) => { sig[s.k][i] = w[s.k]; }); });
      lakeCache[id] = { sig, stats: data.stats };
    }
  }
  const WB = { l: 40, r: 10, t: 12, b: 20 };
  function drawWorkbench() {
    if (activeTab() !== "board") return;
    const li = S.lake, l = B.lakes[li], t = tierOf(li);
    $("wb-name").textContent = l.name; $("wb-pill").innerHTML = `<span class="pill ${t}">${TIER_LABEL[t]}</span>`;
    const assessed = B.risk[li].filter((v) => v != null), peak = assessed.length ? Math.max(...assessed) : null;
    $("wb-meta").innerHTML = `${l.region} · ${l.id}${hasXY(l) ? " · " + coordText(l) : ""} · ${assessed.length} assessed of ${B.dates.length} windows · peak <b>${pct(peak)}</b>`;
    const cv = $("wb-risk"), { g, w, h } = fitCanvas(cv, 250); g.clearRect(0, 0, w, h);
    const n = B.dates.length, px = (i) => WB.l + (i / (n - 1)) * (w - WB.l - WB.r), py = (v) => WB.t + (1 - v) * (h - WB.t - WB.b);
    // abstain shading
    for (let i = 0; i < n; i++) if (B.code[li][i] === 5) { g.fillStyle = "rgba(107,117,128,.16)"; g.fillRect(px(i) - 1, WB.t, 2.2, h - WB.t - WB.b); }
    // regional windows
    for (let i = 0; i < n; i++) if (B.code[li][i] === 4) { g.fillStyle = "rgba(76,195,217,.10)"; g.fillRect(px(i) - 1, WB.t, 2.2, h - WB.t - WB.b); }
    g.font = "10px " + col("--mono"); g.textBaseline = "middle"; g.lineWidth = 1;
    [["high", B.thresholds.high], ["concern", B.thresholds.concern], ["watch", B.thresholds.watch], [null, 0], [null, 1]].forEach(([k, v]) => {
      g.strokeStyle = k ? tierColor(k) : "#1e2a36"; g.setLineDash(k ? [4, 4] : []); g.globalAlpha = k ? 0.7 : 1;
      g.beginPath(); g.moveTo(WB.l, py(v)); g.lineTo(w - WB.r, py(v)); g.stroke(); g.globalAlpha = 1; g.setLineDash([]);
      g.fillStyle = k ? tierColor(k) : "#566574"; g.fillText(v.toFixed(2), 4, py(v));
    });
    // fleet median
    g.strokeStyle = "#5b8cff"; g.setLineDash([2, 3]); g.beginPath(); let pen = false;
    B.median.forEach((v, i) => { if (v == null) { pen = false; return; } pen ? g.lineTo(px(i), py(v)) : g.moveTo(px(i), py(v)); pen = true; });
    g.stroke(); g.setLineDash([]);
    // lake risk
    g.strokeStyle = col("--accent"); g.lineWidth = 1.4; g.beginPath(); pen = false;
    B.risk[li].forEach((v, i) => { if (v == null) { pen = false; return; } pen ? g.lineTo(px(i), py(v)) : g.moveTo(px(i), py(v)); pen = true; });
    g.stroke(); g.lineWidth = 1;
    B.risk[li].forEach((v, i) => { const tt = TIERS[B.code[li][i]]; if (v != null && (tt === "high" || tt === "concern")) { g.fillStyle = tierColor(tt); g.beginPath(); g.arc(px(i), py(v), 2.2, 0, 7); g.fill(); } });
    // years + event
    g.fillStyle = "#566574"; g.textBaseline = "top";
    B.dates.forEach((d, i) => { if (d.slice(5, 7) === "01" && (i === 0 || B.dates[i - 1].slice(0, 4) !== d.slice(0, 4))) g.fillText(d.slice(0, 4), px(i), h - WB.b + 5); });
    const ei = winAtOrBefore(B.event.date);
    if (l.id === B.event.lake) {
      g.strokeStyle = "#fff"; g.setLineDash([2, 3]); g.beginPath(); g.moveTo(px(ei), WB.t); g.lineTo(px(ei), h - WB.b); g.stroke(); g.setLineDash([]);
      g.fillStyle = "#fff"; g.fillText(`GLOF ${fd(B.event.date)}`, Math.min(px(ei) + 4, w - 130), WB.t + 2);
    }
    g.strokeStyle = "rgba(255,255,255,.85)"; g.beginPath(); g.moveTo(px(S.win), WB.t); g.lineTo(px(S.win), h - WB.b); g.stroke();
    cv._geom = { px, py, n, w, h }; drawSignals(); wbFoot(); chips();
  }
  function drawSignals() {
    const cv = $("wb-sig"), { g, w, h } = fitCanvas(cv, 110); g.clearRect(0, 0, w, h);
    const n = B.dates.length, px = (i) => WB.l + (i / (n - 1)) * (w - WB.l - WB.r), data = lakeCache[B.lakes[S.lake].id];
    if (!data) return;
    g.fillStyle = "#566574"; g.font = "10px " + col("--mono"); g.textAlign = "right"; g.fillText("each signal scaled to its own range", w - WB.r, 10); g.textAlign = "left";
    SIG.filter((s) => S.sig.has(s.k)).forEach((s) => {
      const v = data.sig[s.k], vals = v.filter((x) => x != null); if (!vals.length) return;
      const lo = Math.min(...vals), hi = Math.max(...vals), sp = hi - lo || 1;
      g.strokeStyle = s.c; g.lineWidth = 1.2; g.beginPath(); let pen = false;
      v.forEach((x, i) => { if (x == null) { pen = false; return; } const y = 16 + (1 - (x - lo) / sp) * (h - 24); pen ? g.lineTo(px(i), y) : g.moveTo(px(i), y); pen = true; });
      g.stroke();
    });
    g.strokeStyle = "rgba(255,255,255,.6)"; g.lineWidth = 1; g.beginPath(); g.moveTo(px(S.win), 14); g.lineTo(px(S.win), h - 6); g.stroke();
  }
  function chips() {
    $("sigchips").innerHTML = SIG.map((s) => `<span class="mini ${S.sig.has(s.k) ? "on" : ""}" data-k="${s.k}" style="${S.sig.has(s.k) ? `background:${s.c};border-color:${s.c}` : `color:${s.c}`}">${s.label}</span>`).join("");
    $("sigchips").querySelectorAll(".mini").forEach((el) => el.onclick = () => { S.sig.has(el.dataset.k) ? S.sig.delete(el.dataset.k) : S.sig.add(el.dataset.k); chips(); drawSignals(); });
  }
  function wbFoot() {
    const li = S.lake, wi = S.win, t = tierOf(li, wi), data = lakeCache[B.lakes[li].id];
    const o = B.obs[li][wi], r = riskOf(li, wi);
    const sig = (k) => { const v = data?.sig[k]?.[wi]; return v == null ? "no reading" : Number(v).toFixed(k === "lake_area_km2" ? 3 : 2); };
    $("wbfoot").innerHTML =
      `<div><h4>Selected window</h4><b>${fd(B.dates[wi])}</b><br>${r == null ? "cannot assess" : `risk ${pct(r)}`} · <span class="pill ${t}">${TIER_LABEL[t]}</span></div>` +
      `<div><h4>Contributing signals</h4>${t === "cannot_assess" ? "none, abstained" : B.drivers[B.driver[li][wi]] || "none"}<br><span class="hint">${nSignals(li, wi)} of 5 signals</span></div>` +
      `<div><h4>Observability</h4>${pct(o)} of the lake visible<div class="obsbar"><i style="width:${(o ?? 0) * 100}%"></i></div><span class="hint">abstains below 30 %</span></div>` +
      `<div><h4>Raw readings</h4>area ${sig("lake_area_km2")} km² · VV ${sig("vv_db")} dB<br>thermal ${sig("thermal_index")} · radar change ${sig("sar_backscatter_change")}</div>`;
  }

  // ---------- trust + volume ----------
  function trust() {
    if (!EV) { $("trust").innerHTML = '<span class="hint">evaluation outputs not available</span>'; return; }
    const r = EV.report, lt = r.sikkim_lead_time_weeks, d = r.detection, ev = EV.leak_and_generalisation.unseen_lake.find((x) => x.role === "event");
    const row = (b) => `<tr><td><span class="pill ${b}">${TIER_LABEL[b]}</span></td><td>${d[b].detected ? '<span class="good">yes</span>' : '<span class="bad">no</span>'}</td>` +
      `<td>${lt[b] == null ? "-" : lt[b] + " wk"}</td><td>${r.false_alarm[b].per_lake_year}</td><td>${r.false_alarm[b].pct_windows}%</td></tr>`;
    $("trust").innerHTML = `<p style="margin-top:0"><b>South Lhonak, ${fd(r.event_date)}</b>: held-out run peaked at <b>${ev ? Number(ev.peak_preburst_risk_unseen).toFixed(2) : "-"}</b> before the burst.
      The High tier ${d.high.detected ? "was reached" : "<b>was never reached</b>"}; Concern was reached <b>${lt.concern ?? "-"} weeks</b> ahead.</p>
      <div class="table-wrap short"><table><thead><tr><th>Tier</th><th>Event seen</th><th>Lead</th><th>False alarms / lake-yr</th><th>% of windows</th></tr></thead><tbody>${["watch", "concern", "high"].map(row).join("")}</tbody></table></div>
      <p class="hint" style="margin-bottom:0">One event shows detection only, not prediction. A typical control lake sits at or above Watch in ${r.false_alarm.watch.pct_windows}% of windows, so an earlier flag would not by itself prove early warning.</p>`;
    const rows = ["watch", "concern", "high"].map((b) => [b, r.false_alarm[b]]);
    $("volume").innerHTML = `<thead><tr><th>Tier</th><th>Episodes</th><th>Per lake-year</th><th>% of windows</th></tr></thead><tbody>` +
      rows.map(([b, f]) => `<tr><td><span class="pill ${b}">${TIER_LABEL[b]}</span></td><td>${f.episodes}</td><td>${f.per_lake_year}</td><td>${f.pct_windows}%</td></tr>`).join("") +
      `<tr><td><span class="pill cannot_assess">Cannot assess</span></td><td>-</td><td>-</td><td>${r.cannot_assess.overall_pct}%</td></tr></tbody>`;
    $("volume-note").textContent = `Across ${r.n_controls} control lakes and ${r.false_alarm.watch.lake_years} lake-years. Monsoon: ${r.cannot_assess.monsoon_pct}% cannot assess, dry season: ${r.cannot_assess.dry_pct}%.`;
  }

  // ---------- rank table + 3D surface ----------
  function spark(li, wi) {
    const a = []; for (let i = Math.max(0, wi - 8); i <= wi; i++) a.push(B.risk[li][i]);
    const pts = a.map((v, i) => v == null ? null : `${(i / 8) * 80 + 2},${20 - v * 18}`).filter(Boolean);
    return `<svg class="spark" viewBox="0 0 84 22"><polyline fill="none" stroke="${tierColor(tierOf(li, wi))}" stroke-width="1.5" points="${pts.join(" ")}"/></svg>`;
  }
  function rank() {
    const rows = B.lakes.map((l, li) => ({ li, t: tierOf(li), r: riskOf(li) }))
      .sort((a, b) => (a.t === "cannot_assess") - (b.t === "cannot_assess") || (b.r ?? -1) - (a.r ?? -1));
    const as = rows.filter((x) => x.t !== "cannot_assess").length;
    $("rank-count").textContent = `${as} assessed · ${rows.length - as} abstaining`;
    $("rank").innerHTML = `<thead><tr><th>#</th><th>Lake</th><th>Risk</th><th>Status</th><th>90-day trace</th></tr></thead><tbody>` +
      rows.map((x, i) => `<tr class="clickable ${x.li === S.lake ? "sel" : ""}" data-li="${x.li}"><td>${String(i + 1).padStart(2, "0")}</td>` +
        `<td><b>${B.lakes[x.li].name}</b>${B.lakes[x.li].id === B.event.lake ? ' <span class="pill high">event</span>' : ""}<br><span class="hint" style="font:10px var(--mono)">${B.lakes[x.li].region}</span></td>` +
        `<td style="font:700 13px var(--mono);color:${tierColor(x.t)}">${x.r == null ? "-" : pct(x.r)}</td>` +
        `<td><span class="pill ${x.t}">${TIER_LABEL[x.t]}</span></td><td>${spark(x.li, S.win)}</td></tr>`).join("") + "</tbody>";
    $("rank").querySelectorAll("tr.clickable").forEach((tr) => tr.onclick = () => { S.lake = +tr.dataset.li; renderAll(); });
  }

  let layout3d = null, tops = [];
  function place() {                       // x = longitude, y = latitude (north at the back), same degrees per unit on both axes
    if (layout3d) return layout3d;
    const have = B.lakes.filter(hasXY), lons = have.map((l) => l.lon), lats = have.map((l) => l.lat);
    const lonC = (Math.min(...lons) + Math.max(...lons)) / 2, latC = (Math.min(...lats) + Math.max(...lats)) / 2;
    const k = 2 / (Math.max(...lons) - Math.min(...lons) + 0.6);
    const regionMid = {};
    B.lakes.forEach((l) => { if (hasXY(l)) { const r = (regionMid[l.region] = regionMid[l.region] || { x: 0, y: 0, n: 0 }); r.x += l.lon; r.y += l.lat; r.n++; } });
    layout3d = {};
    B.lakes.forEach((l, li) => {
      if (hasXY(l)) layout3d[li] = [(l.lon - lonC) * k, -(l.lat - latC) * k];
      else { const r = regionMid[l.region]; layout3d[li] = r ? [(r.x / r.n - lonC) * k + 0.04, -(r.y / r.n - latC) * k + 0.04] : [0, 0]; }   // no coordinates: beside its region
    });
    return layout3d;
  }
  function draw3D() {
    const cv = $("surf"), { g, w, h } = fitCanvas(cv, 470); g.clearRect(0, 0, w, h);
    const cy_ = Math.cos(S.yaw), sy_ = Math.sin(S.yaw), sc = Math.min(w * 0.36, 300), cx = w / 2, cy = h * 0.62, Z = h * 0.46;
    const P = (x, y, z) => { const xr = x * cy_ - y * sy_, yr = x * sy_ + y * cy_; return [cx + xr * sc, cy + yr * sc * 0.48 - z * Z, yr]; };
    g.strokeStyle = "rgba(79,240,160,.18)"; g.lineWidth = 1;
    for (let i = -10; i <= 10; i++) {
      const v = i / 10 * 1.05; let a = P(v, -1.05, 0), b = P(v, 1.05, 0); g.beginPath(); g.moveTo(a[0], a[1]); g.lineTo(b[0], b[1]); g.stroke();
      a = P(-1.05, v, 0); b = P(1.05, v, 0); g.beginPath(); g.moveTo(a[0], a[1]); g.lineTo(b[0], b[1]); g.stroke();
    }
    g.setLineDash([4, 4]); g.strokeStyle = "rgba(245,197,66,.45)";
    const wy = B.thresholds.watch, c4 = [[-1.05, -1.05], [1.05, -1.05], [1.05, 1.05], [-1.05, 1.05]].map(([x, y]) => P(x, y, wy));
    g.beginPath(); c4.forEach((p, i) => (i ? g.lineTo(p[0], p[1]) : g.moveTo(p[0], p[1]))); g.closePath(); g.stroke(); g.setLineDash([]);
    const pos = place(); tops = [];
    const order = B.lakes.map((_, li) => li).sort((a, b) => P(...pos[a], 0)[2] - P(...pos[b], 0)[2]);
    order.forEach((li) => {
      const [x, y] = pos[li], t = tierOf(li), r = riskOf(li) ?? 0, c = tierColor(t), base = P(x, y, 0), top = P(x, y, t === "cannot_assess" ? 0.02 : r * 0.9);
      g.fillStyle = "rgba(0,0,0,.35)"; g.beginPath(); g.ellipse(base[0], base[1], 7, 3.4, 0, 0, 7); g.fill();
      if (t === "cannot_assess") {
        g.strokeStyle = "#8a96a3"; g.lineWidth = 1; g.beginPath(); g.ellipse(base[0], base[1], 6, 3, 0, 0, 7); g.stroke();
        g.beginPath(); g.moveTo(base[0] - 4, base[1] + 1.5); g.lineTo(base[0] + 4, base[1] - 1.5); g.stroke();
      } else {
        g.strokeStyle = c; g.lineWidth = 3.2; g.shadowColor = c; g.shadowBlur = 8; g.beginPath(); g.moveTo(base[0], base[1]); g.lineTo(top[0], top[1]); g.stroke();
        g.shadowBlur = 0; g.fillStyle = c; g.beginPath(); g.arc(top[0], top[1], 4.2, 0, 7); g.fill();
      }
      if (li === S.lake) { g.strokeStyle = "#fff"; g.lineWidth = 1.2; g.beginPath(); g.arc(top[0], top[1], 8, 0, 7); g.stroke(); }
      if (li === S.lake || t === "high") { g.fillStyle = "#fff"; g.font = "600 11px " + col("--mono"); g.textAlign = "center"; g.fillText(B.lakes[li].name, top[0], top[1] - 12); g.textAlign = "left"; }
      tops.push({ li, x: top[0], y: top[1] });
    });
    g.fillStyle = "rgba(245,197,66,.8)"; g.font = "10px " + col("--mono"); g.fillText(`Watch ${B.thresholds.watch}`, c4[0][0] + 4, c4[0][1] - 4);
  }
  function surfPick(ev) {
    const r = $("surf").getBoundingClientRect(), x = ev.clientX - r.left, y = ev.clientY - r.top;
    let best = null, bd = 14; tops.forEach((t) => { const d = Math.hypot(t.x - x, t.y - y); if (d < bd) { bd = d; best = t; } });
    return best;
  }

  // ---------- pointer events ----------
  function bindCanvas() {
    const heat = $("heat");
    heat.onclick = (ev) => { const p = heatPick(ev); stop(); if (p.wi != null) setWin(p.wi); if (p.li != null) selectLake(p.li); };
    heat.onmousemove = (ev) => { const p = heatPick(ev); heat.style.cursor = p.wi != null ? "pointer" : "default"; };
    const wb = $("wb-risk");
    wb.onmousemove = (ev) => {
      const gm = wb._geom; if (!gm) return; const r = wb.getBoundingClientRect(), x = ev.clientX - r.left;
      const i = Math.max(0, Math.min(gm.n - 1, Math.round(((x - WB.l) / (gm.w - WB.l - WB.r)) * (gm.n - 1)))), v = riskOf(S.lake, i), t = tierOf(S.lake, i);
      $("wb-tip").innerHTML = `<b>${fd(B.dates[i])}</b> · ${v == null ? "cannot assess" : `risk ${pct(v)} · fleet median ${pct(medianAt(i))}`} · ${TIER_LABEL[t]}`;
    };
    wb.onclick = (ev) => { const gm = wb._geom, r = wb.getBoundingClientRect(); stop(); setWin(Math.max(0, Math.min(gm.n - 1, Math.round(((ev.clientX - r.left - WB.l) / (gm.w - WB.l - WB.r)) * (gm.n - 1))))); drawWorkbench(); };
    const sf = $("surf"); let drag = null;
    sf.onmousedown = (ev) => { drag = { x: ev.clientX, yaw: S.yaw, moved: false }; };
    window.addEventListener("mouseup", () => { drag = null; });
    sf.onmousemove = (ev) => {
      if (drag) { const dx = ev.clientX - drag.x; if (Math.abs(dx) > 3) drag.moved = true; S.yaw = drag.yaw + dx * 0.008; draw3D(); return; }
      const t = surfPick(ev), tip = $("surf-tip");
      if (t) { const tt = tierOf(t.li), r = riskOf(t.li); tip.style.display = "block"; tip.style.left = `${t.x + 12}px`; tip.style.top = `${t.y - 8}px`;
        tip.innerHTML = `<b>${B.lakes[t.li].name}</b><br>${r == null ? "cannot assess" : "risk " + pct(r)} · ${TIER_LABEL[tt]}`; } else tip.style.display = "none";
    };
    sf.onclick = (ev) => { const t = surfPick(ev); if (t && !(drag && drag.moved)) { S.lake = t.li; renderAll(); } };
  }
})();
