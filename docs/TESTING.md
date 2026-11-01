# Verification record

Review date: November 1, 2026. Baseline: `e8e59c48208e42c7b6de9b0bffa45d75ed5ddfe1`.

## Results

| Check | Result | Scope |
| --- | --- | --- |
| Baseline `python -m pytest -q` | **67 passed in 3.15s** | Original suite, Python 3.11.17, temporary SQLite and test doubles |
| Baseline `ruff check .` | **Passed** | Existing E9/F correctness rules; F401/F841 remain excluded |
| Updated `python -m pytest -q` | **82 passed in 3.19s** | Includes 15 new cases covering issuance limits, logging privacy, demo isolation, sign-in gating/routing, timezone, URL fallback, and safe rendering |
| Updated `ruff check .` | **Passed** | Same lint scope; no artificial coverage target |
| `python scripts/capture_demo.py` | **Passed** | Real Chromium + Streamlit + synthetic SQLite: email login, dose logging, snooze, caregiver View/Add med, view-only controls, 375px render; three screenshots |
| SQL access-boundary script | **Passed locally with PGlite** | Real PostgreSQL-compatible engine, schema applied twice; server-role CRUD; client reads/writes denied; all twelve tables protected |
| `git diff --check` | **Passed** | Whitespace / patch integrity |
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

Observed key versions: Python 3.11.17, pytest 9.2.0, Ruff 0.16.1, Streamlit 1.66.1, APScheduler 3.11.3, bcrypt 5.0.0, Supabase client 2.33.0. Dependencies are not fully locked, so another install may resolve different versions. The Streamlit lower bound was corrected to 1.36 for `st.navigation`/`st.Page`; the full suite was not run against every minimum dependency version.

## Reproduce browser checks

See [DEMO.md](DEMO.md). Playwright 1.51.0 / Chromium 134 were used. This is an optional smoke/capture script, not a full browser regression suite or an accessibility certification. Images were visually inspected; no screenshots were synthesized or edited to mimic application behavior.

## Reproduce PostgreSQL checks

In a **new disposable local database** using an administrative test role:

```bash
psql -d medsync_test -v ON_ERROR_STOP=1 -f tests/sql/server_access.sql
```

The script creates test roles, models older permissive client defaults, applies the schema twice, verifies server-role CRUD and client restrictions, then rolls back. Never run it against a production project. The CI job uses an ephemeral PostgreSQL 16 service. The local environment did not provide PostgreSQL server binaries; the same SQL was also executed through PGlite after expanding psql `\ir` includes. Hosted Supabase/PostgREST was not contacted.

## What these checks do not establish

- Hosted Supabase adapter behavior, API exposure, policies, secret rotation, or deployment status.
- Actual Twilio delivery, SMTP delivery, consent/recipient correctness, or medication safety.
- Exactly-once delivery under crashes or multiple workers, per-recipient retry, midnight/DST behavior, or performance at scale.
- Full password-reset/email-verification browser flows; their route handlers are absent.
- Full session lifecycle behavior in a browser, all page/role combinations, all themes, keyboard/screen-reader behavior, or WCAG conformance.
- Complete vulnerability/advisory absence. The bounded source/history scan is described in [SECURITY.md](../SECURITY.md).
