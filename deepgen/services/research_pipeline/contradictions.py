from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from deepgen.services.research_pipeline.extraction import ClaimItem


class PersonLike(Protocol):
    name: str
    birth_year: int | None


@dataclass
class ContradictionResult:
    by_relationship: dict[str, list[str]]
    global_flags: list[str]


def _norm_name(value: str | None) -> str:
    return " ".join((value or "").lower().split())


def _extract_year(text: str) -> int | None:
    matches = re.findall(r"(\d{4})", text or "")
    if not matches:
        return None
    year = int(matches[-1])
    if 1500 <= year <= 2100:
        return year
    return None


def evaluate_contradictions(person: PersonLike, claims: list[ClaimItem]) -> ContradictionResult:
    by_relationship: dict[str, list[str]] = {"father": [], "mother": []}
    global_flags: list[str] = []

    person_name_norm = _norm_name(person.name)
    high_conf: dict[str, set[str]] = {"father": set(), "mother": set()}

    top_name_by_rel: dict[str, str] = {}
    top_conf_by_rel: dict[str, float] = {"father": -1.0, "mother": -1.0}

    for claim in claims:
        rel = claim.relationship
        name_norm = _norm_name(claim.candidate_name)

        if name_norm and name_norm == person_name_norm:
            by_relationship[rel].append("self_parent_conflict")

        if claim.candidate_name and claim.confidence >= 0.65:
            high_conf[rel].add(name_norm)

        if claim.candidate_name and claim.confidence > top_conf_by_rel[rel]:
            top_conf_by_rel[rel] = claim.confidence
            top_name_by_rel[rel] = name_norm

        rationale_year = _extract_year(claim.rationale)
        if person.birth_year and rationale_year and rationale_year > person.birth_year - 12:
            by_relationship[rel].append("chronology_conflict")

    for rel, values in high_conf.items():
        values.discard("")
        if len(values) > 1:
            by_relationship[rel].append("multiple_high_confidence_candidates")

    father_name = top_name_by_rel.get("father")
    mother_name = top_name_by_rel.get("mother")
    if father_name and mother_name and father_name == mother_name:
        global_flags.append("same_parent_name_for_both_relationships")

    for rel in ("father", "mother"):
        deduped = sorted(set(by_relationship[rel]))
        by_relationship[rel] = deduped

    global_flags = sorted(set(global_flags))
    return ContradictionResult(by_relationship=by_relationship, global_flags=global_flags)
