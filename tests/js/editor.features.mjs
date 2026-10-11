// Checks editor features in Chromium with the page opened as a file (no server):
// unselecting, command lines, swapping panes, settings moving up the tree,
// resizing the preview monitor and the margin control.
//   node tests/js/editor.features.mjs
import { createRequire } from "node:module";
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, join } from "node:path";

const require = createRequire(process.env.PLAYWRIGHT_DIR || "/opt/node-tools/node_modules/");
const { chromium } = require("playwright");
const root = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const url = pathToFileURL(join(root, "src/tilepane/editor/editor.html")).href;

const browser = await chromium.launch(process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : {});
const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
page.on("dialog", (d) => d.accept());
const expect = (cond, msg) => { if (!cond) throw new Error(`FAILED: ${msg}`); };
const step = (msg) => console.log(`- ${msg}`);
const doc = () => page.evaluate(() => JSON.parse(JSON.stringify(S.doc)));
const loadDoc = (d) => page.evaluate((text) => load(text, "test.json"), JSON.stringify(d));
const sel = () => page.evaluate(() => S.sel.kind);

await page.goto(url);
await page.waitForSelector(".pane");

// Unselect: click outside the monitor picture.
await page.locator(".pane").first().click();
expect((await sel()) === "pane", "pane selected");
expect((await page.textContent("#screen-tip")).includes("click outside the monitor"), "tip about unselecting");
const stage = await page.locator("#stage").boundingBox();
await page.mouse.click(stage.x + 8, stage.y + 8);
expect((await sel()) === "layout", "click outside the monitor clears the selection");
expect((await page.textContent("#screen-tip")).includes("click a pane"), "tip when nothing is selected");
step("click outside the monitor unselects");

// Command lines in the layout panel and the Commands dialog.
let code = await page.locator("#command-lines code").first().textContent();
expect(code === "tilepane my-layout.json", `open command (got ${code})`);
await page.click("#commands");
expect(await page.isVisible("#commands-dialog"), "commands dialog opens");
const lines = await page.locator("#commands-dialog code").allTextContents();
expect(lines.some((l) => l.startsWith("tilepane --toggle")) && lines.some((l) => l.startsWith("tilepane --edit")), "dialog lists the commands");
await page.click('#commands-dialog button:text-is("Close")');
expect(!(await page.isVisible("#commands-dialog")), "commands dialog closes");
step(`command lines: ${code}`);

// Splitting moves inheriting settings up; the command stays with the first half.
await loadDoc({ name: "t", split: { run: "htop", cwd: "/srv", shell: "zsh", title: "top" } });
await page.locator(".pane").first().click();
await page.click("text=Split ⇆ left | right");
let d = await doc();
expect(d.cwd === "/srv" && d.shell === "zsh", `settings moved up (got ${JSON.stringify(d)})`);
expect(JSON.stringify(d.split.a) === JSON.stringify({ run: "htop", title: "top" }) && JSON.stringify(d.split.b) === "{}", "first half keeps run and title");
step(`split: ${JSON.stringify(d)}`);

// Common settings rise: give both panes the same terminal.
await loadDoc({ name: "t", split: { dir: "columns", a: { run: "a", terminal: "xterm" }, b: { run: "b" } } });
await page.locator(".pane").nth(1).click();
await page.click("text=More settings").catch(() => {});
await page.fill('input[data-key="terminal"]', "xterm");
await page.locator('input[data-key="terminal"]').blur();
d = await doc();
expect(d.terminal === "xterm" && !("terminal" in d.split.a) && !("terminal" in d.split.b), `terminal moved to the layout (got ${JSON.stringify(d)})`);
step(`common setting moved up: ${JSON.stringify(d)}`);

// Swap by dragging: contents (with inherited settings) change places, sizes stay.
await loadDoc({ name: "t", split: { dir: "columns", at: "30%", a: { run: "left" },
  b: { dir: "rows", cwd: "/right", a: { run: "top" }, b: { run: "bottom" } } } });
const sizesBefore = await page.locator(".pane .meta").allTextContents();
const src = await page.locator(".pane").nth(0).boundingBox();
const dst = await page.locator(".pane").nth(2).boundingBox();
await page.mouse.move(src.x + src.width / 2, src.y + src.height / 2);
await page.mouse.down();
await page.mouse.move(dst.x + dst.width / 2, dst.y + dst.height / 2, { steps: 10 });
const ghost = await page.locator("#drag-ghost").boundingBox();
expect(ghost, "a copy of the pane is shown while dragging");
await page.waitForTimeout(150);
const landed = await page.locator("#drag-ghost").boundingBox();
expect(Math.abs(landed.x - dst.x) < 3 && Math.abs(landed.width - dst.width) < 3, `over a pane the copy takes its place (${JSON.stringify(landed)} vs ${JSON.stringify(dst)})`);
expect((await page.locator(".pane.drop-target").count()) === 1, "drop target highlighted");
await page.mouse.up();
expect((await page.locator("#drag-ghost").count()) === 0, "the copy is removed after the drop");
d = await doc();
const leftPane = d.split.a, bottomPane = d.split.b.b;
console.log("  after swap:", JSON.stringify(d));
expect(leftPane.run === "bottom" && (leftPane.cwd || d.cwd) === "/right", `bottom pane moved left with its cwd (got ${JSON.stringify(leftPane)})`);
expect(bottomPane.run === "left" && d.split.at === "30%", `left pane moved to the bottom (got ${JSON.stringify(d)})`);
expect(JSON.stringify(await page.locator(".pane .meta").allTextContents()) === JSON.stringify(sizesBefore), "sizes unchanged");
step(`swapped: ${JSON.stringify(d.split)}`);

