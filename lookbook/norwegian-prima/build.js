#!/usr/bin/env node
// Render lookbook.html to a print-ready PDF (six A4 landscape pages) and,
// with --png, one PNG per page for previews and social cards.
//
//   node lookbook/norwegian-prima/build.js          -> dist/norwegian-prima-lookbook.pdf
//   node lookbook/norwegian-prima/build.js --png    -> also dist/page-1.png … page-6.png
//
// Drop the six hero images into images/ first (see images/README.md).
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const dir = __dirname;
const out = path.join(dir, "dist");
const wantPng = process.argv.includes("--png");

(async () => {
  fs.mkdirSync(out, { recursive: true });
  // The source is an artifact fragment; wrap it in a full document for rendering.
  const fragment = fs.readFileSync(path.join(dir, "lookbook.html"), "utf8");
  const doc = `<!doctype html><html lang="en"><head><meta charset="utf-8">` +
    `<meta name="viewport" content="width=device-width, initial-scale=1"></head><body>${fragment}</body></html>`;
  const tmp = path.join(dir, ".render.html");
  fs.writeFileSync(tmp, doc);

  const proxy = process.env.HTTPS_PROXY || process.env.https_proxy;
  const browser = await chromium.launch(proxy ? { proxy: { server: proxy } } : {});
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    await page.goto("file://" + tmp, { waitUntil: "networkidle" });
    await page.evaluate(() => document.fonts.ready);

    const missing = await page.$$eval("figure.has-slot img", els => els.map(e => e.dataset.slot));
    if (missing.length) console.warn("Image slots still empty: " + missing.join(", "));

    await page.emulateMedia({ media: "print" });
    const pdf = path.join(out, "norwegian-prima-lookbook.pdf");
    await page.pdf({ path: pdf, printBackground: true, preferCSSPageSize: true });
    console.log("Wrote " + path.relative(process.cwd(), pdf));

    if (wantPng) {
      await page.emulateMedia({ media: "screen" });
      await page.setViewportSize({ width: 1480, height: 1100 });
      const sheets = await page.$$("section.page");
      for (let i = 0; i < sheets.length; i++) {
        const file = path.join(out, `page-${i + 1}.png`);
        await sheets[i].screenshot({ path: file });
        console.log("Wrote " + path.relative(process.cwd(), file));
      }
    }
  } finally {
    await browser.close();
    fs.unlinkSync(tmp);
  }
})().catch(err => { console.error(err); process.exit(1); });
