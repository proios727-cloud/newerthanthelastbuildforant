---
name: rotation-review
description: Review the ETF rotation rule's monthly paper decision before anyone acts on it. It re-derives the picks from the stored bars, checks the rule's settings, the paper tickets' sizes and limits, the data checks and the record so far, and writes a one-page pass/flag review with blank sign-off lines for analyst, Risk Officer and trader. Use on the first trading days of a month after the forward test logs a decision, when the nightly feed reports `decision_tonight`, or when asked whether this month's rotation is right, safe to review or ready to hand over. Research only; it never previews, places or approves an order.
---

# Rotation review

The forward test logs one decision a month (`docs/forward-feed.md`). This skill is the check between that log and any
person who might act on it: **recompute → check → write the review → hand over**. It changes nothing in the log.

## 1. Get the log

```bash
git fetch -q origin shadow-data
D=$(mktemp -d) && git worktree add -q --detach "$D" origin/shadow-data
```

The log is `$D/chart-forward/` (`rotation.jsonl`, `rotation_tickets.jsonl`, `ROTATION.json`, `DOCTOR.json`,
`VALIDATE.json`, `OVERLAY.json`, `rotation_trend200.jsonl`, the bars in `etf/`).

## 2. Run the review

```bash
python3 scripts/rotation_review.py "$D/chart-forward" REVIEW.md   # exit 1 if anything is flagged
```

It checks:

| Check | Passes when |
|---|---|
| Decision is this month's | the last decision falls in the latest bar's month |
| Recorded on time | the entry has no `late` flag (a late entry is still made from bars up to the decision day) |
| Rule settings unchanged | `{"lookback": 60, "top": 3}`, the rule as vetted in `docs/rotation-sleeve.md` |
| Picks recompute | `chart.forward.rotation_signal` on the stored bars up to the decision day gives the same picks and momentum |
| Paper tickets | each buy is 5% of the 100,000 paper NAV at the decision close, rounded down, with a limit 50 bp above it; each sell has a limit 50 bp below; buys are exactly the new picks |
| Data checks | `DOCTOR.json` is ok |
| Price validation | no fund has problems in `VALIDATE.json` |

Then it summarises the record so far (completed months, rule against basket), the defensive 200-session variant and
the SPY regime flag.

## 3. Read every flag before handing over

A flag is a question to answer, not a verdict. Find the cause, then say it in one line in the review's chat summary:

- **Picks recompute** fails: compare the momentum tables. Usually a vendor bar changed after the decision, or a fund
  is missing a day. Never edit the log or the bars by hand; report the difference.
- **Recorded on time** fails: the feed missed the decision day and caught up (`CATCH_UP` in `chart/forward.py`). The
  picks are still from the decision day's bars. Note how many sessions late.
- **Paper tickets** fails: recompute one ticket by hand from the close in `etf/<FUND>.csv`, then report which side is
  wrong.
- **Data checks / Price validation** fail: quote the problems. A lagging fund stalls the rule (the rotation uses only
  dates every fund has).
- **Rule settings unchanged** fails: someone changed the rule. That needs a new vetting (`strategy-vetting` skill),
  not a review.

## 4. Hand over

- Post `REVIEW.md`'s contents, or a short summary plus the flagged rows, to the person who asked.
- Leave the sign-off lines blank. People fill them, in order: analyst, then Risk Officer, then trader, then
  `EXECUTE`. A green review is not an approval.
- Clean up with `git worktree remove --force "$D"`.

## Never

- Place, preview, or approve an order, or fill in a sign-off line.
- Edit `rotation.jsonl`, the tickets, or any bar to make a check pass.
- Call one month's result evidence for or against the rule. The long-history verdict is in `docs/rotation-sleeve.md`.