// A pane using a default keeps it when it moves under a split that sets another value.
await loadDoc({ name: "t", split: { dir: "columns", a: { run: "plain" },
  b: { dir: "rows", shell: "zsh", a: { run: "z1" }, b: { run: "z2" } } } });
const p0 = await page.locator(".pane").nth(0).boundingBox();
const p2 = await page.locator(".pane").nth(2).boundingBox();
await page.mouse.move(p0.x + 20, p0.y + 20);
await page.mouse.down();
await page.mouse.move(p2.x + 30, p2.y + 30, { steps: 10 });
await page.mouse.up();
d = await doc();
const eff = await page.evaluate(() => [inheritedValues([0]).shell, S.doc.split.a.shell, inheritedValues([1, 1]).shell, S.doc.split.b.b.shell]);
expect((eff[1] || eff[0]) === "zsh" && (eff[3] || eff[2]) === "auto", `shells follow their panes (got ${JSON.stringify(d)})`);
step(`defaults travel too: ${JSON.stringify(d)}`);

// Resize the preview monitor from its corner; the size is shown in pixels.
await page.keyboard.press("Escape");
const before = await page.textContent("#monitor-size");
const corner = await page.locator(".mon-handle.se").boundingBox();
await page.mouse.move(corner.x + 7, corner.y + 7);
await page.mouse.down();
await page.mouse.move(corner.x - 120, corner.y - 60, { steps: 6 });
await page.mouse.up();
const after = await page.textContent("#monitor-size");
expect(after !== before && /^\d+0 × \d+0 px$/.test(after), `monitor size changed and rounded (${before} -> ${after})`);
expect((await page.locator("#monitor option[value=custom]").count()) === 1, "custom size in the monitor list");
await page.click("text=Reset size");
expect((await page.textContent("#monitor-size")) === before, "reset size");
step(`monitor resize: ${before} -> ${after} -> reset`);

// Margin control under the preview.
await page.click('#screenbar button[title="Larger gap"]');
d = await doc();
expect(d.margin === 9, `margin + (got ${d.margin})`);
await page.fill("#margin-input", "12");
await page.locator("#margin-input").blur();
expect((await doc()).margin === 12, "margin typed");
step("margin control");

// Workspace: chosen in the header, saved in the layout before its split.
await loadDoc({ name: "w", split: { run: "x" } });
await page.selectOption("#workspace", "4");
d = await doc();
expect(d.workspace === 4 && Object.keys(d).indexOf("workspace") < Object.keys(d).indexOf("split"), `workspace saved in the layout (got ${JSON.stringify(d)})`);
expect((await page.inputValue('input[data-key="workspace"]')) === "4", "layout panel shows the workspace");
await page.selectOption("#workspace", "");
expect(!("workspace" in (await doc())), "current removes it");
step("workspace select");

// Cut line across the whole monitor: every pane it crosses is cut, in the unit
// the pane was cut with before; the contents stay in the first piece.
await loadDoc({ name: "c", margin: 8, split: { dir: "columns", at: "60%", a: { run: "htop" },
  b: { dir: "rows", at: "300px", a: { run: "sensors" }, b: { run: "logs" } } } });
await page.keyboard.press("h");
expect(await page.isVisible("#cut-overlay"), "cut mode on");
const toScreen = async (x, y) => page.evaluate(([x, y]) => {
  const r = document.querySelector("#screen").getBoundingClientRect();
  return [r.left + x * S.view.scale, r.top + y * S.view.scale];
}, [x, y]);
let [cx, cy] = await toScreen(400, 640);
await page.mouse.move(cx, cy);
expect((await page.locator(".pane.cut-target").count()) === 2, "two panes marked for the cut");
await page.mouse.click(cx, cy);
d = await doc();
expect(d.split.a.dir === "rows" && /%$/.test(d.split.a.at) && d.split.a.a.run === "htop" && JSON.stringify(d.split.a.b) === "{}", `left pane cut in % (got ${JSON.stringify(d.split.a)})`);
expect(d.split.b.b.dir === "rows" && d.split.b.b.at === "340px" && d.split.b.b.a.run === "logs", `right pane cut in px (got ${JSON.stringify(d.split.b.b)})`);
const ys = await page.evaluate(() => S.geo.leaves.map((l) => l.outer.y));
expect(ys.filter((y) => y === 640).length === 2, `both pieces start at y=640 (got ${ys})`);
expect(!(await page.isVisible("#cut-overlay")), "cut mode ends after the cut");
step(`cut: ${JSON.stringify(d.split)}`);

