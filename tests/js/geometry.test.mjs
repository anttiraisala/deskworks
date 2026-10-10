// Checks the editor's JavaScript geometry against tests/vectors/geometry.json.
// Run by tests/test_editor.py when node is installed:  node tests/js/geometry.test.mjs
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const root = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const html = readFileSync(join(root, "src/tilepane/editor/editor.html"), "utf8");
const m = /\/\/ BEGIN GEOMETRY([\s\S]*?)\/\/ END GEOMETRY/.exec(html);
if (!m) throw new Error("geometry block not found in editor.html");
const Geometry = new Function(`${m[1]}; return Geometry;`)();

const cases = JSON.parse(readFileSync(join(root, "tests/vectors/geometry.json"), "utf8"));
let failed = 0;
for (const c of cases) {
  const [x, y, width, height] = c.area;
  let got;
  try {
    got = Geometry.compute(c.layout, { x, y, width, height }).map((l) => [
      l.id, l.rect.x, l.rect.y, l.rect.width, l.rect.height, l.outer.x, l.outer.y, l.outer.width, l.outer.height]);
  } catch (e) {
    if (!(e instanceof Geometry.GeometryError)) throw e;
    got = null;
  }
  if (JSON.stringify(got) !== JSON.stringify(c.expected)) {
    failed++;
    if (failed <= 5) console.log(`MISMATCH ${c.name}\n  python ${JSON.stringify(c.expected)}\n  js     ${JSON.stringify(got)}`);
  }
}
console.log(`${cases.length - failed}/${cases.length} geometry vectors match`);
process.exit(failed ? 1 : 0);
