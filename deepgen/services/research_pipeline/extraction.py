from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel, Field, ValidationError, field_validator

from deepgen.services.llm import LLMClient


class PersonLike(Protocol):
    name: str
    xref: str
    birth_date: str | None
    birth_year: int | None


class ClaimItem(BaseModel):
    relationship: Literal["father", "mother"]
    candidate_name: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str = ""
    evidence_ids: list[int] = Field(default_factory=list)

    @field_validator("candidate_name")
    @classmethod
    def _clean_candidate_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class ClaimEnvelope(BaseModel):
    claims: list[ClaimItem] = Field(default_factory=list)


@dataclass
class ExtractionOutcome:
    claims: list[ClaimItem]
    parse_valid: bool
    raw_text: str
    retries_used: int
    repairs_used: int
    errors: list[str]


def _extract_json_blob(text: str) -> dict | list | None:
    payload = text.strip()
    if not payload:
        return None

    try:
        parsed = json.loads(payload)
        if isinstance(parsed, (dict, list)):
            return parsed
    except json.JSONDecodeError:
        pass

    match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", payload)
    if not match:
        return None

    try:
        parsed = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, (dict, list)) else None


def _build_prompt(person: PersonLike, evidence_items: list[object], prompt_template_version: str) -> str:
    lines = []
    for item in evidence_items:
        evidence_id = getattr(item, "id", None)
        source = getattr(item, "source", "")
        title = getattr(item, "title", "")
        url = getattr(item, "url", "")
        note = getattr(item, "note", "")
        lines.append(f"- id={evidence_id} source={source} title={title} url={url} note={note}")

    return (
        f"Template version: {prompt_template_version}.\n"
        "You are a genealogy claims extractor.\n"
        "Return JSON only. Do not include markdown.\n"
        "Output schema: {\"claims\": [{\"relationship\": \"father|mother\", \"candidate_name\": string|null, "
        "\"confidence\": number 0..1, \"rationale\": string, \"evidence_ids\": [int]}]}\n"
        "Rules:\n"
        "1) candidate_name must be null when evidence is weak.\n"
        "2) evidence_ids must use only listed evidence ids.\n"
        "3) keep claims conservative; avoid fabrication.\n"
        f"Person name: {person.name}\n"
        f"Person xref: {person.xref}\n"
        f"Birth date: {person.birth_date or 'unknown'}\n"
        f"Birth year: {person.birth_year or 'unknown'}\n"
        "Evidence:\n"
        + "\n".join(lines)
    )


def _build_repair_prompt(raw_text: str) -> str:
    return (
        "Convert the following text into valid JSON matching this schema exactly:\n"
        '{"claims":[{"relationship":"father|mother","candidate_name":null,"confidence":0.0,'
        '"rationale":"","evidence_ids":[]}]}\n'
        "Text:\n"
        f"{raw_text}"
    )


def _parse_claims_payload(text: str, valid_evidence_ids: set[int]) -> list[ClaimItem]:
    blob = _extract_json_blob(text)
    if blob is None:
        raise ValueError("No JSON payload found")

    if isinstance(blob, list):
        blob = {"claims": blob}
    elif isinstance(blob, dict) and "claims" not in blob:
        # Backward compatible repair for models returning relationship keys.
        flat_claims: list[dict] = []
        for relationship in ("father", "mother"):
            section = blob.get(relationship)
            if not isinstance(section, dict):
                continue
            flat_claims.append(
                {
                    "relationship": relationship,
                    "candidate_name": section.get("name"),
                    "confidence": section.get("confidence", 0.0),
                    "rationale": section.get("reason", ""),
                    "evidence_ids": section.get("evidence_ids", []),
                }
            )
        blob = {"claims": flat_claims}

    envelope = ClaimEnvelope.model_validate(blob)
    cleaned: list[ClaimItem] = []
    for claim in envelope.claims:
        evidence_ids = [eid for eid in claim.evidence_ids if eid in valid_evidence_ids]
        cleaned.append(
            ClaimItem(
                relationship=claim.relationship,
                candidate_name=claim.candidate_name,
                confidence=round(float(claim.confidence), 3),
                rationale=(claim.rationale or "").strip(),
                evidence_ids=evidence_ids,
            )
        )
    return cleaned


def extract_claims_for_person(
    llm_client: LLMClient | None,
    person: PersonLike,
    evidence_items: list[object],
    *,
    prompt_template_version: str,
) -> ExtractionOutcome:
    if llm_client is None:
        return ExtractionOutcome(
            claims=[],
            parse_valid=True,
            raw_text="",
            retries_used=0,
            repairs_used=0,
            errors=["LLM backend disabled or missing credentials"],
        )

    valid_evidence_ids = {int(getattr(item, "id")) for item in evidence_items if getattr(item, "id", None) is not None}
    prompt = _build_prompt(person=person, evidence_items=evidence_items, prompt_template_version=prompt_template_version)

    retries_used = 0
    repairs_used = 0
    errors: list[str] = []

    try:
        raw = llm_client.generate(prompt)
    except Exception as exc:  # noqa: BLE001
        return ExtractionOutcome(
            claims=[],
            parse_valid=False,
            raw_text="",
            retries_used=0,
            repairs_used=0,
            errors=[f"LLM request failed: {exc}"],
        )

    try:
        claims = _parse_claims_payload(raw, valid_evidence_ids)
        return ExtractionOutcome(
            claims=claims,
            parse_valid=True,
            raw_text=raw,
            retries_used=retries_used,
            repairs_used=repairs_used,
            errors=errors,
        )
    except (ValidationError, ValueError) as exc:
        errors.append(f"Primary parse failed: {exc}")

    retries_used += 1
    repairs_used += 1
    try:
        repair_prompt = _build_repair_prompt(raw)
        repaired_raw = llm_client.generate(repair_prompt)
        claims = _parse_claims_payload(repaired_raw, valid_evidence_ids)
        return ExtractionOutcome(
            claims=claims,
            parse_valid=True,
            raw_text=repaired_raw,
            retries_used=retries_used,
            repairs_used=repairs_used,
            errors=errors,
        )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"Repair parse failed: {exc}")
        return ExtractionOutcome(
            claims=[],
            parse_valid=False,
            raw_text=raw,
            retries_used=retries_used,
            repairs_used=repairs_used,
            errors=errors,
        )
