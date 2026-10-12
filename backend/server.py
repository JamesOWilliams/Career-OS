"""Career OS backend. Product loop: Upload -> Verify -> Target -> Analyze ->
Match Evidence -> Generate -> Validate -> Review. AI proposes; humans verify; code guards truth.
"""
import os
import re
import io
import asyncio
import logging
from datetime import datetime, timezone

from fastapi import FastAPI, APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, EmailStr, Field
from starlette.middleware.cors import CORSMiddleware
from bson import ObjectId

from db import db, OwnedRepo, ensure_indexes
from security import (
    hash_password, verify_password, create_access_token,
    get_current_user, require_admin,
)
import ai
import pipeline
import resume_export
from extraction import extract_text
from seed import seed_admin, seed_james_kb

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("careeros")

app = FastAPI(title="Career OS")
api = APIRouter(prefix="/api")


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def ser(doc: dict) -> dict:
    if not doc:
        return doc
    d = dict(doc)
    if "_id" in d:
        d["id"] = str(d.pop("_id"))
    d.pop("owner_user_id", None)
    return d


# =========================== AUTH ===========================
class RegisterBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)


class LoginBody(BaseModel):
    email: EmailStr
    password: str


@api.post("/auth/register")
async def register(body: RegisterBody):
    email = body.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=409, detail="Email already registered")
    doc = {
        "email": email,
        "password_hash": hash_password(body.password),
        "role": "user",
        "status": "active",
        "created_at": now_iso(),
    }
    res = await db.users.insert_one(doc)
    uid = str(res.inserted_id)
    token = create_access_token(uid, email, "user")
    return {"access_token": token, "user": {"id": uid, "email": email, "role": "user"}}


@api.post("/auth/login")
async def login(body: LoginBody):
    email = body.email.lower()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if user.get("status") == "disabled":
        raise HTTPException(status_code=403, detail="Account disabled")
    uid = str(user["_id"])
    token = create_access_token(uid, email, user.get("role", "user"))
    return {"access_token": token, "user": {"id": uid, "email": email, "role": user.get("role", "user")}}


@api.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return {"id": user["id"], "email": user["email"], "role": user.get("role", "user")}


# =========================== CAREER KNOWLEDGE ===========================
TRACK_ABBR = {"civilian": "CIV", "military": "MIL", "intellectual_property": "IP"}


async def _next_node_id(repo: OwnedRepo, track: str, employer: str) -> str:
    slug = re.sub(r"[^A-Z0-9]", "", (employer or "GEN").upper())[:6] or "GEN"
    n = await repo.count() + 1
    return f"CKN-{TRACK_ABBR.get(track,'CIV')}-{slug}-{n:03d}"


class NodeBody(BaseModel):
    track: str
    identity: dict = {}
    context: dict = {}
    evidence: list[str] = []
    retrieval: dict = {}


@api.get("/career/nodes")
async def list_nodes(track: str | None = None, state: str | None = None,
                     user: dict = Depends(get_current_user)):
    repo = OwnedRepo("career_knowledge", user["id"])
    q = {}
    if track:
        q["track"] = track
    if state:
        q["state"] = state
    nodes = await repo.find(q, sort=[("created_at", -1)])
    return [ser(n) for n in nodes]


@api.post("/career/nodes")
async def create_node(body: NodeBody, user: dict = Depends(get_current_user)):
    repo = OwnedRepo("career_knowledge", user["id"])
    node_id = await _next_node_id(repo, body.track, body.identity.get("employer", ""))
    doc = {
        "node_id": node_id, "track": body.track, "state": "PROPOSED",
        "identity": body.identity, "context": body.context, "evidence": body.evidence,
        "retrieval": {"capabilities": [], "technologies": [], "metrics": [], **body.retrieval},
        "guardrails": [], "provenance": {"source_upload_id": None, "source_span": "manual"},
        "created_at": now_iso(), "verified_at": None,
    }
    saved = await repo.insert(doc)
    return ser(saved)


