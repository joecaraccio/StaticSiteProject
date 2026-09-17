/**
 * Screenshot the built site into docs/screenshots/.
 *
 * Serves the build over a local static server (so directory URLs and absolute
 * asset paths behave exactly as they will in production) and captures each page
 * type in light, dark and at phone width.
 *
 * Usage:
 *   node scripts/screenshot_site.mjs [distDir] [outDir]
 */
import { chromium } from "playwright";
import http from "node:http";
import fs from "node:fs";
import path from "node:path";

const repo = path.resolve(import.meta.dirname, "..");
const dist = path.resolve(repo, process.argv[2] ?? "site/dist-mockup");
const outDir = path.resolve(repo, process.argv[3] ?? "docs/screenshots");

if (!fs.existsSync(dist)) {
  console.error(`No build at ${dist}. Run the site build first.`);
  process.exit(1);
}
fs.mkdirSync(outDir, { recursive: true });

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".xml": "application/xml; charset=utf-8",
  ".txt": "text/plain; charset=utf-8",
  ".svg": "image/svg+xml",
};

const server = http.createServer((req, res) => {
  let file = path.join(dist, decodeURIComponent(req.url.split("?")[0]));
  if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, "index.html");
  if (!fs.existsSync(file)) {
    res.writeHead(404);
    return res.end("not found");
  }
  res.writeHead(200, { "Content-Type": MIME[path.extname(file)] ?? "application/octet-stream" });
  fs.createReadStream(file).pipe(res);
});
await new Promise((resolve) => server.listen(0, resolve));
const base = `http://127.0.0.1:${server.address().port}`;

/** Pick a real example of each page type out of the manifest-driven build. */
function findFirst(pattern) {
  const walk = (dir) =>
    fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
      const full = path.join(dir, e.name);
      return e.isDirectory() ? walk(full) : full;
    });
  const hit = walk(dist)
    .filter((f) => f.endsWith("index.html"))
    .map((f) => "/" + path.relative(dist, path.dirname(f)).split(path.sep).join("/"))
    .filter((u) => pattern.test(u))
    .sort()[0];
  return hit ?? null;
}

const targets = [
  { name: "01-home", url: "/", label: "Home" },
  { name: "02-route", url: findFirst(/^\/routes\/[A-Z]{3}-[A-Z]{3}$/), label: "Route page" },
  { name: "03-flight", url: findFirst(/^\/flights\//), label: "Flight page" },
  { name: "04-airport", url: findFirst(/^\/airports\/[A-Z]{3}$/), label: "Airport page" },
  { name: "05-airline", url: findFirst(/^\/airlines\/[A-Z0-9]{2}$/), label: "Airline page" },
  { name: "06-routes-index", url: "/routes", label: "Routes index" },
  { name: "07-connections", url: "/connections", label: "Connection checker" },
].filter((t) => t.url);

const browser = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium" });
const written = [];

// 1x rather than retina: these are committed to the repo for design review, and
// at 2x the set is ~12MB, which is not worth carrying in git history.
for (const variant of [
  { suffix: "light", colorScheme: "light", viewport: { width: 1100, height: 1200 } },
  { suffix: "dark", colorScheme: "dark", viewport: { width: 1100, height: 1200 } },
  { suffix: "mobile", colorScheme: "light", viewport: { width: 390, height: 844 } },
]) {
  const context = await browser.newContext({
    viewport: variant.viewport,
    colorScheme: variant.colorScheme,
    deviceScaleFactor: 1,
  });
  const page = await context.newPage();
  for (const target of targets) {
    await page.goto(base + target.url, { waitUntil: "load" });
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth + 1,
    );
    if (overflow) console.warn(`  ! horizontal overflow: ${target.url} (${variant.suffix})`);
    const file = path.join(outDir, `${target.name}-${variant.suffix}.png`);
    await page.screenshot({ path: file, fullPage: true });
    written.push(path.relative(repo, file));
  }
  await context.close();
}

await browser.close();
server.close();

console.log(`Wrote ${written.length} screenshots to ${path.relative(repo, outDir)}/`);
for (const target of targets) console.log(`  ${target.label.padEnd(20)} ${target.url}`);
