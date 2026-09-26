/* Brands & keywords: create, edit, delete brands and manage keywords. */
(function () {
  const TIERS = [["target", "Target"], ["brand", "Brand"], ["seed", "Seed"]];

  async function load() {
    const { brands } = await SVP.api("/api/brands");
    const mount = document.getElementById("brands");
    mount.innerHTML = "";
    if (!brands.length) {
      mount.innerHTML = '<div class="panel"><div class="empty">No brands yet. Create your first one above.</div></div>';
      return;
    }
    brands.forEach((b) => mount.appendChild(renderBrand(b)));
  }

  function field(label, value, cls) {
    const wrap = SVP.el("div", { class: "field" });
    wrap.appendChild(SVP.el("label", { text: label }));
    wrap.appendChild(SVP.el("input", { class: "input " + (cls || ""), value: value }));
    return wrap;
  }

  function renderBrand(b) {
    const panel = SVP.el("div", { class: "panel" });
    const head = SVP.el("div", { class: "panel-head" });
    head.appendChild(SVP.el("h3", { text: b.name }));
    head.appendChild(SVP.el("span", { class: "meta", text: b.domain + " · " + b.keywords.length + " keywords" }));
    panel.appendChild(head);

    const body = SVP.el("div", { class: "panel-body" });

    const grid = SVP.el("div", { class: "split", style: "grid-template-columns:1fr 1fr 150px 130px" });
    const nameField = field("Brand name", b.name);
    const domField = field("Domain", b.domain);
    const locField = field("Location code", b.location_code);
    const langField = field("Language", b.language_code);
    grid.appendChild(SVP.el("div", { style: "padding:0" }, [nameField]));
    grid.appendChild(SVP.el("div", { style: "padding:0 0 0 18px" }, [domField]));
    grid.appendChild(SVP.el("div", { style: "padding:0 0 0 18px" }, [locField]));
    grid.appendChild(SVP.el("div", { style: "padding:0 0 0 18px" }, [langField]));
    body.appendChild(grid);

    const actions = SVP.el("div", { style: "display:flex;gap:10px;justify-content:flex-end;margin-bottom:6px" });
    const save = SVP.el("button", { class: "btn btn-sm btn-primary", text: "Save brand" });
    save.onclick = async () => {
      try {
        await SVP.api("/api/brands/" + b.id, {
          method: "PUT",
          body: JSON.stringify({
            name: nameField.querySelector("input").value,
            domain: domField.querySelector("input").value,
            location_code: parseInt(locField.querySelector("input").value, 10) || 2840,
            language_code: langField.querySelector("input").value || "en",
          }),
        });
        SVP.toast("Brand saved", "ok");
        await load();
      } catch (e) { SVP.toast(e.message, "err"); }
    };
    const del = SVP.el("button", { class: "btn btn-sm btn-danger", text: "Delete" });
    del.onclick = async () => {
      if (!confirm("Delete " + b.name + " and all its keywords/history?")) return;
      try {
        await SVP.api("/api/brands/" + b.id, { method: "DELETE" });
        SVP.toast("Brand deleted");
        await load();
      } catch (e) { SVP.toast(e.message, "err"); }
    };
    actions.appendChild(del);
    actions.appendChild(save);
    body.appendChild(actions);

    TIERS.forEach(([tier, label]) => {
      const kws = b.keywords.filter((k) => k.tier === tier);
      const row = SVP.el("div", { style: "margin-top:12px" });
      row.appendChild(SVP.el("div", { class: "sublbl", text: label + " · " + kws.length }));
      const chips = SVP.el("div", { class: "chips" });
      kws.forEach((k) => {
        const chip = SVP.el("span", { class: "chip", style: "display:inline-flex;align-items:center" });
        chip.appendChild(SVP.el("span", { text: k.keyword }));
        const x = SVP.el("span", { class: "chip-x", text: "✕", title: "Remove keyword" });
        x.style.display = "inline";
        x.onclick = async () => {
          try { await SVP.api("/api/keywords/" + k.id, { method: "DELETE" }); await load(); }
          catch (e) { SVP.toast(e.message, "err"); }
        };
        chip.appendChild(x);
        chips.appendChild(chip);
      });
      if (!kws.length) chips.appendChild(SVP.el("span", { class: "who", style: "color:var(--muted)", text: "none" }));
      row.appendChild(chips);
      body.appendChild(row);
    });

    const addRow = SVP.el("div", { style: "display:flex;gap:10px;margin-top:18px;flex-wrap:wrap" });
    const input = SVP.el("input", { class: "input", placeholder: "Add a keyword…", style: "max-width:340px" });
    const select = SVP.el("select", { class: "input", style: "max-width:150px" });
    TIERS.forEach(([v, l]) => select.appendChild(SVP.el("option", { value: v, text: l })));
    const add = SVP.el("button", { class: "btn btn-sm btn-primary", text: "Add" });
    const doAdd = async () => {
      const kw = input.value.trim();
      if (!kw) return;
      try {
        await SVP.api("/api/brands/" + b.id + "/keywords", {
          method: "POST", body: JSON.stringify({ keyword: kw, tier: select.value }),
        });
        input.value = "";
        await load();
      } catch (e) { SVP.toast(e.message, "err"); }
    };
    add.onclick = doAdd;
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") doAdd(); });
    addRow.appendChild(input);
    addRow.appendChild(select);
    addRow.appendChild(add);
    body.appendChild(addRow);

    panel.appendChild(body);
    return panel;
  }

  function bindCreate() {
    const panel = document.getElementById("create-panel");
    document.getElementById("new-brand").onclick = () => { panel.hidden = !panel.hidden; };
    document.getElementById("c-cancel").onclick = () => { panel.hidden = true; };
    document.getElementById("c-save").onclick = async () => {
      const name = document.getElementById("c-name").value.trim();
      const domain = document.getElementById("c-domain").value.trim();
      if (!name || !domain) { SVP.toast("Name and domain are required", "err"); return; }
      try {
        await SVP.api("/api/brands", {
          method: "POST",
          body: JSON.stringify({
            name, domain,
            location_code: parseInt(document.getElementById("c-loc").value, 10) || 2840,
            language_code: document.getElementById("c-lang").value || "en",
          }),
        });
        panel.hidden = true;
        ["c-name", "c-domain"].forEach((id) => { document.getElementById(id).value = ""; });
        SVP.toast("Brand created", "ok");
        await load();
      } catch (e) { SVP.toast(e.message, "err"); }
    };
  }

  bindCreate();
  load().catch((e) => SVP.toast(e.message, "err"));
})();
