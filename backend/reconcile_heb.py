"""Bounded canonical reconciliation for the HEB test account (owner-scoped).

Authorized scope ONLY: owner 6a99a9f579a11f66402c7fa6. Adds non-destructive authority
fields (authority / position_ref) + two human-confirmed factual corrections. No node is
deleted; original IDs, provenance, verified_at, and evidence are preserved.

Usage:
  python reconcile_heb.py           # snapshot (first run) then apply (idempotent)
  python reconcile_heb.py --verify  # print current authority/title/metric state only
  python reconcile_heb.py --rollback  # restore from the before-snapshot
"""
import sys
import json
import asyncio
from pathlib import Path
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import dotenv_values

cfg = dotenv_values(str(Path(__file__).parent / ".env"))
db = AsyncIOMotorClient(cfg["MONGO_URL"])[cfg["DB_NAME"]]
OWNER = "6a99a9f579a11f66402c7fa6"
SNAPSHOT = Path(__file__).parent / "reconcile_heb_before.json"

AUTHORITATIVE = [
    "CKN-CIV-USAA-013", "CKN-CIV-CPSENE-006", "CKN-CIV-AVANTU-003",
    "CKN-MIL-UNITED-004", "CKN-MIL-GEN-019",
    "CKN-IP-GEN-016", "CKN-IP-GEN-010", "CKN-IP-GEN-012", "CKN-IP-GEN-017",
]
ASSOCIATED = {
    "CKN-CIV-USAA-001": "CKN-CIV-USAA-013",
    "CKN-CIV-USAA-005": "CKN-CIV-USAA-013",
    "CKN-CIV-CPSENE-002": "CKN-CIV-CPSENE-006",
    "CKN-CIV-CPSENE-014": "CKN-CIV-CPSENE-006",
    "CKN-CIV-AVANTU-015": "CKN-CIV-AVANTU-003",
    "CKN-IP-GEN-011": "CKN-IP-GEN-016",
}
SUPERSEDED = {
    "CKN-CIV-DEFENS-008": "CKN-CIV-AVANTU-003",
    "CKN-MIL-GEN-020": "CKN-MIL-UNITED-004",
}
# Human-confirmed formal title (Cluster A)
TITLE_OVERRIDE = {"CKN-CIV-USAA-013": "Digital Product Owner"}
# Factual metric direction correction (Cluster A)
METRIC_FIX = {"CKN-CIV-USAA-001": ("Migration from DFW to ATL", "Migration from ATL to DFW")}

AFFECTED = sorted(set(AUTHORITATIVE) | set(ASSOCIATED) | set(SUPERSEDED)
                  | set(TITLE_OVERRIDE) | set(METRIC_FIX))


async def _fetch():
    docs = await db.career_knowledge.find(
        {"owner_user_id": OWNER, "node_id": {"$in": AFFECTED}}
    ).to_list(500)
    return {d["node_id"]: d for d in docs}


async def snapshot(by_id):
    if SNAPSHOT.exists():
        return
    dump = []
    for nid in AFFECTED:
        d = by_id.get(nid)
        if not d:
            continue
        dump.append({
            "node_id": nid, "authority": d.get("authority"),
            "position_ref": d.get("position_ref"),
            "role": d.get("identity", {}).get("role"),
            "metrics": d.get("retrieval", {}).get("metrics"),
        })
    SNAPSHOT.write_text(json.dumps(dump, indent=2))
    print(f"before-snapshot written: {SNAPSHOT}")


