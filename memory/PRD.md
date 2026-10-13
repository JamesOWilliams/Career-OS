# Career OS — Product Requirements & Build Record

## Original Problem Statement
Career OS MVP v1.0 — a web-based enterprise-intelligence workbench for evidence-grounded
resume intelligence. Product loop must stay observable end to end:
Upload → Verify → Target → Analyze → Match Evidence → Generate → Validate → Review.
AI proposes; humans verify; deterministic code guards truth. Evidence Map is core scope
and must remain visible; "No sufficient canonical evidence" is a first-class result.

## Stack / Architecture
- Frontend: React (CRA + craco), Tailwind, shadcn/ui, lucide-react, sonner. JWT Bearer in localStorage.
- Backend: FastAPI, all routes under `/api`. Modules: `db.py` (Mongo + `OwnedRepo` isolation choke point),
  `security.py` (bcrypt + JWT Bearer, `get_current_user`, `require_admin`), `ai.py` (Claude Sonnet 4.6 via
  Emergent LLM key — extraction, JD analysis, match suggestion, resume language), `pipeline.py`
  (deterministic match strength, weighting, Resume Contract gates), `extraction.py` (PDF/DOCX/TXT),
  `seed.py` (admin + James Williams KB), `server.py` (routes + startup).
- Persistence: MongoDB. Collections: users, career_knowledge, resume_uploads, opportunities,
  requirements, evidence_matches, representations, validation_runs.

## Isolation & Boundaries (enforced)
- Every private collection carries `owner_user_id` derived from the token (never client input);
  `OwnedRepo` force-merges the owner filter on every read/mutation. Verified: cross-user read/mutate → 404.
- Admin = pilot lifecycle only (list usage metadata, invite, enable, disable). No implicit access to
  any user's private content.
- Generation never writes back to canonical knowledge (verified: nodes byte-identical after generate).

## User Personas
- Pilot user: uploads resume, verifies canonical knowledge, targets opportunities, generates & validates resumes.
- Admin/owner (willsky.james@gmail.com): manages pilots; also owns the seeded James Williams KB for regression.

## Implemented (2026-06)
- Phase 1 Auth/Isolation/Data-layer/Admin boundary — DONE (28/28 backend tests pass).
- Phase 2 Resume ingestion → PROPOSED → VERIFIED (edit returns VERIFIED→PROPOSED) — DONE.
- Phase 3 Opportunity + JD analysis + Tier 1–4 + fail-closed preflight (BLOCKED) — DONE.
- Phase 4 Verified-only retrieval, staged matching (relevance→strength→differentiation→recency),
  deterministic weighting (primary/supporting/contextual/chronology/none), Evidence Map UI with
  visible gaps — DONE.
- Phase 5 Generation into Resume Template v1.0 with per-claim provenance + 10 Resume Contract gates — DONE.
- Phase 6/7 Golden path (James KB + Allstate DPM) confirmed: all 10 gates pass; USAA primary; USAA
  SOAP→REST/Java→Go/AWS DFW→ATL/~52 APIs / multi-team release readiness selected; CPS Energy product
  evidence; Avantus employer with DLA as client (relationship integrity); USAF Reserve as program
  management (not PM tenure); IP never rendered as employment; conditional 30% metric excluded.

## HEB final-artifact corrections (2026-06-13) — authorized, implemented, validated
- Suppress IP positions with no verified project name (empty organization) from generated
  resumes (server.py generate_resume); evidence stays canonical + Evidence Map. Fixes the generic
  "Developer — Independent Project" entries (GEN-010/012). Root cause: representation selection.
