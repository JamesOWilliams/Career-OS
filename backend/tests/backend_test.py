"""Career OS backend regression tests.

Covers: auth (register/login/me), cross-user isolation, admin boundary,
PROPOSED/VERIFIED lifecycle, opportunities + JD analysis, evidence matching,
generation (provenance/IP/chronology/no-writeback), validation gates.
"""
import os
import re
import time
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")
API = f"{BASE_URL}/api"

LONG = 180  # AI calls can be slow

ALLSTATE_JD = """Allstate is hiring a Director of Product Management to lead enterprise
product strategy for our claims modernization portfolio. Responsibilities: own the product
roadmap and vision for multiple product lines; lead cross-functional teams of engineers,
designers and data scientists; partner with executive stakeholders to align investment;
drive agile delivery and program management across multiple workstreams; establish OKRs and
measurable business outcomes; manage vendor and platform partnerships; govern data and
regulatory compliance requirements. Requirements: 10+ years product management experience,
5+ years leading teams, Bachelor's degree required, MBA preferred, experience with
enterprise SaaS platforms, cloud infrastructure, and insurance or financial services domain.
Strong communication and executive presentation skills required."""


# ---------- fixtures ----------
@pytest.fixture(scope="session")
def admin_creds():
    p = Path("/app/memory/test_credentials.md")
    if not p.exists():
        pytest.skip("missing test_credentials.md")
    c = p.read_text()
    email = re.search(r"(?im)^\s*(?:[-*]\s*)?(?:\*\*)?Email(?:\*\*)?\s*:\s*`?([^`\s]+)", c)
    pwd = re.search(r"(?im)^\s*(?:[-*]\s*)?(?:\*\*)?Password(?:\*\*)?\s*:\s*`?([^`\s]+)", c)
    if not email or not pwd:
        pytest.skip("no creds parsed")
    return {"email": email.group(1), "password": pwd.group(1)}


def _poll_match(client, opp_id, timeout=240):
    """Poll GET /match-status until it leaves 'running' (matching is a background job)."""
    deadline = time.time() + timeout
    status = "running"
    while time.time() < deadline:
        r = client.get(f"{API}/opportunities/{opp_id}/match-status", timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        status = body["status"]
        if status in ("complete", "error"):
            assert status == "complete", f"matching errored: {body.get('error')}"
            return status
        time.sleep(3)
    return f"timeout(last={status})"


def _client(token=None):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="session")
def admin_token(admin_creds):
    r = requests.post(f"{API}/auth/login", json=admin_creds, timeout=60)
    if r.status_code != 200:
        pytest.fail(f"admin login failed {r.status_code}: {r.text[:300]}")
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def admin(admin_token):
    return _client(admin_token)


def _register(prefix):
    email = f"TEST_{prefix}_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": "TestPass123!"}, timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    return d["access_token"], d["user"], "TestPass123!"


@pytest.fixture(scope="session")
def user_a():
    tok, u, _ = _register("usera")
    return {"token": tok, "user": u, "c": _client(tok)}


@pytest.fixture(scope="session")
def user_b():
    tok, u, _ = _register("userb")
    return {"token": tok, "user": u, "c": _client(tok)}


