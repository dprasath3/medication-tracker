# CLAUDE.md — repo scope contract

This file is the **scope contract** for AI coding assistants working in this
repo. It exists so future sessions don't drift away from decisions we've
already made together.

Read it before touching anything.

---

## What this project is

Streamlit + Supabase medication tracker for elderly patients (55+, often 75+)
and their family support circle. The current implementation and known gaps are documented in README.md,
SECURITY.md, and docs/AUDIT.md. The original UI sprint constraints below guide
UI work; an explicitly authorized maintenance/security task may touch other layers.

Design system source of truth: **`design-system/MASTER.md`**. Per-page
overrides in `design-system/pages/`. Every UI decision must trace to one of
those files or to a fresh query against the installed
[ui-ux-pro-max skill](.claude/skills/ui-ux-pro-max/SKILL.md).

---

## Do

- Read `design-system/MASTER.md` before adding CSS or picking a color.
- Use CSS custom properties from the theme system. Every color reference
  should be `var(--surface-card)`, `var(--text)`, `var(--accent)`, etc.
- Keep body text at **≥ 17px** and line-height **≥ 1.55**. Patients skew older.
- Use `Fraunces` for headings, `Instrument Sans` for body — both via Google Fonts.
- Wrap animations in `@media (prefers-reduced-motion: no-preference)`.
- Wrap DB reads in `@st.cache_data(ttl=60)`. Wrap the DB client and auth
  service in `@st.cache_resource`.
- Route with `st.navigation` + `st.Page`. Every screen has a stable URL.
- Commit in logical chunks. Follow the user's branch/PR instructions; an explicit
  request to commit and open a PR already authorizes those actions.

## Don't

- Don't hardcode hex outside the theme definitions.
- Don't use emoji as structural icons (only allowed in user-generated content).
- Don't ship a corner radius below **8px**. Softness is a design signal.
- Don't use pure `#000` on pure `#FFF` outside the `high-contrast` theme.
- Don't add violet/pink/AI-purple gradients or glassmorphism.
- Don't touch `src/utils/database*.py`, `src/models/`, or `src/services/`
  except when a UI change legitimately requires a new return field or method.
- Keep production UI backed by real database operations. Synthetic demos and
  test fixtures belong in isolated temporary databases (see scripts/demo.py).
- Don't skip the skill workflow for design decisions. Run
  `python3 .claude/skills/ui-ux-pro-max/scripts/search.py "..." --domain <d>`
  and cite the result.

---

## Design pillars

1. **Warm, not clinical.** Cream backgrounds over pure white, warm accents
   (terracotta, sage teal, amber) over saturated primaries.
2. **Semi-formal, not playful.** No exclamation marks, no cutesy copy.
   The interface is a trusted family friend, not a mascot.
3. **Soft.** No hard edges. Everything ≥ 12px radius. Cards and inputs
   default to 16px. Sheets to 24px.
4. **Big and legible.** 17px body minimum. 48px input height. 44×44pt touch
   targets. High contrast in every theme.
5. **Motion means something.** Every animation communicates cause and
   effect. Never decorative-only. Always motion-safe.

## Themes shipped

`warm-cream` (default), `cool-sage`, `twilight` (soft warm dark),
`high-contrast` (high-contrast design target; no conformance certification). Users pick from Settings, choice persists to
the `users.theme` column. Swap via `[data-theme]` on `<html>`; never
regenerate whole CSS blocks.

## Routing

The implemented router is in `src/web_app.py`. Signed-out users see `/`;
patients default to Today and caregivers to Dashboard. Other routes include
`/patients?id=...`, `/add-med?patient=...`, `/circle`, `/onboarding`, and `/settings`.
Auth substeps mostly use session state. The old `/auth/otp` and `/patients/<id>`
paths were design plans, not implemented routes. See docs/ARCHITECTURE.md.

Use session state to pass patient selection through `st.switch_page`, which
can clear query parameters. Treat URL identifiers as untrusted. URL bearer-token
persistence is a known security/usability limitation, not a recommended design.

## Fonts

```html
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600;9..144,700&family=Instrument+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
```

- Heading: `'Fraunces', serif` (optical-size aware)
- Body: `'Instrument Sans', sans-serif`

## Pre-flight before you ship a change

- Boot `venv/bin/streamlit run src/web_app.py` and walk the route you changed.
- Toggle every theme, confirm no hardcoded colors leaked in.
- Enable OS reduced-motion, confirm animations degrade cleanly.
- Test at 375px viewport (small phone).
- Diff the change; if it grew past its stated scope, split it.

---

## The skill

`ui-ux-pro-max` is installed at `.claude/skills/ui-ux-pro-max/`. It's a local
Python-only search engine over 35+ CSV databases of design guidance. Use it:

```bash
# Full design system query (do this once per project or per major change)
python3 .claude/skills/ui-ux-pro-max/scripts/search.py \
  "<multi-word product description>" --design-system \
  --variance <1-10> --motion <1-10> --density <1-10> \
  --persist -p "Medication Tracker"

# Domain query (do this for individual decisions)
python3 .claude/skills/ui-ux-pro-max/scripts/search.py \
  "<keywords>" --domain <style|color|typography|ux|gsap|icons|chart|landing|react|web>

# Stack-specific query
python3 .claude/skills/ui-ux-pro-max/scripts/search.py \
  "<keywords>" --stack html-tailwind   # closest to our Streamlit CSS
```

For our design dials, use **variance 4** (balanced/modern), **motion 6**
(standard), **density 3** (spacious — patient-friendly).
