# MedSync — Historical Hardening Sprint Brief

> **Historical planning document, preserved for context.** The brief below
> describes the repository before the hardening and reminder work. Its original
> instructions and unchecked boxes are not a current task list. Current behavior
> is described in [README.md](README.md), [SECURITY.md](SECURITY.md), and
> [the November 2026 audit](docs/AUDIT.md).

## Reconciliation with current source (November 1, 2026)

| Original finding/plan | Current state |
| --- | --- |
| No tests / no CI | Baseline has 67 passing tests and a real push/PR workflow; this PR expands both. |
| Patient-ID authorization vulnerability | Shared application policy is implemented in both adapters; SQLite tests cover forged IDs, unrelated callers, permission levels, and system read-only access. Internal account/circle/worker helpers still require trusted callers. |
| Leave RLS disabled | **Superseded security advice.** A service key bypasses RLS, but direct client API access still needs protection. This PR proposes RLS plus explicit grants/revocations; it does not apply changes to hosted databases. |
| Duplicate Supabase implementation | The unreachable `SupabaseDB` and `supabase_client.py` are absent from the current tree. |
| Plain OTP digest | HMAC-SHA256 is implemented. This PR also counts actual issuance requests and removes plaintext OTP logging. |
| Reminder engine deferred / timers lost on restart | Reconciliation and persistent ledger are implemented. Recovery is current-day only; SMS send/ledger writes are not atomic. |
| Medication rename detaches history | Names are locked in editing; name/time-based identity and duplicate-dose limitations remain. |
| UI/design claims | Four themes are implemented; route, contrast, and motion details in specifications remain design intent rather than conformance evidence. |

---

## Original brief (historical)


## Context

You are working on `medication-tracker` (MedSync): a Streamlit + Supabase medication
adherence app for elderly patients (55+, often 75+) and their family support circle.
~7,200 LOC of Python. It works as a prototype. It has zero tests and at least one live
authorization vulnerability.

Your job this sprint is **hardening, not features.** Read that again — scope creep is the
primary failure mode for this task, and a bigger codebase is a worse outcome than a
smaller correct one.

## Scope boundaries — non-negotiable

**Do not:**
- Add any user-facing feature.
- Build the reminder escalation engine. It is deliberately deferred to next sprint.
- Touch `design-system/` or redesign any UI. The design system is the strongest part of
  this repo. Leave it alone.
- Refactor for elegance. Every diff must trace to a numbered finding below.
- Migrate to Supabase Auth. Too large for this sprint — document the path instead.
- Change the timezone/TEXT-column schema. Real problem, next sprint.

**Do:**
- Read `CLAUDE.md` first and respect the existing constraint contract.
- Verify each finding in the actual code before changing anything. If a finding is wrong,
  stop and say so — do not fix a bug that isn't there.
- Work on a branch. Atomic commits, one finding per commit, real commit messages. The
  commit history is part of the deliverable.

---

## Finding 1 — Live IDOR: write access to any patient's medications (CRITICAL)

`src/pages/add_med.py:145`. `render()` reads `?patient=<id>` from `st.query_params`,
casts it to int, and writes it to `st.session_state["add_medication_for"]` with no
verification that the authenticated user has any relationship to that patient.
`show_add_medication()` then writes a medication row for them.

**Impact:** any authenticated user can append a medication — name, dosage, frequency,
schedule — to any stranger's regimen by editing a URL. The patient sees it on their Today
screen and takes it.

The read path is equally exposed. `src/utils/database_supabase.py:172`:
`get_patient_medications(self, patient_id)` accepts no caller identity. There is no
argument to check against even if you wanted to.

**Fix architecture — this matters more than the fix itself.** Do not scatter `if` checks
across pages. Establish ONE authorization chokepoint in the data layer:

- Change signatures to take the caller:
  `get_patient_medications(self, caller_id: int, patient_id: int)`. Same for
  `get_patient_adherence`, `log_dose`, `add_medication`, and every other patient-scoped
  method.
- Add one private helper — `_assert_can_access_patient(caller_id, patient_id, level)`
  where `level` is `read` or `write` — resolving through `family_members.permissions`.
- Raise a typed `AuthorizationError`. Never return empty on denial; silent empties hide
  bugs and read as correct behavior.
- A patient always has access to themselves.
- Every patient-scoped method calls the helper as its first statement. No exceptions, no
  "internal" bypass variants — a bypass method is how this regresses in six months.
- Update all callers in `src/pages/` and `src/services/`.
- `src/services/scheduler.py:31` runs as a background service. Give it an explicit system
  identity rather than a bypass, or document precisely why it's exempt.
- Mirror the identical signature change in `src/utils/database.py` (`MedicationDB`,
  SQLite) so the two backends stay interchangeable.

Then audit **every** `st.query_params` read that feeds an identifier.
`src/pages/auth.py:841` reads a `mode` param (lower risk, still check it),
`src/pages/patient.py` touches params around `selected_patient`. Treat all of them as
untrusted input.

---

## Finding 2 — The RLS trap: read this before touching the schema

`supabase_schema.sql` enables RLS on all 11 tables and adds zero policies. Its own comment
admits it.

**Do not "fix" this by writing `auth.uid()`-based policies.** They would be worse than
useless, and understanding why is the entire point of this finding:

