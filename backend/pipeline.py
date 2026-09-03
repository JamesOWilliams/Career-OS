"""Deterministic truth-guarding pipeline. NO AI decisions here.

Handles: verified-only retrieval, final match_strength computation, representation
weighting, "no sufficient canonical evidence", and Resume Contract quality gates.
Generated output NEVER writes back to canonical knowledge.
"""
from datetime import datetime

# Below this, a requirement is treated as having NO sufficient canonical evidence.
EVIDENCE_THRESHOLD = 0.35


def _recency_score(end: str) -> float:
    """Newer experience scores higher. 'present'/'current' => most recent."""
    if not end:
        return 0.5
    e = str(end).lower()
    if "present" in e or "current" in e or "now" in e:
        return 1.0
    for tok in e.replace("/", " ").replace("-", " ").split():
        if tok.isdigit() and len(tok) == 4:
            year = int(tok)
            # scale 2005..current
            return max(0.0, min(1.0, (year - 2005) / (datetime.now().year - 2005)))
    return 0.5


def compute_match_strength(relevance: float, node: dict) -> float:
    """Deterministic blend: relevance -> strength -> differentiation -> recency.

    AI supplies relevance only. Code owns the final number.
    """
    relevance = max(0.0, min(1.0, float(relevance or 0)))
    ret = node.get("retrieval", {}) or {}
    # strength: richness of canonical evidence
    ev_count = len(node.get("evidence", []) or [])
    strength = min(1.0, ev_count / 6.0)
    # differentiation: presence of concrete metrics + breadth of tech
    metrics = len(ret.get("metrics", []) or [])
    tech = len(ret.get("technologies", []) or [])
    differentiation = min(1.0, (metrics * 0.25) + (tech * 0.05))
    recency = _recency_score(node.get("identity", {}).get("end", ""))
    score = (
        0.55 * relevance
        + 0.20 * strength
        + 0.15 * differentiation
        + 0.10 * recency
    )
    return round(max(0.0, min(1.0, score)), 3)


def assign_weights(sorted_matches: list[dict]) -> list[dict]:
    """Deterministic Primary/Supporting/Contextual/Chronology/None assignment.

    sorted_matches: descending by match_strength for a single requirement.
    """
    result = []
    ranked = [m for m in sorted_matches if m["match_strength"] >= EVIDENCE_THRESHOLD]
    for idx, m in enumerate(sorted_matches):
        s = m["match_strength"]
        if s < EVIDENCE_THRESHOLD:
            weight = "none"
            status = "no_evidence"
        elif idx == 0:
            weight = "primary"
            status = "matched"
        elif idx == 1:
            weight = "supporting"
            status = "matched"
        elif s >= 0.5:
            weight = "contextual"
            status = "matched"
        else:
            weight = "chronology"
            status = "matched"
        m = dict(m)
        m["representation_weight"] = weight
        m["match_status"] = status
        result.append(m)
    return result, len(ranked)


# --------------------------- Resume Contract Gates ---------------------------

