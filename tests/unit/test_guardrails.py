from app.guardrails.rules import apply_guardrails, never_guess
from app.models import SubstanceVerdict, VerdictStatus


def _verdict(**overrides) -> SubstanceVerdict:
    base = dict(
        substance_name="Test Substance", cas_number="000-00-0", component_name="Test Component",
        status=VerdictStatus.COMPLIANT, regulation_name="ROHS_ANNEX_II", threshold_value=0.1,
        threshold_unit="pct", measured_value=0.01, measured_unit="pct",
        citations=[], explanation="fine",
        reason_code="within_threshold",
    )
    base.update(overrides)
    return SubstanceVerdict(**base)


def test_never_guess_forces_review_when_not_found():
    assert never_guess(found_in_graph=False, proposed_status=VerdictStatus.COMPLIANT) == VerdictStatus.NEEDS_REVIEW
    assert never_guess(found_in_graph=False, proposed_status=VerdictStatus.NON_COMPLIANT) == VerdictStatus.NEEDS_REVIEW


def test_never_guess_passes_through_when_found():
    assert never_guess(found_in_graph=True, proposed_status=VerdictStatus.COMPLIANT) == VerdictStatus.COMPLIANT


def test_apply_guardrails_overrides_compliant_when_not_found_in_graph():
    verdict = _verdict(status=VerdictStatus.COMPLIANT)
    result_verdict, result = apply_guardrails(verdict, found_in_graph=False)
    assert result_verdict.status == VerdictStatus.NEEDS_REVIEW
    assert result_verdict.reason_code == "not_found_in_graph"
    assert result.rewritten is True


def test_apply_guardrails_downgrades_decided_verdict_missing_citation():
    verdict = _verdict(status=VerdictStatus.COMPLIANT, citations=[])
    result_verdict, result = apply_guardrails(verdict, found_in_graph=True)
    assert result_verdict.status == VerdictStatus.NEEDS_REVIEW
    assert result_verdict.reason_code == "missing_citation"


def test_apply_guardrails_allows_decided_verdict_with_full_citation():
    from app.models import RagCitation
    verdict = _verdict(status=VerdictStatus.NON_COMPLIANT, reason_code="exceeds_threshold",
                        citations=[RagCitation(text="x", source_id="y", regulation_name="ROHS_ANNEX_II")])
    result_verdict, result = apply_guardrails(verdict, found_in_graph=True)
    assert result_verdict.status == VerdictStatus.NON_COMPLIANT
    assert result.rewritten is False


def test_apply_guardrails_strips_banned_hedge_language():
    from app.models import RagCitation
    verdict = _verdict(
        status=VerdictStatus.COMPLIANT, reason_code="within_threshold",
        citations=[RagCitation(text="x", source_id="y", regulation_name="ROHS_ANNEX_II")],
        explanation="This is probably fine, no need to check further.",
    )
    result_verdict, result = apply_guardrails(verdict, found_in_graph=True)
    assert "probably fine" not in result_verdict.explanation.lower()
    assert result.rewritten is True
    assert "probably fine" in result.matched_phrases


def test_apply_guardrails_strips_legal_conclusion_language():
    from app.models import RagCitation
    verdict = _verdict(
        status=VerdictStatus.COMPLIANT, reason_code="within_threshold",
        citations=[RagCitation(text="x", source_id="y", regulation_name="ROHS_ANNEX_II")],
        explanation="This product is fully compliant with the law.",
    )
    result_verdict, result = apply_guardrails(verdict, found_in_graph=True)
    assert "fully compliant with the law" not in result_verdict.explanation.lower()
    assert result.rewritten is True


def test_needs_review_verdict_is_exempt_from_citation_requirement():
    verdict = _verdict(status=VerdictStatus.NEEDS_REVIEW, reason_code="borderline_concentration",
                        regulation_name=None, threshold_value=None, threshold_unit=None, citations=[])
    result_verdict, result = apply_guardrails(verdict, found_in_graph=True)
    assert result_verdict.status == VerdictStatus.NEEDS_REVIEW
    assert result.rewritten is False
