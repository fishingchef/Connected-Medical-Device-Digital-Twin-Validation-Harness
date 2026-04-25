"""
FastAPI Application — Connected Device Validation Harness
"""
from __future__ import annotations
import traceback
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.models import IngestedPacket, SimulationRun, ValidationResult, create_tables, get_db
from core.generators.physiology import NAMED_SCENARIOS, PhysiologyGenerator
from core.simulators.wearable import WearableConfig, WearableSimulator, FirmwareVersion
from core.simulators.gateway import GatewayConfig, GatewaySimulator
from core.injectors.network import FAULT_PROFILES, NetworkFaultInjector
from validation.engine import SimulationResult, ValidationEngine

app = FastAPI(
    title="Medical Device Digital Twin — Validation Harness",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

create_tables()


class RunScenarioRequest(BaseModel):
    scenario_id:         str   = "GW_WIFI_OUTAGE_01"
    firmware_version:    str   = "1.2.0"
    initial_battery_pct: float = 95.0
    ambient_temp_c:      float = 22.0
    fault_profile:       str   = "clean"
    outage_start_min:    Optional[int] = None
    outage_end_min:      Optional[int] = None


@app.get("/")
def health():
    return {"status": "ok", "service": "meddevice-sim", "version": "0.1.0"}


@app.get("/api/scenarios")
def list_scenarios():
    return {
        "scenarios": [
            {"id": "GW_WIFI_OUTAGE_01", "name": "Gateway Wi-Fi outage with delayed upload",
             "description": "2-hour rest session. Gateway offline min 40–60. Tests buffering, timestamp preservation, no duplicate on retry.",
             "risk": "RISK-DP-001, RISK-DP-002, RISK-DP-003"},
            {"id": "HIGH_MOTION_01", "name": "High motion — degraded signal",
             "description": "30 min vigorous activity. Tests low-confidence HR/RR handling and alert suppression.",
             "risk": "RISK-ALERT-001"},
            {"id": "FEVER_TREND_01", "name": "Fever trend",
             "description": "Gradual temp rise over 60 min. Tests threshold alert trigger.",
             "risk": "RISK-ALERT-002"},
            {"id": "POOR_CONTACT_01", "name": "Poor sensor contact",
             "description": "30 min poor contact. Tests low-confidence data annotation.",
             "risk": "RISK-DQ-001"},
        ]
    }


@app.get("/api/debug/run-test")
def debug_run_test(db: Session = Depends(get_db)):
    return {"status": "ok", "message": "use /api/scenarios/run via POST"}


@app.post("/api/scenarios/run")
def run_scenario(req: RunScenarioRequest, db: Session = Depends(get_db)):
    try:
        if req.scenario_id not in NAMED_SCENARIOS:
            raise HTTPException(404, f"Unknown scenario: {req.scenario_id}")

        run_id = f"RUN-{uuid.uuid4().hex[:12].upper()}"

        fw_map = {"1.0.0": FirmwareVersion.V1_0, "1.2.0": FirmwareVersion.V1_2, "2.0.0": FirmwareVersion.V2_0}
        fw = fw_map.get(req.firmware_version, FirmwareVersion.V1_2)

        phys_config = NAMED_SCENARIOS[req.scenario_id]()
        samples     = list(PhysiologyGenerator(phys_config).generate())

        wearable = WearableSimulator(WearableConfig(
            firmware_version=fw,
            initial_battery_pct=req.initial_battery_pct,
            ambient_temp_c=req.ambient_temp_c,
        ))

        fault_schedule = []
        if req.outage_start_min is not None and req.outage_end_min is not None:
            fault_schedule = [(req.outage_start_min * 60, req.outage_end_min * 60, "WIFI_DOWN")]
        elif req.fault_profile == "outage_20min":
            fault_schedule = [(2400, 3600, "WIFI_DOWN")]

        gateway    = GatewaySimulator(GatewayConfig(fault_schedule=fault_schedule))
        fault_prof = FAULT_PROFILES.get(req.fault_profile, FAULT_PROFILES["clean"])
        uploaded_packets = []

        def upload_fn(packets):
            now_str  = datetime.now(timezone.utc).isoformat()
            accepted = []
            seen     = set()
            for p in packets:
                if p.packet_id in seen:
                    continue
                seen.add(p.packet_id)
                p.received_at = now_str
                accepted.append(p)

            for p in accepted:
                pd = p.to_dict()
                try:
                    s = datetime.fromisoformat(pd["sample_timestamp"].replace("Z", "+00:00"))
                    r = datetime.fromisoformat(pd["received_at"].replace("Z", "+00:00"))
                    delay = (r - s).total_seconds()
                except Exception:
                    delay = 0.0

                unique_id = f"{run_id}-{pd['packet_id']}"
                row = IngestedPacket(
                    run_id                = run_id,
                    packet_id             = unique_id,
                    device_id             = pd["device_id"],
                    firmware_version      = pd["firmware_version"],
                    sample_timestamp      = pd["sample_timestamp"],
                    received_at           = pd["received_at"],
                    elapsed_sec           = pd["elapsed_sec"],
                    motion                = pd["motion"],
                    hr_bpm                = pd["hr_bpm"],
                    rr_rpm                = pd["rr_rpm"],
                    temp_c                = pd["temp_c"],
                    signal_confidence     = pd["signal_confidence"],
                    activity_label        = pd["activity_label"],
                    battery_pct           = pd["battery_pct"],
                    firmware_state        = pd["firmware_state"],
                    ambient_temp_c        = pd["ambient_temp_c"],
                    ble_rssi_dbm          = pd["ble_rssi_dbm"],
                    crc_ok                = pd["crc_ok"],
                    retry_count           = pd["retry_count"],
                    buffered              = pd["buffered"],
                    duplicate             = False,
                    ingestion_delay_sec   = delay,
                    hr_spike_rejected     = pd.get("hr_spike_rejected", False),
                    motion_artifact_active= pd.get("motion_artifact_active", False),
                    alert_triggered       = pd.get("alert_triggered", False),
                    alert_type            = pd.get("alert_type"),
                    fw_config_snapshot    = pd.get("fw_config_snapshot"),
                )
                db.add(row)
                uploaded_packets.append(pd)
            db.commit()
            return {"success": True, "accepted": len(accepted)}

        gw_summary = gateway.run_scenario(wearable, samples, upload_fn=upload_fn)

        interval          = getattr(phys_config, "sample_interval_sec", 60)
        expected_buffered = 0
        if fault_schedule:
            start_s, end_s, _ = fault_schedule[0]
            expected_buffered  = (end_s - start_s) // interval

        sim_result = SimulationResult(
            scenario_id=req.scenario_id,
            run_id=run_id,
            uploaded_packets=uploaded_packets,
            gateway_events=gw_summary["events"],
            gateway_summary=gw_summary,
            fault_profile=fault_prof.__dict__,
            config={
                "fault_schedule":          fault_schedule,
                "expected_buffered_count": expected_buffered,
                "firmware_version":        req.firmware_version,
                "ambient_temp_c":          req.ambient_temp_c,
            },
        )

        report = ValidationEngine().run(sim_result)

        for cr in report.results:
            db.add(ValidationResult(
                run_id=run_id, scenario_id=req.scenario_id,
                requirement_id=cr.requirement_id, risk_id=cr.risk_id,
                check_name=cr.check_id, expected=str(cr.expected),
                actual=str(cr.actual), passed=cr.passed, evidence=cr.evidence,
            ))

        db.add(SimulationRun(
            run_id=run_id, scenario_id=req.scenario_id, status="complete",
            config_json=req.model_dump(), summary_json=report.to_dict(),
        ))
        db.commit()

        return {
            "run_id":         run_id,
            "scenario_id":    req.scenario_id,
            "status":         "complete",
            "total_uploaded": len(uploaded_packets),
            "validation":     report.to_dict(),
            "gateway_events": gw_summary["events"][:20],
        }

    except Exception as e:
        db.rollback()
        error_detail = traceback.format_exc()
        # Return 200 with error info so CORS headers are included
        return JSONResponse(status_code=200, content={
            "status":    "error",
            "error":     str(e),
            "traceback": error_detail,
        })


@app.get("/api/runs")
def list_runs(db: Session = Depends(get_db)):
    runs = db.query(SimulationRun).order_by(SimulationRun.id.desc()).limit(20).all()
    return {"runs": [
        {"run_id": r.run_id, "scenario_id": r.scenario_id, "status": r.status,
         "created_at": r.created_at.isoformat() if r.created_at else None,
         "passed": r.summary_json.get("passed") if r.summary_json else None}
        for r in runs
    ]}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str, db: Session = Depends(get_db)):
    run = db.query(SimulationRun).filter(SimulationRun.run_id == run_id).first()
    if not run:
        raise HTTPException(404, "Run not found")
    return {"run_id": run.run_id, "scenario_id": run.scenario_id,
            "status": run.status, "created_at": run.created_at.isoformat() if run.created_at else None,
            "config": run.config_json, "summary": run.summary_json}


