/* RecipCheck client-side optimizer — faithful port of optimizer/rules.py + model.py.
 *
 * Pure, deterministic, no DOM. Works in the browser (window.RecipOptimizer) and in Node
 * (module.exports) so optimizer/tests/parity.mjs can check it against the Python reference
 * on the shared fixture.
 */
(function (root) {
  "use strict";

  const ADULT_AGE = 18;
  const EARTH_RADIUS_MILES = 3958.7613;
  const FULL = "full_free";
  const PARTIAL_TYPES = new Set(["fifty_percent", "discount_varies"]);

  // ---------------------------------------------------------------- rules
  function haversine(lat1, lng1, lat2, lng2) {
    const r = Math.PI / 180;
    const p1 = lat1 * r, p2 = lat2 * r;
    const dphi = (lat2 - lat1) * r, dlmb = (lng2 - lng1) * r;
    const a = Math.sin(dphi / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dlmb / 2) ** 2;
    return 2 * EARTH_RADIUS_MILES * Math.asin(Math.sqrt(a));
  }

  function splitHousehold(ages, childFreeUnderAge) {
    const free = childFreeUnderAge || 0;
    let adults = 0, children = 0;
    for (const a of ages) {
      if (a >= ADULT_AGE) adults++;
      else if (a >= free) children++;
    }
    return [adults, children];
  }

  function tierFits(tier, ages, guests) {
    const [adults, children] = splitHousehold(ages, tier.child_free_under_age);
    const capAdults = tier.adults_admitted;
    const capChildren = tier.children_admitted;
    const named = tier.named_guests_allowed || 0;
    let ok = true;
    if (capAdults !== null && capAdults !== undefined) ok = ok && (capAdults + named) >= (adults + guests);
    if (capChildren !== null && capChildren !== undefined) ok = ok && capChildren >= children;
    return ok;
  }

  function distanceClears(program, home, cand, target) {
    const d = program.distance_miles || 0;
    const basis = program.distance_basis || "none";
    if (d <= 0 || basis === "none") return true;
    const checks = [];
    if (basis === "residence" || basis === "both") checks.push(haversine(home[0], home[1], target[0], target[1]));
    if (basis === "home_institution" || basis === "both") checks.push(haversine(cand[0], cand[1], target[0], target[1]));
    return checks.every((dist) => dist >= d);
  }

  function resolvedReciprocity(target, programCode, programs) {
    const ov = (target.reciprocity_overrides || {})[programCode];
    if (ov) return ov;
    return (programs[programCode] || {}).reciprocity_type || "varies";
  }

  function coverageFor(target, candInst, tier, home, programs) {
    const candLL = [candInst.lat, candInst.lng];
    const tgtLL = [target.lat, target.lng];
    if (candInst.id === target.id) return { status: "own", program: null, reason: "own membership" };
    if ((target.flags || []).includes("non_participating"))
      return { status: "no_program", program: null, reason: "target non-participating" };

    const tierProgs = new Set(tier.programs_unlocked || []);
    const shared = (target.programs || []).filter((p) => tierProgs.has(p));
    if (shared.length === 0) return { status: "no_program", program: null, reason: "no shared program" };

    let best = { status: "no_program", program: null, reason: "no shared program" };
    for (const p of shared) {
      const prog = programs[p] || {};
      if (!distanceClears(prog, home, candLL, tgtLL)) {
        if (best.status === "no_program")
          best = { status: "blocked_distance", program: p, reason: `within ${prog.distance_miles}mi exclusion (${p})` };
        continue;
      }
      const rtype = resolvedReciprocity(target, p, programs);
      if (rtype === FULL) return { status: "full", program: p, reason: `free via ${p}` };
      if (PARTIAL_TYPES.has(rtype) && best.status !== "full")
        best = { status: "partial", program: p, reason: `${rtype} via ${p}` };
    }
    return best;
  }

  function admissionCost(target, ages, guests) {
    const ga = target.general_admission || {};
    const adult = ga.adult_price_usd;
    let child = ga.child_price_usd;
    const free = ga.child_free_under_age || 0;
    if (adult === null || adult === undefined) return 0;
    if (child === null || child === undefined) child = adult;
    let total = 0;
    for (const a of ages) {
      if (a >= ADULT_AGE) total += adult;
      else if (a >= free) total += child;
    }
    return total + guests * adult;
  }

  // ---------------------------------------------------------------- model
  const RANK = { own: 3, full: 3, partial: 2, blocked_distance: 1, no_program: 0 };
  const isCoveredFree = (s) => s === "full" || s === "own";

  function reciprocityBearingTiers(inst) {
    return (inst.tiers || []).filter((t) => (t.programs_unlocked || []).length > 0);
  }

  function buildCandidates(dataset, inputs, targets) {
    const { ages } = inputs;
    const guests = inputs.guests || 0;
    const map = new Map();
    for (const inst of dataset.institutions) {
      for (const tier of reciprocityBearingTiers(inst)) {
        if (tier.annual_price_usd === null || tier.annual_price_usd === undefined) continue;
        if (!tierFits(tier, ages, guests)) continue;
        map.set(`${inst.id}:${tier.name}`, { inst, tier });
      }
    }
    for (const tgt of targets) {
      for (const tier of tgt.tiers || []) {
        if (tier.annual_price_usd === null || tier.annual_price_usd === undefined) continue;
        if (!tierFits(tier, ages, guests)) continue;
        map.set(`${tgt.id}:${tier.name}`, { inst: tgt, tier });
      }
    }
    return [...map.values()];
  }

  function setCoverage(cset, targets, home, programs, preCovered) {
    const result = {};
    for (const tgt of targets) {
      if (preCovered.has(tgt.id)) { result[tgt.id] = { status: "full", program: null, reason: "already held" }; continue; }
      let best = { status: "no_program", program: null, reason: "no coverage" };
      for (const c of cset) {
        const cov = coverageFor(tgt, c.inst, c.tier, home, programs);
        if (RANK[cov.status] > RANK[best.status]) best = cov;
      }
      result[tgt.id] = best;
    }
    return result;
  }

  function breadth(cset, dataset, home, programs) {
    const reach = new Set();
    for (const inst of dataset.institutions) {
      for (const c of cset) {
        const cov = coverageFor(inst, c.inst, c.tier, home, programs);
        if (isCoveredFree(cov.status)) { reach.add(inst.id); break; }
      }
    }
    return reach.size;
  }

  function computeSavings(cset, targets, coverage, inputs, idx) {
    const { ages } = inputs;
    const guests = inputs.guests || 0;
    const factor = (inputs.visit_window_months || 12) / 12;
    const perTarget = [];
    let totalAvoided = 0;
    for (const tgt of targets) {
      const cov = coverage[tgt.id];
      const visits = (tgt.visits_per_year || 0) * factor;
      const full = admissionCost(idx[tgt.id], ages, guests);
      let value = 0;
      if (cov.status === "full" || cov.status === "own") value = visits * full;
      else if (cov.status === "partial") value = visits * full * 0.5;
      totalAvoided += value;
      perTarget.push({
        id: tgt.id, name: idx[tgt.id].name, visits_per_year: tgt.visits_per_year || 0,
        per_visit_admission: round2(full), status: cov.status, avoided_value: round2(value),
      });
    }
    const cost = cset.reduce((s, c) => s + c.tier.annual_price_usd, 0);
    return { per_target: perTarget, total_avoided: round2(totalAvoided), membership_cost: round2(cost), net_savings: round2(totalAvoided - cost) };
  }

  const round2 = (x) => Math.round(x * 100) / 100;

  function optimize(dataset, inputs) {
    const programs = dataset.programs;
    const idx = {};
    for (const i of dataset.institutions) idx[i.id] = i;
    const home = inputs.home;
    const cap = Math.max(1, inputs.membership_cap || 2);
    const objective = inputs.objective || "must_cover_all";
    const anchor = inputs.anchor || { mode: "cheapest" };
    const valueUnplanned = !!inputs.value_unplanned;

    const targets = [];
    for (const t of inputs.targets) {
      if (idx[t.id]) { idx[t.id].visits_per_year = t.visits_per_year || 0; targets.push(idx[t.id]); }
    }

    const existing = new Set(inputs.existing || []);
    const preCovered = new Set();
    for (const tgt of targets) {
      for (const eid of existing) {
        const einst = idx[eid];
        if (!einst) continue;
        const tiers = reciprocityBearingTiers(einst);
        const probe = tiers.length ? tiers : [{}];
        for (const tier of probe) {
          const cov = coverageFor(tgt, einst, tier, home, programs);
          if (isCoveredFree(cov.status) || tgt.id === eid) preCovered.add(tgt.id);
        }
      }
    }

    const candidates = buildCandidates(dataset, inputs, targets);
    const sets = [[]];
    for (const c of candidates) sets.push([c]);
    if (cap >= 2) {
      const seen = new Set();
      for (let i = 0; i < candidates.length; i++) {
        for (let j = i + 1; j < candidates.length; j++) {
          const a = candidates[i], b = candidates[j];
          if (a.inst.id === b.inst.id) continue;
          const key = [`${a.inst.id}:${a.tier.name}`, `${b.inst.id}:${b.tier.name}`].sort().join("|");
          if (seen.has(key)) continue;
          seen.add(key);
          sets.push([a, b]);
        }
      }
    }

    const scored = sets.map((cset) => {
      const coverage = setCoverage(cset, targets, home, programs, preCovered);
      const coveredFree = targets.filter((t) => isCoveredFree(coverage[t.id].status));
      const visitValue = coveredFree.reduce((s, t) => s + (t.visits_per_year || 0), 0);
      const cost = cset.reduce((s, c) => s + c.tier.annual_price_usd, 0);
      return { cset, coverage, coveredFree, visitValue, cost };
    });

    const nTargets = targets.length;
    const anchorHit = (cset) =>
      anchor.mode === "anchor" && anchor.institution_id && cset.some((c) => c.inst.id === anchor.institution_id);

    let best, alternatives;
    const cmp = (keyFn) => (x, y) => {
      const kx = keyFn(x), ky = keyFn(y);
      for (let i = 0; i < kx.length; i++) { if (kx[i] < ky[i]) return -1; if (kx[i] > ky[i]) return 1; }
      return 0;
    };

    if (objective === "must_cover_all") {
      const pool = scored.filter((s) => s.coveredFree.length === nTargets && nTargets > 0);
      if (pool.length) {
        pool.sort(cmp((s) => [s.cost, -(valueUnplanned ? breadth(s.cset, dataset, home, programs) : 0), anchorHit(s.cset) ? 0 : 1, s.cset.length]));
        best = pool[0]; alternatives = pool.slice(1, 4);
      } else {
        scored.sort(cmp((s) => [-s.visitValue, s.cost]));
        best = scored[0]; alternatives = scored.slice(1, 4);
      }
    } else {
      scored.sort(cmp((s) => [-s.visitValue, s.cost, -(valueUnplanned ? breadth(s.cset, dataset, home, programs) : 0), anchorHit(s.cset) ? 0 : 1, s.cset.length]));
      best = scored[0]; alternatives = scored.slice(1, 4);
    }

    return formatOutput(best, alternatives, targets, idx, inputs, programs, dataset, preCovered);
  }

  function formatOutput(best, alternatives, targets, idx, inputs, programs, dataset, preCovered) {
    if (!best) return { feasible: false, reason: "no candidates", coverage: [], recommendation: [] };
    const { cset, coverage, coveredFree, cost } = best;
    const savings = computeSavings(cset, targets, coverage, inputs, idx);
    const rec = cset.map((c) => ({
      institution_id: c.inst.id, institution_name: c.inst.name, tier_name: c.tier.name,
      annual_price_usd: c.tier.annual_price_usd, programs_unlocked: c.tier.programs_unlocked || [],
      flags: c.inst.flags || [],
    }));
    const nTargets = targets.length;
    const coveredAll = coveredFree.length === nTargets && nTargets > 0;
    const coverageRows = targets.map((t) => ({
      id: t.id, name: idx[t.id].name, status: coverage[t.id].status,
      program: coverage[t.id].program, reason: coverage[t.id].reason, flags: idx[t.id].flags || [],
    }));
    const uncovered = targets.filter((t) => !isCoveredFree(coverage[t.id].status))
      .map((t) => ({ id: t.id, name: idx[t.id].name, status: coverage[t.id].status, reason: coverage[t.id].reason }));
    const altOut = alternatives.map((a) => ({
      recommendation: a.cset.map((c) => ({ institution_name: c.inst.name, tier_name: c.tier.name, annual_price_usd: c.tier.annual_price_usd })),
      total_cost: round2(a.cost), covered_count: a.coveredFree.length,
    }));
    const FLAGSET = new Set(["stale", "needs_manual", "non_participating", "possibly_closed", "js_only_page"]);
    const flags = [...new Set(cset.flatMap((c) => (c.inst.flags || []).filter((f) => FLAGSET.has(f))))].sort();
    return {
      feasible: true, objective: inputs.objective || "must_cover_all", covered_all: coveredAll,
      recommendation: rec, total_cost: round2(cost), coverage: coverageRows, uncovered,
      savings, alternatives: altOut, pre_covered: [...preCovered].sort(), flags, build: dataset.build,
    };
  }

  const api = { optimize, haversine, coverageFor, tierFits, admissionCost, splitHousehold };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.RecipOptimizer = api;
})(typeof window !== "undefined" ? window : globalThis);
