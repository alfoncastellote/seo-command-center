/* Settings: caps, concurrency, weekly schedules, recent jobs, demo seed. */
(function () {
  const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
  const HOURS = Array.from({ length: 24 }, (_, i) => i);

  async function load() {
    const s = await SVP.api("/api/settings");
    document.getElementById("s-concurrency").value = s.concurrency || "8";
    document.getElementById("s-ai-cap").value = s.ai_daily_cap || "2";
    document.getElementById("s-grid-cap").value = s.geogrid_daily_cap || "1";
    document.getElementById("s-brand").value = s.brand_name || "";

    const wrap = document.getElementById("schedules");
    wrap.innerHTML = "";
    wrap.appendChild(schedule("ai", "AI Visibility", s));
    wrap.appendChild(schedule("geogrid", "Map Grid", s));
  }

  async function loadEngines() {
    const wrap = document.getElementById("engines");
    try {
      const { providers } = await SVP.api("/api/providers/status");
      wrap.innerHTML = "";
      providers.forEach((p) => {
        const row = SVP.el("div", { style: "display:flex;align-items:center;gap:14px;padding:10px 0;border-bottom:1px solid var(--line)" });
        const toggle = SVP.el("label", { class: "cmp", style: "min-width:190px" });
        const cb = SVP.el("input", { type: "checkbox" });
        cb.checked = p.enabled;
        cb.dataset.engine = p.key;
        toggle.appendChild(cb);
        toggle.appendChild(SVP.el("span", { text: p.label }));
        row.appendChild(toggle);
        row.appendChild(SVP.el("span", { class: "pill " + (p.configured ? "ok" : "none"), text: p.configured ? "configured" : "no API key" }));
        wrap.appendChild(row);
      });
    } catch (e) { wrap.innerHTML = '<div class="empty">Could not load engine status.</div>'; }
  }

  function schedule(prefix, label, s) {
    const row = SVP.el("div", { style: "display:flex;align-items:flex-end;gap:22px;flex-wrap:wrap;padding:12px 0;border-bottom:1px solid var(--line)" });
    const toggle = SVP.el("label", { class: "cmp", style: "padding-bottom:10px" });
    const cb = SVP.el("input", { type: "checkbox" });
    cb.checked = s[prefix + "_schedule_enabled"] === "1";
    cb.dataset.prefix = prefix;
    cb.dataset.kind = "enabled";
    toggle.appendChild(cb);
    toggle.appendChild(SVP.el("span", { text: label }));

    const dayWrap = SVP.el("div", { class: "field", style: "margin:0;width:170px" });
    dayWrap.appendChild(SVP.el("label", { text: "Day" }));
    const daySel = SVP.el("select", { class: "input", "data-prefix": prefix, "data-kind": "dow" });
    DAYS.forEach((d, i) => {
      const o = SVP.el("option", { value: i, text: d });
      if (String(i) === (s[prefix + "_schedule_dow"] || "1")) o.selected = true;
      daySel.appendChild(o);
    });
    dayWrap.appendChild(daySel);

    const hourWrap = SVP.el("div", { class: "field", style: "margin:0;width:120px" });
    hourWrap.appendChild(SVP.el("label", { text: "Hour (server)" }));
    const hourSel = SVP.el("select", { class: "input", "data-prefix": prefix, "data-kind": "hour" });
    HOURS.forEach((h) => {
      const o = SVP.el("option", { value: h, text: String(h).padStart(2, "0") + ":00" });
      if (String(h) === (s[prefix + "_schedule_hour"] || "6")) o.selected = true;
      hourSel.appendChild(o);
    });
    hourWrap.appendChild(hourSel);

    row.appendChild(toggle);
    row.appendChild(dayWrap);
    row.appendChild(hourWrap);
    return row;
  }

  async function save() {
    const payload = {
      concurrency: document.getElementById("s-concurrency").value,
      ai_daily_cap: document.getElementById("s-ai-cap").value,
      geogrid_daily_cap: document.getElementById("s-grid-cap").value,
      brand_name: document.getElementById("s-brand").value,
    };
    document.querySelectorAll("#schedules input[data-kind='enabled']").forEach((cb) => {
      payload[cb.dataset.prefix + "_schedule_enabled"] = cb.checked ? "1" : "0";
    });
    document.querySelectorAll("#schedules select[data-kind]").forEach((sel) => {
      payload[sel.dataset.prefix + "_schedule_" + sel.dataset.kind] = sel.value;
    });
    document.querySelectorAll("#engines input[data-engine]").forEach((cb) => {
      payload[cb.dataset.engine + "_enabled"] = cb.checked ? "1" : "0";
    });
    try {
      await SVP.api("/api/settings", { method: "POST", body: JSON.stringify(payload) });
      SVP.toast("Settings saved", "ok");
    } catch (e) { SVP.toast(e.message, "err"); }
  }

  function jobRow(job) {
    const row = SVP.el("div", { class: "job" });
    const line = SVP.el("div", { class: "row" });
    const label = job.type === "ai_visibility" ? "AI Visibility" : "Map Grid";
    line.appendChild(SVP.el("b", { text: label }));
    line.appendChild(SVP.el("span", { text: job.brand || "" }));
    line.appendChild(SVP.el("span", { class: "pill " + (job.status === "done" ? "ok" : job.status === "error" ? "miss" : "warn"), text: job.status }));
    const meta = job.error || job.message || "";
    line.appendChild(SVP.el("span", { class: "m", text: meta }));
    row.appendChild(line);
    if (job.status === "running" || job.status === "queued") {
      const pct = job.total ? Math.round((job.progress / job.total) * 100) : 5;
      const progress = SVP.el("div", { class: "progress", style: "margin-top:8px" });
      progress.appendChild(SVP.el("i", { style: "width:" + pct + "%" }));
      row.appendChild(progress);
    }
    return row;
  }

  async function loadJobs() {
    try {
      const { jobs } = await SVP.api("/api/jobs");
      const mount = document.getElementById("jobs");
      document.getElementById("jobs-meta").textContent = jobs.length ? jobs.filter((j) => j.status === "running" || j.status === "queued").length + " active" : "";
      mount.innerHTML = "";
      if (!jobs.length) { mount.innerHTML = '<div class="empty">No scans yet.</div>'; return; }
      jobs.forEach((j) => mount.appendChild(jobRow(j)));
    } catch (e) { /* ignore */ }
  }

  document.getElementById("save-settings").onclick = save;
  document.getElementById("test-creds").onclick = async () => {
    const btn = document.getElementById("test-creds");
    const out = document.getElementById("creds-result");
    btn.disabled = true;
    out.textContent = "Testing…";
    out.style.color = "var(--muted)";
    try {
      const r = await SVP.api("/api/credentials/test", { method: "POST" });
      out.textContent = r.ok ? "✓ " + r.message : "✗ " + r.message;
      out.style.color = r.ok ? "var(--pos)" : "var(--neg)";
    } catch (e) {
      out.textContent = "✗ " + e.message;
      out.style.color = "var(--neg)";
    } finally {
      btn.disabled = false;
    }
  };
  document.getElementById("seed-demo").onclick = async () => {
    if (!confirm("Replace all current data with sample demo data?")) return;
    try {
      await SVP.api("/api/demo/seed", { method: "POST" });
      SVP.toast("Demo data loaded — open AI Visibility or Map Grid", "ok");
      await load();
      await loadJobs();
    } catch (e) { SVP.toast(e.message, "err"); }
  };

  load().catch((e) => SVP.toast(e.message, "err"));
  loadEngines();
  loadJobs();
  setInterval(loadJobs, 5000);
})();
