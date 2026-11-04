# Verification record

Initial review: November 1, 2026. Final review: November 4, 2026. Baseline: `e8e59c48208e42c7b6de9b0bffa45d75ed5ddfe1`.

## Final review results (November 4)

- Before fixes, the existing branch suite passed: **82 tests in 5.23s**, plus Ruff, in a fresh Python 3.11.17 environment.
- The first new review tests reproduced **10 failures and 1 pass** against `84860b9`. They cover gaps in session revalidation, OTP demo gating, routing, and HTML escaping; these are not ten separately introduced PR vulnerabilities.
- After fixes and expanded coverage: **99 tests passed in 4.11s**; **Ruff passed**. The additional cases include the Supabase OTP count contract with zero/large/missing totals and redaction of provider errors.
- The expanded real Chromium walkthrough **passed**: original sign-in/logging/snooze/views, medication submission, valid-session refresh, forbidden write form, unrelated-patient denial, loaded-session revocation, auth Back navigation, guest refresh, and 375px rendering. It used an unused loopback port and a disposable synthetic SQLite database.
- The strengthened SQL script **passed locally with PGlite**: twelve table boundaries, table/column/sequence denial, server privileges and CRUD, preserved denial despite an old permissive policy, and repeat application after a sequence rename. The prior schema reproduced a missing `users_id_seq` error with that renamed-sequence fixture.
- Fresh captures went to a scratch directory; the original three November 1 screenshots were visually reviewed and preserved. Browser tests are a local smoke check, not a GitHub Actions job or a complete mobile/accessibility audit.

- GitHub PR CI [run 41917122698](https://github.com/dprasath3/medication-tracker/actions/runs/41917122698), head `df27bd1`, **passed**: **99 tests in 3.07s**, Ruff, and the strengthened SQL checks against **PostgreSQL 16.15**. The PR event tested GitHub's temporary merge commit against the unchanged base. The paired branch-push run also passed. The following documentation-only commit does not change the tested application, workflow, or SQL; its current-head status remains visible in the PR Checks tab.
- **54 relative documentation links resolve**; `git diff --check` passed. CI emitted a non-blocking warning that `actions/checkout@v4` and `actions/setup-python@v5` target deprecated Node 20 and are being run on Node 24. Review and update/pin action versions as part of dependency maintenance.

Earlier run IDs below establish only the earlier revisions' results.

## Initial review results (November 1)

| Check | Result | Scope |
| --- | --- | --- |
| Baseline `python -m pytest -q` | **67 passed in 3.15s** | Original suite, Python 3.11.17, temporary SQLite and test doubles |
| Baseline `ruff check .` | **Passed** | Existing E9/F correctness rules; F401/F841 remain excluded |
| Updated `python -m pytest -q` | **82 passed in 3.19s** | Includes 15 new cases covering issuance limits, logging privacy, demo isolation, sign-in gating/routing, timezone, URL fallback, and safe rendering |
| Updated `ruff check .` | **Passed** | Same lint scope; no artificial coverage target |
| `python scripts/capture_demo.py` | **Passed** | Real Chromium + Streamlit + synthetic SQLite: email login, dose logging, snooze, caregiver View/Add med, view-only controls, 375px render; three screenshots |
| SQL access-boundary script | **Passed locally with PGlite** | Real PostgreSQL-compatible engine, schema applied twice; server-role CRUD; client reads/writes denied; all twelve tables protected |
| `git diff --check` | **Passed** | Whitespace / patch integrity |
| Updated GitHub CI | **Success: 82 tests in 3.22s, Ruff, PostgreSQL 16 boundary job** | [Run 41354502942](https://github.com/dprasath3/medication-tracker/actions/runs/41354502942), head `f8dabf5`, November 1, 2026 |
| Baseline GitHub CI | **Success** | [Run 33538876393](https://github.com/dprasath3/medication-tracker/actions/runs/33538876393), September 1, 2026, baseline SHA |

Durations above are single observations, not benchmarks. Remote results for this branch are shown in the pull request's Checks tab. The main-branch README badge is not proof that an unmerged PR passed.

## Reproduce the Python checks

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -q
ruff check .
```

`tests/conftest.py` clears inherited service credentials, disables `.env` loading, and blocks socket connections during tests. SQLite fixtures use temporary files. Notification tests use fake providers or patched send methods; no real SMS or email is needed.

Observed local versions: Python 3.11.17, pytest 9.2.0, Ruff 0.16.1, Streamlit 1.66.1, APScheduler 3.11.3, bcrypt 5.0.0, Supabase client 2.33.0. Final-review CI resolved Supabase 2.34.0. Dependencies are not fully locked, so another install may resolve different versions. The Streamlit lower bound was corrected to 1.36 for `st.navigation`/`st.Page`; the full suite was not run against every minimum dependency version.

## Reproduce browser checks

See [DEMO.md](DEMO.md). Playwright 1.51.0 / Chromium 134 were used. This is an optional smoke/capture script, not a full browser regression suite or an accessibility certification. Images were visually inspected; no screenshots were synthesized or edited to mimic application behavior.

## Reproduce PostgreSQL checks

In a **new disposable local database** using an administrative test role:

```bash
psql -d medsync_test -v ON_ERROR_STOP=1 -f tests/sql/server_access.sql
```

The script creates test roles, models older permissive client defaults, applies the schema twice (with a renamed sequence and permissive-policy fixture between applications), verifies server-role CRUD and client table/column/sequence restrictions, then rolls back. Never run it against a production project. The CI job uses an ephemeral PostgreSQL 16 service. The local environment did not provide PostgreSQL server binaries; the same SQL was also executed through PGlite after expanding psql `\ir` includes. Hosted Supabase/PostgREST was not contacted.

## What these checks do not establish

- Hosted Supabase adapter behavior, API exposure, policies, secret rotation, or deployment status.
- Actual Twilio delivery, SMTP delivery, consent/recipient correctness, or medication safety.
- Exactly-once delivery under crashes or multiple workers, per-recipient retry, midnight/DST behavior, or performance at scale.
- Full password-reset/email-verification browser flows; their route handlers are absent.
- All session lifecycle combinations (beyond tested refresh/revocation), all page/role combinations, all themes, keyboard/screen-reader behavior, or WCAG conformance.
- Complete vulnerability/advisory absence. The bounded source/history scan is described in [SECURITY.md](../SECURITY.md).
