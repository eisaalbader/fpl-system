# WEEKLY BRIEF — FIXED OUTPUT FORMAT

**Read this after `AGENT_CONTEXT.md`. It is not advice, it is a contract.**

The user wants the same brief, in the same shape, every week. Do not redesign
it. Do not add sections because a week feels interesting. Do not drop sections
because a week feels quiet — a section with nothing in it says "nothing this
week" and that is information.

---

## The trigger

One message, pasted into a new chat in this Project:

```
Read https://raw.githubusercontent.com/eisaalbader/fpl-system/main/AGENT_CONTEXT.md then give me my weekly FPL briefing.
```

Timing: **Friday 19:30 Kuwait** for Friday-deadline gameweeks, **Saturday
11:30 Kuwait** for the usual Saturday 13:00/13:30 Kuwait deadlines. The report
workflow runs 90 minutes before each. Always re-read the deadline from the
report header rather than assuming — it moves for midweek rounds and TV.

---

## What you do before writing a word

1. Fetch `reports/latest.md`.
2. **Check the freshness banner.** 🔴 → say so first, in bold, and lower
   confidence throughout. Do not give confident advice on stale data.
3. **Check the report's own generation timestamp against the deadline.** If the
   report predates matches that have since been played, say so at the top and
   treat every number as provisional. This is the single most common failure
   mode of this brief.
4. Web-search team news for: the captain's club, the vice's club, and every
   player flagged below 100% in the report. Press conferences land Thu/Fri.
5. Check the FT reconciliation banner. If unverified, tell the user to confirm
   in the app before transferring.

Never fabricate a number, a news item, or a source. If you did not query
something, say you did not.

---

## The format — exactly these nine sections, in this order

### 0. Headline
One or two lines. The decision, and the deadline in **Kuwait time**. If there
is nothing to do, say that first and say it plainly.

### 1. Transfer plan
Lead with the verdict: **ROLL / TRANSFER / HIT**. Then the options table from
Section 0 of the report. Then, in one line each:
- the one-gameweek net xP difference,
- your own read on the next 4–6 gameweeks, flagged as judgement not model
  output, because `transfers.py` is one gameweek deep (AGENT_CONTEXT §6.6).

### 2. Starting XI
Table. Columns fixed: `Player | Team | Fixture | xP | P(60+) | Note`.
State the formation. Copy-pasteable names only — no nicknames, no emoji in the
name column.

### 3. Bench
Ordered 1→3 plus the GK, with one line on why that order.

### 4. Captain
Table: `Captain | Vice | xP | Floor (p10) | Ceiling (p90) | Own%`.
Then two lines: why, and what would change it.
State that ceiling/floor are parametric, not simulated (§6.1).

### 5. Chip call
Always present, even when the answer is "hold all four". Name the chips held,
the expiry of the first set (**GW19 deadline, 13:30 GMT, Sat 2 Jan 2027**), and
whether anything is approaching. Flag that there is no option-value model
(§6.7), so this is judgement.

### 6. Risks
Three to five bullets. The assumptions most likely to make the recommendation
wrong — not generic caveats. Reference the specific limitation number where one
applies.

### 7. Watchlist
What could change the decision before the deadline, and when it lands.

### 8. Confidence
One line: **high / medium / low**, and the single biggest driver of the
uncertainty. Be willing to say low.

### 9. Your actions
**Always last. Always present. Numbered. Never more than five.**
Only things the user must physically do — clicks in the FPL app, a commit, a
workflow to trigger. If there is nothing, write `Nothing — you're set.`

---

## Tone rules

- Concise. Decision first, reasoning second.
- No architecture recaps unless asked.
- Tables for anything with more than three rows.
- Never soften a bad recommendation to be encouraging.
- If models or sources disagree, show the disagreement rather than averaging it
  away silently.
- If confidence is low, lower it in the text. Do not hedge in prose while
  presenting a confident-looking table.

---

## Things that are never in this brief

- No Monte Carlo language. It is not built and the user does not want it built.
- No price-change predictions. FPL ships an official one.
- No claim that a transfer was made. The user clicks; you advise.
- No request for an FPL password, ever.