@api.patch("/career/nodes/{node_id}")
async def edit_node(node_id: str, body: dict, user: dict = Depends(get_current_user)):
    repo = OwnedRepo("career_knowledge", user["id"])
    node = await repo.get(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    allowed = {k: body[k] for k in ("track", "identity", "context", "evidence", "retrieval") if k in body}
    # editing an already-verified node returns it to PROPOSED (no silent canonicalization)
    if node.get("state") == "VERIFIED" and allowed:
        allowed["state"] = "PROPOSED"
        allowed["verified_at"] = None
    await repo.update(node_id, allowed)
    return ser(await repo.get(node_id))


@api.post("/career/nodes/{node_id}/verify")
async def verify_node(node_id: str, user: dict = Depends(get_current_user)):
    repo = OwnedRepo("career_knowledge", user["id"])
    node = await repo.get(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    await repo.update(node_id, {"state": "VERIFIED", "verified_at": now_iso()})
    return ser(await repo.get(node_id))


@api.post("/career/nodes/{node_id}/reject")
async def reject_node(node_id: str, user: dict = Depends(get_current_user)):
    repo = OwnedRepo("career_knowledge", user["id"])
    ok = await repo.delete(node_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Node not found")
    return {"deleted": True}


# =========================== RESUME UPLOAD -> PROPOSED ===========================
@api.post("/resume/upload")
async def upload_resume(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    data = await file.read()
    text = extract_text(file.filename, data)
    if not text or len(text.strip()) < 30:
        raise HTTPException(status_code=422, detail="Could not extract text from file")
    up_repo = OwnedRepo("resume_uploads", user["id"])
    upload = await up_repo.insert({
        "filename": file.filename, "format": file.filename.split(".")[-1].lower(),
        "raw_text": text, "storage_ref": None, "status": "extracted", "created_at": now_iso(),
    })
    upload_id = str(upload["_id"])

    try:
        proposals = await ai.extract_nodes(text)
    except Exception as e:
        logger.exception("extraction failed")
        raise HTTPException(status_code=502, detail=f"AI extraction failed: {e}")

    node_repo = OwnedRepo("career_knowledge", user["id"])
    created = []
    for p in proposals:
        track = p.get("track", "civilian")
        node_id = await _next_node_id(node_repo, track, p.get("identity", {}).get("employer", ""))
        doc = {
            "node_id": node_id, "track": track, "state": "PROPOSED",
            "identity": p.get("identity", {}), "context": p.get("context", {}),
            "evidence": p.get("evidence", []),
            "retrieval": {"capabilities": [], "technologies": [], "metrics": [], **p.get("retrieval", {})},
            "guardrails": [],
            "provenance": {"source_upload_id": upload_id, "source_span": "ai_extraction"},
            "created_at": now_iso(), "verified_at": None,
        }
        created.append(ser(await node_repo.insert(doc)))
    return {"upload": ser(upload), "proposed_nodes": created}


@api.get("/resume/uploads")
async def list_uploads(user: dict = Depends(get_current_user)):
    repo = OwnedRepo("resume_uploads", user["id"])
    ups = await repo.find(sort=[("created_at", -1)])
    for u in ups:
        u.pop("raw_text", None)
    return [ser(u) for u in ups]


# =========================== OPPORTUNITIES + JD ANALYSIS ===========================
class OpportunityBody(BaseModel):
    target_role: str
    organization: str = ""
    job_description: str


@api.post("/opportunities")
async def create_opportunity(body: OpportunityBody, user: dict = Depends(get_current_user)):
    if not body.job_description.strip():
        raise HTTPException(status_code=422, detail="Job description is required")
    repo = OwnedRepo("opportunities", user["id"])
    opp = await repo.insert({
        "target_role": body.target_role, "organization": body.organization,
        "job_description": body.job_description, "created_at": now_iso(),
    })
    opp_id = str(opp["_id"])
    await _analyze_opportunity(user["id"], opp_id, body.target_role, body.organization, body.job_description)
    return ser(await repo.get(opp_id))


async def _analyze_opportunity(owner_id, opp_id, role, org, jd):
    req_repo = OwnedRepo("requirements", owner_id)
    for r in await req_repo.find({"opportunity_id": opp_id}):
        await req_repo.delete(str(r["_id"]))
    reqs = await ai.analyze_jd(role, org, jd)
    for r in reqs:
        await req_repo.insert({
            "opportunity_id": opp_id, "text": r.get("text", ""),
            "category": r.get("category", "explicit_requirement"),
            "tier": int(r.get("tier", 3)), "created_at": now_iso(),
        })


@api.get("/opportunities")
async def list_opportunities(user: dict = Depends(get_current_user)):
    repo = OwnedRepo("opportunities", user["id"])
    return [ser(o) for o in await repo.find(sort=[("created_at", -1)])]


@api.get("/opportunities/{opp_id}")
async def get_opportunity(opp_id: str, user: dict = Depends(get_current_user)):
    repo = OwnedRepo("opportunities", user["id"])
    opp = await repo.get(opp_id)
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    req_repo = OwnedRepo("requirements", user["id"])
    reqs = await req_repo.find({"opportunity_id": opp_id})
    node_repo = OwnedRepo("career_knowledge", user["id"])
    verified_count = await node_repo.count({"state": "VERIFIED"})
    preflight = _preflight(opp, verified_count)
    return {
        "opportunity": ser(opp),
        "requirements": sorted([ser(r) for r in reqs], key=lambda r: r["tier"]),
        "preflight": preflight,
    }


def _preflight(opp, verified_count):
    """Fail-closed runtime profile preflight (Manifest §14/§18)."""
    checks = {
        "core_runtime": True,          # bundled in build
        "resume_contract": True,       # bundled in build
        "resume_template": True,       # bundled in build
        "target_jd": bool(opp.get("job_description", "").strip()),
        "verified_evidence": verified_count > 0,
    }
    blocked = not all(checks.values())
    reasons = [k for k, v in checks.items() if not v]
    return {"status": "BLOCKED" if blocked else "READY", "checks": checks, "missing": reasons}


@api.post("/opportunities/{opp_id}/analyze")
async def reanalyze(opp_id: str, user: dict = Depends(get_current_user)):
    repo = OwnedRepo("opportunities", user["id"])
    opp = await repo.get(opp_id)
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    await _analyze_opportunity(user["id"], opp_id, opp["target_role"], opp.get("organization", ""), opp["job_description"])
    return {"reanalyzed": True}


# =========================== EVIDENCE MATCHING PIPELINE ===========================
_match_tasks: set = set()  # keep strong refs so background jobs aren't garbage-collected


@api.post("/opportunities/{opp_id}/match")
async def run_matching(opp_id: str, user: dict = Depends(get_current_user)):
    """Launch evidence matching as a background job and return immediately.

    Per-requirement AI suggestion calls, run inline, take longer than the ingress
    gateway timeout and cause 'origin webserver returns invalid'. The job runs in the
    background (with bounded concurrency); the client polls GET .../match-status.
    Matching SEMANTICS are unchanged (verified-only retrieval, relevance->strength->
    differentiation->recency scoring, deterministic weighting).
    """
    opp_repo = OwnedRepo("opportunities", user["id"])
    opp = await opp_repo.get(opp_id)
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    node_repo = OwnedRepo("career_knowledge", user["id"])
    if not await node_repo.count({"state": "VERIFIED"}):
        raise HTTPException(status_code=409, detail="No VERIFIED canonical evidence available")

    if opp.get("matching_status") == "running":
        return {"status": "running"}  # idempotent: don't start a duplicate job

    await opp_repo.update(opp_id, {"matching_status": "running", "matching_error": None})
    match_repo = OwnedRepo("evidence_matches", user["id"])
    for m in await match_repo.find({"opportunity_id": opp_id}):
        await match_repo.delete(str(m["_id"]))

    task = asyncio.create_task(_run_matching_job(user["id"], opp_id))
    _match_tasks.add(task)
    task.add_done_callback(_match_tasks.discard)
    return {"status": "running"}


async def _match_one(req, verified, nodes_by_id, sem):
    async with sem:
        req_id = str(req["_id"])
        req_public = {**req, "id": req_id}
        try:
            suggestions = await ai.suggest_matches(req_public, verified)
        except Exception:
            logger.exception("match suggestion failed for req %s", req_id)
            suggestions = []
        scored = []
        for s in suggestions:
            node = nodes_by_id.get(s.get("node_id"))
            if not node:
                continue
            strength = pipeline.compute_match_strength(s.get("relevance", 0), node)
            scored.append({
                "requirement_id": req_id, "source_experience": node["node_id"],
                "canonical_evidence_ref": node["node_id"],
                "provenance": {"rationale": s.get("rationale", ""), "node_id": node["node_id"]},
                "match_strength": strength,
            })
        scored.sort(key=lambda x: x["match_strength"], reverse=True)
        weighted, _ = pipeline.assign_weights(scored)
        return [w for w in weighted if w["match_status"] == "matched"]


async def _run_matching_job(owner_id, opp_id):
    opp_repo = OwnedRepo("opportunities", owner_id)
    try:
        node_repo = OwnedRepo("career_knowledge", owner_id)
        verified = [ser_keep(n) for n in await node_repo.find({"state": "VERIFIED"})]
        nodes_by_id = {n["node_id"]: n for n in verified}
        req_repo = OwnedRepo("requirements", owner_id)
        requirements = await req_repo.find({"opportunity_id": opp_id})
        match_repo = OwnedRepo("evidence_matches", owner_id)

        sem = asyncio.Semaphore(5)
        results = await asyncio.gather(
            *[_match_one(r, verified, nodes_by_id, sem) for r in requirements]
        )
        for matched in results:
            for w in matched:
                await match_repo.insert({"opportunity_id": opp_id, **w, "created_at": now_iso()})
        await opp_repo.update(opp_id, {"matching_status": "complete", "matching_error": None})
    except Exception as e:
        logger.exception("matching job failed")
        await opp_repo.update(opp_id, {"matching_status": "error", "matching_error": str(e)})


@api.get("/opportunities/{opp_id}/match-status")
async def match_status(opp_id: str, user: dict = Depends(get_current_user)):
    repo = OwnedRepo("opportunities", user["id"])
    opp = await repo.get(opp_id)
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return {"status": opp.get("matching_status", "idle"), "error": opp.get("matching_error")}


def ser_keep(doc):
    d = dict(doc)
    d["id"] = str(d.pop("_id"))
    d.pop("owner_user_id", None)
    return d


@api.get("/opportunities/{opp_id}/evidence-map")
async def evidence_map(opp_id: str, user: dict = Depends(get_current_user)):
    opp_repo = OwnedRepo("opportunities", user["id"])
    opp = await opp_repo.get(opp_id)
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    req_repo = OwnedRepo("requirements", user["id"])
    requirements = await req_repo.find({"opportunity_id": opp_id})
    match_repo = OwnedRepo("evidence_matches", user["id"])
    matches = await match_repo.find({"opportunity_id": opp_id})
    node_repo = OwnedRepo("career_knowledge", user["id"])
    nodes = {n["node_id"]: ser_keep(n) for n in await node_repo.find({})}

    rows = []
    for req in sorted(requirements, key=lambda r: r.get("tier", 3)):
        req_id = str(req["_id"])
        rmatches = [m for m in matches if str(m["requirement_id"]) == req_id]
        rmatches.sort(key=lambda m: m["match_strength"], reverse=True)
        enriched = []
        for m in rmatches:
            node = nodes.get(m["source_experience"], {})
            enriched.append({
                "id": str(m["_id"]),
                "source_experience": m["source_experience"],
                "identity": node.get("identity", {}),
                "track": node.get("track"),
                "canonical_evidence": node.get("evidence", [])[:3],
                "provenance": m.get("provenance", {}),
                "match_strength": m["match_strength"],
                "representation_weight": m["representation_weight"],
            })
        rows.append({
            "requirement": ser(req),
            "matches": enriched,
            "gap": len(enriched) == 0,
        })
    total = len(rows)
    gaps = sum(1 for r in rows if r["gap"])
    return {
        "opportunity": ser(opp),
        "rows": rows,
        "matched": len(matches) > 0,
        "summary": {"total": total, "gaps": gaps, "covered": total - gaps},
    }


# =========================== GENERATION + VALIDATION ===========================
def _end_year(end):
    e = str(end or "").lower()
    if "present" in e or "current" in e:
        return 9999
    yrs = [int(t) for t in re.split(r"[^0-9]", e) if t.isdigit() and len(t) == 4]
    return yrs[0] if yrs else 0


@api.post("/opportunities/{opp_id}/generate")
async def generate_resume(opp_id: str, user: dict = Depends(get_current_user)):
    opp_repo = OwnedRepo("opportunities", user["id"])
    opp = await opp_repo.get(opp_id)
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    node_repo = OwnedRepo("career_knowledge", user["id"])
    verified_count = await node_repo.count({"state": "VERIFIED"})
    pf = _preflight(opp, verified_count)
    if pf["status"] == "BLOCKED":
        raise HTTPException(status_code=409, detail={"blocked": True, "preflight": pf})

    match_repo = OwnedRepo("evidence_matches", user["id"])
    matches = await match_repo.find({"opportunity_id": opp_id})
    if not matches:
        raise HTTPException(status_code=409, detail="Run evidence matching before generation")

    nodes = {n["node_id"]: ser_keep(n) for n in await node_repo.find({"state": "VERIFIED"})}
    # only matched verified evidence, grouped by node
    used_node_ids = {m["source_experience"] for m in matches}
    blocks = []
    for nid in used_node_ids:
        node = nodes.get(nid)
        if not node:
            continue
        blocks.append({
            "node_id": nid, "identity": node["identity"],
            "evidence": node["evidence"], "metrics": node.get("retrieval", {}).get("metrics", []),
        })

    try:
        gen = await ai.write_resume_language(opp["target_role"], opp.get("organization", ""), blocks)
    except Exception as e:
        logger.exception("generation failed")
        raise HTTPException(status_code=502, detail=f"AI generation failed: {e}")

    # Build sections deterministically; enforce reverse-chronological order.
    gen_exp = {e.get("node_id"): e for e in gen.get("experiences", [])}
    experiences = []
    claim_prov = []
    for nid in used_node_ids:
        node = nodes.get(nid)
        if not node:
            continue
        ident = node["identity"]
        # IP is never rendered as employment
        employer = "" if node["track"] == "intellectual_property" else ident.get("employer", "")
        bullets = []
        for b in gen_exp.get(nid, {}).get("bullets", []):
            text = b.get("text", "")
            bullets.append({"text": text, "source_node_id": nid})
            claim_prov.append({"text": text, "node_id": nid})
        if not bullets:
            # fall back to canonical evidence directly (still verified)
            for ev in node["evidence"][:3]:
                bullets.append({"text": ev, "source_node_id": nid})
                claim_prov.append({"text": ev, "node_id": nid})
        experiences.append({
            "node_id": nid, "employer": employer, "role": ident.get("role", ""),
            "organization": ident.get("organization", ""), "client": ident.get("client", ""),
            "track": node["track"], "start": ident.get("start", ""), "end": ident.get("end", ""),
            "bullets": bullets,
        })
    experiences.sort(key=lambda e: _end_year(e["end"]), reverse=True)

    sections = {"summary": gen.get("summary", ""), "experiences": experiences}
    rep_repo = OwnedRepo("representations", user["id"])
    for r in await rep_repo.find({"opportunity_id": opp_id}):
        await rep_repo.delete(str(r["_id"]))
    rep = await rep_repo.insert({
        "opportunity_id": opp_id, "template_version": "1.0", "contract_version": "1.0",
        "sections": sections, "claim_provenance": claim_prov, "created_at": now_iso(),
    })
    return ser(rep)


@api.get("/opportunities/{opp_id}/representation")
async def get_representation(opp_id: str, user: dict = Depends(get_current_user)):
    repo = OwnedRepo("representations", user["id"])
    rep = await repo.find_one({"opportunity_id": opp_id})
    if not rep:
        raise HTTPException(status_code=404, detail="No representation generated yet")
    return ser(rep)


@api.get("/opportunities/{opp_id}/export")
async def export_representation(opp_id: str, format: str = "pdf",
                                user: dict = Depends(get_current_user)):
    """Read-only export of the persisted representation as PDF or DOCX.

    Renders the stored representation verbatim; never reads/writes canonical knowledge.
    """
    fmt = (format or "pdf").lower()
    if fmt not in ("pdf", "docx"):
        raise HTTPException(status_code=422, detail="format must be 'pdf' or 'docx'")
    rep_repo = OwnedRepo("representations", user["id"])
    rep = await rep_repo.find_one({"opportunity_id": opp_id})
    if not rep:
        raise HTTPException(status_code=404, detail="No representation generated yet")
    opp_repo = OwnedRepo("opportunities", user["id"])
    opp = await opp_repo.get(opp_id)
    role = (opp or {}).get("target_role", "Resume")
    org = (opp or {}).get("organization", "")
    safe = re.sub(r"[^A-Za-z0-9]+", "_", role).strip("_") or "resume"

    if fmt == "docx":
        data = resume_export.build_docx(rep, role, org)
        media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        fname = f"{safe}_resume.docx"
    else:
        data = resume_export.build_pdf(rep, role, org)
        media = "application/pdf"
        fname = f"{safe}_resume.pdf"
    return StreamingResponse(
        io.BytesIO(data), media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@api.post("/opportunities/{opp_id}/validate")
async def validate(opp_id: str, user: dict = Depends(get_current_user)):
    rep_repo = OwnedRepo("representations", user["id"])
    rep = await rep_repo.find_one({"opportunity_id": opp_id})
    if not rep:
        raise HTTPException(status_code=409, detail="Generate a representation first")

    node_repo = OwnedRepo("career_knowledge", user["id"])
    nodes_by_id = {n["node_id"]: ser_keep(n) for n in await node_repo.find({})}
    req_repo = OwnedRepo("requirements", user["id"])
    requirements = [{**ser(r)} for r in await req_repo.find({"opportunity_id": opp_id})]
    match_repo = OwnedRepo("evidence_matches", user["id"])
    matches = [ser(m) for m in await match_repo.find({"opportunity_id": opp_id})]

    result = pipeline.run_quality_gates(rep, nodes_by_id, requirements, matches)
    vr_repo = OwnedRepo("validation_runs", user["id"])
    for v in await vr_repo.find({"opportunity_id": opp_id}):
        await vr_repo.delete(str(v["_id"]))
    saved = await vr_repo.insert({
        "opportunity_id": opp_id, "gate_results": result["gate_results"],
        "passed": result["passed"], "created_at": now_iso(),
    })
    return ser(saved)


@api.get("/opportunities/{opp_id}/validation")
async def get_validation(opp_id: str, user: dict = Depends(get_current_user)):
    repo = OwnedRepo("validation_runs", user["id"])
    vr = await repo.find_one({"opportunity_id": opp_id})
    if not vr:
        raise HTTPException(status_code=404, detail="No validation run yet")
    return ser(vr)


# =========================== ADMIN (pilot lifecycle ONLY) ===========================
@api.get("/admin/pilots")
async def admin_list_pilots(admin: dict = Depends(require_admin)):
    users = await db.users.find({}).to_list(1000)
    out = []
    for u in users:
        uid = str(u["_id"])
        # usage metadata only — NEVER private content
        out.append({
            "id": uid, "email": u["email"], "role": u.get("role", "user"),
            "status": u.get("status", "active"), "created_at": u.get("created_at"),
            "usage": {
                "uploads": await db.resume_uploads.count_documents({"owner_user_id": uid}),
                "verified_nodes": await db.career_knowledge.count_documents({"owner_user_id": uid, "state": "VERIFIED"}),
                "proposed_nodes": await db.career_knowledge.count_documents({"owner_user_id": uid, "state": "PROPOSED"}),
                "opportunities": await db.opportunities.count_documents({"owner_user_id": uid}),
                "representations": await db.representations.count_documents({"owner_user_id": uid}),
            },
        })
    return out


class InviteBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)


@api.post("/admin/pilots/invite")
async def admin_invite(body: InviteBody, admin: dict = Depends(require_admin)):
    email = body.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=409, detail="Email already exists")
    res = await db.users.insert_one({
        "email": email, "password_hash": hash_password(body.password),
        "role": "user", "status": "active", "created_at": now_iso(),
    })
    return {"id": str(res.inserted_id), "email": email}


async def _set_pilot_status(user_id: str, status: str):
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=404, detail="Pilot not found")
    res = await db.users.update_one({"_id": ObjectId(user_id)}, {"$set": {"status": status}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Pilot not found")
    return {"id": user_id, "status": status}


@api.post("/admin/pilots/{user_id}/enable")
async def admin_enable(user_id: str, admin: dict = Depends(require_admin)):
    return await _set_pilot_status(user_id, "active")


@api.post("/admin/pilots/{user_id}/disable")
async def admin_disable(user_id: str, admin: dict = Depends(require_admin)):
    return await _set_pilot_status(user_id, "disabled")


# =========================== STARTUP ===========================
@app.on_event("startup")
async def startup():
    await ensure_indexes()
    owner_id = await seed_admin()
    await seed_james_kb(owner_id)
    logger.info("Career OS ready. Owner/admin seeded: %s", os.environ["ADMIN_EMAIL"])


@api.get("/")
async def root():
    return {"service": "Career OS", "status": "ok"}


app.include_router(api)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=False,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)