// Merge with an arrow: the lower piece is empty, so it merges without asking.
await page.locator(".pane").first().click();
await page.click('.merge-btn[data-merge="below"]');
expect((await page.locator("dialog.tp-dialog").count()) === 0, "no question for an empty pane");
d = await doc();
expect(JSON.stringify(d.split.a) === JSON.stringify({ run: "htop" }), `merged back (got ${JSON.stringify(d.split.a)})`);
step("merge with an empty neighbour");

// Delete on a line between two panes with commands asks which one stays.
await loadDoc({ name: "m", split: { dir: "columns", a: { run: "left" }, b: { run: "right" } } });
await page.locator(".handle.v").first().click();
await page.keyboard.press("Delete");
await page.click('dialog.tp-dialog button:has-text("Keep right")');
d = await doc();
expect(JSON.stringify(d.split) === JSON.stringify({ run: "right" }), `line removed, right kept (got ${JSON.stringify(d.split)})`);
step("delete a line, keep the right pane");

// A line with several panes on one side is not removed.
await loadDoc({ name: "m", split: { dir: "columns", a: { run: "left" }, b: { dir: "rows", a: { run: "x" }, b: { run: "y" } } } });
const before2 = JSON.stringify(await doc());
await page.locator(".handle.v").first().click();
await page.keyboard.press("Delete");
expect((await page.textContent("dialog.tp-dialog")).includes("cannot be removed"), "explains why");
await page.click('dialog.tp-dialog button:has-text("OK")');
expect(JSON.stringify(await doc()) === before2, "nothing changed");
step("a line with two panes on one side stays");

// Panes in different branches: the tree is rebuilt.
await loadDoc({ name: "g", margin: 0, split: { dir: "columns", a: { dir: "rows", a: { run: "A1" }, b: { run: "A2" } },
  b: { dir: "rows", a: {}, b: { run: "B2" } } } });
await page.locator(".pane").first().click();
await page.click('.merge-btn[data-merge="right"]');
d = await doc();
const rects = await page.evaluate(() => S.geo.leaves.map((l) => [l.leaf.run || "", l.outer.x, l.outer.y, l.outer.width, l.outer.height]));
expect(rects.length === 3 && rects.some((r) => r[0] === "A1" && r[1] === 0 && r[3] === 1920 && r[4] === 540), `A1 fills the top row (got ${JSON.stringify(rects)})`);
step(`rebuilt: ${JSON.stringify(d.split)}`);

// Pieces cut in different units: the editor asks % or px.
await loadDoc({ name: "u", margin: 0, split: { dir: "columns", sizes: ["300px", "1frac", "1frac"], children: [{ run: "a" }, {}, { run: "c" }] } });
await page.locator(".pane").first().click();
await page.click('.merge-btn[data-merge="right"]');
expect((await page.textContent("dialog.tp-dialog")).includes("Percent or pixels"), "unit question");
await page.click('dialog.tp-dialog button:has-text("Pixels")');
d = await doc();
expect(d.split.dir === "columns" && d.split.at === "1110px" && d.split.a.run === "a", `merged size in px (got ${JSON.stringify(d.split)})`);
step(`unit question: ${JSON.stringify(d.split)}`);

// Shift while dragging a line snaps it onto a parallel line; the panes then
// line up exactly and can be merged.
await loadDoc({ name: "s", margin: 8, split: { dir: "columns", a: { dir: "rows", at: "40%", a: { run: "L1" }, b: { run: "L2" } },
  b: { dir: "rows", at: "300px", a: {}, b: { run: "R2" } } } });
const hLeft = await page.evaluate(() => {
  const el = [...document.querySelectorAll(".handle.h")].find((x) => x.dataset.split === "0");
  const r = el.getBoundingClientRect();
  return [r.left + r.width / 2, r.top + r.height / 2];
});
const target = await toScreen(200, 300);
await page.mouse.move(hLeft[0], hLeft[1]);
await page.mouse.down();
await page.keyboard.down("Shift");
await page.mouse.move(hLeft[0], target[1] + 12, { steps: 6 });
expect(await page.isVisible("#snap-guide"), "snap guide shown");
await page.mouse.up();
await page.keyboard.up("Shift");
d = await doc();
const tops = await page.evaluate(() => S.geo.leaves.map((l) => [l.leaf.run || "", l.outer.y, l.outer.height]));
expect(/^27\.778%$/.test(d.split.a.at) && tops.find((t) => t[0] === "L1")[2] === 300, `left line snapped to 300px exactly (got ${d.split.a.at}, ${JSON.stringify(tops)})`);
await page.locator(".pane").first().click();
expect((await page.locator('.merge-btn[data-merge="right"]').count()) === 1, "the lined-up panes can be merged");
step(`shift snap: at ${d.split.a.at}`);

expect(errors.length === 0, `no page errors: ${errors.join("; ")}`);
await browser.close();
console.log("editor features: ok");
