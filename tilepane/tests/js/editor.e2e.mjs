// End-to-end check of the editor in Chromium, driven by Playwright.
// Start an editor first, then pass its address:
//   tilepane --edit /tmp/e2e.json --no-browser      (prints the address)
//   node tests/js/editor.e2e.mjs 'http://127.0.0.1:PORT/?t=TOKEN' [--open-on-screen]
// Needs the playwright package (NODE_PATH or a global install).
import { createRequire } from "node:module";

const require = createRequire(process.env.PLAYWRIGHT_DIR || "/opt/node-tools/node_modules/");
const { chromium } = require("playwright");
const [url, ...flags] = process.argv.slice(2);
const shot = (name) => (process.env.SHOTS ? { path: `${process.env.SHOTS}/${name}.png` } : undefined);

const browser = await chromium.launch(process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : {});
const page = await browser.newPage({ viewport: { width: 1400, height: 860 } });
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
page.on("dialog", (d) => d.accept());
const step = (msg) => console.log(`- ${msg}`);
const expect = (cond, msg) => { if (!cond) throw new Error(`FAILED: ${msg}`); };

await page.goto(url);
await page.waitForSelector(".pane");
step(`loaded: ${await page.locator(".pane").count()} pane(s), file ${await page.textContent("#file")}`);

// The command line names the file on disk and the monitor, by number or by name.
const path = await page.evaluate(() => BOOT.path);
const mon = await page.evaluate(() => S.monitors[0]);
let cmd = await page.locator("#command-lines code").first().textContent();
expect(cmd.includes(path.split("/").pop()) && cmd.endsWith(`--monitor ${mon.number}`), `command line (got ${cmd})`);
await page.click('#command-lines button:has-text("name")');
cmd = await page.locator("#command-lines code").first().textContent();
expect(cmd.endsWith(`--monitor ${mon.name}`), `command line by name (got ${cmd})`);
await page.click('#command-lines button:has-text("number")');
step(`command line: ${cmd}`);

// Cut the right pane into rows, give the bottom one a command list.
await page.locator(".pane").nth(1).click();
const rightPane = await page.locator(".pane").nth(1).boundingBox();
await page.click("text=✂ Cut pane ─");
await page.mouse.move(rightPane.x + rightPane.width / 2, rightPane.y + rightPane.height / 2);
await page.mouse.click(rightPane.x + rightPane.width / 2, rightPane.y + rightPane.height / 2);
expect((await page.locator(".pane").count()) === 3, "three panes after split");
await page.fill('textarea[data-key="run"]', "date\nwhoami\nls");
await page.locator('textarea[data-key="run"]').blur();
step("cut the right pane and set a command list on the new bottom pane");

// Drag the vertical line between the columns to about 30 %.
const handle = page.locator(".handle.v").first();
const box = await handle.boundingBox();
const screen = await page.locator("#screen").boundingBox();
await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
await page.mouse.down();
await page.mouse.move(screen.x + screen.width * 0.3, box.y + box.height / 2, { steps: 8 });
await page.mouse.up();
const at = await page.inputValue('input[data-key="at"]');
step(`dragged the column split: at = ${at}`);
expect(/^2\d(\.\d)?%$|^3\d(\.\d)?%$/.test(at), `at near 30% (got ${at})`);
await page.screenshot(shot("editor-dragged"));

// Undo and redo the drag.
await page.click("#undo");
const undone = await page.inputValue('input[data-key="at"]').catch(() => null);
await page.click("#redo");
step(`undo/redo: ${undone} -> ${await page.inputValue('input[data-key="at"]')}`);

// An invalid value blocks saving and is shown next to the field.
await page.locator(".pane").first().click();
await page.click("text=More settings");
await page.fill('input[data-key="margin"]', "-5");
await page.locator('input[data-key="margin"]').blur();
expect(await page.isDisabled("#save"), "save disabled while there is an error");
step(`invalid margin: ${await page.textContent("footer .problem.error")}`);
await page.fill('input[data-key="margin"]', "");
await page.locator('input[data-key="margin"]').blur();
expect(!(await page.isDisabled("#save")), "save enabled again");

await page.click("#save");
await page.waitForFunction(() => document.querySelector("footer .status").textContent.includes("saved"));
step(`saved: ${await page.textContent("footer .status")}`);

if (flags.includes("--open-on-screen")) {
  await page.click("#open-screen");
  await page.waitForFunction(() => /opened on screen|exited/.test(document.querySelector("footer .status").textContent), null, { timeout: 30000 });
  step(`open on screen: ${await page.textContent("footer .status")}`);
  console.log((await page.textContent("footer pre").catch(() => "")).split("\n").map((l) => `    ${l}`).join("\n"));
  await page.screenshot(shot("editor-opened"));
}

expect(errors.length === 0, `no page errors (${errors.join("; ")})`);
await page.close();          // the tab says goodbye; the server stops shortly after
await browser.close();
console.log("editor e2e: ok");
