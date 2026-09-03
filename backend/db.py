"""MongoDB connection + central owner-scoped data-access layer.

Isolation invariant: every private collection carries owner_user_id, and the
value is ALWAYS derived from the auth token, never from client input. All reads
and mutations of private collections must go through OwnedRepo so the owner
filter is enforced centrally.
"""
import os
from pathlib import Path
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

_client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = _client[os.environ["DB_NAME"]]

# Collections that carry owner_user_id and are private to a single user.
PRIVATE_COLLECTIONS = {
    "career_knowledge",
    "resume_uploads",
    "opportunities",
    "requirements",
    "evidence_matches",
    "representations",
    "validation_runs",
}


class OwnedRepo:
    """Owner-scoped wrapper around a MongoDB collection.

    Every query is force-merged with {"owner_user_id": owner_id}. Callers cannot
    override the owner filter; this is the single choke point for data isolation.
    """

    def __init__(self, collection_name: str, owner_id: str):
        assert collection_name in PRIVATE_COLLECTIONS, collection_name
        self.col = db[collection_name]
        self.owner_id = owner_id

    def _scope(self, query: dict | None) -> dict:
        q = dict(query or {})
        q["owner_user_id"] = self.owner_id  # always override, never trust client
        return q

    async def insert(self, doc: dict) -> dict:
        doc["owner_user_id"] = self.owner_id
        res = await self.col.insert_one(doc)
        doc["_id"] = res.inserted_id
        return doc

    async def find(self, query: dict | None = None, sort=None, limit: int = 500):
        cursor = self.col.find(self._scope(query))
        if sort:
            cursor = cursor.sort(sort)
        return await cursor.to_list(limit)

    async def find_one(self, query: dict | None = None):
        return await self.col.find_one(self._scope(query))

    async def get(self, _id: str):
        if not ObjectId.is_valid(_id):
            return None
        return await self.col.find_one(self._scope({"_id": ObjectId(_id)}))

    async def update(self, _id: str, changes: dict) -> bool:
        if not ObjectId.is_valid(_id):
            return False
        res = await self.col.update_one(
            self._scope({"_id": ObjectId(_id)}), {"$set": changes}
        )
        return res.matched_count > 0

    async def delete(self, _id: str) -> bool:
        if not ObjectId.is_valid(_id):
            return False
        res = await self.col.delete_one(self._scope({"_id": ObjectId(_id)}))
        return res.deleted_count > 0

    async def count(self, query: dict | None = None) -> int:
        return await self.col.count_documents(self._scope(query))


async def ensure_indexes():
    await db.users.create_index("email", unique=True)
    await db.career_knowledge.create_index([("owner_user_id", 1), ("track", 1), ("state", 1)])
    await db.career_knowledge.create_index([("owner_user_id", 1), ("node_id", 1)])
    await db.resume_uploads.create_index([("owner_user_id", 1)])
    await db.opportunities.create_index([("owner_user_id", 1)])
    await db.requirements.create_index([("owner_user_id", 1), ("opportunity_id", 1)])
    await db.evidence_matches.create_index([("owner_user_id", 1), ("opportunity_id", 1)])
    await db.representations.create_index([("owner_user_id", 1), ("opportunity_id", 1)])
    await db.validation_runs.create_index([("owner_user_id", 1), ("opportunity_id", 1)])
