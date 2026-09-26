/* AI Visibility page: brand selection, KPIs, table, citation leaders, history. */
(function () {
  const state = { brands: [], brandId: null, data: null, running: false, filter: "all", query: "" };

  function chart(history) {
    if (!history || history.length < 2) {
      return '<div class="empty">Trend appears after the second scan. Every run is kept.</div>';
    }
    const W = 720, H = 150, P = 26;
    const maxN = Math.max(1, ...history.map((h) => Math.max(h.n_ai, h.n_cited, h.total_kw)));
    const x = (i) => P + i * (W - 2 * P) / (history.length - 1);
    const y = (v) => H - P - (v / maxN) * (H - 2 * P);
    const line = (key, color, dash) =>
      '<polyline fill="none" stroke="' + color + '" stroke-width="2.5"' +
      (dash ? ' stroke-dasharray="5 4"' : '') + ' stroke-linejoin="round" points="' +
      history.map((h, i) => x(i) + ',' + y(h[key])).join(" ") + '"/>';
    let dots = "";
    history.forEach((h, i) => {
      dots += '<circle cx="' + x(i) + '" cy="' + y(h.n_cited) + '" r="3.2" fill="#3ddc97"><title>' +
        h.ran_at + " — cited " + h.n_cited + ", AI overviews " + h.n_ai + "</title></circle>";
      dots += '<circle cx="' + x(i) + '" cy="' + y(h.n_ai) + '" r="3.2" fill="#5fe3c7"/>';
    });
    let labels = "";
    const step = Math.max(1, Math.ceil(history.length / 6));
    history.forEach((h, i) => {
      if (i % step === 0 || i === history.length - 1) {
        labels += '<text x="' + x(i) + '" y="' + (H - 6) + '" fill="#667888" font-size="10" text-anchor="middle">' +
          h.ran_at.slice(5, 10) + "</text>";
      }
    });
    return '<svg class="chart" viewBox="0 0 ' + W + " " + H + '" style="height:' + H + 'px">' +
      '<line x1="' + P + '" y1="' + (H - P) + '" x2="' + (W - P) + '" y2="' + (H - P) + '" stroke="#1d2833"/>' +
      line("n_ai", "#5fe3c7", true) + line("n_cited", "#3ddc97", false) + dots + labels + "</svg>";
  }

  function renderReport() {
    const mount = document.getElementById("report");
    const data = state.data;
    if (!data || !data.run) {
      mount.innerHTML = '<div class="panel"><div class="empty">No scan yet for this brand.<br>' +
        "Add keywords under <b>Brands &amp; keywords</b>, then press <b>Run scan</b>.</div></div>";
      return;
    }
    const run = data.run;
    const share = run.n_ai ? Math.round((run.n_cited / run.n_ai) * 100) : 0;

    let rows = data.rows.filter((r) => {
      if (state.query && r.keyword.toLowerCase().indexOf(state.query) === -1) return false;
      if (state.filter === "ai") return r.has_ai;
      if (state.filter === "cited") return r.cited;
      if (state.filter === "missing") return r.has_ai && !r.cited;
      return true;
    });
    let trs = rows.map((r) => {
      let status;
      if (!r.has_ai) status = '<span class="pill none">No AI Overview</span>';
      else if (r.cited) status = '<span class="pill ok">Cited</span>';
      else status = '<span class="pill miss">Not cited</span>';
      const refs = r.refs && r.refs.length ? r.refs.slice(0, 5).join(", ") + (r.refs.length > 5 ? " …" : "") : "—";
      return '<tr><td class="kw">' + SVP.escapeHtml(r.keyword) + "</td><td>" + status +
        '</td><td class="who">' + SVP.escapeHtml(refs) + "</td></tr>";
    }).join("");
    if (!trs) trs = '<tr><td colspan="3"><div class="empty">No keywords match this filter.</div></td></tr>';

    const leaders = data.top_cited.length
      ? data.top_cited.map((c) => '<tr><td class="kw">' + SVP.escapeHtml(c.domain) +
          '</td><td class="num">' + c.count + "</td></tr>").join("")
      : '<tr><td colspan="2"><div class="empty">No citations recorded.</div></td></tr>';

    mount.innerHTML =
      '<div class="panel">' +
        '<div class="readout-row">' +
          cell(run.n_ai + " / " + run.total_kw, "keywords with AI Overview") +
          cell(run.n_cited, "of those, you are cited") +
          cell(share + "%", "citation share") +
          cell(SVP.fmt.money(run.cost), "run cost") +
        "</div>" +
        '<div class="panel-head"><h3>' + SVP.escapeHtml(data.brand.name) + "</h3>" +
          '<span class="meta">' + SVP.escapeHtml(data.brand.domain) + " · " + run.ran_at + "</span></div>" +
        '<div class="split">' +
          "<div><div class=\"sublbl\">Who AI cites instead</div>" +
            '<div class="table-wrap" style="max-height:360px"><table><thead><tr><th>Domain</th><th class="num">Hits</th></tr></thead><tbody>' +
            leaders + "</tbody></table></div></div>" +
          '<div><div class="sublbl">Keyword · status · sources cited</div>' +
            '<div class="table-wrap" style="max-height:360px"><table><thead><tr><th>Keyword</th><th>Status</th><th>Sources</th></tr></thead><tbody>' +
            trs + "</tbody></table></div></div>" +
        "</div>" +
      "</div>" +
      '<div class="panel"><div class="panel-head"><h3>Citation trend</h3>' +
        '<span class="meta">' + data.history.length + " runs</span></div>" +
        '<div class="panel-body"><div class="legend">' +
          '<span class="swatch"><i class="dot" style="background:#5fe3c7"></i>AI Overviews present</span>' +
          '<span class="swatch"><i class="dot" style="background:#3ddc97"></i>You cited</span>' +
        "</div>" + chart(data.history) + "</div></div>";
  }

  function cell(value, label) {
    return '<div class="readout-cell"><div class="v">' + value + '</div><div class="k">' + label + "</div></div>";
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

  function bindControls() {
    document.getElementById("run-btn").onclick = runScan;
    document.querySelectorAll("#filter-bar [data-f]").forEach((btn) => {
      btn.onclick = () => {
        state.filter = btn.dataset.f;
        document.querySelectorAll("#filter-bar [data-f]").forEach((z) => z.classList.toggle("on", z === btn));
        renderReport();
      };
    });
    const bar = document.getElementById("run-progress");
    function setRunning(on) {
      state.running = on;
      bar.hidden = !on;
      const btn = document.getElementById("run-btn");
      btn.disabled = on;
      btn.textContent = on ? "Scanning…" : "Run scan";
    }
    state.setRunning = setRunning;
  }

  async function runScan() {
    if (state.running) return;
    if (!state.brandId) { SVP.toast("Add a brand first", "err"); return; }
    state.setRunning(true);
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
      state.setRunning(false);
    }
  }

  async function refreshOverview() {
    const { brands } = await SVP.api("/api/ai-visibility");
    state.brands = brands;
  }

  async function init() {
    const { brands } = await SVP.api("/api/ai-visibility");
    state.brands = brands;
    bindControls();
    renderChips();
    const hashId = parseInt(location.hash.slice(1), 10);
    const pick = brands.find((b) => b.id === hashId) || brands[0];
    if (pick) await selectBrand(pick.id);
    else { renderReadouts(); renderReport(); }
  }

  init().catch((e) => SVP.toast(e.message, "err"));
})();
