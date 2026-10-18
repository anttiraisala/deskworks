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
// "Cut pane": press the button of the selected pane, then click inside the pane (fx, fy are fractions of its size).
const cutPane = async (button, pane, fx = 0.5, fy = 0.5) => {
  const box = await pane.boundingBox();
  await page.click(`text=${button}`);
  await page.mouse.move(box.x + box.width * fx, box.y + box.height * fy);
  await page.mouse.click(box.x + box.width * fx, box.y + box.height * fy);
};

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
await cutPane("✂ Cut pane │", page.locator(".pane").first());
let d = await doc();
expect(d.cwd === "/srv" && d.shell === "zsh", `settings moved up (got ${JSON.stringify(d)})`);
expect(JSON.stringify(d.split.a) === JSON.stringify({ run: "htop", title: "top" }) && JSON.stringify(d.split.b) === "{}", "first half keeps run and title");
step(`cut pane: ${JSON.stringify(d)}`);

// "Cut pane" works like "Cut screen": a line follows the mouse and only the selected pane is cut, along the line.
await loadDoc({ name: "cp", margin: 8, split: { dir: "columns", at: "50%", a: { run: "left" }, b: { run: "right" } } });
const labels = await page.locator("header button").allTextContents();
expect(labels.some((t) => t.includes("Cut screen ─")) && labels.some((t) => t.includes("Cut screen │")), `Cut screen buttons (got ${JSON.stringify(labels)})`);
await page.locator(".pane").first().click();
const paneButtons = await page.locator(".actions button").allTextContents();
expect(paneButtons.includes("✂ Cut pane ─") && paneButtons.includes("✂ Cut pane │"), `Cut pane buttons (got ${JSON.stringify(paneButtons)})`);
expect(!paneButtons.some((t) => t.startsWith("Split ")), "the old Split buttons are gone");
const leftBox = await page.locator(".pane").first().boundingBox();
await page.click("text=✂ Cut pane ─");
expect(await page.isVisible("#cut-overlay"), "Cut pane starts the cut mode");
await page.mouse.move(leftBox.x + leftBox.width / 2, leftBox.y + leftBox.height / 3);
const lineBox = await page.locator("#cut-overlay .cut-line").boundingBox();
expect(Math.abs(lineBox.width - leftBox.width) < 12 && Math.abs(lineBox.x - leftBox.x) < 12 && lineBox.width < leftBox.width * 1.1, `the line spans only the pane (line ${lineBox.width}px, pane ${leftBox.width}px)`);
await page.mouse.click(leftBox.x + leftBox.width / 2, leftBox.y + leftBox.height / 3);
d = await doc();
expect(d.split.a.dir === "rows" && d.split.a.a.run === "left" && JSON.stringify(d.split.b) === JSON.stringify({ run: "right" }), `only the left pane was cut, top and bottom (got ${JSON.stringify(d.split)})`);
expect(!(await page.isVisible("#cut-overlay")), "the cut mode ends after the cut");
step("cut pane: only the selected pane, along the line");

// A click outside the pane, or Escape, stops Cut pane without cutting.
await loadDoc({ name: "cp", margin: 8, split: { dir: "columns", at: "50%", a: { run: "left" }, b: { run: "right" } } });
await page.locator(".pane").first().click();
const rightBox = await page.locator(".pane").nth(1).boundingBox();
const docBeforeCut = JSON.stringify(await doc());
await page.click("text=✂ Cut pane │");
await page.mouse.click(rightBox.x + rightBox.width / 2, rightBox.y + rightBox.height / 2);
expect(!(await page.isVisible("#cut-overlay")) && JSON.stringify(await doc()) === docBeforeCut, "a click outside the pane stops the mode");
await page.click("text=✂ Cut pane │");
await page.keyboard.press("Escape");
expect(!(await page.isVisible("#cut-overlay")) && JSON.stringify(await doc()) === docBeforeCut, "Escape stops the mode");
step("cut pane can be stopped");

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

// The preview size can be undone and redone, also in a fresh, empty editor, and it does not make the file dirty.
await loadDoc({ name: "fresh", split: {} });
const size0 = await page.textContent("#monitor-size");
expect(await page.isDisabled("#undo"), "nothing to undo in a fresh editor");
const dragCorner = async (dx, dy) => {
  const c = await page.locator(".mon-handle.se").boundingBox();
  await page.mouse.move(c.x + 7, c.y + 7);
  await page.mouse.down();
  await page.mouse.move(c.x + 7 + dx, c.y + 7 + dy, { steps: 6 });
  await page.mouse.up();
};
await dragCorner(-120, -60);
const size1 = await page.textContent("#monitor-size");
expect(size1 !== size0, `the drag changed the size (${size0} -> ${size1})`);
expect(!(await page.isDisabled("#undo")), "the size change can be undone");
expect(!(await page.evaluate(() => S.dirty)), "a size change does not make the file dirty");
await page.click("#undo");
expect((await page.textContent("#monitor-size")) === size0, "undo restores the size");
expect(await page.isDisabled("#undo") && !(await page.isDisabled("#redo")), "undo used up, redo available");
await page.click("#redo");
expect((await page.textContent("#monitor-size")) === size1, "redo brings the size back");
await dragCorner(-60, -30);
const size2 = await page.textContent("#monitor-size");
await page.keyboard.press("Control+z");
expect((await page.textContent("#monitor-size")) === size1, "Ctrl+Z undoes the second drag");
await page.keyboard.press("Control+z");
expect((await page.textContent("#monitor-size")) === size0, "Ctrl+Z again undoes the first drag");
await page.keyboard.press("Control+y");
await page.keyboard.press("Control+y");
expect((await page.textContent("#monitor-size")) === size2, "Ctrl+Y redoes both");
expect(!(await page.evaluate(() => S.dirty)), "the file stayed clean through undo and redo");
await page.click('#screenbar button[title="Larger gap"]');
expect(await page.evaluate(() => S.dirty), "an edit of the layout makes it dirty");
await page.keyboard.press("Control+z");
expect((await page.textContent("#monitor-size")) === size2, "undoing a layout edit leaves the preview size alone");
await page.click("text=Reset size");
expect(!(await page.isDisabled("#undo")), "Reset size is undoable too");
await page.click("#undo");
expect((await page.textContent("#monitor-size")) === size2, "undo of Reset size brings the custom size back");
await page.click("text=Reset size");   // later checks use the monitor from the list
step(`preview size undo/redo: ${size0} -> ${size1} -> ${size2}`);

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
await page.selectOption("#workspace", "0");
expect((await doc()).workspace === 0, "workspace 0 (bottom left) is a number, not 'not set'");
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