@app.get("/api/runs/{run_id}/packets")
def get_packets(run_id: str, limit: int = 200, db: Session = Depends(get_db)):
    pkts = db.query(IngestedPacket).filter(IngestedPacket.run_id == run_id)\
             .order_by(IngestedPacket.elapsed_sec).limit(limit).all()
    return {"run_id": run_id, "count": len(pkts), "packets": [
        {"packet_id": p.packet_id, "sample_timestamp": p.sample_timestamp,
         "elapsed_sec": p.elapsed_sec, "hr_bpm": p.hr_bpm, "rr_rpm": p.rr_rpm,
         "temp_c": p.temp_c, "signal_confidence": p.signal_confidence,
         "motion": p.motion, "activity_label": p.activity_label,
         "battery_pct": p.battery_pct, "buffered": p.buffered,
         "firmware_state": p.firmware_state, "ingestion_delay_sec": p.ingestion_delay_sec,
         "hr_spike_rejected": p.hr_spike_rejected,
         "motion_artifact_active": p.motion_artifact_active,
         "alert_triggered": p.alert_triggered, "alert_type": p.alert_type,
         "fw_config_snapshot": p.fw_config_snapshot}
        for p in pkts
    ]}


@app.get("/api/runs/{run_id}/report")
def get_report(run_id: str, db: Session = Depends(get_db)):
    results = db.query(ValidationResult).filter(ValidationResult.run_id == run_id).all()
    if not results:
        raise HTTPException(404, "No validation results for this run")
    return {"run_id": run_id, "passed": all(r.passed for r in results),
            "results": [{"check_name": r.check_name, "requirement_id": r.requirement_id,
                         "risk_id": r.risk_id, "passed": r.passed,
                         "expected": r.expected, "actual": r.actual, "evidence": r.evidence}
                        for r in results]}
