from backend.science import regulations as R

EV = [{"incident_no": "441788", "start_date": "2025-06-08T18:00", "end_date": "2025-06-09T20:00"}]


def test_super_emitter_statuses():
    assert R.super_emitter(150, 400, 250)["status"] == "EXCEEDS"
    assert R.super_emitter(10, 90, 40)["status"] == "BELOW"
    assert R.super_emitter(60, 300, 120)["status"] == "INCONCLUSIVE"
    assert "not an enforcement finding" in R.super_emitter(150, 400, 250)["note"]


def test_reporting_no_matching_report():
    r = R.emissions_event_reporting(20000, ["2025-08-08"], EV)
    assert r["status"] == "NO_MATCHING_REPORT_FOUND"


def test_reporting_reported_within_window():
    r = R.emissions_event_reporting(20000, ["2025-06-10"], EV)  # within ±1 day of the event end
    assert r["status"] == "REPORTED"
    assert r["matches"][0]["incident_no"] == "441788"


def test_reporting_below_rq():
    assert R.emissions_event_reporting(500, ["2025-08-08"], EV)["status"] == "BELOW_RQ"


def test_physics_and_not_assessed():
    rules = R.evaluate({"p5_kg_h": 150, "p95_kg_h": 400, "median_kg_h": 250}, ["2025-08-08"], EV,
                       {"classification": "flare_slip_implausible", "ceiling_t_h": 300, "q_t_h": 0.25,
                        "q_fraction_of_ceiling": 0.001, "interpretation": "x"})
    by = {r["rule_id"]: r["status"] for r in rules}
    assert by["PLANT_PHYSICS_CEILING"] == "CONSISTENT"
    assert by["NOX_PERMIT_LIMITS"] == by["GHGRP_REPORTED"] == "NOT_ASSESSED"
