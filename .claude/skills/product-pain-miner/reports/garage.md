# Garage: pain → redesign report

_Generated from `data/garage.json` (updated 2026-11-03). Do not edit by hand._

**Opportunity** = pain × feasibility. **Pain** = frequency × max(severity, annoyance) × workaround difficulty (0–100). A nuisance counts as much as harm.

## Ranked opportunities

| # | Item | Complaint | Failure | Pain | Opp. | Redesign |
|---|---|---|---|---|---|---|
| 1 | Extension cords | Long cords twist and kink into a tangle when coiled, and the kinks damage the wire inside | Wears out early | 29 | **23** | A flat cord that coils without twisting, with a built-in strap and a lit end that shows the cord is live |
| 2 | Garage door openers | Nothing tells you the door was left open overnight, and built-in alerts are missing, fixed at an hour, or don't fire | No feedback | 22 | **22** | A light on the wall button that stays lit while the door is open, plus an opener setting that auto-closes after a set time or after dark |
| 3 | Cordless power tool batteries | Every brand, and sometimes each line within a brand, uses its own battery, so switching brands means buying new batteries and chargers | Seller-first | 51 | **20** | A shared battery connector standard across brands, with each brand competing on the tool itself |
| 4 | Garage door keypads & remotes | Keypads and remotes stop working with no warning, usually a dead battery, lost pairing or lock mode, and each brand resets differently | No feedback | 19 | **19** | A low-battery blink on the keypad weeks ahead, and an opener light that shows when lock mode is on |
| 5 | Pegboard hooks | Thin 1/8-inch hooks wobble in 1/4-inch holes and fall out every time a tool is taken down | Wears out early | 19 | **19** | Hooks with a twist-lock tab that snaps behind the board, sized to the hole, and sold in the same kit as the board |

## Failure-mode mix

| Failure | Entries |
|---|---|
| No feedback | 2 |
| Wears out early | 2 |
| Seller-first | 1 |

## Evidence

- `extension-cord-tangles`: [1](https://blogs.popularwoodworking.com/review/how-to-roll-up-an-extension-cord), [2](https://www.thisoldhouse.com/tools/21015253/proper-use-and-storage-of-extension-cords), [3](https://www.monoprice.com/p/resources/smart-ways-to-store-extension-cords-safely-and-efficiently). Prior art: Flat cords; lighted-end extension cords.
- `garage-door-left-open`: [1](https://forums.wyze.com/t/garage-door-left-open-notification/37016), [2](https://community.smartthings.com/t/garage-door-open-ness-detection-alert/12097), [3](https://www.techradar.com/home/smart-home/googles-nest-cameras-will-now-alert-you-if-you-left-the-garage-door-open), [4](https://forums.wyze.com/t/garage-door-notification-if-door-is-open-at-specific-time-and-for-time-duration/233941). Prior art: Timer-to-close features; camera-based open-door alerts.
- `tool-batteries-locked-in`: [1](https://toolguyd.com/universal-cordless-power-tool-battery/), [2](https://lawnmowerforum.com/threads/the-insanity-of-battery-incompatibility.16310/exportthread), [3](https://www.alltools.com.au/blog/2021/power-tool-batteries-are-interchangeable), [4](https://ukworkshop.co.uk/threads/battery-compatibility.146494). Prior art: Cordless Alliance System; Power X Change; Bosch Amp Share.
- `garage-keypad-dies`: [1](https://ahs.com/home-matters/repair-maintenance/how-to-troubleshoot-a-garage-door-keypad), [2](https://www.libertyhomeguard.com/troubleshooting-your-garage-door-keypad), [3](https://www.smarthomeperfected.com/garage-door-keypad-not-working/), [4](https://www.trunetto.com/troubleshooting/garage-doors/liftmaster/liftmaster-wireless-keypad-not-working-reset-reprogram).
- `pegboard-hooks-fall-out`: [1](https://www.garagejournal.com/forum/threads/peg-board-hardware-advice.1304/), [2](https://wallcontrol.com/blogs/wall-storage-organization-blog/how-to-prevent-pegboard-hooks-from-falling-out-or-sagging-a-durable-solution-for-organized-wall-storage), [3](https://grassrootsmotorsports.com/forum/grm/how-do-you-pegboard/140927/page1). Prior art: Locking pegboard hooks; steel pegboard systems.