async def apply():
    by_id = await _fetch()
    missing = [n for n in AFFECTED if n not in by_id]
    assert not missing, f"missing affected nodes (owner scope): {missing}"
    await snapshot(by_id)

    changes = 0
    for nid in AUTHORITATIVE:
        changes += await _set(nid, {"authority": "authoritative", "position_ref": nid})
    for nid, auth in ASSOCIATED.items():
        changes += await _set(nid, {"authority": "associated", "position_ref": auth})
    for nid, auth in SUPERSEDED.items():
        changes += await _set(nid, {"authority": "superseded", "position_ref": auth})

    for nid, title in TITLE_OVERRIDE.items():
        d = by_id[nid]
        if d.get("identity", {}).get("role") != title:
            ident = dict(d["identity"])
            if "role_original" not in d:
                await db.career_knowledge.update_one(
                    {"owner_user_id": OWNER, "node_id": nid},
                    {"$set": {"role_original": ident.get("role")}})
            ident["role"] = title
            await db.career_knowledge.update_one(
                {"owner_user_id": OWNER, "node_id": nid}, {"$set": {"identity": ident}})
            changes += 1

    for nid, (old, new) in METRIC_FIX.items():
        d = by_id[nid]
        metrics = list(d.get("retrieval", {}).get("metrics", []))
        newm = [m.replace(old, new) for m in metrics]
        if newm != metrics:
            ret = dict(d.get("retrieval", {}))
            ret["metrics"] = newm
            await db.career_knowledge.update_one(
                {"owner_user_id": OWNER, "node_id": nid}, {"$set": {"retrieval": ret}})
            changes += 1

    print(f"applied changes: {changes}")
    await verify()


async def _set(nid, fields):
    res = await db.career_knowledge.update_one(
        {"owner_user_id": OWNER, "node_id": nid, "$or": [
            {"authority": {"$ne": fields["authority"]}},
            {"position_ref": {"$ne": fields["position_ref"]}},
        ]},
        {"$set": fields})
    return res.modified_count


async def verify():
    by_id = await _fetch()
    print(f"\n{'NODE':<22} {'AUTHORITY':<14} {'POSITION_REF':<22} ROLE")
    for nid in AFFECTED:
        d = by_id.get(nid, {})
        print(f"{nid:<22} {str(d.get('authority')):<14} {str(d.get('position_ref')):<22} {d.get('identity',{}).get('role')}")
    u1 = by_id.get("CKN-CIV-USAA-001", {})
    print("\nUSAA-001 metrics:", u1.get("retrieval", {}).get("metrics"))
    print("USAA-013 role:", by_id.get("CKN-CIV-USAA-013", {}).get("identity", {}).get("role"))
    # invariant: DEFENS-008 identity preserved (DLA employer kept for audit lineage)
    d8 = by_id.get("CKN-CIV-DEFENS-008", {})
    print("DEFENS-008 identity.employer PRESERVED:", d8.get("identity", {}).get("employer"),
          "| authority:", d8.get("authority"))


async def rollback():
    assert SNAPSHOT.exists(), "no snapshot to roll back from"
    data = json.loads(SNAPSHOT.read_text())
    for r in data:
        nid = r["node_id"]
        unset = {}
        setf = {}
        # restore authority/position_ref
        if r.get("authority") is None:
            unset["authority"] = ""
        else:
            setf["authority"] = r["authority"]
        if r.get("position_ref") is None:
            unset["position_ref"] = ""
        else:
            setf["position_ref"] = r["position_ref"]
        d = await db.career_knowledge.find_one({"owner_user_id": OWNER, "node_id": nid})
        if d and r.get("role") is not None:
            ident = dict(d["identity"]); ident["role"] = r["role"]; setf["identity"] = ident
        if d and r.get("metrics") is not None:
            ret = dict(d.get("retrieval", {})); ret["metrics"] = r["metrics"]; setf["retrieval"] = ret
        op = {}
        if setf:
            op["$set"] = setf
        if unset:
            op["$unset"] = unset
        if op:
            await db.career_knowledge.update_one({"owner_user_id": OWNER, "node_id": nid}, op)
    print("rollback complete from snapshot")


async def main():
    if "--verify" in sys.argv:
        await verify()
    elif "--rollback" in sys.argv:
        await rollback()
    else:
        await apply()


if __name__ == "__main__":
    asyncio.run(main())
