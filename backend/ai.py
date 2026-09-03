"""AI boundary. Claude Sonnet 4.6 via Emergent LLM key.

AI RESPONSIBILITIES ONLY: resume extraction (-> PROPOSED), JD analysis,
evidence-match suggestion, resume language. AI never establishes canonical
truth and never assigns final weights/thresholds — that is deterministic code
in pipeline.py.
"""
import os
import json
import uuid
import logging

from emergentintegrations.llm.chat import LlmChat, UserMessage

logger = logging.getLogger(__name__)

_KEY = os.environ["EMERGENT_LLM_KEY"]
_MODEL = os.environ.get("LLM_MODEL", "claude-sonnet-4-6")


def _chat(system: str) -> LlmChat:
    return LlmChat(
        api_key=_KEY,
        session_id=f"careeros-{uuid.uuid4()}",
        system_message=system,
    ).with_model("anthropic", _MODEL)


async def _ask_json(system: str, prompt: str):
    """Send one prompt, parse a JSON object/array out of the reply."""
    chat = _chat(system)
    raw = await chat.send_message(UserMessage(text=prompt))
    text = (raw or "").strip()
    if "```" in text:
        # strip code fences
        text = text.split("```", 2)
        text = text[1] if len(text) > 1 else text[0]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip("` \n")
    # find first { or [
    for opener, closer in (("{", "}"), ("[", "]")):
        s = text.find(opener)
        e = text.rfind(closer)
        if s != -1 and e != -1 and e > s:
            try:
                return json.loads(text[s : e + 1])
            except json.JSONDecodeError:
                continue
    logger.error("LLM did not return valid JSON: %s", text[:400])
    raise ValueError("LLM response was not valid JSON")


EXTRACTION_SYSTEM = """You are the Career OS extraction engine. You read a resume and
break it into discrete CAREER KNOWLEDGE NODES. Each node is one distinct professional
experience (a role at an employer, a military assignment, or an intellectual-property /
publication / patent item).

You PROPOSE structured data only. You never invent facts. If a metric or detail is not
explicitly present in the text, leave it out. Return ONLY JSON."""

EXTRACTION_PROMPT = """Extract career knowledge nodes from this resume text.

Return a JSON array. Each element:
{{
  "track": "civilian" | "military" | "intellectual_property",
  "identity": {{
     "employer": "", "role": "", "organization": "", "assignment": "",
     "client": "", "collaboration": "", "location": "", "start": "", "end": ""
  }},
  "context": {{ "summary": "" }},
  "evidence": ["short factual bullet grounded in the text", ...],
  "retrieval": {{
     "capabilities": ["skill/capability demonstrated", ...],
     "technologies": ["tech/tool named in text", ...],
     "metrics": ["only metrics explicitly stated in the text", ...]
  }}
}}

Rules:
- civilian = normal employment. military = armed-forces service/assignment. intellectual_property = patents, papers, talks, open-source.
- Put ONLY explicitly stated metrics in metrics[]. Do not estimate or invent numbers.
- "client" / "collaboration" are for consulting clients or partner orgs — never treat them as the employer.
- Keep evidence bullets faithful to the source.

RESUME TEXT:
{text}
"""


async def extract_nodes(resume_text: str) -> list[dict]:
    data = await _ask_json(EXTRACTION_SYSTEM, EXTRACTION_PROMPT.format(text=resume_text[:12000]))
    return data if isinstance(data, list) else data.get("nodes", [])


JD_SYSTEM = """You are the Career OS job-description analyst. You decompose a target job
description into discrete REQUIREMENTS across six categories, then assign a tier.
Return ONLY JSON."""

