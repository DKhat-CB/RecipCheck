/* RecipCheck UI controller — loads the compiled dataset + ZIP table, drives the form
   (progressive disclosure, derive-don't-ask), runs the client-side optimizer, renders results. */
(function () {
  "use strict";

  const $ = (s, r = document) => r.querySelector(s);
  const el = (tag, cls, html) => { const n = document.createElement(tag); if (cls) n.className = cls; if (html != null) n.innerHTML = html; return n; };
  const money = (x) => "$" + (Math.round(x * 100) / 100).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 });

  let DATA = null, ZIPS = null;
  const MAX_TARGETS = 5;

  const STATUS_LABEL = {
    full: "Free", own: "Your card", partial: "50% off",
    blocked_distance: "90-mile block", no_program: "No coverage",
  };
  const FLAG_LABEL = {
    non_participating: "doesn't honor reciprocity — join directly",
    manually_verified: "hand-verified data",
    stale: "data may be stale", needs_manual: "needs manual check",
    possibly_closed: "may have closed", js_only_page: "page not auto-readable",
  };

  // ------------------------------------------------------------------- boot
  Promise.all([
    fetch("dataset.json").then((r) => r.json()),
    fetch("zips.json").then((r) => r.json()),
  ]).then(([data, zips]) => {
    DATA = data; ZIPS = zips;
    initMetros();
    addAge(40); addAge(38); addAge(7);
    addTarget();
    wire();
    if (DATA.build) $("#build-stamp").textContent = `Dataset build ${DATA.build.build_id} · ${DATA.institutions.length} institutions`;
  }).catch((e) => {
    document.querySelector("main").innerHTML = `<p class="error">Could not load the dataset: ${e}</p>`;
  });

  function metroInstitutions(metro) {
    return DATA.institutions.filter((i) => i.metro === metro).sort((a, b) => a.name.localeCompare(b.name));
  }

  function initMetros() {
    const sel = $("#metro");
    for (const [key, m] of Object.entries(DATA.metros)) sel.append(new Option(m.label, key));
    sel.value = Object.keys(DATA.metros)[0];
    sel.addEventListener("change", onMetroChange);
    onMetroChange();
  }

  function onMetroChange() {
    refreshTargetOptions();
    const metro = $("#metro").value;
    const insts = metroInstitutions(metro);
    const anchor = $("#anchor-place"); anchor.innerHTML = "";
    const existing = $("#existing"); existing.innerHTML = "";
    for (const i of insts) {
      anchor.append(new Option(i.name, i.id));
      existing.append(new Option(i.name, i.id));
    }
  }

  // ------------------------------------------------------------------- ages
  function addAge(val) {
    const chip = el("span", "chip");
    chip.innerHTML = `<input type="number" min="0" max="120" value="${val != null ? val : 30}" aria-label="age" /><button type="button" title="remove">×</button>`;
    chip.querySelector("button").onclick = () => chip.remove();
    $("#ages").append(chip);
  }

  // ------------------------------------------------------------------- targets
  function addTarget() {
    const rows = $("#targets").querySelectorAll(".target-row").length;
    if (rows >= MAX_TARGETS) return;
    const row = el("div", "target-row");
    const tsel = el("select"); tsel.setAttribute("aria-label", "place");
    const visits = el("div", "field visits");
    visits.innerHTML = `<label>visits / yr</label><input type="number" min="1" value="4" aria-label="visits per year" />`;
    const del = el("button", "del", "remove"); del.type = "button";
    del.onclick = () => { row.remove(); updateAddTargetBtn(); };
    row.append(tsel, visits, del);
    $("#targets").append(row);
    fillTargetSelect(tsel);
    updateAddTargetBtn();
  }

  function fillTargetSelect(sel) {
    const cur = sel.value;
    sel.innerHTML = "";
    for (const i of metroInstitutions($("#metro").value)) sel.append(new Option(i.name, i.id));
    if (cur) sel.value = cur;
  }
  function refreshTargetOptions() { $("#targets").querySelectorAll(".target-row select").forEach(fillTargetSelect); }
  function updateAddTargetBtn() {
    $("#add-target").style.display = $("#targets").querySelectorAll(".target-row").length >= MAX_TARGETS ? "none" : "";
  }

  // ------------------------------------------------------------------- wiring
  function wire() {
    $("#add-age").onclick = () => addAge(10);
    $("#add-target").onclick = addTarget;
    $("#anchor-mode").onchange = (e) => { $("#anchor-place-field").hidden = e.target.value !== "anchor"; };
    $("#zip").addEventListener("input", onZip);
    $("#form").addEventListener("submit", onSubmit);
  }

  function onZip() {
    const z = $("#zip").value.trim().slice(0, 5);
    const hint = $("#zip-hint");
    if (z.length < 5) { hint.textContent = ""; return; }
    const ll = ZIPS[z];
    if (!ll) { hint.innerHTML = `<span class="error">ZIP not in the Bay Area / NYC coverage table.</span>`; return; }
    // derive-don't-ask: name the nearest in-scope metro center
    let best = null;
    for (const [key, m] of Object.entries(DATA.metros)) {
      const d = RecipOptimizer.haversine(ll[0], ll[1], m.center.lat, m.center.lng);
      if (!best || d < best.d) best = { key, label: m.label, d };
    }
    hint.textContent = `Recognized · ~${Math.round(best.d)} mi from ${best.label} center`;
  }

  function gatherInputs() {
    const ages = [...$("#ages").querySelectorAll("input")].map((i) => parseInt(i.value, 10)).filter((n) => !isNaN(n));
    const z = $("#zip").value.trim().slice(0, 5);
    const home = ZIPS[z];
    const targets = [...$("#targets").querySelectorAll(".target-row")].map((r) => ({
      id: r.querySelector("select").value,
      visits_per_year: parseInt(r.querySelector(".visits input").value, 10) || 0,
    })).filter((t) => t.id);
    // de-dup targets by id (keep first)
    const seen = new Set(); const uniqTargets = [];
    for (const t of targets) { if (!seen.has(t.id)) { seen.add(t.id); uniqTargets.push(t); } }

    const anchorMode = $("#anchor-mode").value;
    return {
      ages, home, _zip: z,
      guests: parseInt($("#guests").value, 10) || 0,
      targets: uniqTargets,
      objective: $("#objective").value,
      membership_cap: parseInt($("#cap").value, 10),
      anchor: { mode: anchorMode, institution_id: anchorMode === "anchor" ? $("#anchor-place").value : null },
      existing: [...$("#existing").selectedOptions].map((o) => o.value),
      value_unplanned: $("#unplanned").checked,
      visit_window_months: parseInt($("#window").value, 10) || 12,
    };
  }

  function onSubmit(e) {
    e.preventDefault();
    const inputs = gatherInputs();
    const box = $("#results");
    box.hidden = false;
    if (!inputs.home) { box.innerHTML = `<div class="rcard"><p class="error">Enter a valid Bay Area or NYC ZIP code.</p></div>`; scrollToResults(); return; }
    if (!inputs.targets.length) { box.innerHTML = `<div class="rcard"><p class="error">Add at least one place you'd visit.</p></div>`; scrollToResults(); return; }
    if (!inputs.ages.length) { box.innerHTML = `<div class="rcard"><p class="error">Add at least one family member.</p></div>`; scrollToResults(); return; }
    const out = RecipOptimizer.optimize(DATA, inputs);
    render(out, inputs);
    scrollToResults();
  }

  const scrollToResults = () => $("#results").scrollIntoView({ behavior: "smooth", block: "start" });

  // ------------------------------------------------------------------- render
  function render(out, inputs) {
    const box = $("#results");
    box.innerHTML = "";
    if (!out.feasible) { box.append(card("No recommendation", `<p class="error">${out.reason || "No options found."}</p>`)); return; }

    box.append(recommendationCard(out));
    box.append(coverageCard(out, inputs));
    box.append(savingsCard(out));
    if (out.alternatives && out.alternatives.length) box.append(alternativesCard(out));
    const flags = collectFlags(out);
    if (flags.length) box.append(flagsCard(flags));
  }

  function card(title, bodyHTML) {
    const c = el("section", "rcard");
    c.append(el("h2", null, title));
    const body = el("div"); body.innerHTML = bodyHTML; c.append(body);
    return c;
  }

  function recommendationCard(out) {
    const c = el("section", "rcard");
    c.append(el("h2", null, "Recommendation"));
    if (!out.recommendation.length) {
      c.append(el("div", "banner ok", "You already hold everything you need — buy nothing."));
      return c;
    }
    const head = el("div", "headline");
    head.append(el("span", "cost", money(out.total_cost)));
    head.append(el("span", "per", "per year, total"));
    c.append(head);

    const banner = out.covered_all
      ? el("div", "banner ok", "✓ Covers every place on your list.")
      : el("div", "banner warn", `Covers ${out.coverage.filter((r) => r.status === "full" || r.status === "own").length} of ${out.coverage.length}. Some places can't be reached — see below.`);
    banner.style.margin = "12px 0";
    c.append(banner);

    const list = el("ul", "rec-list");
    for (const r of out.recommendation) {
      const item = el("li", "rec-item");
      const left = el("div");
      left.append(el("div", "who", r.institution_name));
      const tier = el("div", "tier", `${r.tier_name} membership`);
      for (const p of r.programs_unlocked) tier.append(pill(p));
      left.append(tier);
      item.append(left);
      item.append(el("div", "price", money(r.annual_price_usd)));
      list.append(item);
    }
    c.append(list);
    return c;
  }

  function pill(text) { const p = el("span", "pill prog", text); return p; }

  function coverageCard(out, inputs) {
    const c = el("section", "rcard");
    c.append(el("h2", null, "Coverage map"));
    const grid = el("div", "cov");
    let hasBlock = false;
    for (const row of out.coverage) {
      const r = el("div", `cov-row ${row.status}`);
      r.append(el("span", "dot"));
      const mid = el("div");
      mid.append(el("div", "name", row.name));
      mid.append(el("div", "why", row.reason || ""));
      r.append(mid);
      r.append(el("div", "status", STATUS_LABEL[row.status] || row.status));
      grid.append(r);
      if (row.status === "blocked_distance") hasBlock = true;
    }
    c.append(grid);
    if (hasBlock) {
      c.append(el("div", "block-note",
        "<strong>The 90-mile rule.</strong> A place within ~90 miles of your home (or of the card you'd buy) " +
        "can't be reached through reciprocity — programs exclude nearby institutions. Join those directly or pay per visit."));
    }
    return c;
  }

  function savingsCard(out) {
    const s = out.savings;
    const c = el("section", "rcard");
    c.append(el("h2", null, "Savings vs. paying per visit"));
    const t = el("table", "savings");
    t.innerHTML = `<thead><tr><th>Place</th><th>Visits/yr</th><th>Per visit</th><th>Status</th><th>Avoided</th></tr></thead>`;
    const tb = el("tbody");
    for (const r of s.per_target) {
      const tr = el("tr");
      tr.innerHTML = `<td>${r.name}</td><td>${r.visits_per_year}</td><td>${money(r.per_visit_admission)}</td>` +
        `<td>${STATUS_LABEL[r.status] || r.status}</td><td>${money(r.avoided_value)}</td>`;
      tb.append(tr);
    }
    t.append(tb);
    t.append(el("tfoot", null,
      `<tr><td>Admission avoided</td><td></td><td></td><td></td><td>${money(s.total_avoided)}</td></tr>` +
      `<tr><td>Membership cost</td><td></td><td></td><td></td><td>−${money(s.membership_cost)}</td></tr>`));
    c.append(t);
    const net = el("p");
    const cls = s.net_savings >= 0 ? "pos" : "neg";
    net.innerHTML = `Net annual ${s.net_savings >= 0 ? "savings" : "cost"}: <span class="net ${cls}">${money(Math.abs(s.net_savings))}</span>`;
    c.append(net);
    return c;
  }

  function alternativesCard(out) {
    const c = el("section", "rcard");
    c.append(el("h2", null, "Other options"));
    const wrap = el("div", "alts");
    for (const a of out.alternatives) {
      const names = a.recommendation.map((r) => `${r.institution_name} (${r.tier_name})`).join(" + ") || "buy nothing";
      const row = el("div", "alt");
      row.append(el("span", null, `${names} — covers ${a.covered_count}`));
      row.append(el("strong", null, money(a.total_cost)));
      wrap.append(row);
    }
    c.append(wrap);
    return c;
  }

  function collectFlags(out) {
    const set = new Map();
    for (const f of out.flags || []) set.set(f, FLAG_LABEL[f] || f);
    for (const row of out.coverage) for (const f of row.flags || []) if (f !== "manually_verified") set.set(f, FLAG_LABEL[f] || f);
    return [...set.entries()];
  }

  function flagsCard(flags) {
    const c = el("section", "rcard");
    c.append(el("h2", null, "Notes & caveats"));
    const wrap = el("div", "flags");
    for (const [key, label] of flags) {
      const warn = ["non_participating", "stale", "possibly_closed", "needs_manual"].includes(key);
      wrap.append(el("span", "flag" + (warn ? " warn" : ""), label));
    }
    c.append(wrap);
    return c;
  }
})();
