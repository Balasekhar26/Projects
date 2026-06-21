from __future__ import annotations

import json

from backend.core.consensus_engine import ConsensusEngine, ConsensusStatus, Decision, EvidenceType
from backend.core.validators import (
    CompilerValidator,
    DataIntegrityValidator,
    PhysicsMathValidator,
    SecurityValidator,
    Severity,
    TestValidator,
    ValidationStatus,
    run_validators,
)


# ---------------------------------------------------------------------------
# 1. Security Validator
# ---------------------------------------------------------------------------

def test_security_flags_hardcoded_secret_and_vetoes():
    r = SecurityValidator().validate({"code": "api_key = 'supersecretvalue123'"})
    assert r.status is ValidationStatus.FAIL
    assert r.severity.rank >= Severity.HIGH.rank
    assert r.veto is True
    assert r.requires_human_approval is True


def test_security_flags_dangerous_command():
    r = SecurityValidator().validate("os.system('rm -rf /')")
    assert r.status is ValidationStatus.FAIL
    assert any(f.code in {"os_system", "destructive_command"} for f in r.findings)


def test_security_passes_clean_code():
    r = SecurityValidator().validate({"code": "def add(a, b):\n    return a + b"})
    assert r.status is ValidationStatus.PASS
    assert r.veto is True  # still veto-capable, but PASS doesn't block


def test_security_critical_for_private_key():
    r = SecurityValidator().validate("-----BEGIN RSA PRIVATE KEY-----\nabc")
    assert r.severity is Severity.CRITICAL


# ---------------------------------------------------------------------------
# 2. Compiler Validator
# ---------------------------------------------------------------------------

def test_compiler_fails_on_syntax_error():
    r = CompilerValidator().validate({"code": "def f(:\n  pass"})
    assert r.status is ValidationStatus.FAIL
    assert r.veto is True
    assert r.details["compile_errors"]
    assert r.requires_human_approval is True


def test_compiler_passes_valid_code():
    r = CompilerValidator().validate({"code": "x = 1\ny = x + 2\n"})
    assert r.status is ValidationStatus.PASS


def test_compiler_skips_non_python():
    r = CompilerValidator().validate({"code": "int main(){}", "language": "c"})
    assert r.status is ValidationStatus.PASS


# ---------------------------------------------------------------------------
# 3. Physics / Math Validator
# ---------------------------------------------------------------------------

def test_physics_rejects_perpetual_motion():
    r = PhysicsMathValidator().validate({"energy_in": 100, "energy_out": 150})
    assert r.status is ValidationStatus.FAIL
    assert r.veto is True
    assert any(f.code == "energy_conservation" for f in r.findings)


def test_physics_power_budget_violation():
    r = PhysicsMathValidator().validate({"power_supply_w": 5, "power_loads_w": [2, 2, 3]})
    assert r.status is ValidationStatus.FAIL
    assert any(f.code == "power_budget" for f in r.findings)


def test_physics_passes_valid_budget():
    r = PhysicsMathValidator().validate({"power_supply_w": 10, "power_loads_w": [2, 3]})
    assert r.status is ValidationStatus.PASS
    assert r.details["power_demand_w"] == 5


def test_physics_unit_mismatch():
    r = PhysicsMathValidator().validate({"unit_check": {"expected": "W", "actual": "V"}})
    assert r.status is ValidationStatus.FAIL


# ---------------------------------------------------------------------------
# 4. Test Validator
# ---------------------------------------------------------------------------

def test_test_validator_flags_regression():
    r = TestValidator().validate({"total": 124, "passed": 122, "failed": 2})
    assert r.status is ValidationStatus.FAIL
    assert r.veto is False  # tests don't hard-veto
    assert r.requires_human_approval is True
    assert r.details["failed"] == 2


def test_test_validator_passes_green():
    r = TestValidator().validate({"total": 50, "passed": 50, "failed": 0})
    assert r.status is ValidationStatus.PASS


def test_test_validator_coverage_warning():
    r = TestValidator().validate({"total": 10, "passed": 10, "failed": 0,
                                  "coverage": 60, "min_coverage": 80})
    assert r.status is ValidationStatus.PASS  # passing but...
    assert any(f.code == "coverage" for f in r.findings)


# ---------------------------------------------------------------------------
# 5. Data Integrity Validator
# ---------------------------------------------------------------------------

def test_data_integrity_detects_invalid_reference():
    r = DataIntegrityValidator().validate({"records": [
        {"id": "a", "refs": ["b"]},
        {"id": "c"},
    ]})
    assert r.status is ValidationStatus.FAIL
    assert any(f.code == "invalid_reference" for f in r.findings)


def test_data_integrity_detects_duplicates():
    r = DataIntegrityValidator().validate({"records": [{"id": "a"}, {"id": "a"}]})
    assert any(f.code == "duplicate" for f in r.findings)


def test_data_integrity_passes_clean_graph():
    r = DataIntegrityValidator().validate({"records": [
        {"id": "a", "refs": ["b"]},
        {"id": "b"},
    ]})
    assert r.status is ValidationStatus.PASS


# ---------------------------------------------------------------------------
# Evidence conversion & consensus integration
# ---------------------------------------------------------------------------

def test_pass_becomes_tool_verified_evidence():
    out = TestValidator().validate({"total": 5, "passed": 5, "failed": 0}).to_consensus_output()
    assert out.decision is Decision.APPROVE
    assert EvidenceType.TOOL_VERIFIED in out.evidence
    assert out.source_id == "validator:Test"


def test_security_fail_vetoes_consensus():
    report = run_validators({"code": "password = 'hunter2value'"}, validators=["Security"])
    decision = ConsensusEngine.decide(report.consensus_outputs())
    assert decision.status is ConsensusStatus.REJECTED
    assert decision.rejected_by == "Security"


def test_all_validators_pass_provides_independent_evidence():
    report = run_validators(
        {"code": "x = 1\n", "energy_in": 100, "energy_out": 50,
         "total": 3, "passed": 3, "failed": 0,
         "records": [{"id": "a"}]},
    )
    assert report.all_passed is True
    assert report.vetoed is False
    outputs = report.consensus_outputs()
    # Each validator is an independent source.
    assert len({o.source_id for o in outputs}) == len(outputs)
    decision = ConsensusEngine.decide(outputs)
    assert decision.status is ConsensusStatus.APPROVED
    assert decision.approve_mass > 0


def test_report_human_approval_and_serialisation():
    report = run_validators({"energy_in": 1, "energy_out": 10})
    assert report.requires_human_approval is True  # physics violation
    assert report.vetoed is True
    json.dumps(report.to_dict())


def test_run_validators_subset():
    report = run_validators({"code": "x=1"}, validators=["Compiler"])
    assert len(report.results) == 1
    assert report.results[0].validator == "Compiler"
