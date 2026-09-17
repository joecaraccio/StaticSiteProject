/**
 * Check every internal link in a built site resolves to a page that exists.
 *
 * This matters because the gates drop pages: a template that links to
 * "the return route" or "this airline" has no way of knowing whether that page
 * survived, so a broken link is the default failure mode rather than an unusual
 * one. With real data most routes will drop, so this is not hypothetical.
 *
 * No dependencies: it reads the built HTML and resolves hrefs against the files
 * on disk, which is exactly what a static host will do.
 *
 * Usage:
 *   node scripts/check_links.mjs [distDir]
 */
import fs from "node:fs";
import path from "node:path";

const repo = path.resolve(import.meta.dirname, "..");
const dist = path.resolve(repo, process.argv[2] ?? "site/dist-mockup");

if (!fs.existsSync(dist)) {
  console.error(`No build at ${dist}.`);
  process.exit(1);
}

const walk = (dir) =>
  fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    return entry.isDirectory() ? walk(full) : [full];
  });

const htmlFiles = walk(dist).filter((f) => f.endsWith(".html"));

/** Does this site serve `href`? Mirrors how a static host resolves a path. */
function resolves(href) {
  const clean = href.split("#")[0].split("?")[0];
  if (clean === "" || clean === "/") return fs.existsSync(path.join(dist, "index.html"));
  const target = path.join(dist, clean);
  return (
    fs.existsSync(target) ||
    fs.existsSync(`${target}.html`) ||
    fs.existsSync(path.join(target, "index.html"))
  );
}

const broken = [];
let checked = 0;

for (const file of htmlFiles) {
  const html = fs.readFileSync(file, "utf8");
  const from = "/" + path.relative(dist, path.dirname(file)).split(path.sep).join("/");
  for (const match of html.matchAll(/href="([^"]+)"/g)) {
    const href = match[1];
    // External links, anchors and non-http schemes are out of scope.
    if (/^(https?:|mailto:|tel:|#|data:)/.test(href)) continue;
    if (!href.startsWith("/")) continue;
    checked += 1;
    if (!resolves(href)) broken.push({ from: from === "/." ? "/" : from, href });
  }
}

console.log(`Checked ${checked} internal links across ${htmlFiles.length} pages.`);

if (broken.length === 0) {
  console.log("No broken internal links.");
  process.exit(0);
}

// Group by target: one dropped page usually breaks the same link from many pages.
const byHref = new Map();
for (const item of broken) {
  byHref.set(item.href, [...(byHref.get(item.href) ?? []), item.from]);
}
console.error(`\n${broken.length} broken internal link(s), ${byHref.size} distinct target(s):`);
for (const [href, sources] of [...byHref].sort((a, b) => b[1].length - a[1].length)) {
  console.error(`  ${href}  <- ${sources.length} page(s), e.g. ${sources.slice(0, 3).join(", ")}`);
}
process.exit(1);
