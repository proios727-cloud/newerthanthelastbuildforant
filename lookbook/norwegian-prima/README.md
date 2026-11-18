# The Unfiltered Field Guide to Norwegian Prima

A 6-page luxury travel lookbook in an editorial style. The tone is sharp, candid and pragmatic.
Each page is built around one hero image. The guide is written in HTML and exports to a
print-ready PDF.

| Page | Section | Hero image |
|------|---------|------------|
| 1 | Executive overview & true identity | Aerial exterior, golden hour |
| 2 | Dining, decoded | Indulge Food Hall, Deck 8 |
| 3 | Stateroom blueprint | The Haven infinity pool |
| 4 | Sea day survival & deck flow | Ocean Boulevard, Infinity Beach |
| 5 | Entertainment & nightlife | Prima Theater & Club, nightclub mode |
| 6 | Pre-cruise cheat sheet | Penrose Atrium |

## Files

```
lookbook.html     The lookbook: content, styles and image loader (Claude Artifact page source)
images/           Hero images (names and crops in images/README.md)
build.js          HTML → PDF / PNG renderer (Playwright)
dist/             Build output (git-ignored)
```

## Build

From the repo root (needs Node and Playwright with Chromium):

```bash
node lookbook/norwegian-prima/build.js          # dist/norwegian-prima-lookbook.pdf
node lookbook/norwegian-prima/build.js --png    # also dist/page-1.png … page-6.png
```

The PDF has six A4 landscape pages (297 × 210 mm) and keeps background colors.

## Images

Put the six generated images in `images/`, using the names in [`images/README.md`](images/README.md).
JPG, PNG and WebP all work. Until an image is added, its page shows a labelled placeholder.

## Editorial notes

- Check "midship engines" on page 1 before publishing. It has not been verified.
- Venue names use NCL's spelling, such as "Prima Theater & Club".
