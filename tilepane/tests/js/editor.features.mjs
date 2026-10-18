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
await page.click("text=✂ Cut pane │");
let d = await doc();
expect(d.cwd === "/srv" && d.shell === "zsh", `settings moved up (got ${JSON.stringify(d)})`);
expect(JSON.stringify(d.split.a) === JSON.stringify({ run: "htop", title: "top" }) && JSON.stringify(d.split.b) === "{}", "first half keeps run and title");
step(`cut pane: ${JSON.stringify(d)}`);

// "Cut pane" halves the selected pane at once, in the direction of the line on the button.
await loadDoc({ name: "cp", margin: 8, split: { dir: "columns", at: "50%", a: { run: "left" }, b: { run: "right" } } });
const labels = await page.locator("header button").allTextContents();
expect(labels.some((t) => t.includes("Cut screen ─")) && labels.some((t) => t.includes("Cut screen │")), `Cut screen buttons (got ${JSON.stringify(labels)})`);
expect(await page.locator("#layout-cut-h").isDisabled() && await page.locator("#layout-cut-v").isDisabled(), "with several panes and none selected Cut pane waits for a selection");
await page.locator(".pane").first().click();
const paneButtons = await page.locator(".actions button").allTextContents();
expect(paneButtons.indexOf("✂ Cut pane ─") >= 0 && paneButtons.indexOf("✂ Cut pane ─") < paneButtons.indexOf("✂ Cut pane │"), `Cut pane buttons in order (got ${JSON.stringify(paneButtons)})`);
expect(!paneButtons.some((t) => t.startsWith("Split ")), "the old Split buttons are gone");
await page.click("text=✂ Cut pane ─");
expect(!(await page.isVisible("#cut-overlay")), "Cut pane needs no clicking on the screen");
d = await doc();
expect(d.split.a.dir === "rows" && d.split.a.at === "50%" && d.split.a.a.run === "left" && JSON.stringify(d.split.a.b) === "{}" && JSON.stringify(d.split.b) === JSON.stringify({ run: "right" }),
  `the left pane was halved into top and bottom, the right one stayed (got ${JSON.stringify(d.split)})`);
expect((await page.evaluate(() => S.sel.path.join(","))) === "0,1", "the new bottom piece is selected");
await page.click("text=✂ Cut pane │");
d = await doc();
expect(d.split.a.b.dir === "columns" && d.split.a.b.at === "50%", `the selected piece was halved into left and right (got ${JSON.stringify(d.split.a)})`);
step("cut pane halves the selected pane");

// Nothing on the screen yet: the first rectangle is the whole screen, and it is cut in half.
await loadDoc({ name: "cp", split: {} });
expect(await page.evaluate(() => S.sel.kind) === "layout", "nothing selected in a fresh editor");
expect(!(await page.locator("#layout-cut-h").isDisabled()), "Cut pane works on the empty screen");
await page.click("#layout-cut-v");
d = await doc();
expect(d.split.dir === "columns" && d.split.at === "50%" && JSON.stringify(d.split.a) === "{}" && JSON.stringify(d.split.b) === "{}", `the empty screen was cut into left and right (got ${JSON.stringify(d.split)})`);
await loadDoc({ name: "cp", split: {} });
await page.click("#layout-cut-h");
d = await doc();
expect(d.split.dir === "rows" && d.split.at === "50%", `or into top and bottom (got ${JSON.stringify(d.split)})`);
expect(!(await page.isVisible("#cut-overlay")), "no cut line is needed");
step("cut pane on the empty screen");

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

// A dragged line snaps by itself onto a nearby parallel line, a tooltip at the cursor says that Alt turns it off,
// and the panes then line up exactly and can be merged.
const snapDoc = { name: "s", margin: 8, split: { dir: "columns", a: { dir: "rows", at: "40%", a: { run: "L1" }, b: { run: "L2" } },
  b: { dir: "rows", at: "300px", a: {}, b: { run: "R2" } } } };
await loadDoc(snapDoc);
const hLeft = await page.evaluate(() => {
  const el = [...document.querySelectorAll(".handle.h")].find((x) => x.dataset.split === "0");
  const r = el.getBoundingClientRect();
  return [r.left + r.width / 2, r.top + r.height / 2];
});
const target = await toScreen(200, 300);
await page.mouse.move(hLeft[0], hLeft[1]);
await page.mouse.down();
await page.mouse.move(hLeft[0], target[1] + 5, { steps: 6 });
expect(await page.isVisible("#snap-guide"), "snap guide shown without any key");
const tipText = await page.locator(".size-tip", { hasText: "Alt" }).first().textContent();
expect(/hold Alt to turn snapping off/i.test(tipText), `tooltip at the cursor tells how to turn snapping off (got ${tipText})`);
await page.mouse.up();
expect(await page.locator(".size-tip", { hasText: "Alt" }).count() === 0, "the tooltip goes away after the drag");
d = await doc();
const tops = await page.evaluate(() => S.geo.leaves.map((l) => [l.leaf.run || "", l.outer.y, l.outer.height]));
expect(/^27\.778%$/.test(d.split.a.at) && tops.find((t) => t[0] === "L1")[2] === 300, `left line snapped to 300px exactly (got ${d.split.a.at}, ${JSON.stringify(tops)})`);
await page.locator(".pane").first().click();
expect((await page.locator('.merge-btn[data-merge="right"]').count()) === 1, "the lined-up panes can be merged");
step(`auto snap: at ${d.split.a.at}`);