- Qualitative over-claim guard: consolidation prompt forbids unverified superlatives/role-labels;
  `_validate_consolidated` rejects bullets with `_UNVERIFIED_QUALIFIERS` (sole/solely/single-handed/
  single-handedly/subject matter expert/foremost) unless grounded in cited evidence. Fixes USAA
  "sole product owner" / "subject matter expert" and CPS "subject matter expert". Root cause:
  language synthesis (numeric-only validator didn't catch qualitative over-claims).
- Avantus 40%/80%: verified + correctly provenanced to CKN-CIV-DEFENS-008 — no change (per user).
- Presentation (rendering only, canonical/profile unchanged): US phone formatter
  (`_format_phone`: 10-digit→(XXX) XXX-XXXX, 11-digit+1→+1 (XXX) XXX-XXXX, non-US passthrough) in
  PDF/DOCX/in-app; reduced PDF section/bullet spacing for ~2 pages; consistent heading/date meta.
- Validated on isolated copy vs real HEB target: 2 named IP projects only (no bare IP), no
  over-claims in any bullet, DOCX phone "(210) 550-0251", unnamed-IP evidence retained+VERIFIED,
  8 entries / 21 bullets. Unit tests TestArtifactCorrections 3/3; profile + refinement suites green.

## AFWERX fellowship reconciliation (2026-06-13) — human-authorized, HEB UAT
- Human confirmed CKN-CIV-AFWERX-007 ("Innovation Consultant Fellow", AFWERX/DoD, 2022–2023,
  200+ metric) and CKN-CIV-GEN-018 ("Innovation Fellow / Evaluator", AFWERX Spark, no dates) are
  the SAME fellowship ingested from two uploads. Both previously had authority/position_ref=None,
  so each rendered as a separate civilian position.
- Determination: required CANONICAL association, not representation-only grouping (grouping keys off
  position_ref; the AI/representation layer must not silently decide two records are the same role).
- Applied via `reconcile_afwerx.py` (rollback snapshot `reconcile_afwerx_before.json`): AFWERX-007
  → authoritative (position_ref=self); GEN-018 → associated (position_ref=AFWERX-007). ONLY authority
  + position_ref changed; evidence/identity/metrics/provenance/state (VERIFIED) untouched.
- Validated on isolated copy against the real HEB target: AFWERX renders ONCE with 2 consolidated
  nonredundant bullets, authoritative title/dates used, both USAF Reserve assignments kept distinct
  (433 SFS and United States Air Force Reserve — per human instruction), no evidence lost (73 total).
- NOTE: existing HEB opportunity representations are pre-reconciliation; regenerate to see the single
  AFWERX entry. No branch merge/deploy.

## Candidate Identity & Contact (2026-06-13) — authorized, implemented, validated
- Owner-scoped `candidate_profiles` collection (one per owner, unique index). Human-controlled
  full_name/email/phone/location/links; NEVER written by AI and NEVER defaulted from login email.
- `GET/PUT /api/profile` (ProfileBody): email format + HTTPS-only link validation (422 on bad
  input); partial saves allowed; owner derived from auth token only.
- `generate_resume` snapshots identity verbatim into `sections.identity`; AI functions never
  receive identity/contact data. `GET /representation` adds `identity_stale` (true when the
  profile changed since generation — offers regeneration, never silently alters stored export).
- Pipeline gate `identity_contact` (fail if full name / location / contact missing). Export
  (`/export`) returns 409 `{reason:identity_incomplete, missing[], remediation}` until complete.
- Rendering: identity header (name prominent, contact line, clickable HTTPS links) in in-app
  Representation, PDF (reportlab `<a href>`) and DOCX (python-docx hyperlink relationships);
  "Target:" never leaked. Experiences/categories/dates unchanged.
- Frontend: Identity & Contact panel in Career Profile (`/profile`), separate Save; export 409
  surfaces a remediation toast; stale-snapshot banner in the Representation.
- Validation: backend pytest TestCandidateProfile 8/8; isolated integrated E2E (generate→export
  409→save→regenerate→export 200 + PDF/DOCX header + hyperlinks + stale flag) all assertions pass;
  frontend testing_agent iteration_7 8/8 (panel, validation, persistence, add/remove link,
  owner isolation). Canonical/evidence/matches/opportunities untouched; no merge/deploy.

## Representation Quality Refinement (2026-06-13) — scopes a–e, representation layer only
- a. Deterministic target-relevant selection in generate_resume: matched source nodes grouped by
  authoritative position; per-position bullet budget driven by strongest representation_weight.
- b. Bounded LLM semantic consolidation (ai.consolidate_position), one call per authoritative
  position, concurrency-limited. _validate_consolidated rejects uncited bullets and unsupported
  numbers; deterministic _fallback_bullets on failure. Budgets BULLET_BUDGET
  {primary:5, supporting:3, contextual:2, chronology:1, ip:2}.
- c. Rendering: IP headings are PROJECT-FIRST with verified project name (never bare generic role,
  never invented; no-name IP → "<role> — Independent Project"); shared _format_date_range
  (same-year collapse, "Present" only when canonical ongoing); categories Experience / Military
  Service / Independent Projects, reverse-chron (end→start) WITHIN each category. Applied in-app,
  PDF and DOCX.
- d. Two-page target: budgets + compression gate detail ("two-page target", warn >28).
- e. Multi-source provenance: claim_provenance[].node_ids and bullet.source_node_ids lists
  (back-compat node_id/source_node_id kept); metric_integrity + canonical_truth gates check across
  all contributing nodes.
- CANONICAL UNTOUCHED: generation never writes career_knowledge; omitted accomplishments remain in
  canonical + Evidence Map. Historical representations untouched. No branch merge/release.
- Validation: 14/14 deterministic unit tests; James golden path generation/validation/export pass;
  isolated HEB E2E (authentic canonical copied into a throwaway account, source account NOT modified,
  cleaned up after) → USAA 11→5, CPS 10→3, Avantus 8→2; 9 entries / 24 bullets (~2 pages); all 10
  gates pass; IP shows DIE Orbit / DPO Foundry; dates normalized; PDF clean (no CKN ids).

## Known deviations / residual risks
- Evidence matching is AI-suggested per requirement; occasionally a valid node (e.g. Java→Go) is not
  surfaced for a specific requirement — surfaced honestly as a gap, never fabricated.
- No login brute-force lockout yet (P2). CORS uses env origins with `allow_credentials=False` (Bearer auth).
- `@app.on_event("startup")` deprecated (works; migrate to lifespan later).

## Backlog
- P1: LinkedIn / Interview Stories representations (deferred per Manifest §31); PDF export of representation.
- P2: login throttling; server.py router modularization; richer admin audit log & parsing-queue metrics.
- P2: OCR/scanned PDFs; automated file loading; plugin architecture; enterprise tenancy (all deferred).

## Test Credentials
See /app/memory/test_credentials.md. Admin: willsky.james@gmail.com / CareerOS2026!
