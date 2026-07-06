import pytest

from app.pipeline.nodes.verdict import _evaluate_threshold, _to_pct


def test_to_pct_conversions():
    assert _to_pct(1.0, "pct") == 1.0
    assert _to_pct(1.0, "ppm") == pytest.approx(1e-4)
    assert _to_pct(1.0, "ppb") == pytest.approx(1e-7)
    assert _to_pct(25, "ppb") == pytest.approx(25e-7)


def test_evaluate_threshold_compliant_well_under():
    assert _evaluate_threshold(measured_pct=0.01, threshold_value=0.1, threshold_unit="pct", band_pct=10) == "compliant"


def test_evaluate_threshold_non_compliant_well_over():
    assert _evaluate_threshold(measured_pct=0.5, threshold_value=0.1, threshold_unit="pct", band_pct=10) == "non_compliant"


def test_evaluate_threshold_borderline_within_band():
    # threshold 0.1%, band 10% -> +/-0.01, so 0.105% should be borderline
    assert _evaluate_threshold(measured_pct=0.105, threshold_value=0.1, threshold_unit="pct", band_pct=10) == "borderline"
    assert _evaluate_threshold(measured_pct=0.098, threshold_value=0.1, threshold_unit="pct", band_pct=10) == "borderline"


def test_evaluate_threshold_just_outside_band_is_non_compliant():
    assert _evaluate_threshold(measured_pct=0.2, threshold_value=0.1, threshold_unit="pct", band_pct=10) == "non_compliant"


def test_evaluate_threshold_ppb_units():
    # PFAS individual threshold 25 ppb = 0.0000025 pct; 24 ppb should be borderline
    measured_pct_24ppb = _to_pct(24, "ppb")
    assert _evaluate_threshold(measured_pct_24ppb, threshold_value=25, threshold_unit="ppb", band_pct=10) == "borderline"
    measured_pct_18ppb = _to_pct(18, "ppb")
    assert _evaluate_threshold(measured_pct_18ppb, threshold_value=25, threshold_unit="ppb", band_pct=10) == "compliant"
    measured_pct_500ppb = _to_pct(500, "ppb")
    assert _evaluate_threshold(measured_pct_500ppb, threshold_value=25, threshold_unit="ppb", band_pct=10) == "non_compliant"