- This app rolls its own auth: custom `users` table with BIGSERIAL ids, custom bcrypt
  credentials, custom session tokens in `user_sessions`. It does not use Supabase Auth.
- Therefore there is no Supabase JWT, and `auth.uid()` is always NULL.
- The app connects with a single key from `SUPABASE_KEY`. If that's the `service_role`
  key, RLS is bypassed entirely and any policy you write never evaluates. If it's the
  `anon` key, RLS-enabled-with-no-policies denies everything and the app could not
  function — so it is the service key.
- Net effect: writing policies makes the repo *look* secured while changing nothing.
  Security theater layered on security theater.

**Correct action:** remove the misleading `ENABLE ROW LEVEL SECURITY` statements, or keep
them with a comment stating plainly that they are inert under the current service-key
architecture. Then document the real trust boundary in the README: Streamlit executes
server-side, the service key never reaches the browser, and authorization is enforced at
the data-layer chokepoint from Finding 1. Include the migration path to Supabase Auth plus
real RLS as future work.

Choosing honesty over theater here, and explaining the reasoning, is the single most
valuable artifact of this sprint. Do not skip the write-up.

---

## Finding 3 — Dead code: an entire unreachable Supabase implementation

`src/utils/database.py` (63KB) contains `class SupabaseDB` alongside the SQLite
`MedicationDB`. `src/utils/supabase_client.py` exists only to serve it and reads a
`SUPABASE_SECRET_KEY` env var. But `db_factory.py` only ever imports
`database_supabase.MedicationDB`, which reads `SUPABASE_KEY`. `SupabaseDB` is unreachable.

Confirm nothing imports them, then delete `class SupabaseDB` and
`src/utils/supabase_client.py`. `SUPABASE_SECRET_KEY` is a phantom env var — remove every
reference, including in docs.

---

## Finding 4 — OTP hashed with unsalted SHA-256

`src/services/auth.py:82`. A 6-digit OTP has a 10⁶ keyspace; unsalted SHA-256 means anyone
with DB read access reverses every pending OTP in about a second. `bcrypt` is already
imported at line 14.

Use HMAC-SHA256 with a server-side secret from env. HMAC is the better fit than bcrypt
here — verification stays fast, and the secret provides the security rather than a work
factor. Existing rows can be invalidated rather than migrated; OTPs are short-lived by
design.

---

## Finding 5 — Tests that prove security properties, not coverage

`tests/test_medication.py` is 0 bytes while the README advertises a test directory. This is
currently the worst signal in the repo.

Do not chase a coverage number. Write ~15–25 targeted tests against the SQLite backend
with a tmp/in-memory DB, proving the properties that matter:

- User A cannot read patient B's medications → raises `AuthorizationError`
- User A cannot write a medication for patient B
- User A cannot log a dose for patient B
- A family member with `view` permission can read but not write
- A family member with `manage_meds` permission can write
- A patient can always access their own data
- A `?patient=<id>` param cannot escalate access
- OTP verification fails on expired, wrong, and already-used codes
- OTP rate limiting locks out after the configured attempt count

Name each test so the property is legible from the name alone:
`test_user_cannot_read_other_patients_medications`, not `test_get_meds_2`.

---

## Finding 6 — CI

No `.github/workflows` exists. Add one: on push and PR, run `pytest` and `ruff check`, on
Python 3.11 to match the README. Add the status badge to the README.

---

## Finding 7 — README rewrite

The highest-leverage artifact in the repo. It gets 30 seconds of attention from people who
will never clone the code. Restructure it around what this sprint produced:

1. What the app is, who it's for, one screenshot.
2. **Security model** — lead with this. The trust boundary, the chokepoint, why RLS is not
   used, the migration path.
3. **The IDOR** — what it was, how it was found, how it's fixed, the test that proves it.
   Be specific and unembarrassed. Finding your own vulnerability is a credential.
4. Testing and CI.
5. **Known limitations, stated honestly:** timezone-naive scheduling (`scheduled_time` and
   `actual_time` are TEXT with no zone); `dose_logs.medication_name` is denormalized text
   rather than an FK, so renaming a medication detaches its history; in-process APScheduler
   loses pending reminders on restart; Streamlit cannot deliver push notifications, which
   is a real ceiling for the actual users.
6. Roadmap: the reminder escalation engine, with one sentence on why it's the interesting
   engineering problem.

Keep the existing design system section. It's good.

---

## Definition of done

- [ ] Every patient-scoped data method requires caller identity and authorizes through one chokepoint
- [ ] `?patient=<id>` cannot reach data the caller isn't entitled to, and a test proves it
- [ ] `SupabaseDB`, `supabase_client.py`, and `SUPABASE_SECRET_KEY` are gone
- [ ] OTPs are HMAC-SHA256 with a server-side secret
- [ ] `pytest` passes with ≥15 tests, each named for the property it proves
- [ ] CI green on a PR
- [ ] README documents the trust boundary and the IDOR honestly
- [ ] Both DB backends expose identical signatures
- [ ] Clean atomic commit history, one finding per commit

## Working agreement

Confirm each finding against the code before changing it. Ask before deviating from the
chokepoint architecture in Finding 1. If you discover something not listed here, report it
rather than silently fixing it — the point of this sprint is that I can defend every line
of the diff in an interview.
