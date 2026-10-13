# Career OS — Representation Quality Refinement: Implementation Contract (AWAITING APPROVAL)

Status: IMPLEMENTED & VALIDATED (2026-06-13) under Option A conditional approval. No canonical
mutation, no DB restore of the existing account, no branch merge. Branch:
`reconciliation/heb-canonical` (NOT merged). Human UAT & release remain separate.

## 0. Environment discrepancy & fixture availability (RESOLVED)
- `owner_user_id` is stored as a STRING in `career_knowledge`; an initial ObjectId-keyed count
  wrongly reported 0 nodes. The AUTHENTIC HEB canonical data IS present in `test_database`
  (owner `6a99a9f579a11f66402c7fa6`, 20 nodes: 12 civilian / 3 military / 5 IP). `/tmp/rep.json`
  is the reviewed problematic representation. No reconstruction from memory was performed.
- HEB end-to-end validation was run against an ISOLATED copy: the 20 canonical nodes were copied
  verbatim into a throwaway test account, the full loop executed, results asserted, and the
  isolated account deleted. The existing HEB account/data was NOT modified.

## 1. Scope (a–e) — representation layer only; canonical untouched
All changes live in: `backend/server.py` (generate_resume, assemble_sections),
`backend/ai.py` (write + new consolidation prompt), `backend/pipeline.py` (gates),
`backend/resume_export.py` (headings/dates), `frontend/src/pages/OpportunityDetail.jsx`
(headings/dates). No change to extraction, canonical storage, or historical representations.

### a. Deterministic target-relevance ranking & per-position selection
- Deterministic code (NOT the LLM) owns selection:
  1. Load `evidence_matches` for the opportunity. For each source node compute its best
     `(representation_weight, match_strength, matched requirement tier)` across all reqs.
  2. Map each source node to its authoritative position via `position_ref` (existing
     `authority_map`). Aggregate per-position: highest weight wins the position's tier
     (primary > supporting > contextual > chronology).
  3. Rank claims within a position by (weight rank, match_strength, requirement tier).
  4. Civilian employment renders in the main Experience section; military and IP render in
     their own labeled sections (relationship/track integrity preserved). Ordering is
     deterministic reverse-chronological (see §c), never relevance-reordered.
- A position is NOT dropped solely for low relevance if it is an authoritative employer in
  the verified history; its bullet budget is reduced instead (chronology-only → 1 line).

### b. Semantic consolidation + configurable bullet budgets
- Budgets (configurable defaults, module constants, not hard truncation):
  `BULLET_BUDGET = {"primary": 5, "supporting": 3, "contextual": 2, "chronology": 1,
  "ip": 2}`.
- Deterministic pre-pass: group a position's candidate bullets; near-duplicate detection
  (normalized token-overlap threshold) clusters overlapping claims (e.g. repeated API
  ownership / SOAP→REST / backlog / 3,078-page assessment).
- LLM consolidation (bounded, read-only on canonical): for each position, send the clustered
  verified evidence + budget to a new `consolidate_bullets` prompt that MAY merge overlapping
  claims and tighten language but MUST NOT add facts/metrics/relationships/accomplishments
  absent from the supplied evidence. One call per authoritative position; bounded concurrency;
  no unbounded retries.
- Validation gate on LLM output (deterministic): every returned bullet must be grounded in
  the supplied evidence (metric tokens must exist in contributing nodes' canonical metrics;
  reject/!drop unsupported bullets). On malformed/timeout/empty → controlled fallback to the
  deterministic top-N canonical/selected bullets (never unvalidated output).
- Distinct, non-overlapping high-value accomplishments are preserved (clustering only merges
  semantically overlapping claims, never unrelated work). If budget would drop an essential
  target-relevant claim, surface a `compression_tradeoff` warning in validation rather than
  silently discarding.

### c. Rendering: IP headings, dates, category ordering (shared, consistent)
- IP heading: use verified project/product identity — prefer `identity.organization`, then a
  verified project/title field if present in canonical; render `"{project} — {role}"`. If no
  verified project name exists, flag a data gap (badge/validation note) — never render a bare
  generic role such as "Developer" and never invent a project name. Same logic in-app + PDF +
  DOCX (shared helper).
- Dates (representation layer, canonical dates unchanged): same-year start==end → show year
  once ("2026"); show "Present" ONLY when canonical explicitly marks ongoing (present/current)
  — never inferred from a missing end; preserve month precision when verified. Shared helper
  used by PDF, DOCX, and frontend.
- Ordering: deterministic reverse-chronological by (end, then start, then stable tiebreak),
  within each category; replaces end-year-only sort. Categories kept separate (Experience /
  Military / Independent Projects).

### d. Two-page target (quality target, not integrity constraint)
- `compression` gate target tuned toward a 2-page recruiter-readable resume via the budgets
  above. Page target never justifies font shrinking, history distortion, or omitting
  essential qualifications; unmet essentials raise `compression_tradeoff` for human review.

### e. Multi-source provenance (backward-compatible)
- `claim_provenance[]` supports `node_ids: [..]` (list) for synthesized bullets AND keeps the
  existing single `node_id` for legacy/unmerged bullets. Bullet objects carry
  `source_node_ids: [..]`; existing `source_node_id` retained for back-compat readers.
- `pipeline._metric_violations` / `metric_integrity` updated to accept a metric if present in
  ANY contributing node's canonical metrics. `canonical_truth` checks all contributing nodes
  are VERIFIED. Frontend evidence popover lists all contributing source nodes.

## 2. Guardrails (hard invariants)
- No canonical `career_knowledge` mutation; omitted accomplishments/metrics remain in canonical
  and visible in the Evidence Map.
- No invented facts/metrics/relationships; no silent metric change.
- Historical `representations` untouched (generation deletes/replaces only the current opp's
  representation, as today).
- No destructive git ops, no branch merge, no release action.

## 3. Regression tests (proposed, synthetic fixtures)
1. Semantic consolidation: a position with 11 overlapping candidate bullets → ≤budget, no two
   bullets semantically duplicate; distinct accomplishments retained.
2. Evidence retention: claims omitted from the resume still present in canonical + evidence-map
   endpoint (nothing destroyed).
3. Provenance: every synthesized bullet maps to ≥1 VERIFIED node; multi-source bullet retains
   all contributing node_ids; metric_integrity passes across contributing nodes; invented
   metric is rejected.
4. Relationship/category integrity: IP never rendered as employment; client never as employer;
   military/IP in their own sections; IP heading uses verified project name, never bare role.
5. Chronology & dates: reverse-chron (end→start tiebreak); same-year collapse; "Present" only
   when canonical ongoing; no invented dates.
6. Target relevance: primary/supporting requirements covered; chronology-only positions
   compressed to ≤1 line.
7. Export consistency: PDF & DOCX == persisted representation; no CKN IDs/footers; headings and
   dates match in-app exactly.
8. Canonical integrity + historical representations: nodes byte-identical before/after
   generate; prior representations unchanged.
9. Compression/2-page: total bullets within budget; `compression_tradeoff` raised when an
   essential target-relevant claim can't fit (not silently dropped).

## 4. Validation strategy
- Synthetic regression fixtures (controlled): overlapping evidence, authoritative/associated/
  superseded clusters, multi-source provenance, target weighting, budgets, IP project headings,
  chronology, malformed-LLM handling, PDF/DOCX consistency.
- HEB end-to-end: DEFERRED — requires an authentic HEB canonical snapshot/export restored into
  a dedicated isolated test account/DB (not an existing user). Will request/receive from human.
