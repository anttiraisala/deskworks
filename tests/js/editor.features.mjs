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
const stage = await page.locator("#stage").boundingBox();
await page.mouse.click(stage.x + 8, stage.y + 8);
expect((await sel()) === "layout", "click outside the monitor clears the selection");
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
await page.mouse.up();
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

expect(errors.length === 0, `no page errors: ${errors.join("; ")}`);
await browser.close();
console.log("editor features: ok");
