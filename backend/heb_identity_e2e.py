"""Integrated identity-header E2E on an ISOLATED copy (source HEB account untouched)."""
import asyncio, os, uuid, io, zipfile
import httpx
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import dotenv_values

cfg = dotenv_values(os.path.join(os.path.dirname(__file__), ".env"))
db = AsyncIOMotorClient(cfg["MONGO_URL"])[cfg["DB_NAME"]]
API = "http://localhost:8001/api"
SRC_OWNER = "6a99a9f579a11f66402c7fa6"
JD = ("Senior Digital Product Owner leading API modernization, SOAP-to-REST, backlog ownership "
      "across multiple teams, cloud/data-center migration, Agile delivery, personalization.")


async def main():
    email = f"idn_{uuid.uuid4().hex[:8]}@example.com"
    async with httpx.AsyncClient(timeout=300) as c:
        tok = (await c.post(f"{API}/auth/register", json={"email": email, "password": "IdnPass123!"})).json()["access_token"]
        H = {"Authorization": f"Bearer {tok}"}
        new_owner = (await c.get(f"{API}/auth/me", headers=H)).json()["id"]
        src = await db.career_knowledge.find({"owner_user_id": SRC_OWNER}).to_list(500)
        for n in src:
            d = dict(n); d.pop("_id", None); d["owner_user_id"] = new_owner; d["state"] = "VERIFIED"
            await db.career_knowledge.insert_one(d)
        opp = (await c.post(f"{API}/opportunities", headers=H, json={
            "target_role": "Senior Digital Product Owner", "organization": "Target Co", "job_description": JD})).json()["id"]
        await c.post(f"{API}/opportunities/{opp}/match", headers=H)
        for _ in range(120):
            s = (await c.get(f"{API}/opportunities/{opp}/match-status", headers=H)).json()
            if s.get("status") in ("complete", "error"): break
            await asyncio.sleep(2)

        # 1. generate WITHOUT profile -> export must be blocked 409
        await c.post(f"{API}/opportunities/{opp}/generate", headers=H)
        r = await c.get(f"{API}/opportunities/{opp}/export?format=pdf", headers=H)
        print("A) export w/o identity ->", r.status_code, "| detail:", r.json().get("detail", {}).get("missing") if r.status_code == 409 else r.text[:80])
        assert r.status_code == 409 and r.json()["detail"]["reason"] == "identity_incomplete"
        # validate gate reflects it
        v = (await c.post(f"{API}/opportunities/{opp}/validate", headers=H)).json()
        print("   identity_contact gate:", v["gate_results"]["identity_contact"]["status"])
        assert v["gate_results"]["identity_contact"]["status"] == "fail"

        # 2. save profile (incl HTTPS link), regenerate, export 200 with header
        await c.put(f"{API}/profile", headers=H, json={
            "full_name": "Jordan H. Candidate", "email": "jordan@pro.dev", "phone": "+1 555 777 0000",
            "location": "San Antonio, TX", "links": [{"label": "LinkedIn", "url": "https://linkedin.com/in/jordan"}]})
        await c.post(f"{API}/opportunities/{opp}/generate", headers=H)
        rep = (await c.get(f"{API}/opportunities/{opp}/representation", headers=H)).json()
        ident = rep["sections"].get("identity", {})
        print("B) identity snapshot:", ident.get("full_name"), "| stale:", rep.get("identity_stale"))
        assert ident["full_name"] == "Jordan H. Candidate" and rep["identity_stale"] is False
        pdf = await c.get(f"{API}/opportunities/{opp}/export?format=pdf", headers=H)
        dx = await c.get(f"{API}/opportunities/{opp}/export?format=docx", headers=H)
        print("   export pdf/docx ->", pdf.status_code, dx.status_code, "| pdf bytes:", len(pdf.content))
        assert pdf.status_code == 200 and dx.status_code == 200
        doc = zipfile.ZipFile(io.BytesIO(dx.content)).read("word/document.xml").decode()
        rels = zipfile.ZipFile(io.BytesIO(dx.content)).read("word/_rels/document.xml.rels").decode()
        print("   DOCX name present:", "Jordan H. Candidate" in doc, "| link rel:", "linkedin.com/in/jordan" in rels, "| no Target leak:", "Target:" not in doc)
        v2 = (await c.post(f"{API}/opportunities/{opp}/validate", headers=H)).json()
        print("   gate identity_contact:", v2["gate_results"]["identity_contact"]["status"], "| all passed:", v2["passed"])

        # 3. change profile after generation -> representation flagged stale (not silently altered)
        await c.put(f"{API}/profile", headers=H, json={
            "full_name": "Jordan H. Candidate", "email": "jordan@pro.dev", "phone": "+1 555 777 0000",
            "location": "Austin, TX", "links": [{"label": "LinkedIn", "url": "https://linkedin.com/in/jordan"}]})
        rep2 = (await c.get(f"{API}/opportunities/{opp}/representation", headers=H)).json()
        print("C) after profile edit -> identity_stale:", rep2.get("identity_stale"),
              "| stored still old location:", rep2["sections"]["identity"]["location"])
        assert rep2["identity_stale"] is True and rep2["sections"]["identity"]["location"] == "San Antonio, TX"

        # cleanup isolated account
        for coll in ["career_knowledge", "opportunities"]:
            await db[coll].delete_many({"owner_user_id": new_owner})
        for coll in ["requirements", "evidence_matches", "representations", "validation_runs"]:
            await db[coll].delete_many({"opportunity_id": opp})
        await db.candidate_profiles.delete_many({"owner_user_id": new_owner})
        await db.users.delete_one({"email": email})
        print("\nALL IDENTITY E2E ASSERTIONS PASSED · cleanup done")


if __name__ == "__main__":
    asyncio.run(main())
