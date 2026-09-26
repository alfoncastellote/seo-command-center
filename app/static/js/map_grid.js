/* Map Grid page: Leaflet map, run selector, compare, KPIs and trend. */
(function () {
  const state = {
    brands: [], grids: {}, brandId: null, kw: null, runIdx: 0, compare: false,
    map: null, layer: null, running: false, setupBrand: null, setupSize: 7,
  };

  const pinColor = (r) => (r === null || r === undefined) ? "#ff6b6b" : r <= 3 ? "#3ddc97" : r <= 10 ? "#f2b94b" : "#ff6b6b";
  const pinText = (r) => (r === null || r === undefined) ? "–" : String(r);

  function runStats(pts) {
    let sum = 0, ranked = 0, t3 = 0, t10 = 0;
    pts.forEach((p) => {
      const r = p.rank;
      if (r !== null && r !== undefined) { sum += r; ranked++; if (r <= 3) t3++; if (r <= 10) t10++; }
    });
    const n = pts.length || 1;
    return { avg: ranked ? sum / ranked : null, t3: (t3 / n) * 100, t10: (t10 / n) * 100, n: pts.length };
  }

  function gridFor(brandId) {
    const g = state.grids[brandId];
    return g || null;
  }

  function metaFor(brandId) {
    return state.brands.find((b) => b.id === brandId);
  }

  function trendSvg(runsMap) {
    const runs = Object.keys(runsMap).sort();
    const st = runs.map((r) => { const s = runStats(runsMap[r]); s.run = r; return s; });
    if (st.length < 2) {
      return '<div class="empty">Trend chart appears after the next scan (' + st.length + " run stored so far).</div>";
    }
    const W = 720, H = 130, P = 26;
    const maxAvg = Math.max(10, ...st.map((s) => (s.avg === null ? 20 : s.avg)));
    const x = (i) => P + i * (W - 2 * P) / (st.length - 1);
    const yAvg = (v) => P + ((v - 1) / (maxAvg - 1)) * (H - 2 * P);
    const yPct = (v) => (H - P) - (v / 100) * (H - 2 * P);
    const avgLine = st.map((s, i) => x(i) + "," + yAvg(s.avg === null ? maxAvg : s.avg)).join(" ");
    const t3Line = st.map((s, i) => x(i) + "," + yPct(s.t3)).join(" ");
    let dots = "";
    st.forEach((s, i) => {
      dots += '<circle cx="' + x(i) + '" cy="' + yAvg(s.avg === null ? maxAvg : s.avg) + '" r="3.2" fill="#5fe3c7"><title>' + s.run + " — avg rank " + (s.avg === null ? "not in pack" : s.avg.toFixed(1)) + "</title></circle>";
      dots += '<circle cx="' + x(i) + '" cy="' + yPct(s.t3) + '" r="3.2" fill="#3ddc97"><title>' + s.run + " — top 3 on " + Math.round(s.t3) + "% of pins</title></circle>";
    });
    let labels = "";
    const step = Math.max(1, Math.ceil(st.length / 6));
    st.forEach((s, i) => {
      if (i % step === 0 || i === st.length - 1) {
        labels += '<text x="' + x(i) + '" y="' + (H - 6) + '" fill="#667888" font-size="10" text-anchor="middle">' + s.run.slice(5, 10) + "</text>";
      }
    });
    return '<svg class="chart" viewBox="0 0 ' + W + " " + H + '" style="height:' + H + 'px">' +
      '<line x1="' + P + '" y1="' + (H - P) + '" x2="' + (W - P) + '" y2="' + (H - P) + '" stroke="#1d2833"/>' +
      '<polyline fill="none" stroke="#3ddc97" stroke-width="2" stroke-dasharray="5 4" stroke-linejoin="round" points="' + t3Line + '"/>' +
      '<polyline fill="none" stroke="#5fe3c7" stroke-width="2.5" stroke-linejoin="round" points="' + avgLine + '"/>' +
      dots + labels + "</svg>";
  }

  function emptyPanel(message, showSetup) {
    return '<div class="panel"><div class="empty">' + message +
      (showSetup ? '<br><br><button class="btn btn-primary" id="empty-setup">Set up grid</button>' : "") +
      "</div></div>";
  }

  function renderReport() {
    const mount = document.getElementById("report");
    if (state.map) { state.map.remove(); state.map = null; state.layer = null; }
    const grid = gridFor(state.brandId);
    const meta = metaFor(state.brandId);
    if (!meta) { mount.innerHTML = emptyPanel("Add a brand first.", false); return; }
    if (!grid || !Object.keys(grid.keywords).length) {
      mount.innerHTML = emptyPanel("No grid configured for " + SVP.escapeHtml(meta.name) + ".", true);
      const b = document.getElementById("empty-setup");
      if (b) b.onclick = () => openSetup(state.brandId);
      return;
    }

    const kws = Object.keys(grid.keywords);
    if (!state.kw || kws.indexOf(state.kw) === -1) state.kw = kws[0];

    mount.innerHTML =
      '<div class="panel"><div class="readout-row">' +
        cell("v-avg", "avg rank") + cell("v-t3", "pins in top 3") +
        cell("v-t10", "pins in top 10") + cell("v-cov", "grid points") +
      "</div>" +
      '<div class="panel-head"><h3>' + SVP.escapeHtml(meta.name) + '</h3>' +
        '<span class="meta">' + SVP.escapeHtml(meta.domain) + " · local map-pack coverage</span></div>" +
      '<div class="map-controls"><span class="sublbl" style="margin:0">Keyword</span>' +
        '<span class="chips" id="kw-chips"></span>' +
        '<span class="runsel"><label class="cmp"><input type="checkbox" id="cmp-box"' + (state.compare ? " checked" : "") + "> vs prev</label>" +
        '<button id="run-prev">‹</button><span class="rlabel" id="run-label"></span><button id="run-next">›</button></span></div>' +
      '<div class="map" id="map"></div></div>' +
      '<div class="panel"><div class="panel-head"><h3>Coverage trend</h3><span class="meta" id="trend-meta"></span></div>' +
        '<div class="panel-body"><div class="legend">' +
          '<span class="swatch"><i class="dot" style="background:#5fe3c7"></i>avg rank (lower is better)</span>' +
          '<span class="swatch"><i class="dot" style="background:#3ddc97"></i>pins in top 3</span>' +
        '</div><div id="trend"></div></div></div>';

    renderChips(grid);
    document.getElementById("run-prev").onclick = () => { const runs = sortedRuns(); if (state.runIdx < runs.length - 1) { state.runIdx++; draw(); } };
    document.getElementById("run-next").onclick = () => { if (state.runIdx > 0) { state.runIdx--; draw(); } };
    document.getElementById("cmp-box").onchange = (e) => { state.compare = e.target.checked; draw(); };

    const center = grid.config.center || [0, 0];
    state.map = L.map("map", { zoomControl: true }).setView(center, 11);
    L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}", {
      maxZoom: 16, attribution: "Tiles &copy; Esri",
    }).addTo(state.map);
    state.layer = L.layerGroup().addTo(state.map);
    draw();
  }

  function cell(id, label) {
    return '<div class="readout-cell"><div class="v" id="' + id + '">—</div><div class="k">' + label + "</div></div>";
  }

  function renderChips(grid) {
    const wrap = document.getElementById("kw-chips");
    wrap.innerHTML = "";
    Object.keys(grid.keywords).forEach((kw) => {
      const b = SVP.el("button", { class: "chip" + (kw === state.kw ? " on" : "") });
      b.appendChild(SVP.el("span", { text: kw }));
      const x = SVP.el("span", { class: "chip-x", text: "✕", title: "Stop tracking this keyword" });
      x.onclick = async (ev) => {
        ev.stopPropagation();
        if (!confirm('Stop tracking "' + kw + '" on this grid?')) return;
        try {
          await SVP.api("/api/geogrid/" + state.brandId + "/keywords/" + encodeURIComponent(kw), { method: "DELETE" });
          SVP.toast("Removed — rerun the grid to refresh pins");
          await refreshData();
          state.kw = null;
          renderReport();
        } catch (e) { SVP.toast(e.message, "err"); }
      };
      b.appendChild(x);
      b.onclick = () => { state.kw = kw; state.runIdx = 0; renderChips(grid); draw(); };
      wrap.appendChild(b);
    });
    const add = SVP.el("button", { class: "chip", text: "＋ keyword", title: "Add a keyword to this grid" });
    add.onclick = async () => {
      const kw = prompt("Keyword to add to this grid:");
      if (!kw || !kw.trim()) return;
      try {
        await SVP.api("/api/geogrid/" + state.brandId + "/keywords", { method: "POST", body: JSON.stringify({ keyword: kw.trim() }) });
        SVP.toast("Keyword added — run the grid to scan it");
        await refreshData();
        renderReport();
      } catch (e) { SVP.toast(e.message, "err"); }
    };
    wrap.appendChild(add);
  }

  function sortedRuns() {
    const grid = gridFor(state.brandId);
    const runsMap = (grid && grid.keywords[state.kw]) || {};
    return Object.keys(runsMap).sort().reverse();
  }

  function draw() {
    const grid = gridFor(state.brandId);
    if (!grid || !state.map) return;
    const runsMap = grid.keywords[state.kw] || {};
    const runs = sortedRuns();
    const label = document.getElementById("run-label");
    const set = (id, v) => { const e = document.getElementById(id); if (e) e.textContent = v; };

    if (!runs.length) {
      state.layer.clearLayers();
      ["v-avg", "v-t3", "v-t10", "v-cov", "ro-points", "ro-avg", "ro-t3", "ro-last"]
        .forEach((id) => set(id, "—"));
      label.textContent = "first scan in progress…";
      document.getElementById("run-prev").disabled = true;
      document.getElementById("run-next").disabled = true;
      document.getElementById("trend").innerHTML = '<div class="empty">"' + SVP.escapeHtml(state.kw) + '" was just added. Its first grid scan runs on the next "Run scan".</div>';
      return;
    }
    if (state.runIdx > runs.length - 1) state.runIdx = runs.length - 1;
    const run = runs[state.runIdx];
    const pts = runsMap[run];
    const prevRun = runs[state.runIdx + 1];
    const prevPts = prevRun ? runsMap[prevRun] : null;
    const prevByPt = {};
    if (prevPts) prevPts.forEach((p) => { prevByPt[p.lat.toFixed(4) + "," + p.lng.toFixed(4)] = p.rank; });

    const stats = runStats(pts);
    state.layer.clearLayers();
    pts.forEach((p) => {
      const col = pinColor(p.rank);
      let delta = "";
      if (state.compare && prevPts) {
        const pr = prevByPt[p.lat.toFixed(4) + "," + p.lng.toFixed(4)];
        if (pr !== undefined) {
          const cur = (p.rank === null || p.rank === undefined) ? 99 : p.rank;
          const old = (pr === null || pr === undefined) ? 99 : pr;
          if (cur < old) delta = '<span class="delta" style="background:#3ddc97;color:#04120e">▲</span>';
          else if (cur > old) delta = '<span class="delta" style="background:#ff6b6b;color:#fff">▼</span>';
        }
      }
      const icon = L.divIcon({
        className: "",
        html: '<div class="gpin" style="width:30px;height:30px;position:relative;background:' + col + '">' + pinText(p.rank) + delta + "</div>",
        iconSize: [30, 30], iconAnchor: [15, 15],
      });
      let pop = "<b>" + (p.rank === null || p.rank === undefined ? "Not in pack" : "Rank #" + p.rank) + "</b><br>" + p.lat.toFixed(4) + ", " + p.lng.toFixed(4);
      if (p.top3 && p.top3.length) {
        pop += '<br><span style="font-size:10px;color:#9fb0bf">Top 3 here</span>';
        p.top3.forEach((c) => { pop += "<br>" + c.r + ". " + SVP.escapeHtml(c.t); });
      }
      L.marker([p.lat, p.lng], { icon }).addTo(state.layer).bindPopup(pop);
    });

    set("v-avg", stats.avg === null ? "—" : stats.avg.toFixed(1));
    set("v-t3", Math.round(stats.t3) + "%");
    set("v-t10", Math.round(stats.t10) + "%");
    set("v-cov", stats.n);
    set("ro-points", stats.n);
    set("ro-avg", stats.avg === null ? "—" : stats.avg.toFixed(1));
    set("ro-t3", Math.round(stats.t3) + "%");
    set("ro-last", run.slice(5, 16));

    const ps = prevPts ? runStats(prevPts) : null;
    const up = (id, diff, formatted) => {
      const cellEl = document.getElementById(id).parentElement;
      let el = cellEl.querySelector(".d");
      if (!el) { el = SVP.el("div", { class: "d" }); cellEl.appendChild(el); }
      el.className = "d";
      if (diff === null || diff === undefined || Math.abs(diff) < 0.05) { el.textContent = ""; return; }
      el.textContent = (diff > 0 ? "▲" : "▼") + formatted(Math.abs(diff));
      el.classList.add(diff > 0 ? "up" : "down");
    };
    const avgDiff = (ps && ps.avg !== null && stats.avg !== null) ? ps.avg - stats.avg : null;
    up("v-avg", avgDiff, (d) => d.toFixed(1));
    up("v-t3", ps ? stats.t3 - ps.t3 : null, (d) => Math.round(d) + "pp");
    up("v-t10", ps ? stats.t10 - ps.t10 : null, (d) => Math.round(d) + "pp");

    document.getElementById("trend").innerHTML = trendSvg(runsMap);
    document.getElementById("trend-meta").textContent = runs.length + " runs";
    label.textContent = run + "  (" + (runs.length - state.runIdx) + "/" + runs.length + ")";
    document.getElementById("run-prev").disabled = state.runIdx >= runs.length - 1;
    document.getElementById("run-next").disabled = state.runIdx <= 0;
    document.getElementById("cmp-box").disabled = !prevPts;
  }

  function renderChips_bar() {
    const wrap = document.getElementById("brand-chips");
    wrap.innerHTML = "";
    if (!state.brands.length) {
      wrap.innerHTML = '<span class="who" style="color:var(--muted)">No brands yet — add one under Brands &amp; keywords.</span>';
      return;
    }
    state.brands.forEach((b) => {
      const btn = SVP.el("button", { class: "chip" + (b.id === state.brandId ? " on" : ""), text: b.name + (b.grid ? "" : " · no grid") });
      btn.onclick = () => { state.brandId = b.id; state.kw = null; state.runIdx = 0; renderChips_bar(); renderReadouts(); renderReport(); };
      wrap.appendChild(btn);
    });
  }

  function renderReadouts() {
    const grid = gridFor(state.brandId);
    const runsMap = grid && state.kw && grid.keywords[state.kw] ? grid.keywords[state.kw] : {};
    const runs = Object.keys(runsMap).sort();
    const latest = runs.length ? runsMap[runs[runs.length - 1]] : null;
    document.getElementById("brand-meta").textContent = metaFor(state.brandId) ? metaFor(state.brandId).domain : "";
    if (!latest) {
      ["ro-points", "ro-avg", "ro-t3", "ro-last"].forEach((id) => { document.getElementById(id).textContent = "—"; });
      return;
    }
    const s = runStats(latest);
    document.getElementById("ro-points").textContent = s.n;
    document.getElementById("ro-avg").textContent = s.avg === null ? "—" : s.avg.toFixed(1);
    document.getElementById("ro-t3").textContent = Math.round(s.t3) + "%";
    document.getElementById("ro-last").textContent = runs[runs.length - 1].slice(5, 16);
  }

  /* ── setup modal ─────────────────────────────────────────────────── */

  function openSetup(brandId) {
    state.setupBrand = brandId || state.brandId;
    const wrap = document.getElementById("setup-brand");
    wrap.innerHTML = "";
    state.brands.forEach((b) => {
      const btn = SVP.el("button", { class: "chip" + (b.id === state.setupBrand ? " on" : ""), text: b.name + (b.grid ? " ✓" : "") });
      btn.onclick = () => { state.setupBrand = b.id; openSetup(b.id); };
      wrap.appendChild(btn);
    });
    const meta = metaFor(state.setupBrand);
    const g = (meta && meta.grid) || null;
    document.getElementById("setup-center").value = g ? g.center[0] + ", " + g.center[1] : "";
    document.getElementById("setup-spacing").value = g ? g.spacing_miles : 3.5;
    document.getElementById("setup-kws").value = g ? g.keywords.join("\n") : "";
    state.setupSize = g ? g.grid : 7;
    document.querySelectorAll("#setup-size button").forEach((z) => z.classList.toggle("on", +z.dataset.v === state.setupSize));
    document.getElementById("setup-remove").style.display = g ? "" : "none";
    document.getElementById("setup-modal").classList.add("open");
  }

  function bindSetup() {
    document.getElementById("setup-btn").onclick = () => openSetup(state.brandId);
    document.querySelectorAll("#setup-size button").forEach((z) => {
      z.onclick = () => { state.setupSize = +z.dataset.v; document.querySelectorAll("#setup-size button").forEach((y) => y.classList.remove("on")); z.classList.add("on"); };
    });
    document.getElementById("setup-modal").addEventListener("click", (e) => {
      if (e.target.id === "setup-modal" || e.target.hasAttribute("data-close")) document.getElementById("setup-modal").classList.remove("open");
    });
    document.getElementById("setup-save").onclick = async () => {
      const parts = (document.getElementById("setup-center").value || "").split(",");
      const lat = parseFloat(parts[0]), lng = parseFloat(parts[1]);
      const kws = document.getElementById("setup-kws").value.split("\n").map((s) => s.trim()).filter(Boolean).slice(0, 10);
      if (!isFinite(lat) || !isFinite(lng)) { SVP.toast("Center must be “lat, lng”", "err"); return; }
      if (!kws.length) { SVP.toast("Add at least one keyword", "err"); return; }
      const pulls = state.setupSize * state.setupSize * kws.length;
      try {
        await SVP.api("/api/geogrid", {
          method: "POST",
          body: JSON.stringify({ brand_id: state.setupBrand, center: [lat, lng], grid: state.setupSize,
            spacing_miles: parseFloat(document.getElementById("setup-spacing").value) || 3.5, keywords: kws }),
        });
        document.getElementById("setup-modal").classList.remove("open");
        SVP.toast("Grid saved — " + pulls + " points, about $" + SVP.fmt.money(pulls * 0.002).slice(1) + " per scan", "ok");
        await refreshData();
        if (state.setupBrand === state.brandId) { state.kw = null; renderReport(); }
        renderChips_bar();
      } catch (e) { SVP.toast(e.message, "err"); }
    };
    document.getElementById("setup-remove").onclick = async () => {
      if (!state.setupBrand || !confirm("Remove this grid? Stored history stays in the database.")) return;
      try {
        await SVP.api("/api/geogrid/" + state.setupBrand, { method: "DELETE" });
        document.getElementById("setup-modal").classList.remove("open");
        SVP.toast("Grid removed");
        await refreshData();
        renderChips_bar();
        renderReport();
      } catch (e) { SVP.toast(e.message, "err"); }
    };
  }

  /* ── run + data ──────────────────────────────────────────────────── */

  function setRunning(on) {
    state.running = on;
    const bar = document.getElementById("run-progress");
    bar.hidden = !on;
    const btn = document.getElementById("run-btn");
    btn.disabled = on;
    btn.textContent = on ? "Scanning…" : "Run scan";
  }

  async function runScan() {
    if (state.running) return;
    if (!gridFor(state.brandId)) { SVP.toast("Set up a grid first", "err"); return; }
    setRunning(true);
    const fill = document.querySelector("#run-progress i");
    try {
      const res = await SVP.api("/api/geogrid/run", { method: "POST", body: JSON.stringify({ brand_id: state.brandId }) });
      SVP.toast("Scan queued — " + res.brands.join(", "));
      for (const id of res.jobs) {
        await SVP.pollJob(id, {
          onTick: (job) => { fill.style.width = job.total ? Math.round((job.progress / job.total) * 100) + "%" : "8%"; if (job.message) fill.title = job.message; },
        });
      }
      await refreshData();
      state.kw = null;
      renderReport();
      renderReadouts();
      SVP.toast("Scan complete", "ok");
    } catch (e) {
      SVP.toast(e.message, "err");
    } finally {
      fill.style.width = "0%";
      setRunning(false);
    }
  }

  async function refreshData() {
    const [brandsRes, gridsRes] = await Promise.all([SVP.api("/api/brands"), SVP.api("/api/geogrid")]);
    state.brands = brandsRes.brands;
    state.grids = {};
    gridsRes.brands.forEach((g) => { state.grids[g.id] = g; });
  }

  async function init() {
    await refreshData();
    bindSetup();
    document.getElementById("run-btn").onclick = runScan;
    const withGrid = state.brands.find((b) => b.grid);
    state.brandId = (withGrid || state.brands[0] || {}).id || null;
    renderChips_bar();
    renderReadouts();
    renderReport();
  }

  init().catch((e) => SVP.toast(e.message, "err"));
})();
