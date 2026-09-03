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
