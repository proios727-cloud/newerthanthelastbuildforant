# Bathroom: pain → redesign report

_Generated from `data/bathroom.json` (updated 2026-10-30). Do not edit by hand._

**Opportunity** = pain × feasibility. **Pain** = frequency × severity × workaround difficulty (0–100).

## Ranked opportunities

| # | Item | Complaint | Failure | Pain | Opp. | Redesign |
|---|---|---|---|---|---|---|
| 1 | Bathroom exhaust fans | The fan sounds like it's working but doesn't remove moisture (it's undersized, has a clogged grille, or is switched off too soon), which leads to mold and peeling paint | No feedback | 38 | **30** | A built-in humidity sensor runs the fan until the room's humidity returns to normal, and an LED on the switch shows airflow as OK, weak (clean the grille) or blocked |
| 2 | Shower valves & controls | Every shower works differently; people can't tell which way is hot, how to switch tub to shower, or where the control is | Mapping mismatch | 29 | **23** | One control turns the shower on and off and a separate dial sets the temperature, marked in degrees with a blue-to-red gradient. The diverter is a clearly marked lever on the same plate. All controls sit near the door so they can be reached without stepping under the water |
| 3 | Toothbrush holders | Water and toothpaste pool in the closed bottom of cup-style holders, turning into slime that is hard to reach and clean | Last-mile waste | 19 | **19** | Open-bottom or wall-mounted holder that grips each brush by the neck so it hangs head-up with nothing beneath it to collect water, made of a single dishwasher-safe part |
| 4 | Shower caddies | Suction cups let go on textured tile and the caddy crashes down; wire caddies sold as rust-resistant rust within months | Wears out early | 19 | **15** | Solid aluminum or plastic caddy with no welds, mounted by tension pole or adhesive plate rather than suction, with open slotted shelves that drain completely |
| 5 | Shower curtain liners | Pink slime and mildew grow in the damp folds of the liner, which then has to be washed or thrown away | Wears out early | 19 | **15** | A quick-drying, machine-washable fabric liner on a rod that stays open so the liner hangs flat and dries without folds, with a removable weighted hem |
| 6 | Bathroom exhaust fans | Older fans get loud (often around 4 sones), and parts loosen and rattle with age, so people avoid running them | Wears out early | 14 | **11** | A 0.5 sone or quieter motor in rubber-isolated mounts with captive screws that can't vibrate loose; the motor swaps out from the room side without removing the housing |
| 7 | Low-flow toilets | Older low-flow models with narrow trapways clog and need double flushing (much less common with newer models) | One size fits all | 14 | **11** | A wide trapway and glazed bowl as standard, with the independently tested flush score (MaP grams) printed on the box |
| 8 | Shampoo & conditioner bottles | The two bottles are nearly identical and labeled in tiny type, so without glasses in a dim shower people can't tell them apart | One size fits all | 5 | **5** | An industry-wide tactile code (raised stripes for shampoo, dots for conditioner, plain for body wash) plus contrasting cap colors |
| 9 | Shower curtain liners | The liner billows inward and sticks to the person showering | One size fits all | 5 | **5** | A weighted hem plus magnets placed where they meet a steel tub, sold standard on every liner, and a curved rod that pushes the liner outward |
| 10 | Toilet paper holders | Swapping the roll on a spring-loaded rod takes two hands, and the spring fails or the arm falls off | Wears out early | 5 | **5** | An open, single-arm holder the roll slides onto with one hand, with no spring or detachable rod |

## Failure-mode mix

| Failure | Entries |
|---|---|
| Wears out early | 4 |
| One size fits all | 3 |
| Mapping mismatch | 1 |
| No feedback | 1 |
| Last-mile waste | 1 |

## Evidence

- `exhaust-fan-leaves-moisture`: [1](https://dev.to/michael_groover_1fe970a66/why-your-bathroom-exhaust-fan-is-running-but-not-removing-moisture-288a), [2](https://siouxcityjournal.com/special-section/local/larger-exhaust-fan-can-prevent-mold-in-bathroom/article_76160d3f-6617-558f-9bb1-891a37f854fc.html), [3](https://www.homedepot.com/p/Panasonic-Whisper-Mighty-Pick-A-Flow-70-90-CFM-Ceiling-Wall-Bathroom-Exhaust-Fan-Energy-Star-with-9-in-x-9-in-Grille-Footprint-RG-M79A/320467425). Prior art: Humidity-sensing fans (Panasonic WhisperSense, Broan).
- `shower-controls-unreadable`: [1](https://www.johndcook.com/blog/2008/08/07/bad-user-interface-design-hotel-showers/), [2](https://onemileatatime.com/a-rant-about-hotel-showers/), [3](https://yourmileagemayvary.com/2019/03/20/my-latest-travel-pet-peeve-left-me-all-wet/), [4](https://juliebestry.com/2025/11/03/when-your-european-hotel-room-feels-like-an-escape-room-conquer-confusing-showers-a-c-and-light-switches/). Prior art: Thermostatic valves with degree scales (common in Japanese hotels).
- `toothbrush-holder-sludge`: [1](https://www.mumsnet.com/talk/_chat/5196418-toothbrush-holders-that-dont-become-disgusting), [2](https://patents.justia.com/patent/7097050), [3](https://thangs.com/designer/Gazzaladra/post/Toothbrush%20holder%20V1-V4-2698), [4](https://www.aol.com/articles/clean-toothbrush-holder-safely-why-140000496.html). Prior art: Bottomless and wall-clip holders.
- `shower-caddy-suction-rust`: [1](https://www.target.com/p/bathroom-shower-caddy-black-made-by-design-8482/-/A-53806199), [2](https://fakespot.com/product/joseph-joseph-easystore-corner-shower-caddy-2-pack-no-mirror-white), [3](https://canadiantire.ca/en/pdp/squiggle-shower-caddy-satin-nickel-25-in-0635929p.html), [4](https://www.fakespot.com/product/zenna-home-7546nsp-expandable-over-the-showerhead-caddy-chrome). Prior art: Tension-pole caddies; powder-coated or aluminum caddies.
- `shower-liner-mold`: [1](https://www.apartmenttherapy.com/shower-curtain-liner-mold-37384412), [2](https://www.bobvila.com/articles/pink-mold-in-shower.md), [3](https://www.utmb.edu/utmb/news-article/utmb-news/2025/04/10/here's-how-often-you-should-actually-replace-your-shower-curtain--according-to-microbiologists). Prior art: Machine-washable fabric liners.
- `exhaust-fan-noise`: [1](https://www.touchstoneenergy.com/why-your-bathroom-fan-so-loud), [2](https://www.appliancepartspros.com/b/?p=19653).
- `low-flow-toilet-clogs`: [1](https://www.pmmag.com/articles/87270-high-marks-for-low-flow-toilets), [2](https://www.epa.gov/sites/production/files/2017-03/documents/ws-flushfact-vs-fiction.pdf), [3](https://terrylove.com/against_the_flow.htm). Prior art: WaterSense-certified toilets; MaP testing.
- `shampoo-conditioner-lookalike`: [1](https://world.hey.com/jz/designers-what-on-earth-is-going-on-with-shampoo-bottles-7f956f0d), [2](https://www.henshaws.org.uk/hints-and-tips/trick-to-distinguish-shampoo-from-conditioner/), [3](https://www.today.com/today/amp/tdna139799). Prior art: Herbal Essences tactile bottles.
- `shower-liner-billows`: [1](https://www.wayfair.com/bed-bath/pdp/kenney-liner-lbkl1162.html), [2](https://www.apartmenttherapy.com/shower-curtain-liner-amazon-36765785). Prior art: Weighted or magnetic liners; curved shower rods.
- `tp-holder-spring-rod`: [1](https://www.perigold.com/bath/pdp/kohler-occasion-pivoting-toilet-paper-holder-p110226644.html), [2](https://www.aol.com/articles/mans-invention-upgrades-familiar-toilet-193000986.html), [3](https://patents.justia.com/patent/20020134881). Prior art: Single-post holders; Roto holder.