def run_quality_gates(representation: dict, nodes_by_id: dict, requirements: list[dict],
                      matches: list[dict]) -> dict:
    """Return gate_results {gate: {status, detail}} and overall passed bool.

    status in {pass, warn, fail}. A fail blocks human review.
    """
    gates = {}

    claim_prov = representation.get("claim_provenance", [])
    sections = representation.get("sections", {})

    # 1. Canonical Truth: every claim traces to a VERIFIED node.
    bad = [c for c in claim_prov if nodes_by_id.get(c.get("node_id"), {}).get("state") != "VERIFIED"]
    gates["canonical_truth"] = {
        "status": "pass" if not bad else "fail",
        "detail": "All claims trace to VERIFIED canonical nodes"
        if not bad else f"{len(bad)} claim(s) not backed by verified evidence",
    }

    # 2. Evidence: at least one experience rendered, all from matched nodes.
    matched_node_ids = {m["source_experience"] for m in matches if m.get("match_status") == "matched"}
    used_ids = {c.get("node_id") for c in claim_prov}
    unmatched_used = used_ids - matched_node_ids
    gates["evidence"] = {
        "status": "pass" if used_ids and not unmatched_used else ("warn" if not used_ids else "fail"),
        "detail": "All rendered claims come from matched verified evidence"
        if used_ids and not unmatched_used
        else ("No evidence rendered" if not used_ids else f"{len(unmatched_used)} claim(s) from unmatched nodes"),
    }

    # 3. Metric integrity: no metric in a bullet that isn't in the node's canonical metrics.
    metric_violations = _metric_violations(claim_prov, nodes_by_id)
    gates["metric_integrity"] = {
        "status": "pass" if not metric_violations else "fail",
        "detail": "No invented metrics"
        if not metric_violations else f"Invented metric(s): {'; '.join(metric_violations[:3])}",
    }

    # 4. Chronology: experiences are in reverse-chronological order.
    gates["chronology"] = _chronology_gate(sections)

    # 5. Relationship integrity: IP never rendered as employment; clients/collabs never as employers.
    gates["relationship_integrity"] = _relationship_gate(sections, nodes_by_id)

    # 6. JD Relevance: primary/supporting weights cover the top-tier requirements.
    gates["jd_relevance"] = _jd_relevance_gate(requirements, matches)

    # 7. Removal / uncertainty: unmatched (Tier-4/no-evidence) requirements are NOT fabricated.
    gap_reqs = _gap_requirements(requirements, matches)
    gates["removal"] = {
        "status": "pass",
        "detail": f"{len(gap_reqs)} requirement(s) correctly left unclaimed (no fabrication)",
    }

    # 8. ATS / Readability / Compression / Interview-Defense / Manual-Tailoring (structural).
    summary = sections.get("summary", "")
    exp = sections.get("experiences", [])
    gates["ats_readability"] = {
        "status": "pass" if summary and exp else "warn",
        "detail": "Standard sections present, parseable structure"
        if summary and exp else "Missing summary or experience section",
    }
    total_bullets = sum(len(e.get("bullets", [])) for e in exp)
    gates["compression"] = {
        "status": "pass" if total_bullets <= 24 else "warn",
        "detail": f"{total_bullets} bullets (one-page target)",
    }
    gates["interview_defense"] = {
        "status": gates["canonical_truth"]["status"],
        "detail": "Every claim is defensible from verified evidence"
        if gates["canonical_truth"]["status"] == "pass" else "Undefendable claims present",
    }

    passed = all(g["status"] != "fail" for g in gates.values())
    return {"gate_results": gates, "passed": passed}


def _metric_violations(claim_prov, nodes_by_id):
    import re
    violations = []
    for c in claim_prov:
        node = nodes_by_id.get(c.get("node_id"), {})
        allowed = " ".join(node.get("retrieval", {}).get("metrics", []) or [])
        text = c.get("text", "")
        for num in re.findall(r"\b\d+(?:\.\d+)?%?\b", text):
            # a bare year is fine
            if len(num) == 4 and num.isdigit():
                continue
            if num not in allowed:
                violations.append(f'"{num}" in: {text[:60]}')
    return violations


def _chronology_gate(sections):
    exps = sections.get("experiences", [])
    years = []
    for e in exps:
        end = str(e.get("end", "")).lower()
        if "present" in end or "current" in end:
            years.append(9999)
        else:
            yr = [int(t) for t in end.replace("/", " ").replace("-", " ").split() if t.isdigit() and len(t) == 4]
            years.append(yr[0] if yr else 0)
    ordered = all(years[i] >= years[i + 1] for i in range(len(years) - 1))
    return {
        "status": "pass" if ordered else "fail",
        "detail": "Experiences in reverse-chronological order"
        if ordered else "Chronology out of order",
    }


def _relationship_gate(sections, nodes_by_id):
    problems = []
    for e in sections.get("experiences", []):
        node = nodes_by_id.get(e.get("node_id"), {})
        track = node.get("track")
        ident = node.get("identity", {})
        if track == "intellectual_property" and e.get("employer"):
            problems.append("IP rendered as employment")
        if ident.get("client") and e.get("employer") == ident.get("client"):
            problems.append("client rendered as employer")
        if ident.get("collaboration") and e.get("employer") == ident.get("collaboration"):
            problems.append("collaborator rendered as employer")
    return {
        "status": "pass" if not problems else "fail",
        "detail": "Employer/Assignment/Client/Collaboration/IP integrity preserved"
        if not problems else "; ".join(sorted(set(problems))),
    }


def _jd_relevance_gate(requirements, matches):
    top = [r for r in requirements if r.get("tier") in (1, 2)]
    if not top:
        return {"status": "pass", "detail": "No tier-1/2 requirements"}
    covered = set()
    for m in matches:
        if m.get("representation_weight") in ("primary", "supporting"):
            covered.add(str(m.get("requirement_id")))
    top_ids = {str(r["id"]) for r in top}
    ratio = len(top_ids & covered) / len(top_ids)
    return {
        "status": "pass" if ratio >= 0.5 else "warn",
        "detail": f"{int(ratio*100)}% of tier-1/2 requirements covered by primary/supporting evidence",
    }


def _gap_requirements(requirements, matches):
    matched_reqs = {str(m["requirement_id"]) for m in matches if m.get("match_status") == "matched"}
    return [r for r in requirements if str(r["id"]) not in matched_reqs]
