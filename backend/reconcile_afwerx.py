"""Bounded AFWERX canonical reconciliation (human-authorized, HEB UAT).

Links the two separately-ingested AFWERX fellowship records into one authoritative position.
ONLY the `authority` and `position_ref` fields are changed. No evidence, identity, metrics,
provenance or state is deleted or rewritten. Idempotent; writes a rollback snapshot first.

  CKN-CIV-AFWERX-007  -> authority=authoritative, position_ref=CKN-CIV-AFWERX-007
  CKN-CIV-GEN-018     -> authority=associated,    position_ref=CKN-CIV-AFWERX-007
"""
import asyncio, os, json
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import dotenv_values

cfg = dotenv_values(os.path.join(os.path.dirname(__file__), ".env"))
db = AsyncIOMotorClient(cfg["MONGO_URL"])[cfg["DB_NAME"]]
OWNER = "6a99a9f579a11f66402c7fa6"
AUTH = "CKN-CIV-AFWERX-007"
ASSOC = "CKN-CIV-GEN-018"
SNAPSHOT = os.path.join(os.path.dirname(__file__), "reconcile_afwerx_before.json")


async def main():
    nodes = {n["node_id"]: n for n in await db.career_knowledge.find(
        {"owner_user_id": OWNER, "node_id": {"$in": [AUTH, ASSOC]}}).to_list(10)}
    assert AUTH in nodes and ASSOC in nodes, f"missing node(s): {set([AUTH, ASSOC]) - set(nodes)}"

    # rollback snapshot (only the fields we touch + evidence counts as integrity witness)
    before = {nid: {"authority": n.get("authority"), "position_ref": n.get("position_ref"),
                    "state": n.get("state"), "evidence_count": len(n.get("evidence", []) or []),
                    "metrics": n.get("retrieval", {}).get("metrics", [])}
              for nid, n in nodes.items()}
    if not os.path.exists(SNAPSHOT):
        with open(SNAPSHOT, "w") as f:
            json.dump(before, f, indent=2)
        print("rollback snapshot ->", SNAPSHOT)
    else:
        print("rollback snapshot already exists (kept):", SNAPSHOT)
    print("BEFORE:", json.dumps(before, indent=2))

    ev_before = {nid: len(n.get("evidence", []) or []) for nid, n in nodes.items()}

    await db.career_knowledge.update_one(
        {"owner_user_id": OWNER, "node_id": AUTH},
        {"$set": {"authority": "authoritative", "position_ref": AUTH}})
    await db.career_knowledge.update_one(
        {"owner_user_id": OWNER, "node_id": ASSOC},
        {"$set": {"authority": "associated", "position_ref": AUTH}})

    after = {n["node_id"]: n for n in await db.career_knowledge.find(
        {"owner_user_id": OWNER, "node_id": {"$in": [AUTH, ASSOC]}}).to_list(10)}
    # integrity assertions: fields set, evidence untouched, still VERIFIED
    assert after[AUTH]["authority"] == "authoritative" and after[AUTH]["position_ref"] == AUTH
    assert after[ASSOC]["authority"] == "associated" and after[ASSOC]["position_ref"] == AUTH
    for nid in (AUTH, ASSOC):
        assert after[nid]["state"] == "VERIFIED", f"{nid} state changed!"
        assert len(after[nid].get("evidence", []) or []) == ev_before[nid], f"{nid} evidence changed!"
    print("AFTER: authoritative + associated set; evidence/state preserved. DONE.")


if __name__ == "__main__":
    asyncio.run(main())