// Alt turns the snapping off: the same drag ends where the mouse is.
await loadDoc(snapDoc);
const hLeft2 = await page.evaluate(() => {
  const el = [...document.querySelectorAll(".handle.h")].find((x) => x.dataset.split === "0");
  const r = el.getBoundingClientRect();
  return [r.left + r.width / 2, r.top + r.height / 2];
});
await page.mouse.move(hLeft2[0], hLeft2[1]);
await page.mouse.down();
await page.keyboard.down("Alt");
await page.mouse.move(hLeft2[0], target[1] + 5, { steps: 6 });
expect(!(await page.isVisible("#snap-guide")), "no snap guide with Alt held");
expect(/snapping is off/i.test(await page.locator(".size-tip", { hasText: "Snapping" }).first().textContent()), "tooltip says snapping is off");
await page.mouse.up();
await page.keyboard.up("Alt");
const heights = await page.evaluate(() => S.geo.leaves.map((l) => [l.leaf.run || "", l.outer.height]));
expect(heights.find((t) => t[0] === "L1")[1] !== 300, `with Alt the line did not snap (got ${JSON.stringify(heights)})`);
step("Alt turns the snapping off");

// A command typed into a field is kept when the next click goes straight to a pane, a button or the screen,
// although the field never lost focus the usual way (the panes cancel the default action of the mouse down).
await loadDoc({ name: "typed", margin: 8, split: { dir: "columns", at: "50%", a: {}, b: {} } });
await page.locator(".pane").first().click();
await page.fill('textarea[data-key="run"]', "htop");
// Some browsers (Firefox) do not move the focus away from the field on this click, so the field gets no change
// event; a synthetic mouse down and up does not move the focus in any browser and reproduces that.
await page.evaluate(() => {
  const pane = document.querySelectorAll(".pane")[1];
  const r = pane.getBoundingClientRect();
  const at = { bubbles: true, cancelable: true, clientX: r.left + r.width / 2, clientY: r.top + r.height / 2, pointerId: 1, button: 0, buttons: 1 };
  pane.dispatchEvent(new PointerEvent("pointerdown", at));
  window.dispatchEvent(new PointerEvent("pointerup", { ...at, buttons: 0 }));
});
await page.waitForTimeout(50);
expect(await page.evaluate(() => S.sel.path.join(",")) === "1", "the second pane got selected");
d = await doc();
expect(d.split.a.run === "htop", `the typed command stayed in the first pane (got ${JSON.stringify(d.split)})`);
await page.locator(".pane").first().click();
await page.fill('textarea[data-key="run"]', "top");
await page.locator(".pane").nth(1).click();
expect((await doc()).split.a.run === "top", "the same with a real click");
await page.locator(".pane").first().click();
expect((await page.inputValue('textarea[data-key="run"]')) === "top", "selecting the pane again shows the command");
expect((await page.evaluate(() => document.title)).startsWith("•"), "the file is marked as changed");
step("typed command survives a click on another pane");

await page.fill('textarea[data-key="run"]', "htop\nwatch date");
await page.click("text=✂ Cut pane ─");
d = await doc();
expect(d.split.a.dir === "rows" && JSON.stringify(d.split.a.a.run) === JSON.stringify(["htop", "watch date"]), `the command was kept and the button worked (got ${JSON.stringify(d.split.a)})`);
step("typed command survives a click on a button, and the button still works");

await page.locator(".pane").first().click();
await page.fill('textarea[data-key="run"]', "top");
const stage2 = await page.locator("#stage").boundingBox();
await page.mouse.click(stage2.x + 8, stage2.y + 8);
expect((await doc()).split.a.a.run === "top", "a click outside the monitor keeps the typed command");
await page.locator(".pane").first().click();
await page.fill('textarea[data-key="run"]', "uptime");
await page.keyboard.press("Control+z");   // undo with typed text first commits it, then undoes it
expect((await doc()).split.a.a.run === "top", "undo after typing goes back to the command before it");
expect(errors.length === 0, `no page errors after typing and clicking: ${errors.join("; ")}`);
step("typed command survives a click outside the monitor");

expect(errors.length === 0, `no page errors: ${errors.join("; ")}`);
await browser.close();
console.log("editor features: ok");
