# Root design failures

Assign exactly one primary mode per complaint. The ids are what goes in `failure_mode`.

| id | Failure | Check question | Typical fix |
|---|---|---|---|
| `no-feedback` | The product hides its state | Can the user tell if it's on, full, hot, done, or oriented correctly? | Indicators, windows, tactile or color cues |
| `mapping-mismatch` | Controls don't match what they control | Does the layout of controls mirror the layout of effects? | Spatial mapping, labels on the control itself |
| `seller-first` | Built for retail, shipping or theft prevention, not the user | Who benefits from this feature, the buyer or the seller? | Move the seller's goal to a part the user never handles |
| `last-mile-waste` | Product gets trapped or lost at the end of use | How much is left that the user can't get out? | Geometry, coatings, inverted or squeeze-to-zero formats |
| `bad-timing` | Alerts, maintenance or failure arrive at the worst moment | When does this demand attention, and is that when the user can act? | Early warnings, quiet hours, scheduled prompts |
| `one-size-fits-all` | Excludes some users (kids, seniors, low grip, left-handed, small spaces) | Who can't use this comfortably? | Adjustable, reversible or inclusive variants |
| `wears-out-early` | Fails, degrades or becomes unsafe well before its expected life | Does it last as long as a reasonable buyer expects? | Durable materials, replaceable wear parts, honest lifespan labels |

## Tie-breaks

- If a complaint fits two modes, pick the one the redesign actually fixes.
- Durability complaints that are really about cleaning damage (e.g. dishwasher-killed coatings) still go under
  `wears-out-early`; mention the cleaning cause in `complaint`.
- Add a new mode only when 3+ entries in a category truly fit none of these. Update this file and `MODES` in
  `scripts/pain_index.py` together.
