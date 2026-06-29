/* Parity check: the client-side JS optimizer (web/optimizer.js) must agree with the Python
 * reference (optimizer/model.py) on the shared fixture + scenarios.
 *
 * Run:  node optimizer/tests/parity.mjs
 * It shells out to Python to produce the reference outputs, runs the JS optimizer on the same
 * scenarios, and compares a canonical projection of each result.
 */
import { createRequire } from "module";
import { execFileSync } from "child_process";
import { readFileSync } from "fs";
import { fileURLToPath } from "url";
import path from "path";

const require = createRequire(import.meta.url);
const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..", "..");

const RecipOptimizer = require(path.join(root, "web", "optimizer.js"));
const dataset = JSON.parse(readFileSync(path.join(here, "fixture_dataset.json")));
const scenarios = JSON.parse(readFileSync(path.join(here, "parity_scenarios.json")));

// Canonical projection: the fields that must match exactly across implementations.
function project(out) {
  return {
    feasible: out.feasible,
    covered_all: out.covered_all,
    total_cost: out.total_cost,
    recommendation: (out.recommendation || [])
      .map((r) => `${r.institution_id}:${r.tier_name}:${r.annual_price_usd}`)
      .sort(),
    coverage: Object.fromEntries((out.coverage || []).map((c) => [c.id, c.status])),
    pre_covered: out.pre_covered || [],
    savings: out.savings
      ? { total_avoided: out.savings.total_avoided, membership_cost: out.savings.membership_cost, net_savings: out.savings.net_savings }
      : null,
  };
}

// Reference outputs from Python.
const py = JSON.parse(
  execFileSync("python3", [path.join(here, "gen_expected.py")], { cwd: root, encoding: "utf8" })
);

let failures = 0;
for (const sc of scenarios) {
  const jsOut = project(RecipOptimizer.optimize(dataset, structuredClone(sc.inputs)));
  const pyOut = py[sc.name];
  const a = JSON.stringify(jsOut), b = JSON.stringify(pyOut);
  if (a === b) {
    console.log(`  ok    ${sc.name}`);
  } else {
    failures++;
    console.log(`  FAIL  ${sc.name}`);
    console.log(`    js: ${a}`);
    console.log(`    py: ${b}`);
  }
}

if (failures) {
  console.error(`\nparity: ${failures} scenario(s) diverged`);
  process.exit(1);
}
console.log(`\nparity: all ${scenarios.length} scenarios agree`);
