from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from deepgen.services.research_pipeline.contradictions import ContradictionResult
from deepgen.services.research_pipeline.extraction import ClaimItem


@dataclass
class ProposalDraft:
    relationship: str
    candidate_name: str | None
    confidence: float
    status: str
    notes: str
    evidence_ids: list[int]
    contradiction_flags: list[str]
    score_components: dict[str, float | int]


def _norm_name(value: str | None) -> str:
    return " ".join((value or "").lower().split())


def _insufficient(relationship: str, reason: str) -> ProposalDraft:
    return ProposalDraft(
        relationship=relationship,
        candidate_name=None,
        confidence=0.0,
        status="pending_review",
        notes=reason,
        evidence_ids=[],
        contradiction_flags=[],
        score_components={
            "avg_confidence": 0.0,
            "support_count": 0,
            "source_diversity": 0.0,
            "evidence_specificity": 0.0,
            "contradiction_penalty": 0.0,
            "final_score": 0.0,
        },
    )


def _compute_candidate_score(
    candidate_claims: list[ClaimItem],
    evidence_sources: dict[int, str],
    contradiction_flags: list[str],
    global_flags: list[str],
) -> tuple[float, dict[str, float | int], list[int]]:
    evidence_ids: set[int] = set()
    confidences: list[float] = []
    claims_with_evidence = 0

    for claim in candidate_claims:
        confidences.append(float(claim.confidence))
        if claim.evidence_ids:
            claims_with_evidence += 1
        for eid in claim.evidence_ids:
            evidence_ids.add(int(eid))

    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    support_count = len(candidate_claims)
    source_diversity_raw = len({evidence_sources.get(eid, "") for eid in evidence_ids if evidence_sources.get(eid, "")})
    source_diversity = min(1.0, source_diversity_raw / 3.0)
    evidence_specificity = claims_with_evidence / support_count if support_count else 0.0

    contradiction_penalty = 0.0
    if contradiction_flags:
        contradiction_penalty += 0.25
    if "same_parent_name_for_both_relationships" in global_flags:
        contradiction_penalty += 0.2

    final_score = (
        (0.45 * avg_confidence)
        + (0.25 * min(1.0, support_count / 3.0))
        + (0.20 * source_diversity)
        + (0.10 * evidence_specificity)
        - contradiction_penalty
    )
    final_score = max(0.0, min(1.0, final_score))

    components: dict[str, float | int] = {
        "avg_confidence": round(avg_confidence, 3),
        "support_count": support_count,
        "source_diversity": round(source_diversity, 3),
        "evidence_specificity": round(evidence_specificity, 3),
        "contradiction_penalty": round(contradiction_penalty, 3),
        "final_score": round(final_score, 3),
    }

    return final_score, components, sorted(evidence_ids)


def synthesize_proposals(
    claims: list[ClaimItem],
    evidence_sources: dict[int, str],
    contradictions: ContradictionResult,
    *,
    minimum_score: float = 0.35,
) -> list[ProposalDraft]:
    proposals: list[ProposalDraft] = []

    by_rel_name: dict[str, dict[str, list[ClaimItem]]] = {
        "father": defaultdict(list),
        "mother": defaultdict(list),
    }

    for claim in claims:
        if claim.candidate_name:
            by_rel_name[claim.relationship][_norm_name(claim.candidate_name)].append(claim)

    for relationship in ("father", "mother"):
        grouped = by_rel_name[relationship]
        if not grouped:
            proposals.append(_insufficient(relationship, "Insufficient evidence for a candidate parent."))
            continue

        best_name = ""
        best_score = -1.0
        best_components: dict[str, float | int] = {}
        best_evidence_ids: list[int] = []

        for name_key, candidate_claims in grouped.items():
            score, components, evidence_ids = _compute_candidate_score(
                candidate_claims=candidate_claims,
                evidence_sources=evidence_sources,
                contradiction_flags=contradictions.by_relationship.get(relationship, []),
                global_flags=contradictions.global_flags,
            )
            if score > best_score:
                best_name = name_key
                best_score = score
                best_components = components
                best_evidence_ids = evidence_ids

        display_name = None
        for claim in grouped.get(best_name, []):
            if claim.candidate_name:
                display_name = claim.candidate_name.strip()
                break

        flags = list(contradictions.by_relationship.get(relationship, []))
        flags.extend(contradictions.global_flags)
        flags = sorted(set(flags))

        if not display_name or not best_evidence_ids:
            proposals.append(_insufficient(relationship, "Insufficient evidence: no valid citations for proposal."))
            continue

        if best_score < minimum_score:
            proposals.append(
                ProposalDraft(
                    relationship=relationship,
                    candidate_name=None,
                    confidence=round(best_score, 3),
                    status="pending_review",
                    notes="Insufficient evidence quality threshold.",
                    evidence_ids=best_evidence_ids,
                    contradiction_flags=flags,
                    score_components=best_components,
                )
            )
            continue

        proposals.append(
            ProposalDraft(
                relationship=relationship,
                candidate_name=display_name,
                confidence=round(best_score, 3),
                status="pending_review",
                notes="Candidate synthesized from evidence and claim agreement.",
                evidence_ids=best_evidence_ids,
                contradiction_flags=flags,
                score_components=best_components,
            )
        )

    return proposals