# ---------- module: auth ----------
class TestAuth:
    def test_health(self):
        r = requests.get(f"{API}/", timeout=30)
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_register_returns_token_and_user(self):
        tok, u, _ = _register("reg")
        assert isinstance(tok, str) and len(tok) > 20
        assert u["role"] == "user"
        assert "@" in u["email"]

    def test_duplicate_register_409(self, admin_creds):
        r = requests.post(f"{API}/auth/register", json={"email": admin_creds["email"], "password": "whatever123"}, timeout=30)
        assert r.status_code == 409

    def test_login_and_me(self, admin_creds, admin_token):
        r = _client(admin_token).get(f"{API}/auth/me", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["email"] == admin_creds["email"].lower()
        assert d["role"] == "admin"

    def test_login_bad_password_401(self, admin_creds):
        r = requests.post(f"{API}/auth/login", json={"email": admin_creds["email"], "password": "WrongPass999"}, timeout=30)
        assert r.status_code == 401

    def test_me_without_token_401(self):
        r = requests.get(f"{API}/auth/me", timeout=30)
        assert r.status_code == 401

    def test_me_with_garbage_token_401(self):
        r = _client("not.a.jwt").get(f"{API}/auth/me", timeout=30)
        assert r.status_code == 401

    def test_short_password_rejected(self):
        r = requests.post(f"{API}/auth/register", json={"email": f"TEST_sp_{uuid.uuid4().hex[:6]}@example.com", "password": "123"}, timeout=30)
        assert r.status_code == 422

    def test_bcrypt_hash_format(self, admin_creds):
        """Stored hash must be bcrypt $2b$."""
        import asyncio
        from motor.motor_asyncio import AsyncIOMotorClient
        env = dotenv_values("/app/backend/.env")

        async def _check():
            cl = AsyncIOMotorClient(env["MONGO_URL"])
            u = await cl[env["DB_NAME"]].users.find_one({"email": admin_creds["email"].lower()})
            cl.close()
            return u

        u = asyncio.get_event_loop().run_until_complete(_check()) if False else asyncio.run(_check())
        assert u is not None
        assert u["password_hash"].startswith("$2b$"), u["password_hash"][:10]


# ---------- module: career nodes lifecycle ----------
class TestNodeLifecycle:
    def test_manual_node_is_proposed_then_verify_then_edit_returns_proposed(self, user_a):
        c = user_a["c"]
        r = c.post(f"{API}/career/nodes", json={
            "track": "civilian",
            "identity": {"employer": "TESTCO", "role": "Product Manager", "start": "2020", "end": "2022"},
            "context": {"scope": "test"},
            "evidence": ["Did a measurable thing improving X by 20%"],
            "retrieval": {"capabilities": ["product"], "metrics": ["20%"]},
        }, timeout=60)
        assert r.status_code == 200, r.text
        node = r.json()
        assert node["state"] == "PROPOSED"
        assert node["node_id"].startswith("CKN-CIV-")
        assert "_id" not in node and "owner_user_id" not in node
        nid = node["id"]

        v = c.post(f"{API}/career/nodes/{nid}/verify", timeout=60)
        assert v.status_code == 200
        assert v.json()["state"] == "VERIFIED"
        assert v.json()["verified_at"]

        p = c.patch(f"{API}/career/nodes/{nid}", json={"evidence": ["Edited evidence claim"]}, timeout=60)
        assert p.status_code == 200
        assert p.json()["state"] == "PROPOSED"
        assert p.json()["verified_at"] is None

        g = c.get(f"{API}/career/nodes", timeout=60)
        assert g.status_code == 200
        found = [n for n in g.json() if n["id"] == nid]
        assert found and found[0]["evidence"] == ["Edited evidence claim"]
        user_a["node_id"] = nid

    def test_verify_unknown_node_404(self, user_a):
        r = user_a["c"].post(f"{API}/career/nodes/64b7f9f9f9f9f9f9f9f9f9f9/verify", timeout=30)
        assert r.status_code == 404

    def test_reject_deletes(self, user_a):
        c = user_a["c"]
        r = c.post(f"{API}/career/nodes", json={"track": "military", "identity": {"employer": "TESTMIL"}, "evidence": ["e"]}, timeout=60)
        nid = r.json()["id"]
        d = c.post(f"{API}/career/nodes/{nid}/reject", timeout=30)
        assert d.status_code == 200 and d.json()["deleted"] is True
        assert all(n["id"] != nid for n in c.get(f"{API}/career/nodes", timeout=30).json())


# ---------- module: isolation (CRITICAL) ----------
class TestIsolation:
    def test_cross_user_node_invisible_and_immutable(self, user_a, user_b):
        a, b = user_a["c"], user_b["c"]
        r = a.post(f"{API}/career/nodes", json={"track": "civilian", "identity": {"employer": "ISOCO"}, "evidence": ["secret A evidence"]}, timeout=60)
        nid = r.json()["id"]

        b_nodes = b.get(f"{API}/career/nodes", timeout=30).json()
        assert all(n["id"] != nid for n in b_nodes)
        assert all("secret A evidence" not in (n.get("evidence") or []) for n in b_nodes)

        assert b.post(f"{API}/career/nodes/{nid}/verify", timeout=30).status_code == 404
        assert b.patch(f"{API}/career/nodes/{nid}", json={"evidence": ["hacked"]}, timeout=30).status_code == 404
        assert b.post(f"{API}/career/nodes/{nid}/reject", timeout=30).status_code == 404

        # A's node unchanged
        a_node = [n for n in a.get(f"{API}/career/nodes", timeout=30).json() if n["id"] == nid][0]
        assert a_node["state"] == "PROPOSED"
        assert a_node["evidence"] == ["secret A evidence"]

    def test_cross_user_opportunity_404(self, user_a, user_b):
        a, b = user_a["c"], user_b["c"]
        r = a.post(f"{API}/opportunities", json={"target_role": "TEST Role", "organization": "ISOORG", "job_description": ALLSTATE_JD}, timeout=LONG)
        assert r.status_code == 200, r.text
        oid = r.json()["id"]
        user_a["opp_id"] = oid
        for path, method in [
            (f"/opportunities/{oid}", "get"),
            (f"/opportunities/{oid}/evidence-map", "get"),
            (f"/opportunities/{oid}/representation", "get"),
            (f"/opportunities/{oid}/validation", "get"),
        ]:
            resp = getattr(b, method)(f"{API}{path}", timeout=60)
            assert resp.status_code == 404, f"{path} -> {resp.status_code}"
        for path in [f"/opportunities/{oid}/analyze", f"/opportunities/{oid}/match", f"/opportunities/{oid}/generate", f"/opportunities/{oid}/validate"]:
            resp = b.post(f"{API}{path}", timeout=60)
            assert resp.status_code in (404, 409), f"{path} -> {resp.status_code}"
            if resp.status_code == 409:
                # must be "nothing of mine" errors, not access to A's data
                assert "VERIFIED" in resp.text or "Generate" in resp.text or "matching" in resp.text
        assert all(o["id"] != oid for o in b.get(f"{API}/opportunities", timeout=30).json())

    def test_uploads_isolated(self, user_a, user_b):
        assert user_b["c"].get(f"{API}/resume/uploads", timeout=30).json() == []


# ---------- module: admin boundary (CRITICAL) ----------
class TestAdminBoundary:
    def test_admin_pilots_usage_only(self, admin, user_a):
        r = admin.get(f"{API}/admin/pilots", timeout=60)
        assert r.status_code == 200, r.text
        pilots = r.json()
        assert isinstance(pilots, list) and len(pilots) >= 2
        target = [p for p in pilots if p["email"] == user_a["user"]["email"].lower()]
        assert target, "user A not listed"
        p = target[0]
        assert set(p["usage"].keys()) == {"uploads", "verified_nodes", "proposed_nodes", "opportunities", "representations"}
        blob = str(p).lower()
        for leak in ["password_hash", "raw_text", "job_description", "evidence", "secret a evidence"]:
            assert leak not in blob, f"leaked {leak}"

    def test_non_admin_403(self, user_a):
        assert user_a["c"].get(f"{API}/admin/pilots", timeout=30).status_code == 403
        assert user_a["c"].post(f"{API}/admin/pilots/invite", json={"email": "x@y.com", "password": "abc123"}, timeout=30).status_code == 403

    def test_admin_cannot_read_user_a_private_content(self, admin, user_a):
        """Admin is owner-scoped on normal endpoints: A's opportunity/node not visible."""
        r = user_a["c"].post(f"{API}/career/nodes", json={"track": "civilian", "identity": {"employer": "ADMINISO"}, "evidence": ["secret A evidence"]}, timeout=60)
        assert r.status_code == 200
        r = user_a["c"].post(f"{API}/opportunities", json={"target_role": "TEST AdminIso", "organization": "ISO", "job_description": ALLSTATE_JD}, timeout=LONG)
        assert r.status_code == 200, r.text
        oid = r.json()["id"]
        assert admin.get(f"{API}/opportunities/{oid}", timeout=30).status_code == 404
        assert admin.get(f"{API}/opportunities/{oid}/evidence-map", timeout=30).status_code == 404
        admin_nodes = admin.get(f"{API}/career/nodes", timeout=30).json()
        assert all("secret A evidence" not in (n.get("evidence") or []) for n in admin_nodes)
        assert all(o["id"] != oid for o in admin.get(f"{API}/opportunities", timeout=30).json())

    def test_invite_enable_disable_lifecycle(self, admin):
        email = f"TEST_invite_{uuid.uuid4().hex[:8]}@example.com"
        r = admin.post(f"{API}/admin/pilots/invite", json={"email": email, "password": "PilotPass123"}, timeout=60)
        assert r.status_code == 200, r.text
        uid = r.json()["id"]
        assert r.json()["email"] == email.lower()
        # duplicate invite
        assert admin.post(f"{API}/admin/pilots/invite", json={"email": email, "password": "PilotPass123"}, timeout=30).status_code == 409
        # invited user can log in
        lr = requests.post(f"{API}/auth/login", json={"email": email, "password": "PilotPass123"}, timeout=30)
        assert lr.status_code == 200
        tok = lr.json()["access_token"]
        # disable -> login blocked and token rejected
        assert admin.post(f"{API}/admin/pilots/{uid}/disable", timeout=30).status_code == 200
        assert requests.post(f"{API}/auth/login", json={"email": email, "password": "PilotPass123"}, timeout=30).status_code == 403
        assert _client(tok).get(f"{API}/auth/me", timeout=30).status_code == 403
        # enable -> works again
        assert admin.post(f"{API}/admin/pilots/{uid}/enable", timeout=30).status_code == 200
        assert requests.post(f"{API}/auth/login", json={"email": email, "password": "PilotPass123"}, timeout=30).status_code == 200
        pilots = admin.get(f"{API}/admin/pilots", timeout=60).json()
        assert [p for p in pilots if p["id"] == uid][0]["status"] == "active"


# ---------- module: golden path (admin seeded James KB + Allstate JD) ----------
@pytest.fixture(scope="class")
def golden_opp(admin):
    # Identity/contact is required for application-ready export (identity_contact gate).
    admin.put(f"{API}/profile", json={
        "full_name": "James Williams", "email": "james.williams@pro.dev",
        "phone": "2105550199", "location": "San Antonio, TX",
        "links": [{"label": "LinkedIn", "url": "https://www.linkedin.com/in/jwilliams/"}],
    }, timeout=30)
    r = admin.post(f"{API}/opportunities", json={
        "target_role": "Director of Product Management",
        "organization": "Allstate",
        "job_description": ALLSTATE_JD,
    }, timeout=LONG)
    assert r.status_code == 200, r.text
    oid = r.json()["id"]
    # Drive the full loop once so a representation exists for ANY dependent test,
    # independent of method execution order under xdist.
    assert admin.post(f"{API}/opportunities/{oid}/match", timeout=30).status_code == 200
    st = "running"
    for _ in range(60):
        st = admin.get(f"{API}/opportunities/{oid}/match-status", timeout=30).json().get("status")
        if st in ("complete", "error"):
            break
        time.sleep(3)
    assert st == "complete", f"matching did not complete: {st}"
    assert admin.post(f"{API}/opportunities/{oid}/generate", timeout=LONG).status_code == 200
    return oid


class TestGoldenPath:
    def test_seeded_verified_nodes(self, admin):
        r = admin.get(f"{API}/career/nodes", params={"state": "VERIFIED"}, timeout=60)
        assert r.status_code == 200
        nodes = r.json()
        assert len(nodes) >= 5, f"expected >=5 seeded VERIFIED nodes, got {len(nodes)}"
        tracks = {n["track"] for n in nodes}
        assert {"civilian", "military", "intellectual_property"} <= tracks, tracks
        blob = str(nodes)
        for kw in ["USAA", "CPS Energy", "DLA", "Reserve"]:
            assert kw in blob, f"missing seeded node {kw}"

    def test_empty_jd_rejected(self, admin):
        r = admin.post(f"{API}/opportunities", json={"target_role": "X", "organization": "Y", "job_description": "   "}, timeout=60)
        assert r.status_code == 422

    def test_jd_analysis_categories_and_tiers(self, admin, golden_opp):
        r = admin.get(f"{API}/opportunities/{golden_opp}", timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["preflight"]["status"] == "READY", d["preflight"]
        reqs = d["requirements"]
        assert len(reqs) >= 8, f"only {len(reqs)} requirements"
        assert all(1 <= q["tier"] <= 4 for q in reqs)
        cats = {q["category"] for q in reqs}
        assert len(cats) >= 3, cats
        assert reqs == sorted(reqs, key=lambda x: x["tier"])

    def test_matching_is_background_job_and_returns_immediately(self, admin, golden_opp):
        """REGRESSION: /match must return fast (no gateway timeout) with status running."""
        t0 = time.time()
        r = admin.post(f"{API}/opportunities/{golden_opp}/match", timeout=30)
        elapsed = time.time() - t0
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "running", r.text
        assert elapsed < 10, f"/match took {elapsed:.1f}s — still running inline"

        # evidence-map must advertise not-yet-matched while running
        em = admin.get(f"{API}/opportunities/{golden_opp}/evidence-map", timeout=60)
        assert em.status_code == 200
        assert "matched" in em.json()

        status = _poll_match(admin, golden_opp)
        assert status == "complete", status

    def test_match_status_unknown_opp_404(self, admin):
        r = admin.get(f"{API}/opportunities/64b7f9f9f9f9f9f9f9f9f9f9/match-status", timeout=30)
        assert r.status_code == 404

    def test_match_status_cross_user_404(self, user_b, golden_opp):
        r = user_b["c"].get(f"{API}/opportunities/{golden_opp}/match-status", timeout=30)
        assert r.status_code == 404

    def test_matching_and_evidence_map(self, admin, golden_opp):
        status = _poll_match(admin, golden_opp)
        assert status == "complete", status
        em = admin.get(f"{API}/opportunities/{golden_opp}/evidence-map", timeout=90)
        assert em.status_code == 200, em.text
        data = em.json()
        assert data["matched"] is True, data.get("summary")
        rows = data["rows"]
        assert len(rows) == data["summary"]["total"] >= 8
        covered = [row for row in rows if not row["gap"]]
        assert len(covered) >= 5, "too few covered requirements"
        weights = set()
        for row in covered:
            for m in row["matches"]:
                assert 0 <= m["match_strength"] <= 1, m
                assert m["representation_weight"] in ("primary", "supporting", "contextual", "chronology")
                assert m["provenance"].get("node_id") == m["source_experience"]
                weights.add(m["representation_weight"])
            strengths = [m["match_strength"] for m in row["matches"]]
            assert strengths == sorted(strengths, reverse=True)
            assert row["matches"][0]["representation_weight"] == "primary"
        assert "primary" in weights
        assert data["summary"]["gaps"] == sum(1 for row in rows if row["gap"])
        assert data["summary"]["covered"] + data["summary"]["gaps"] == data["summary"]["total"]

    def test_matching_requires_verified_evidence(self, user_b):
        r = user_b["c"].post(f"{API}/opportunities", json={"target_role": "TEST NoEv", "job_description": ALLSTATE_JD}, timeout=LONG)
        assert r.status_code == 200
        oid = r.json()["id"]
        m = user_b["c"].post(f"{API}/opportunities/{oid}/match", timeout=90)
        assert m.status_code == 409, m.text
        # preflight must be BLOCKED (no verified evidence)
        g = user_b["c"].get(f"{API}/opportunities/{oid}", timeout=60).json()
        assert g["preflight"]["status"] == "BLOCKED"
        assert "verified_evidence" in g["preflight"]["missing"]
        gen = user_b["c"].post(f"{API}/opportunities/{oid}/generate", timeout=90)
        assert gen.status_code == 409

    def test_generation_provenance_ip_and_chronology_no_writeback(self, admin, golden_opp):
        before = admin.get(f"{API}/career/nodes", timeout=60).json()
        r = admin.post(f"{API}/opportunities/{golden_opp}/generate", timeout=LONG * 2)
        assert r.status_code == 200, r.text
        rep = r.json()
        assert rep["sections"]["summary"].strip()
        exps = rep["sections"]["experiences"]
        assert len(exps) >= 3
        assert len(rep["claim_provenance"]) >= 5
        node_ids = {n["node_id"] for n in before}
        for e in exps:
            assert e["bullets"], e
            for b in e["bullets"]:
                assert b["source_node_id"] == e["node_id"]
                assert b["source_node_id"] in node_ids
                assert b["text"].strip()
            if e["track"] == "intellectual_property":
                assert e["employer"] == "", f"IP rendered as employer: {e}"
        # reverse chronological WITHIN each category (experience/military/projects)
        def ey(v):
            s = str(v or "").lower()
            if "present" in s or "current" in s:
                return 9999
            ys = [int(t) for t in re.split(r"[^0-9]", s) if t.isdigit() and len(t) == 4]
            return ys[0] if ys else 0
        cats = {}
        for e in exps:
            cat = e.get("category") or ("projects" if e["track"] == "intellectual_property"
                                        else "military" if e["track"] == "military" else "experience")
            cats.setdefault(cat, []).append(ey(e["end"]))
        for cat, years in cats.items():
            assert years == sorted(years, reverse=True), (cat, years)
        # no write-back to canonical
        after = admin.get(f"{API}/career/nodes", timeout=60).json()
        norm = lambda ns: sorted([(n["node_id"], n["state"], tuple(n.get("evidence") or []), n["verified_at"]) for n in ns])
        assert norm(before) == norm(after), "generation mutated canonical knowledge"
        # GET representation matches
        g = admin.get(f"{API}/opportunities/{golden_opp}/representation", timeout=60)
        assert g.status_code == 200 and g.json()["id"] == rep["id"]

    def test_validation_gates_pass(self, admin, golden_opp):
        r = admin.post(f"{API}/opportunities/{golden_opp}/validate", timeout=LONG)
        assert r.status_code == 200, r.text
        vr = r.json()
        gates = vr["gate_results"]
        assert isinstance(gates, dict) and len(gates) >= 5, gates
        for name, g in gates.items():
            assert g["status"] in ("pass", "warn", "fail"), (name, g)
            assert g["detail"].strip()
        failed = {k: v for k, v in gates.items() if v["status"] == "fail"}
        assert vr["passed"] is (len(failed) == 0)
        assert vr["passed"] is True, f"failed gates: {failed}"
        warns = {k: v for k, v in gates.items() if v["status"] == "warn"}
        print("GATE_WARNS:", warns)
        print("GATES:", gates)
        g = admin.get(f"{API}/opportunities/{golden_opp}/validation", timeout=60)
        assert g.status_code == 200 and g.json()["passed"] is True

    # ---------- feature: resume export (PDF/DOCX) ----------
    def _rep(self, admin, opp_id):
        g = admin.get(f"{API}/opportunities/{opp_id}/representation", timeout=60)
        assert g.status_code == 200, g.text
        return g.json()

    def test_representation_still_has_claim_provenance_with_node_ids(self, admin, golden_opp):
        """Provenance preserved in DATA — exports hide CKN ids but /representation still returns them."""
        rep = self._rep(admin, golden_opp)
        cp = rep.get("claim_provenance")
        assert isinstance(cp, list) and len(cp) >= 1, "claim_provenance missing"
        total_bullets = sum(len(e["bullets"]) for e in rep["sections"]["experiences"])
        assert len(cp) == total_bullets, (len(cp), total_bullets)
        for p in cp:
            assert p.get("node_id", "").startswith("CKN-"), p

    def test_heading_helper_handles_empty_role(self):
        """Unit test: resume_export._heading — no dangling separator; IP is PROJECT-FIRST."""
        import sys as _sys
        _sys.path.insert(0, "/app/backend")
        from resume_export import _heading
        assert _heading({"role": "", "track": "intellectual_property", "organization": "X", "employer": ""}) == "X"
        assert _heading({"role": "", "track": "employment", "organization": "", "employer": ""}) == ""
        # IP: project name first, then role (never a bare generic role)
        assert _heading({"role": "Creator / Product Lead", "track": "intellectual_property",
                         "organization": "DIE Orbit", "employer": ""}) == "DIE Orbit \u2014 Creator / Product Lead"
        # IP with NO verified project name must NOT render as a bare generic role
        assert _heading({"role": "Developer", "track": "intellectual_property",
                         "organization": "", "employer": ""}) != "Developer"
        assert _heading({"role": "SWE", "track": "employment", "employer": "Acme"}) == "SWE \u2014 Acme"
        # No output should start with em-dash
        for sample in [
            {"role": "", "employer": "Acme"},
            {"role": "", "organization": "Org", "track": "intellectual_property"},
        ]:
            h = _heading(sample)
            assert not h.startswith("\u2014"), h
            assert " \u2014 " not in (h + " \n")  # no dangling separator newline either

    def test_export_pdf_parses_and_matches_representation(self, admin, golden_opp):
        import io as _io
        from pdfminer.high_level import extract_text
        rep = self._rep(admin, golden_opp)
        r = admin.get(f"{API}/opportunities/{golden_opp}/export", params={"format": "pdf"}, timeout=LONG)
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("application/pdf"), r.headers
        cd = r.headers.get("content-disposition", "")
        assert "attachment" in cd and ".pdf" in cd, cd
        assert r.content[:5] == b"%PDF-", r.content[:20]
        text = extract_text(_io.BytesIO(r.content))
        flat = re.sub(r"\s+", " ", text)
        # summary present
        assert rep["sections"]["summary"].split(".")[0][:40].strip() in flat, "summary missing from PDF"
        # BOUNDED remediation: CKN ids, contract footer, Target line must all be hidden in export
        assert "CKN-" not in flat, f"CKN identifier leaked into PDF: {flat[:400]}"
        assert "Contract v" not in flat, "contract footer should be removed from PDF"
        assert "Resume Template v" not in flat, "template footer should be removed from PDF"
        assert "traceable claim" not in flat.lower(), "traceable-claims footer should be removed"
        assert "Target:" not in flat, "Target opportunity metadata line should be removed from PDF"
        # every experience role, employer/organization rendering, bullets intact
        exps = rep["sections"]["experiences"]
        exp_part = flat.split("Experience", 1)[-1]
        cursor, positions = 0, []
        for e in exps:
            role = (e.get("role") or "").strip()
            if e["track"] == "intellectual_property":
                disp = (e.get("organization") or "").strip()
                headline = f"{disp} \u2014 {role}" if (disp and role) else (
                    disp or (f"{role} \u2014 Independent Project" if role else "Independent Project"))
            else:
                disp = e["employer"]
                headline = f"{role} \u2014 {disp}" if (role and disp) else (role or disp)
            idx = exp_part.find(headline, cursor)
            assert idx >= 0, f"headline missing/out-of-order in PDF: {headline!r}"
            # empty-role entries must not render a dangling ' — '
            assert not headline.startswith(" \u2014") and not headline.startswith("\u2014 ")
            cursor = idx + len(headline)
            positions.append(idx)
            if e.get("client"):
                assert f'Client: {e["client"]}' in flat, "client relationship missing"
        assert positions == sorted(positions), f"PDF chronology differs from app order: {positions}"
        # content assertions gated on what the engine actually selected into `rep`
        blob = str(exps)
        if "52 APIs" in blob or "52 production APIs" in blob:
            assert re.search(r"52\s+\S*\s*APIs?", flat), "USAA 52-API metric missing from PDF"
        for anchor in ["Avantus", "Regional Cloud Meetup", "Reserve", "Speaker"]:
            if anchor in blob:
                assert anchor in flat, f"{anchor} is in representation but missing from PDF"
        # IP must not be rendered as an employer line
        ip = [e for e in exps if e["track"] == "intellectual_property"]
        assert ip and ip[0]["employer"] == "", ip

    def test_export_docx_parses_and_matches_representation(self, admin, golden_opp):
        import io as _io
        from docx import Document
        rep = self._rep(admin, golden_opp)
        r = admin.get(f"{API}/opportunities/{golden_opp}/export", params={"format": "docx"}, timeout=LONG)
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"), r.headers
        assert "attachment" in r.headers.get("content-disposition", "")
        assert r.content[:2] == b"PK", r.content[:10]
        doc = Document(_io.BytesIO(r.content))
        paras = [p.text for p in doc.paragraphs]
        flat = re.sub(r"\s+", " ", " \n ".join(paras))
        assert rep["sections"]["summary"] in flat.replace(" \n ", " ") or rep["sections"]["summary"] in " ".join(paras)
        # BOUNDED remediation: CKN/contract/target hidden in DOCX
        assert "CKN-" not in flat, "CKN identifier leaked into DOCX"
        assert "Contract v" not in flat, "contract footer should be removed from DOCX"
        assert "Resume Template v" not in flat
        assert "Target:" not in flat, "Target line should be removed from DOCX"
        exps = rep["sections"]["experiences"]
        exp_part = flat.split("Experience", 1)[-1]
        cursor, positions = 0, []
        for e in exps:
            role = (e.get("role") or "").strip()
            if e["track"] == "intellectual_property":
                disp = (e.get("organization") or "").strip()
                headline = f"{disp} \u2014 {role}" if (disp and role) else (
                    disp or (f"{role} \u2014 Independent Project" if role else "Independent Project"))
            else:
                disp = e["employer"]
                headline = f"{role} \u2014 {disp}" if (role and disp) else (role or disp)
            idx = exp_part.find(headline, cursor)
            assert idx >= 0, f"headline missing/out-of-order in DOCX: {headline!r}"
            assert not headline.startswith(" \u2014") and not headline.startswith("\u2014 ")
            cursor = idx + len(headline)
            positions.append(idx)
            for b in e["bullets"]:
                assert b["text"][:40] in flat, "bullet text missing from DOCX"
        assert positions == sorted(positions), "DOCX chronology differs"
        blob = str(exps)
        if "52 APIs" in blob or "52 production APIs" in blob:
            assert re.search(r"52\s+\S*\s*APIs?", flat), "USAA 52-API metric missing from DOCX"
        for anchor in ["Avantus", "Regional Cloud Meetup", "Reserve", "Speaker"]:
            if anchor in blob:
                assert anchor in flat, f"{anchor} is in representation but missing from DOCX"

    def test_export_does_not_mutate_canonical_or_representation(self, admin, golden_opp):
        norm = lambda ns: sorted([(n["node_id"], n["state"], tuple(n.get("evidence") or []),
                                   n["verified_at"], str(n.get("metrics"))) for n in ns])
        before_nodes = admin.get(f"{API}/career/nodes", params={"state": "VERIFIED"}, timeout=60).json()
        before_rep = self._rep(admin, golden_opp)
        before_val = admin.get(f"{API}/opportunities/{golden_opp}/validation", timeout=60).json()
        for fmt in ("pdf", "docx", "pdf"):
            assert admin.get(f"{API}/opportunities/{golden_opp}/export", params={"format": fmt},
                             timeout=LONG).status_code == 200
        after_nodes = admin.get(f"{API}/career/nodes", params={"state": "VERIFIED"}, timeout=60).json()
        assert len(after_nodes) == len(before_nodes) >= 5
        assert norm(before_nodes) == norm(after_nodes), "export mutated canonical knowledge"
        assert "52 APIs" in str(after_nodes), "USAA 52 APIs metric changed after export"
        after_rep = self._rep(admin, golden_opp)
        assert after_rep == before_rep, "export mutated the representation"
        after_val = admin.get(f"{API}/opportunities/{golden_opp}/validation", timeout=60).json()
        assert after_val == before_val, "export mutated validation run"

    def test_validation_still_passes_after_export(self, admin, golden_opp):
        r = admin.post(f"{API}/opportunities/{golden_opp}/validate", timeout=LONG)
        assert r.status_code == 200, r.text
        vr = r.json()
        assert len(vr["gate_results"]) == 11, list(vr["gate_results"])
        assert vr["passed"] is True, vr["gate_results"]

    def test_export_unsupported_format_422(self, admin, golden_opp):
        r = admin.get(f"{API}/opportunities/{golden_opp}/export", params={"format": "xls"}, timeout=60)
        assert r.status_code == 422, r.status_code

    def test_export_cross_user_404(self, user_b, golden_opp):
        r = user_b["c"].get(f"{API}/opportunities/{golden_opp}/export", params={"format": "pdf"}, timeout=60)
        assert r.status_code == 404, r.status_code

    def test_export_without_token_401(self, golden_opp):
        r = requests.get(f"{API}/opportunities/{golden_opp}/export", params={"format": "pdf"}, timeout=60)
        assert r.status_code in (401, 403), r.status_code

    def test_validate_before_generate_409(self, user_b):
        r = user_b["c"].post(f"{API}/opportunities", json={"target_role": "TEST V", "job_description": ALLSTATE_JD}, timeout=LONG)
        oid = r.json()["id"]
        assert user_b["c"].post(f"{API}/opportunities/{oid}/validate", timeout=60).status_code == 409
        assert user_b["c"].get(f"{API}/opportunities/{oid}/representation", timeout=30).status_code == 404
        # export before generate -> 404
        assert user_b["c"].get(f"{API}/opportunities/{oid}/export", params={"format": "pdf"}, timeout=60).status_code == 404
        assert user_b["c"].get(f"{API}/opportunities/64b7f9f9f9f9f9f9f9f9f9f9/export", params={"format": "pdf"}, timeout=60).status_code == 404


# ---------- module: brute force / lockout (playbook check) ----------
class TestBruteForce:
    def test_repeated_failures_lockout(self, admin_creds):
        codes = []
        for _ in range(6):
            r = requests.post(f"{API}/auth/login", json={"email": admin_creds["email"], "password": "Wrong!123"}, timeout=30)
            codes.append(r.status_code)
            time.sleep(0.2)
        # correct password must still work (no self-lockout of valid creds required by spec)
        ok = requests.post(f"{API}/auth/login", json=admin_creds, timeout=30)
        assert ok.status_code == 200, f"admin locked out after failures: {ok.status_code}"
        assert all(c in (401, 429) for c in codes), codes



# ---------- module: generation hardening (malformed LLM output) ----------
import sys as _sys
_sys.path.insert(0, "/app/backend")


def _nodes_fixture():
    return {
        "CKN-A": {"node_id": "CKN-A", "track": "civilian",
                  "identity": {"employer": "Acme", "role": "Engineer", "organization": "Tech",
                               "client": "", "start": "2020", "end": "2023"},
                  "evidence": ["Built X", "Shipped Y", "Scaled Z"], "retrieval": {"metrics": []}},
        "CKN-IP": {"node_id": "CKN-IP", "track": "intellectual_property",
                   "identity": {"employer": "", "role": "Speaker", "organization": "Meetup",
                                "client": "", "start": "2021", "end": "2021"},
                   "evidence": ["Gave a talk"], "retrieval": {"metrics": []}},
    }


class TestGenerationHardening:
    """assemble_sections must tolerate malformed LLM output without 500 or invented claims."""

    def _assemble(self, gen):
        from server import assemble_sections
        nodes = _nodes_fixture()
        return assemble_sections(gen, nodes, ["CKN-A", "CKN-IP"])

    def test_gen_is_a_list_not_dict(self):
        sections, cp = self._assemble(["unexpected", "list"])
        assert sections["summary"] == ""
        assert len(sections["experiences"]) == 2
        # falls back to canonical evidence; every claim traces to a node
        assert cp and all(c["node_id"] in ("CKN-A", "CKN-IP") for c in cp)

    def test_experiences_contains_non_dict_items(self):
        gen = {"summary": "S", "experiences": ["oops", 123, {"node_id": "CKN-A",
               "bullets": [{"text": "Real bullet"}]}]}
        sections, cp = self._assemble(gen)
        acme = next(e for e in sections["experiences"] if e["node_id"] == "CKN-A")
        assert any(b["text"] == "Real bullet" for b in acme["bullets"])
        # IP node had no LLM experience -> falls back to canonical evidence, not invented
        ip = next(e for e in sections["experiences"] if e["node_id"] == "CKN-IP")
        assert ip["bullets"] and ip["bullets"][0]["text"] == "Gave a talk"
        assert ip["employer"] == ""  # IP never rendered as employment

    def test_bullets_contains_non_dict_and_empty(self):
        gen = {"summary": 999, "experiences": [{"node_id": "CKN-A",
               "bullets": ["str-bullet", {"text": ""}, {"text": "  "}, {"text": "Kept"}]}]}
        sections, cp = self._assemble(gen)
        acme = next(e for e in sections["experiences"] if e["node_id"] == "CKN-A")
        texts = [b["text"] for b in acme["bullets"]]
        assert "Kept" in texts
        assert "" not in texts and "  " not in texts and "str-bullet" not in texts
        assert sections["summary"] == ""  # non-str summary coerced

    def test_missing_experiences_key(self):
        sections, cp = self._assemble({"summary": "only summary"})
        assert sections["summary"] == "only summary"
        # both nodes fall back to canonical evidence
        assert {e["node_id"] for e in sections["experiences"]} == {"CKN-A", "CKN-IP"}
        assert all(b["source_node_id"] for e in sections["experiences"] for b in e["bullets"])


# ---------- module: canonical correction (USAA migration direction) ----------
class TestCanonicalCorrection:
    def test_usaa_migration_direction_corrected(self, admin):
        nodes = admin.get(f"{API}/career/nodes", params={"state": "VERIFIED"}, timeout=60).json()
        usaa = [n for n in nodes if n["node_id"] == "CKN-CIV-USAA-001"]
        # admin owns the seeded James USAA node (seed direction is DFW->ATL by design);
        # the real-account correction (ATL->DFW) is validated separately. Here we assert
        # the seeded node still exists, is VERIFIED, and retains its 52-API metric.
        assert usaa, "seeded USAA node missing"
        n = usaa[0]
        assert n["state"] == "VERIFIED"
        assert "52 APIs" in str(n["retrieval"]["metrics"])



# ---------- module: canonical reconciliation (authority grouping) ----------
class TestReconciliationGrouping:
    """assemble_sections groups associated/superseded nodes under one authoritative entry
    while preserving each bullet's provenance to its ORIGINAL source node."""

    def _call(self, authority_map):
        import sys as _s
        _s.path.insert(0, "/app/backend")
        from server import assemble_sections
        nodes = {
            "USAA-AUTH": {"node_id": "USAA-AUTH", "track": "civilian", "position_ref": "USAA-AUTH",
                          "identity": {"employer": "USAA", "role": "Digital Product Owner",
                                       "organization": "", "client": "", "start": "Dec 2024", "end": "Dec 2025"},
                          "evidence": ["auth ev"], "retrieval": {"metrics": []}},
            "USAA-ASSOC": {"node_id": "USAA-ASSOC", "track": "civilian", "position_ref": "USAA-AUTH",
                           "identity": {"employer": "USAA", "role": "Dev Product Owner",
                                        "organization": "", "client": "", "start": "2024", "end": "2025"},
                           "evidence": ["assoc ev"], "retrieval": {"metrics": []}},
            "DLA-SUP": {"node_id": "DLA-SUP", "track": "civilian", "position_ref": "AVANTUS",
                        "identity": {"employer": "Defense Logistics Agency", "role": "UX Lead",
                                     "organization": "", "client": "", "start": "2020", "end": "2022"},
                        "evidence": ["40% reduction"], "retrieval": {"metrics": []}},
            "AVANTUS": {"node_id": "AVANTUS", "track": "civilian", "position_ref": "AVANTUS",
                        "identity": {"employer": "Avantus Federal", "role": "Lead Dev",
                                     "organization": "", "client": "Defense Logistics Agency",
                                     "start": "2020", "end": "2022"},
                        "evidence": ["avantus ev"], "retrieval": {"metrics": []}},
        }
        gen = {"summary": "S", "experiences": [
            {"node_id": "USAA-AUTH", "bullets": [{"text": "b-auth"}]},
            {"node_id": "USAA-ASSOC", "bullets": [{"text": "b-assoc"}]},
            {"node_id": "DLA-SUP", "bullets": [{"text": "b-dla-40pct"}]},
            {"node_id": "AVANTUS", "bullets": [{"text": "b-avantus"}]},
        ]}
        used = ["USAA-AUTH", "USAA-ASSOC", "DLA-SUP", "AVANTUS"]
        return assemble_sections(gen, nodes, used, authority_map)

    def test_single_entry_per_authoritative_position(self):
        amap = {"USAA-AUTH": "USAA-AUTH", "USAA-ASSOC": "USAA-AUTH",
                "DLA-SUP": "AVANTUS", "AVANTUS": "AVANTUS"}
        sections, cp = self._call(amap)
        exps = sections["experiences"]
        # exactly two entries: one USAA, one Avantus (no DLA-as-employer, no USAA duplicate)
        assert len(exps) == 2, [e["node_id"] for e in exps]
        usaa = next(e for e in exps if e["node_id"] == "USAA-AUTH")
        assert usaa["role"] == "Digital Product Owner" and usaa["employer"] == "USAA"
        srcs = sorted({b["source_node_id"] for b in usaa["bullets"]})
        assert srcs == ["USAA-ASSOC", "USAA-AUTH"], srcs  # provenance preserved to origin
        av = next(e for e in exps if e["node_id"] == "AVANTUS")
        assert av["employer"] == "Avantus Federal" and av["client"] == "Defense Logistics Agency"
        # superseded DLA evidence survives, attributed to its origin node, but NOT as an employer
        assert any(b["source_node_id"] == "DLA-SUP" for b in av["bullets"])
        assert all(e["employer"] != "Defense Logistics Agency" for e in exps)

    def test_no_authority_map_is_backward_compatible(self):
        sections, cp = self._call({})  # empty map -> per-node (legacy) behaviour
        assert len(sections["experiences"]) == 4



# ---------- module: representation quality refinement (consolidation/dates/category) ----------
class TestRepresentationRefinement:
    """Deterministic unit coverage for the bounded refinement: semantic consolidation
    validation, multi-source provenance, date formatting, category ordering, IP headings."""

    def _import(self):
        import sys as _s
        _s.path.insert(0, "/app/backend")
        import server
        return server

    def test_date_same_year_collapse_and_present(self):
        s = self._import()
        assert s._format_date_range("2026", "2026") == "2026"
        assert s._format_date_range("Dec 2024", "Dec 2025") == "Dec 2024 – Dec 2025"
        assert s._format_date_range("2020", "2022") == "2020 – 2022"
        # 'Present' only when canonical explicitly marks ongoing, never inferred from empty end
        assert s._format_date_range("2021", "Present") == "2021 – Present"
        assert s._format_date_range("2021", "") == "2021"  # missing end != Present
        assert s._format_date_range("", "") == ""

    def test_category_classification(self):
        s = self._import()
        assert s._category("civilian") == "experience"
        assert s._category("military") == "military"
        assert s._category("intellectual_property") == "projects"

    def test_assemble_orders_by_category_then_reverse_chron(self):
        s = self._import()
        nodes = {
            "CIV1": {"node_id": "CIV1", "track": "civilian", "position_ref": "CIV1",
                     "identity": {"employer": "A", "role": "R", "organization": "", "client": "",
                                  "start": "2024", "end": "2025"}, "evidence": ["e"], "retrieval": {"metrics": []}},
            "CIV2": {"node_id": "CIV2", "track": "civilian", "position_ref": "CIV2",
                     "identity": {"employer": "B", "role": "R", "organization": "", "client": "",
                                  "start": "2019", "end": "2021"}, "evidence": ["e"], "retrieval": {"metrics": []}},
            "MIL": {"node_id": "MIL", "track": "military", "position_ref": "MIL",
                    "identity": {"employer": "USAF", "role": "Officer", "organization": "USAF", "client": "",
                                 "start": "2014", "end": "2025"}, "evidence": ["e"], "retrieval": {"metrics": []}},
            "IP": {"node_id": "IP", "track": "intellectual_property", "position_ref": "IP",
                   "identity": {"employer": "", "role": "Creator", "organization": "DIE Orbit", "client": "",
                                "start": "2026", "end": "2026"}, "evidence": ["e"], "retrieval": {"metrics": []}},
        }
        gen = {"summary": "S", "experiences": [{"node_id": k, "bullets": [{"text": f"b-{k}"}]} for k in nodes]}
        used = list(nodes.keys())
        sections, _ = s.assemble_sections(gen, nodes, used, {k: k for k in nodes})
        cats = [e["category"] for e in sections["experiences"]]
        assert cats == ["experience", "experience", "military", "projects"], cats
        # civilian reverse-chron: 2025 before 2021
        civ = [e for e in sections["experiences"] if e["category"] == "experience"]
        assert civ[0]["node_id"] == "CIV1" and civ[1]["node_id"] == "CIV2"
        # IP carries display_dates collapsed to single year
        ip = next(e for e in sections["experiences"] if e["category"] == "projects")
        assert ip["display_dates"] == "2026"

    def test_multi_source_provenance_preserved(self):
        s = self._import()
        nodes = {
            "AUTH": {"node_id": "AUTH", "track": "civilian", "position_ref": "AUTH",
                     "identity": {"employer": "USAA", "role": "DPO", "organization": "", "client": "",
                                  "start": "2024", "end": "2025"}, "evidence": ["x"], "retrieval": {"metrics": []}},
        }
        # one synthesized bullet drawing from two source nodes
        gen = {"summary": "", "experiences": [{"node_id": "AUTH", "bullets": [
            {"text": "Merged claim", "source_node_ids": ["AUTH", "ASSOC"]}]}]}
        sections, cp = s.assemble_sections(gen, nodes, ["AUTH"], {"AUTH": "AUTH"})
        b = sections["experiences"][0]["bullets"][0]
        assert b["source_node_ids"] == ["AUTH", "ASSOC"]
        assert b["source_node_id"] == "AUTH"  # back-compat primary
        assert cp[0]["node_ids"] == ["AUTH", "ASSOC"] and cp[0]["node_id"] == "AUTH"

    def test_validate_consolidated_rejects_uncited_and_invented_metrics(self):
        s = self._import()
        items = [{"idx": 0, "node_id": "N1", "text": "Led API modernization across ~52 APIs"}]
        idx_to_node = {0: "N1"}
        nodes = {"N1": {"retrieval": {"metrics": ["~52 enterprise APIs"]}}}
        raw = [
            {"text": "Led API modernization across 52 APIs", "evidence_idxs": [0]},   # supported
            {"text": "Grew revenue 300%", "evidence_idxs": [0]},                       # invented metric -> reject
            {"text": "Did stuff", "evidence_idxs": []},                                # no citation -> reject
        ]
        out = s._validate_consolidated(raw, items, idx_to_node, nodes, budget=5)
        assert len(out) == 1
        assert out[0]["source_node_ids"] == ["N1"]
        assert "52" in out[0]["text"]

    def test_validate_consolidated_respects_budget(self):
        s = self._import()
        items = [{"idx": i, "node_id": "N1", "text": f"claim {i}"} for i in range(6)]
        idx_to_node = {i: "N1" for i in range(6)}
        nodes = {"N1": {"retrieval": {"metrics": []}}}
        raw = [{"text": f"bullet {i}", "evidence_idxs": [i]} for i in range(6)]
        out = s._validate_consolidated(raw, items, idx_to_node, nodes, budget=3)
        assert len(out) == 3

    def test_fallback_bullets_dedup_and_authoritative_first(self):
        s = self._import()
        nodes = {
            "AUTH": {"evidence": ["Alpha accomplishment", "Shared claim"]},
            "ASSOC": {"evidence": ["shared claim", "Beta accomplishment"]},
        }
        out = s._fallback_bullets(["ASSOC", "AUTH"], "AUTH", nodes, budget=5)
        texts = [b["text"] for b in out]
        assert texts[0] == "Alpha accomplishment"  # authoritative first
        # case-insensitive dedup of 'shared claim'
        assert sum(1 for t in texts if t.lower().startswith("shared claim")) == 1



# ---------- module: candidate identity & contact profile ----------
class TestCandidateProfile:
    """Owner-scoped identity/contact: isolation, validation, HTTPS links, partial saves."""

    def test_new_user_profile_is_empty_shell(self):
        tok, _, _ = _register("profempty")
        r = _client(tok).get(f"{API}/profile", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["full_name"] == "" and d["email"] == "" and d["links"] == []

    def test_save_and_fetch_profile(self):
        tok, _, _ = _register("profsave")
        c = _client(tok)
        payload = {
            "full_name": "Jane A. Candidate", "email": "jane@pro.dev",
            "phone": "+1 555 100 2000", "location": "Austin, TX",
            "links": [{"label": "LinkedIn", "url": "https://linkedin.com/in/jane"}],
        }
        r = c.put(f"{API}/profile", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["full_name"] == "Jane A. Candidate"
        assert d["email"] == "jane@pro.dev"
        assert d["links"][0]["url"] == "https://linkedin.com/in/jane"
        # fetched back identically
        assert _client(tok).get(f"{API}/profile", timeout=30).json()["phone"] == "+1 555 100 2000"

    def test_partial_save_allowed(self):
        tok, _, _ = _register("profpartial")
        r = _client(tok).put(f"{API}/profile", json={"full_name": "Only Name"}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["full_name"] == "Only Name" and d["email"] == "" and d["location"] == ""

    def test_one_profile_per_owner_upsert(self):
        tok, _, _ = _register("profupsert")
        c = _client(tok)
        c.put(f"{API}/profile", json={"full_name": "First"}, timeout=30)
        c.put(f"{API}/profile", json={"full_name": "Second", "location": "NYC"}, timeout=30)
        d = c.get(f"{API}/profile", timeout=30).json()
        assert d["full_name"] == "Second" and d["location"] == "NYC"

    def test_non_https_link_rejected(self):
        tok, _, _ = _register("profhttp")
        r = _client(tok).put(
            f"{API}/profile",
            json={"links": [{"label": "x", "url": "http://insecure.com"}]}, timeout=30,
        )
        assert r.status_code == 422, r.text

    def test_invalid_email_rejected(self):
        tok, _, _ = _register("profmail")
        r = _client(tok).put(f"{API}/profile", json={"email": "not-an-email"}, timeout=30)
        assert r.status_code == 422, r.text

    def test_owner_isolation(self):
        tok_a, _, _ = _register("profiso_a")
        tok_b, _, _ = _register("profiso_b")
        _client(tok_a).put(f"{API}/profile", json={"full_name": "A Secret", "email": "a@pro.dev"}, timeout=30)
        # B never sees A's data and has its own independent (empty) profile
        b = _client(tok_b).get(f"{API}/profile", timeout=30).json()
        assert b["full_name"] == "" and b["email"] == ""
        # A unchanged after B reads
        a = _client(tok_a).get(f"{API}/profile", timeout=30).json()
        assert a["full_name"] == "A Secret"

    def test_profile_requires_auth(self):
        r = requests.get(f"{API}/profile", timeout=30)
        assert r.status_code in (401, 403)


# ---------- module: final-artifact corrections (qualifier guard, phone, IP suppression) ----------
class TestArtifactCorrections:
    def _import(self):
        import sys as _s
        _s.path.insert(0, "/app/backend")
        import server
        return server

    def test_qualifier_guard_rejects_unverified_superlatives(self):
        s = self._import()
        items = [{"idx": 0, "node_id": "N1", "text": "Owned and prioritized the product backlog"}]
        idx_to_node = {0: "N1"}
        nodes = {"N1": {"retrieval": {"metrics": []}}}
        raw = [
            {"text": "Served as sole product owner for the platform", "evidence_idxs": [0]},   # 'sole' not in evidence -> reject
            {"text": "Served as subject matter expert for the platform", "evidence_idxs": [0]}, # SME not in evidence -> reject
            {"text": "Owned and prioritized the product backlog", "evidence_idxs": [0]},         # clean -> keep
        ]
        out = s._validate_consolidated(raw, items, idx_to_node, nodes, budget=5)
        texts = [b["text"] for b in out]
        assert len(out) == 1 and "sole" not in texts[0].lower() and "subject matter expert" not in texts[0].lower()

    def test_qualifier_guard_allows_grounded_term(self):
        s = self._import()
        items = [{"idx": 0, "node_id": "N1", "text": "Served as subject matter expert across teams"}]
        idx_to_node = {0: "N1"}
        nodes = {"N1": {"retrieval": {"metrics": []}}}
        raw = [{"text": "Acted as subject matter expert across teams", "evidence_idxs": [0]}]
        out = s._validate_consolidated(raw, items, idx_to_node, nodes, budget=5)
        assert len(out) == 1  # term is grounded in cited evidence -> allowed

    def test_us_phone_formatting(self):
        import sys as _s
        _s.path.insert(0, "/app/backend")
        from resume_export import _format_phone
        assert _format_phone("2105500251") == "(210) 550-0251"
        assert _format_phone("12105500251") == "+1 (210) 550-0251"
        assert _format_phone("(210) 550-0251") == "(210) 550-0251"
        assert _format_phone("+44 20 7946 0000") == "+44 20 7946 0000"  # non-US passthrough
        assert _format_phone("") == ""




    def test_heb_pdf_pagination_no_orphan_trailing_page(self):
        """Regression against the ACTUAL HEB representation structure (9 entries / 27 bullets):
        renders on <=2 pages with no orphaned section/entry heading and no lost entries."""
        import pytest, sys as _s, json, os
        pymupdf = pytest.importorskip("pymupdf")
        _s.path.insert(0, "/app/backend")
        from resume_export import build_pdf, _heading
        fx = os.path.join(os.path.dirname(__file__), "fixtures", "heb_rep.json")
        rep = json.load(open(fx))
        exps = rep["sections"]["experiences"]
        pdf = build_pdf(rep, "Senior Product Manager, Data Platform", "HEB")
        doc = pymupdf.open(stream=pdf, filetype="pdf")
        assert doc.page_count <= 2, f"expected <=2 pages, got {doc.page_count}"
        pages = [doc[i].get_text() for i in range(doc.page_count)]
        full = "\n".join(pages)
        # every entry heading and its first bullet render, and sit on the SAME page (no orphan)
        for e in exps:
            h = _heading(e)
            first_bullet = (e.get("bullets") or [{}])[0].get("text", "")
            snippet = first_bullet[:40]
            if not h or not snippet:
                continue
            # locate the page containing the heading; its first bullet must be on that same page
            hp = next((i for i, p in enumerate(pages) if h in p), None)
            assert hp is not None, f"heading missing from PDF: {h!r}"
            assert snippet in pages[hp], f"orphaned heading (bullet on another page): {h!r}"
        # section labels present
        for label in ("Experience", "Independent Projects"):
            assert label in full, f"section label missing: {label}"
        doc.close()
