/* AI Visibility page: multi-engine matrix, KPIs, citation leaders, trend. */
(function () {
  const state = { brands: [], brandId: null, data: null, running: false, query: "" };

  const COLORS = {
    google_ai_overview: "#5fe3c7",
    openai: "#f2b94b",
    gemini: "#6ab0ff",
  };

  function pill(provider, hasAi, cited, mentioned) {
    if (provider === "google_ai_overview" && !hasAi) {
      return '<span class="pill none">No AI Overview</span>';
    }
    if (cited) return '<span class="pill ok">Cited</span>';
    if (mentioned) return '<span class="pill warn">Mentioned</span>';
    return '<span class="who" style="color:var(--muted)">—</span>';
  }

  function multiChart(history, providers) {
    if (!history || history.length < 1) {
      return '<div class="empty">Trend appears after the first scan. Every run is kept.</div>';
    }
    const byProvider = {};
    history.forEach((h) => { (byProvider[h.provider] = byProvider[h.provider] || []).push(h); });
    const series = providers
      .map((p) => ({ key: p.key, label: p.label, points: (byProvider[p.key] || []).sort((a, b) => a.ran_at.localeCompare(b.ran_at)) }))
      .filter((s) => s.points.length);

    const W = 720, H = 150, P = 26;
    const allX = Array.from(new Set(history.map((h) => h.ran_at))).sort();
    if (allX.length < 2 && series.every((s) => s.points.length < 2)) {
      return '<div class="empty">Trend chart appears after the second scan.</div>';
    }
    const xi = (t) => P + (allX.indexOf(t) / Math.max(1, allX.length - 1)) * (W - 2 * P);
    const maxPct = Math.max(1, ...series.flatMap((s) => s.points.map((p) => p.n ? (p.cited / p.n) * 100 : 0)));
    const y = (pct) => H - P - (pct / maxPct) * (H - 2 * P);

    let lines = "", dots = "";
    series.forEach((s) => {
      const pts = s.points.map((p) => xi(p.ran_at) + "," + y(p.n ? (p.cited / p.n) * 100 : 0)).join(" ");
      lines += '<polyline fill="none" stroke="' + (COLORS[s.key] || "#5fe3c7") + '" stroke-width="2.5" stroke-linejoin="round" points="' + pts + '"/>';
      s.points.forEach((p) => {
        dots += '<circle cx="' + xi(p.ran_at) + '" cy="' + y(p.n ? (p.cited / p.n) * 100 : 0) + '" r="3.2" fill="' + (COLORS[s.key] || "#5fe3c7") + '"><title>' + s.label + " — " + p.ran_at + " — cited " + p.cited + "/" + p.n + "</title></circle>";
      });
    });
    let labels = "";
    const step = Math.max(1, Math.ceil(allX.length / 6));
    allX.forEach((t, i) => {
      if (i % step === 0 || i === allX.length - 1) {
        labels += '<text x="' + xi(t) + '" y="' + (H - 6) + '" fill="#667888" font-size="10" text-anchor="middle">' + t.slice(5, 10) + "</text>";
      }
    });
    return '<svg class="chart" viewBox="0 0 ' + W + " " + H + '" style="height:' + H + 'px">' +
      '<line x1="' + P + '" y1="' + (H - P) + '" x2="' + (W - P) + '" y2="' + (H - P) + '" stroke="#1d2833"/>' +
      lines + dots + labels + "</svg>";
  }

  function renderReport() {
    const mount = document.getElementById("report");
    const data = state.data;
    if (!data || !data.run || !data.providers.length) {
      mount.innerHTML = '<div class="panel"><div class="empty">No scan yet for this brand.<br>' +
        "Add keywords under <b>Brands &amp; keywords</b>, then press <b>Run scan</b>.</div></div>";
      return;
    }
    const providers = data.providers;
    const run = data.run;

    const byCell = {};
    data.rows.forEach((r) => { byCell[r.provider + "|" + r.keyword] = r; });
    let keywords = Array.from(new Set(data.rows.map((r) => r.keyword)));
    if (state.query) {
      const q = state.query.toLowerCase();
      keywords = keywords.filter((k) => k.toLowerCase().indexOf(q) !== -1);
    }

    // share of voice
    const enginesCiting = providers.filter((p) => p.cited > 0).length;

    const cells = providers.map((p) =>
      '<div class="readout-cell"><div class="v" style="color:' + (COLORS[p.key] || "var(--ink)") + '">' +
      p.cited + " / " + p.n + '</div><div class="k">' + SVP.escapeHtml(p.label) + " cited</div></div>"
    ).join("");

    const headCols = providers.map((p) => "<th>" + SVP.escapeHtml(p.label) + "</th>").join("");
    let trs = keywords.map((kw) => {
      const cols = providers.map((p) => {
        const r = byCell[p.key + "|" + kw] || {};
        return "<td>" + pill(p.key, r.has_ai, r.cited, r.mentioned) + "</td>";
      }).join("");
      return '<tr><td class="kw">' + SVP.escapeHtml(kw) + "</td>" + cols + "</tr>";
    }).join("");
    if (!trs) trs = '<tr><td colspan="' + (providers.length + 1) + '"><div class="empty">No keywords match this filter.</div></td></tr>';

    const leaders = providers.map((p) => {
      const list = data.top_cited[p.key] || [];
      const rows = list.length
        ? list.map((c) => '<tr><td class="kw">' + SVP.escapeHtml(c.domain) + '</td><td class="num">' + c.count + "</td></tr>").join("")
        : '<tr><td colspan="2"><div class="empty">No citations recorded.</div></td></tr>';
      return '<div><div class="sublbl">' + SVP.escapeHtml(p.label) + " — who it cites instead</div>" +
        '<div class="table-wrap" style="max-height:280px"><table><thead><tr><th>Domain</th><th class="num">Hits</th></tr></thead><tbody>' +
        rows + "</tbody></table></div></div>";
    }).join("");

    const legend = providers.map((p) =>
      '<span class="swatch"><i class="dot" style="background:' + (COLORS[p.key] || "#5fe3c7") + '"></i>' + SVP.escapeHtml(p.label) + "</span>"
    ).join("");

    mount.innerHTML =
      '<div class="panel"><div class="readout-row">' +
        '<div class="readout-cell"><div class="v">' + enginesCiting + " / " + providers.length +
        '</div><div class="k">engines citing you</div></div>' + cells +
      "</div></div>" +
      '<div class="panel"><div class="panel-head"><h3>' + SVP.escapeHtml(data.brand.name) + '</h3>' +
        '<span class="meta">' + SVP.escapeHtml(data.brand.domain) + " · " + run.ran_at + "</span></div>" +
        '<div class="table-wrap" style="max-height:560px"><table><thead><tr><th>Keyword</th>' + headCols + "</tr></thead><tbody>" + trs + "</tbody></table></div></div>" +
      '<div class="panel"><div class="panel-head"><h3>Who AI cites instead</h3></div>' +
        '<div class="panel-body">' + leaders + "</div></div>" +
      '<div class="panel"><div class="panel-head"><h3>Citation trend</h3>' +
        '<span class="meta">% of keywords cited</span></div>' +
        '<div class="panel-body"><div class="legend">' + legend + "</div>" +
        multiChart(data.history, providers) + "</div></div>";
  }

  function renderReadouts() {
    const run = state.data && state.data.run;
    document.getElementById("ro-keywords").textContent = run ? run.total_kw : "—";
    document.getElementById("ro-cited").textContent = run ? run.n_cited : "—";
    document.getElementById("ro-last").textContent = run ? run.ran_at.slice(5, 16) : "—";
    document.getElementById("ro-cost").textContent = run ? SVP.fmt.money(run.cost) : "—";
  }

  function renderChips() {
    const wrap = document.getElementById("brand-chips");
    wrap.innerHTML = "";
    if (!state.brands.length) {
      wrap.innerHTML = '<span class="who" style="color:var(--muted)">No brands yet — add one under Brands &amp; keywords.</span>';
      return;
    }
    state.brands.forEach((b) => {
      const btn = SVP.el("button", { class: "chip" + (b.id === state.brandId ? " on" : ""), text: b.name });
      btn.onclick = () => selectBrand(b.id);
      wrap.appendChild(btn);
    });
  }

  async function selectBrand(id) {
    const brand = state.brands.find((b) => b.id === id);
    if (!brand) return;
    state.brandId = id;
    history.replaceState(null, "", "#" + id);
    document.getElementById("brand-meta").textContent = brand.domain + " · " + brand.keywords + " keywords";
    state.data = await SVP.api("/api/ai-visibility/" + id);
    renderChips();
    renderReport();
    renderReadouts();
  }

  async function runScan() {
    if (state.running) return;
    if (!state.brandId) { SVP.toast("Add a brand first", "err"); return; }
    state.running = true;
    const bar = document.getElementById("run-progress");
    bar.hidden = false;
    document.getElementById("run-btn").disabled = true;
    document.getElementById("run-btn").textContent = "Scanning…";
    const fill = document.querySelector("#run-progress i");
    try {
      const res = await SVP.api("/api/ai-visibility/run", {
        method: "POST", body: JSON.stringify({ brand_id: state.brandId }),
      });
      SVP.toast("Scan queued — " + res.brands.join(", "));
      for (const id of res.jobs) {
        await SVP.pollJob(id, {
          onTick: (job) => {
            fill.style.width = job.total ? Math.round((job.progress / job.total) * 100) + "%" : "8%";
            if (job.message) fill.title = job.message;
          },
        });
      }
      await refreshOverview();
      await selectBrand(state.brandId);
      SVP.toast("Scan complete", "ok");
    } catch (e) {
      SVP.toast(e.message, "err");
    } finally {
      fill.style.width = "0%";
      document.getElementById("run-progress").hidden = true;
      document.getElementById("run-btn").disabled = false;
      document.getElementById("run-btn").textContent = "Run scan";
      state.running = false;
    }
  }

  async function refreshOverview() {
    const { brands } = await SVP.api("/api/ai-visibility");
    state.brands = brands;
  }

  async function init() {
    const { brands } = await SVP.api("/api/ai-visibility");
    state.brands = brands;
    document.getElementById("run-btn").onclick = runScan;
    document.getElementById("filter-query").addEventListener("input", (e) => {
      state.query = e.target.value.trim().toLowerCase();
      renderReport();
    });
    renderChips();
    const hashId = parseInt(location.hash.slice(1), 10);
    const pick = brands.find((b) => b.id === hashId) || brands[0];
    if (pick) await selectBrand(pick.id);
    else { renderReadouts(); renderReport(); }
  }

  init().catch((e) => SVP.toast(e.message, "err"));
})();
