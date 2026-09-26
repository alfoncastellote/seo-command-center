/* Shared helpers for the SEO Visibility Panel. */
window.SVP = (function () {
  async function api(path, opts) {
    const res = await fetch(path, Object.assign({ headers: { "Content-Type": "application/json" } }, opts || {}));
    let data = null;
    try { data = await res.json(); } catch (e) { /* no body */ }
    if (!res.ok) throw new Error((data && data.error) || ("Request failed (" + res.status + ")"));
    return data;
  }

  let toastTimer;
  function toast(message, kind) {
    const el = document.getElementById("toast");
    el.textContent = message;
    el.className = "toast show" + (kind ? " " + kind : "");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { el.className = "toast"; }, 5200);
  }

  async function pollJob(id, handlers) {
    handlers = handlers || {};
    for (;;) {
      let job;
      try { job = await api("/api/jobs/" + id); }
      catch (e) { (handlers.onError || toast)(e.message); return null; }
      if (handlers.onTick) handlers.onTick(job);
      if (job.status === "done") { if (handlers.onDone) handlers.onDone(job); return job; }
      if (job.status === "error") {
        const msg = job.error || "Scan failed";
        if (handlers.onError) handlers.onError(msg); else toast(msg, "err");
        return job;
      }
      await new Promise((r) => setTimeout(r, 2000));
    }
  }

  const fmt = {
    pct(value, digits) {
      if (value === null || value === undefined || isNaN(value)) return "—";
      return value.toFixed(digits === undefined ? 0 : digits) + "%";
    },
    num(value, digits) {
      if (value === null || value === undefined || isNaN(value)) return "—";
      return Number(value).toFixed(digits === undefined ? 1 : digits);
    },
    money(value) {
      if (value === null || value === undefined) return "$0.00";
      return "$" + Number(value).toFixed(4);
    },
  };

  function el(tag, attrs, children) {
    const node = document.createElement(tag);
    if (attrs) for (const k in attrs) {
      if (k === "class") node.className = attrs[k];
      else if (k === "html") node.innerHTML = attrs[k];
      else if (k === "text") node.textContent = attrs[k];
      else if (k.startsWith("on")) node.addEventListener(k.slice(2), attrs[k]);
      else node.setAttribute(k, attrs[k]);
    }
    (children || []).forEach((c) => node.appendChild(typeof c === "string" ? document.createTextNode(c) : c));
    return node;
  }

  function escapeHtml(value) {
    return String(value === null || value === undefined ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  return { api, toast, pollJob, fmt, el, escapeHtml };
})();
