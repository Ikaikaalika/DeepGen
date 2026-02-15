from types import SimpleNamespace

from deepgen.services.research_pipeline.contradictions import evaluate_contradictions
from deepgen.services.research_pipeline.extraction import ClaimItem
from deepgen.services.research_pipeline.scoring import synthesize_proposals


def _person() -> SimpleNamespace:
    return SimpleNamespace(
        xref="@I3@",
        name="Jane Doe",
        birth_year=1930,
    )


def test_contradictions_detect_multiple_high_confidence_candidates():
    claims = [
        ClaimItem(
            relationship="father",
            candidate_name="John Doe",
            confidence=0.9,
            rationale="source A",
            evidence_ids=[1],
        ),
        ClaimItem(
            relationship="father",
            candidate_name="James Doe",
            confidence=0.85,
            rationale="source B",
            evidence_ids=[2],
        ),
    ]

    contradictions = evaluate_contradictions(_person(), claims)

    assert "multiple_high_confidence_candidates" in contradictions.by_relationship["father"]


def test_scoring_forces_null_candidate_when_citations_missing():
    claims = [
        ClaimItem(
            relationship="mother",
            candidate_name="Mary Smith",
            confidence=0.88,
            rationale="strong but no citations",
            evidence_ids=[],
        )
    ]
    contradictions = evaluate_contradictions(_person(), claims)

    proposals = synthesize_proposals(claims=claims, evidence_sources={}, contradictions=contradictions)
    mother = [p for p in proposals if p.relationship == "mother"][0]

    assert mother.candidate_name is None
    assert "Insufficient evidence" in mother.notes
