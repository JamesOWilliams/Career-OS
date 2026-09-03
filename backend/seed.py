"""Seed: admin/owner account + James Williams canonical KB for golden regression."""
import os
import re
from datetime import datetime, timezone

from db import db
from security import hash_password, verify_password


def _now():
    return datetime.now(timezone.utc).isoformat()


async def seed_admin() -> str:
    email = os.environ["ADMIN_EMAIL"].lower()
    password = os.environ["ADMIN_PASSWORD"]
    existing = await db.users.find_one({"email": email})
    if existing is None:
        doc = {
            "email": email,
            "password_hash": hash_password(password),
            "role": "admin",
            "status": "active",
            "created_at": _now(),
        }
        res = await db.users.insert_one(doc)
        return str(res.inserted_id)
    if not verify_password(password, existing["password_hash"]):
        await db.users.update_one(
            {"email": email}, {"$set": {"password_hash": hash_password(password), "role": "admin"}}
        )
    return str(existing["_id"])


JAMES_NODES = [
    {
        "node_id": "CKN-CIV-USAA-001",
        "track": "civilian",
        "identity": {
            "employer": "USAA", "role": "Lead Software Engineer", "organization": "Bank / Digital Platform",
            "assignment": "", "client": "", "collaboration": "", "location": "San Antonio / DFW, TX",
            "start": "2016", "end": "2021",
        },
        "context": {"summary": "Owned a large API platform and led major modernization efforts across multiple engineering teams."},
        "evidence": [
            "Owned and operated a portfolio of approximately 52 production APIs across the digital banking platform.",
            "Led migration of legacy SOAP services to REST APIs, improving interoperability and developer experience.",
            "Drove language modernization migrating core services from Java to Go.",
            "Led cloud infrastructure migration on AWS relocating workloads from the DFW region footprint to ATL.",
            "Coordinated multi-team release readiness across dependent squads for major platform releases.",
        ],
        "retrieval": {
            "capabilities": ["API platform ownership", "service modernization", "cloud migration", "cross-team release readiness", "microservices architecture"],
            "technologies": ["Java", "Go", "SOAP", "REST", "AWS", "microservices"],
            "metrics": ["52 APIs"],
        },
    },
    {
        "node_id": "CKN-CIV-CPS-001",
        "track": "civilian",
        "identity": {
            "employer": "CPS Energy", "role": "Senior Software Engineer", "organization": "Energy Utility",
            "assignment": "", "client": "", "collaboration": "", "location": "San Antonio, TX",
            "start": "2021", "end": "Present",
        },
        "context": {"summary": "Built and delivered product software in the energy-utility domain."},
        "evidence": [
            "Delivered customer-facing product features for utility operations and grid data services.",
            "Built cloud-hosted APIs integrating metering and billing data sources.",
        ],
        "retrieval": {
            "capabilities": ["product engineering", "systems integration", "API development"],
            "technologies": ["cloud", "REST", "APIs"],
            "metrics": [],
        },
    },
    {
        "node_id": "CKN-CIV-AVANTUS-001",
        "track": "civilian",
        "identity": {
            "employer": "Avantus Federal", "role": "Software Engineer", "organization": "Federal Contractor",
            "assignment": "", "client": "Defense Logistics Agency (DLA)", "collaboration": "", "location": "TX",
            "start": "2014", "end": "2016",
        },
        "context": {"summary": "Delivered software for a federal client under contract; DLA is the client, not the employer."},
        "evidence": [
            "Developed and maintained logistics software for the Defense Logistics Agency (DLA) as the contracting client.",
            "Supported secure data integration workflows for federal supply-chain systems.",
        ],
        "retrieval": {
            "capabilities": ["federal software delivery", "secure data integration"],
            "technologies": ["Java", "SQL", "web services"],
            "metrics": [],
        },
    },
    {
        "node_id": "CKN-MIL-USAF-001",
        "track": "military",
        "identity": {
            "employer": "United States Air Force Reserve", "role": "Program Management Officer",
            "organization": "USAF Reserve", "assignment": "Program Management", "client": "", "collaboration": "",
            "location": "TX", "start": "2010", "end": "Present",
        },
        "context": {"summary": "Program management duties within USAF Reserve service — program management, not civilian product-management tenure."},
        "evidence": [
            "Performed program management for reserve unit initiatives, coordinating schedules, resources and readiness.",
            "Led planning and execution of multi-stakeholder program milestones.",
        ],
        "retrieval": {
            "capabilities": ["program management", "resource coordination", "readiness planning"],
            "technologies": [],
            "metrics": [],
        },
    },
    {
        "node_id": "CKN-IP-TALK-001",
        "track": "intellectual_property",
        "identity": {
            "employer": "", "role": "Speaker", "organization": "Regional Cloud Meetup",
            "assignment": "", "client": "", "collaboration": "", "location": "San Antonio, TX",
            "start": "2020", "end": "2020",
        },
        "context": {"summary": "Conference talk on API modernization — intellectual property, not employment."},
        "evidence": [
            "Delivered a technical talk on migrating monolithic SOAP services to cloud-native REST architectures.",
        ],
        "retrieval": {
            "capabilities": ["technical communication", "API modernization thought leadership"],
            "technologies": ["REST", "cloud"],
            "metrics": [],
        },
    },
]


async def seed_james_kb(owner_id: str):
    """Seed James Williams VERIFIED canonical nodes under the owner account (idempotent)."""
    for n in JAMES_NODES:
        existing = await db.career_knowledge.find_one(
            {"owner_user_id": owner_id, "node_id": n["node_id"]}
        )
        if existing:
            continue
        doc = {
            "owner_user_id": owner_id,
            "node_id": n["node_id"],
            "track": n["track"],
            "state": "VERIFIED",
            "identity": n["identity"],
            "context": n["context"],
            "evidence": n["evidence"],
            "retrieval": n["retrieval"],
            "guardrails": [],
            "provenance": {"source_upload_id": None, "source_span": "seed:james-williams"},
            "created_at": _now(),
            "verified_at": _now(),
        }
        await db.career_knowledge.insert_one(doc)
