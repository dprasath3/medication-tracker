# /today — patient's today's medications

**Overrides MASTER for this screen only.** Everything unstated inherits from
`../MASTER.md`.

> This is the original design intent. The current screen has a 120px ring,
> Streamlit action buttons below cards, and session-local snooze; not every
> planned layout or animation below is implemented. See `src/pages/today.py`.

## Intent

The single most important screen in the product. A patient opens the app,
looks at this screen once, sees exactly what to take now, marks it taken,
closes the app. No decisions, no navigation, no clutter.

## Layout

- Single column, max-width 640px, centered on all viewports.
- Sticky today's-date header at top (Fraunces H1, muted eyebrow "Today").
- Progress ring: 96×96px SVG, `--accent`, centered under the header.
  Text inside the ring is a large tabular numeral ("3/5").
- Below: a chronological list of per-dose cards, staggered entrance (40ms
  each), grouped by time-of-day if there are more than 6.

## Per-dose card

- `--radius-md`, `--surface-card`, `--shadow-1`.
- Left: medication name (Fraunces H3), dosage line (Body Small, muted).
- Right: single primary action button ("I took it", 56px tall, `--accent`).
- Below the button, one tap on the small "Snooze 30 min" text link.
- When taken: card fades to `--surface-inset`, checkmark badge slides in
  from the right (`--dur-slow`, `--ease-out`), primary button replaced by
  small "Taken at 8:42 AM" caption.

## Copy

- Never "medication" — always "med" or the medication name.
- Never "dose" — say "take Metformin".
- Never "administer" — say "took".
- Empty state: "No meds to take right now. Nice." with a subtle SVG blob.

## Motion overrides

- Card entrance: 400ms per card (slower than MASTER's 320) — patients
  need time to read.
- Success animation on "I took it": 480ms checkmark draw, 200ms card fade.