JD_PROMPT = """Target role: {role}
Organization: {org}

Analyze this job description into requirements.

Return JSON array. Each element:
{{
  "text": "the concrete requirement, one sentence",
  "category": "role_identity" | "core_outcome" | "core_capability" | "tech_domain" | "operating_expectation" | "explicit_requirement",
  "tier": 1 | 2 | 3 | 4
}}

Tier meaning:
- 1 = defining / must-have identity of the role
- 2 = core capability strongly required
- 3 = important but secondary
- 4 = nice-to-have / peripheral
Categories:
- role_identity: what the role fundamentally is
- core_outcome: outcomes the role must deliver
- core_capability: capabilities/skills required
- tech_domain: specific technologies/domains
- operating_expectation: ways of working, collaboration, process
- explicit_requirement: explicitly stated hard requirements (degree, years, clearance)

Produce 8-16 requirements. Return ONLY the JSON array.

JOB DESCRIPTION:
{jd}
"""


async def analyze_jd(role: str, org: str, jd: str) -> list[dict]:
    data = await _ask_json(JD_SYSTEM, JD_PROMPT.format(role=role, org=org or "", jd=jd[:10000]))
    return data if isinstance(data, list) else data.get("requirements", [])


MATCH_SYSTEM = """You are the Career OS evidence-match suggester. Given ONE requirement and a
list of VERIFIED canonical experience nodes, you suggest which nodes are relevant and how
relevant each is. You only SUGGEST — deterministic code decides the final match strength and
weight. Return ONLY JSON."""

MATCH_PROMPT = """REQUIREMENT (tier {tier}, {category}): {req}

VERIFIED CANONICAL NODES (id :: summary):
{nodes}

For each node that provides genuine evidence for this requirement, return an entry.
If NO node genuinely supports it, return an empty array.

Return JSON array:
[{{
  "node_id": "<the node id exactly>",
  "relevance": 0.0-1.0,
  "rationale": "one short sentence citing which capability/tech/evidence supports it"
}}]

Only include nodes with real supporting evidence. Return ONLY the JSON array."""


async def suggest_matches(requirement: dict, nodes: list[dict]) -> list[dict]:
    if not nodes:
        return []
    listing = "\n".join(
        f'{n["node_id"]} :: {n.get("identity", {}).get("role","")} @ '
        f'{n.get("identity", {}).get("employer","")} | caps: '
        f'{", ".join(n.get("retrieval", {}).get("capabilities", [])[:6])} | tech: '
        f'{", ".join(n.get("retrieval", {}).get("technologies", [])[:8])}'
        for n in nodes
    )
    data = await _ask_json(
        MATCH_SYSTEM,
        MATCH_PROMPT.format(
            tier=requirement.get("tier"),
            category=requirement.get("category"),
            req=requirement.get("text"),
            nodes=listing,
        ),
    )
    return data if isinstance(data, list) else data.get("matches", [])


RESUME_SYSTEM = """You are the Career OS resume language writer. You render ALREADY-SELECTED,
ALREADY-VERIFIED evidence into resume prose. You may sharpen emphasis and phrasing but you may
NOT change reality: no invented metrics, no new employers, no merged timelines. Every bullet must
trace to the evidence you are given. Return ONLY JSON."""

RESUME_PROMPT = """Write resume content for target role "{role}" at "{org}".
Use ONLY the selected evidence below. Do not invent metrics or facts.

SELECTED EVIDENCE (grouped by experience):
{evidence}

Return JSON:
{{
  "summary": "3-4 sentence professional summary grounded only in the evidence",
  "experiences": [
     {{ "node_id": "<id>", "bullets": [ {{"text": "resume bullet", "source_node_id": "<id>"}} ] }}
  ]
}}
Emphasis may change; reality may not. Return ONLY the JSON."""


async def write_resume_language(role: str, org: str, evidence_blocks: list[dict]) -> dict:
    blocks = []
    for b in evidence_blocks:
        ident = b.get("identity", {})
        blocks.append(
            f'[{b["node_id"]}] {ident.get("role","")} @ {ident.get("employer","")} '
            f'({ident.get("start","")}-{ident.get("end","")})\n  evidence: '
            + " | ".join(b.get("evidence", [])[:8])
            + "\n  metrics: "
            + " | ".join(b.get("metrics", []))
        )
    data = await _ask_json(
        RESUME_SYSTEM,
        RESUME_PROMPT.format(role=role, org=org or "", evidence="\n\n".join(blocks)),
    )
    return data
