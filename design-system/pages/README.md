# Per-page design overrides

Files here override `../MASTER.md` for a single page only. Retrieval pattern:

1. Every screen loads `MASTER.md` first.
2. Then, if `<route-slug>.md` exists in this folder, its rules replace the
   corresponding sections from MASTER for that route.
3. If no override file exists, MASTER is used verbatim.

Route slug = filesystem-safe version of the route (`/today` → `today.md`,
`/patients?id=...` → `patient-detail.md`; auth substeps currently share `/`).

Add an override file only when a screen genuinely deviates from the system
(a special animation, a wider layout, a screen-specific illustration). Don't
duplicate MASTER's tokens here.
