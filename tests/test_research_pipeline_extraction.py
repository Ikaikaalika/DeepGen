from types import SimpleNamespace

from deepgen.services.research_pipeline.extraction import extract_claims_for_person


class _StubLLM:
    def __init__(self, outputs):
        self.outputs = list(outputs)

    def generate(self, prompt: str) -> str:  # noqa: ARG002
        if not self.outputs:
            raise RuntimeError("No stub output configured")
        return self.outputs.pop(0)


def _person() -> SimpleNamespace:
    return SimpleNamespace(
        xref="@I1@",
        name="Jane Doe",
        birth_date=None,
        birth_year=1930,
    )


def test_extract_claims_filters_invalid_evidence_ids():
    llm = _StubLLM(
        [
            '{"claims":[{"relationship":"father","candidate_name":"John Doe","confidence":0.82,'
            '"rationale":"from sources","evidence_ids":[1,999]}]}'
        ]
    )
    evidence = [SimpleNamespace(id=1, source="nara", title="doc", url="u", note="n")]

    result = extract_claims_for_person(llm_client=llm, person=_person(), evidence_items=evidence, prompt_template_version="v2")

    assert result.parse_valid is True
    assert result.claims[0].candidate_name == "John Doe"
    assert result.claims[0].evidence_ids == [1]
    assert result.repairs_used == 0


def test_extract_claims_runs_single_repair_pass_on_invalid_json():
    llm = _StubLLM(
        [
            "not json",
            '{"claims":[{"relationship":"mother","candidate_name":"Mary Smith","confidence":0.67,'
            '"rationale":"repair output","evidence_ids":[2]}]}',
        ]
    )
    evidence = [SimpleNamespace(id=2, source="loc", title="doc2", url="u2", note="n2")]

    result = extract_claims_for_person(llm_client=llm, person=_person(), evidence_items=evidence, prompt_template_version="v2")

    assert result.parse_valid is True
    assert result.retries_used == 1
    assert result.repairs_used == 1
    assert result.claims[0].relationship == "mother"
    assert result.claims[0].evidence_ids == [2]
