# Laundry: pain → redesign report

_Generated from `data/laundry.json` (updated 2026-10-30). Do not edit by hand._

**Opportunity** = pain × feasibility. **Pain** = frequency × max(severity, annoyance) × workaround difficulty (0–100). A nuisance counts as much as harm.

## Ranked opportunities

| # | Item | Complaint | Failure | Pain | Opp. | Redesign |
|---|---|---|---|---|---|---|
| 1 | Front-load washers | Water and detergent sit in the door gasket folds after every load, growing mold and a musty smell that gets into clean clothes | Last-mile waste | 60 | **36** | A gasket with no folds that slopes to drain holes, plus a short fan-dry run after each cycle that blows out the drum and gasket, so no one has to wipe it down or leave the door open |
| 2 | Clothes dryers | Lint gets past the filter and builds up behind the drum or in the vent, where owners can't see or reach it, until it starts a fire | No feedback | 48 | **29** | A sealed lint path with no gaps around the filter, an airflow sensor that warns on the display when the vent is restricted, and a front panel that comes off without tools to reach the area behind the drum |
| 3 | Liquid detergent caps | Faint or confusing fill lines inside the cap lead people to use too much detergent, which wastes money and leaves residue on clothes and in the machine | Seller-first | 26 | **26** | High-contrast dose lines molded on the outside of the cap with load-size words, and a full cap equal to one normal dose so 'fill it up' is correct |
| 4 | Washer & dryer chimes | The end-of-cycle chime is very loud by default, is silenced with hidden button combinations that differ by model, and some beeps can't be turned off at all | Bad timing | 26 | **26** | A labeled volume control on the panel (off, low, high) that also mutes button beeps, with quiet hours that switch the chime to a light or phone notification overnight |
| 5 | Bedding in washers & dryers | Fitted sheets and duvet covers wad into a damp ball that swallows socks and small items and comes out wet in the middle | One size fits all | 38 | **23** | A bedding cycle that reverses the drum direction to keep the load from wadding up, and fitted sheets with corner snaps that clip together before washing |
| 6 | Clothing care labels | More than three dozen care symbols that most people can't read, so clothes get shrunk or ruined in the wash | No feedback | 29 | **23** | Plain-words care instructions printed on the inside seam (for example, 'Wash cold · Hang dry · No bleach') next to the symbols, with no scratchy sewn-in tag |

## Failure-mode mix

| Failure | Entries |
|---|---|
| No feedback | 2 |
| Last-mile waste | 1 |
| Seller-first | 1 |
| Bad timing | 1 |
| One size fits all | 1 |

## Evidence

- `front-load-gasket-mold`: [1](https://www.consumerreports.org/cro/news/2009/12/mold-and-odor-issues-for-some-front-loading-washing-machines-spur-class-actions/index.htm), [2](https://www.nbcnews.com/business/consumer/front-loader-odor-stinky-washer-class-action-lawsuit-finally-settled-n609316), [3](https://laundry.reviewed.com/news/supreme-court-wont-hear-moldy-washing-machine-suit), [4](https://www.ksat.com/consumer/2016/09/08/people-complain-of-smelly-washing-machines). Prior art: LG's redesigned gasket with drain holes; machines with drum-dry or auto-vent features.
- `dryer-hidden-lint`: [1](https://www.classaction.org/lg-dryer-fires-lawsuit), [2](https://caselaw.findlaw.com/tx-supreme-court/1505499.html), [3](https://www.foxnews.com/real-estate/dryers-get-better-at-letting-you-know-lint-is-blocking-the-vent), [4](https://www.cpsc.gov/s3fs-public/clothes_1.pdf). Prior art: Dryers with clogged-vent warnings.
- `detergent-cap-dose-lines`: [1](https://www.consumerreports.org/cro/news/2009/06/some-laundry-detergent-caps-can-lead-to-overdosing/index.htm), [2](https://www.consumerreports.org/cro/news/2012/02/confusing-caps-don-t-oversuds-your-duds/index.htm), [3](https://consumerreports.org/cro/magazine/2012/03/detergent-doses-ultra-confusing/index.htm), [4](https://packagingstrategies.com/articles/91263-some-laundry-detergent-caps-can-lead-to-overdosing). Prior art: Pump dispensers; pre-measured pods.
- `end-of-cycle-chime`: [1](https://www.lg.com/us/support/help-library/how-to-turn-onoff-the-washer-chime--20154464592039), [2](https://www.coolblue.de/en/advice/adjust-end-signal-tune-of-samsung-washing-machine.html), [3](https://us.community.samsung.com:443/t5/Washers-and-Dryers/How-to-turn-off-end-of-cycle-chime-on-washer/m-p/2166860), [4](https://www.cyclechat.net/threads/bosch-washing-machine-help.73906).
- `sheets-ball-up`: [1](https://www.whirlpool.com/blog/washers-and-dryers/how-to-stop-sheets-from-balling-up-in-the-dryer.html), [2](https://automaticwasher.org/threads/beko-heat-pump-dpu-8360w-tangling-bedding-into-a-ball.50409), [3](https://www.hunker.com/1930585/how-to-prevent-sheets-balling-up-in-dryer-tricks). Prior art: Reverse-tumble dryers; anti-wad sheet clips.
- `care-label-symbols`: [1](https://laundryandcleaningnews.com/news/carelabel-confusion), [2](https://www.cleveland19.com/story/34535670/what-do-the-laundry-symbols-mean-on-clothes-tags), [3](https://blogs.extension.iastate.edu/answerline/2016/01/21/confused-by-clothing-care-labels/).
