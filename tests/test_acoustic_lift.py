from evaluation.acoustic_lift import ACOUSTIC, ELECTRIC, split_evidence


def test_electric_guitar_must_be_a_late_event():
    rows = [
        {"start_seconds": 0, "end_seconds": 4, ACOUSTIC: 0.68, ELECTRIC: 0.05},
        {"start_seconds": 4, "end_seconds": 8, ACOUSTIC: 0.55, ELECTRIC: 0.07},
        {"start_seconds": 72, "end_seconds": 76, ACOUSTIC: 0.22, ELECTRIC: 0.58},
    ]
    result = split_evidence(rows, 96)
    assert result["acoustic_opening_supported"] and result["late_electric_supported"]
    rows[0][ELECTRIC] = 0.83
    result = split_evidence(rows, 96)
    assert not result["acoustic_opening_supported"]
    assert not result["late_electric_supported"]
