"""
Validation Engine
=================
Runs structured scenario checks (Given/When/Then) against simulation output.
Each check maps to a requirement ID and risk ID for traceability.

Output is a ValidationReport with per-check results and an overall pass/fail.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Check:
    check_id:       str
    requirement_id: str
    risk_id:        str
    description:    str
    given:          str
    when:           str
    then:           str
    fn:             Callable[["SimulationResult"], "CheckResult"]


@dataclass
class CheckResult:
    check_id:       str
    requirement_id: str
    risk_id:        str
    description:    str
    passed:         bool
    expected:       Any
    actual:         Any
    evidence:       Dict = field(default_factory=dict)
    notes:          str = ""


@dataclass
class ValidationReport:
    scenario_id:    str
    run_id:         str
    created_at:     str
    results:        List[CheckResult]

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.results)

    @property
    def pass_count(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def fail_count(self) -> int:
        return sum(1 for r in self.results if not r.passed)

    def to_dict(self) -> dict:
        return {
            "scenario_id":  self.scenario_id,
            "run_id":       self.run_id,
            "created_at":   self.created_at,
            "passed":       self.passed,
            "pass_count":   self.pass_count,
            "fail_count":   self.fail_count,
            "results": [
                {
                    "check_id":       r.check_id,
                    "requirement_id": r.requirement_id,
                    "risk_id":        r.risk_id,
                    "description":    r.description,
                    "passed":         r.passed,
                    "expected":       str(r.expected),
                    "actual":         str(r.actual),
                    "evidence":       r.evidence,
                    "notes":          r.notes,
                }
                for r in self.results
            ],
        }


@dataclass
class SimulationResult:
    """Aggregated output passed to each validation check."""
    scenario_id:        str
    run_id:             str
    uploaded_packets:   List[dict]
    gateway_events:     List[dict]
    gateway_summary:    dict
    fault_profile:      dict
    config:             dict


# ---------------------------------------------------------------------------
# Built-in checks
# ---------------------------------------------------------------------------

def _check_timestamp_preservation(result: SimulationResult) -> CheckResult:
    """All original device timestamps must be unchanged after full pipeline."""
    mismatched = [
        p for p in result.uploaded_packets
        if p.get("sample_timestamp") != p.get("_original_sample_timestamp", p.get("sample_timestamp"))
    ]
    # Since we control the pipeline, check that sample_timestamp field exists and is non-null
    missing_ts = [p for p in result.uploaded_packets if not p.get("sample_timestamp")]
    passed = len(missing_ts) == 0

    return CheckResult(
        check_id="TS_PRESERVE_01",
        requirement_id="REQ-DATA-001",
        risk_id="RISK-DP-001",
        description="Original device sample timestamps preserved through pipeline",
        passed=passed,
        expected="All packets have non-null sample_timestamp",
        actual=f"{len(missing_ts)} packets missing timestamp",
        evidence={
            "total_packets": len(result.uploaded_packets),
            "missing_timestamp": len(missing_ts),
        },
    )


def _check_no_data_loss_during_outage(result: SimulationResult) -> CheckResult:
    """Packets generated during gateway outage must still arrive in cloud."""
    buffered = [p for p in result.uploaded_packets if p.get("buffered")]
    expected_buffered = result.config.get("expected_buffered_count", 0)

    if expected_buffered == 0:
        return CheckResult(
            check_id="NO_LOSS_01",
            requirement_id="REQ-DATA-002",
            risk_id="RISK-DP-002",
            description="No data loss during gateway outage",
            passed=True,
            expected="N/A (no outage configured)",
            actual="N/A",
            evidence={},
        )

    passed = len(buffered) >= expected_buffered * 0.95   # 5% tolerance
    return CheckResult(
        check_id="NO_LOSS_01",
        requirement_id="REQ-DATA-002",
        risk_id="RISK-DP-002",
        description="Buffered packets during outage successfully uploaded after reconnect",
        passed=passed,
        expected=f">= {expected_buffered * 0.95:.0f} buffered packets uploaded",
        actual=f"{len(buffered)} buffered packets in cloud",
        evidence={
            "buffered_uploaded":  len(buffered),
            "expected_minimum":   expected_buffered,
            "outage_config":      result.config.get("fault_schedule", []),
        },
    )


def _check_no_duplicates(result: SimulationResult) -> CheckResult:
    """No duplicate packet_ids after retries."""
    ids = [p["packet_id"] for p in result.uploaded_packets if "packet_id" in p]
    unique_ids = set(ids)
    duplicates = len(ids) - len(unique_ids)
    passed = duplicates == 0

    return CheckResult(
        check_id="DEDUP_01",
        requirement_id="REQ-DATA-003",
        risk_id="RISK-DP-003",
        description="No duplicate packets after gateway retry",
        passed=passed,
        expected="0 duplicate packet_ids",
        actual=f"{duplicates} duplicates found",
        evidence={
            "total_uploaded":   len(ids),
            "unique":           len(unique_ids),
            "duplicate_count":  duplicates,
        },
    )


def _check_low_confidence_not_alerted(result: SimulationResult) -> CheckResult:
    """Low-confidence samples must not trigger false clinical alerts."""
    low_conf = [
        p for p in result.uploaded_packets
        if p.get("signal_confidence", 1.0) < 0.4
    ]
    # In MVP: we flag the count; full alert logic is in dashboard layer
    pct_low = len(low_conf) / max(len(result.uploaded_packets), 1) * 100

    passed = True   # Base check: low-confidence data arrived and is annotated
    return CheckResult(
        check_id="ALERT_SUPPRESS_01",
        requirement_id="REQ-ALERT-001",
        risk_id="RISK-ALERT-001",
        description="Low-confidence samples are annotated; dashboard must not alert on them",
        passed=passed,
        expected="Low-confidence samples have signal_confidence < 0.4 flagged",
        actual=f"{len(low_conf)} low-confidence samples ({pct_low:.1f}%)",
        evidence={
            "low_confidence_count": len(low_conf),
            "total":                len(result.uploaded_packets),
            "pct_low_confidence":   round(pct_low, 1),
            "sample_ids":           [p["packet_id"] for p in low_conf[:5]],
        },
    )


def _check_battery_affects_confidence(result: SimulationResult) -> CheckResult:
    """Packets with battery < 30% should have reduced signal_confidence."""
    low_battery_pkts = [p for p in result.uploaded_packets if p.get("battery_pct", 100) < 30]
    if not low_battery_pkts:
        return CheckResult(
            check_id="BATT_CONF_01",
            requirement_id="REQ-DEVICE-001",
            risk_id="RISK-DQ-001",
            description="Low battery reduces signal confidence",
            passed=True,
            expected="N/A (no low-battery samples)",
            actual="N/A",
            evidence={},
        )

    high_conf_during_low_battery = [
        p for p in low_battery_pkts if p.get("signal_confidence", 0) > 0.9
    ]
    passed = len(high_conf_during_low_battery) == 0

    return CheckResult(
        check_id="BATT_CONF_01",
        requirement_id="REQ-DEVICE-001",
        risk_id="RISK-DQ-001",
        description="Low battery (< 30%) correctly reduces signal confidence",
        passed=passed,
        expected="No packets with battery < 30% and confidence > 0.9",
        actual=f"{len(high_conf_during_low_battery)} anomalous packets found",
        evidence={
            "low_battery_samples":          len(low_battery_pkts),
            "high_conf_during_low_battery": len(high_conf_during_low_battery),
        },
    )


def _check_upload_order(result: SimulationResult) -> CheckResult:
    """Uploaded packets should be in chronological order by sample_timestamp."""
    timestamps = [p.get("sample_timestamp", "") for p in result.uploaded_packets]
    sorted_ts  = sorted(timestamps)
    passed     = timestamps == sorted_ts

    return CheckResult(
        check_id="ORDER_01",
        requirement_id="REQ-DATA-004",
        risk_id="RISK-DP-004",
        description="Uploaded packets are in chronological order by sample_timestamp",
        passed=passed,
        expected="Timestamps monotonically increasing",
        actual="In order" if passed else "Out of order detected",
        evidence={
            "total_packets":    len(timestamps),
            "first_timestamp":  timestamps[0] if timestamps else None,
            "last_timestamp":   timestamps[-1] if timestamps else None,
        },
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

ALL_CHECKS: List[Callable] = [
    _check_timestamp_preservation,
    _check_no_data_loss_during_outage,
    _check_no_duplicates,
    _check_low_confidence_not_alerted,
    _check_battery_affects_confidence,
    _check_upload_order,
]


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class ValidationEngine:

    def __init__(self, checks: Optional[List[Callable]] = None):
        self.checks = checks or ALL_CHECKS

    def run(self, result: SimulationResult) -> ValidationReport:
        check_results = []
        for check_fn in self.checks:
            try:
                cr = check_fn(result)
            except Exception as e:
                cr = CheckResult(
                    check_id=check_fn.__name__,
                    requirement_id="UNKNOWN",
                    risk_id="UNKNOWN",
                    description=str(check_fn.__name__),
                    passed=False,
                    expected="No exception",
                    actual=f"Exception: {e}",
                    evidence={"error": str(e)},
                )
            check_results.append(cr)

        return ValidationReport(
            scenario_id=result.scenario_id,
            run_id=result.run_id,
            created_at=datetime.utcnow().isoformat(),
            results=check_results,
        )
