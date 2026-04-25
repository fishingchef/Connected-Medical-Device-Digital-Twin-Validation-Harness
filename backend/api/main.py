"""
FastAPI — Connected Device Validation Harness
Supports both legacy fixed scenarios and the new scenario builder.
"""
from __future__ import annotations
import traceback, uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.models import IngestedPacket, SimulationRun, ValidationResult, create_tables, get_db
from core.generators.physiology import (
    NAMED_SCENARIOS, PhysiologyGenerator, ScenarioConfig, ScenarioSegment,
    NAMED_SCHEDULES, SUBJECT_PROFILES, PhysiologyEngine, DaySchedule
)
from core.simulators.wearable import WearableConfig, WearableSimulator, FirmwareVersion
from core.simulators.gateway import GatewayConfig, GatewaySimulator
from core.injectors.network import FAULT_PROFILES
from validation.engine import SimulationResult, ValidationEngine

app = FastAPI(title="Medical Device Digital Twin — Validation Harness", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

create_tables()


# ── Request model ─────────────────────────────────────────────────────────────

class RunScenarioRequest(BaseModel):
    # Legacy fixed scenario
    scenario_id:         str            = "GW_WIFI_OUTAGE_01"
    firmware_version:    str            = "1.2.0"
    initial_battery_pct: float          = 95.0
    ambient_temp_c:      float          = 22.0
    fault_profile:       str            = "clean"
    outage_start_min:    Optional[int]  = None
    outage_end_min:      Optional[int]  = None
    # Scenario builder fields
    subject_profile:     Optional[str]       = None
    day_schedule:        Optional[str]       = None
    duration_seconds:    Optional[int]       = None
    activity_profiles:   Optional[List[str]] = None
    wear_conditions:     Optional[List[str]] = None
    signal_profiles:     Optional[List[str]] = None
    network_conditions:  Optional[List[str]] = None
    behavior_checks:     Optional[List[str]] = None
    sync_interval_sec:   Optional[int]       = None  # BLE scan/upload interval override


# ── Scenario builder → physiology config mapper ───────────────────────────────

# Map activity profile IDs to physiology generator activity names
ACTIVITY_MAP = {
    "resting":       "rest",
    "walking":       "light",
    "sleeping":      "rest",
    "high_motion":   "vigorous",
    "mixed_daily":   "moderate",
    "clinical_rest": "rest",
}

# Map wear/contact conditions to confidence penalty + activity override
# Wear condition effects on FirmwareConfig and signal quality
# confidence_floor: minimum confidence regardless of activity (0=no floor, 0.6=capped at 60%)
# motion_artifact_threshold: lower = firmware rejects more samples as motion-corrupted
# hr_noise_multiplier: multiplies subject's hr_noise_std
# min_ppg_amplitude: raise threshold = firmware rejects weak signals
WEAR_CONDITION_MAP = {
    "normal": {
        "confidence_floor": 0.0, "motion_artifact_threshold": None,
        "min_ppg_amplitude": None, "hr_noise_multiplier": 1.0,
    },
    "low_adhesion": {
        "confidence_floor": 0.55, "motion_artifact_threshold": 0.3,
        "min_ppg_amplitude": 0.15, "hr_noise_multiplier": 2.5,
    },
    "intermittent": {
        "confidence_floor": 0.40, "motion_artifact_threshold": 0.25,
        "min_ppg_amplitude": 0.20, "hr_noise_multiplier": 3.0,
    },
    "perspiration": {
        "confidence_floor": 0.60, "motion_artifact_threshold": 0.40,
        "min_ppg_amplitude": 0.10, "hr_noise_multiplier": 1.8,
    },
    "poor_placement": {
        "confidence_floor": 0.45, "motion_artifact_threshold": 0.30,
        "min_ppg_amplitude": 0.18, "hr_noise_multiplier": 2.8,
    },
    "high_motion_artifact": {
        "confidence_floor": 0.30, "motion_artifact_threshold": 0.15,
        "min_ppg_amplitude": 0.05, "hr_noise_multiplier": 2.0,
    },
    "low_amplitude": {
        "confidence_floor": 0.25, "motion_artifact_threshold": 0.35,
        "min_ppg_amplitude": 0.30, "hr_noise_multiplier": 3.5,
    },
    "noisy_signal": {
        "confidence_floor": 0.35, "motion_artifact_threshold": 0.20,
        "min_ppg_amplitude": 0.12, "hr_noise_multiplier": 3.0,
    },
}

# Map signal profiles to scenario segments
SIGNAL_PROFILE_MAP = {
    "stable":         lambda dur: [ScenarioSegment("rest", max(1, dur // 60))],
    "hr_increase":    lambda dur: [ScenarioSegment("rest", max(1, dur // 120)), ScenarioSegment("moderate", max(1, dur // 120))],
    "temp_increase":  lambda dur: [ScenarioSegment("rest", max(1, dur // 60), temp_ramp_per_min=0.02)],
    "rr_spike":       lambda dur: [ScenarioSegment("rest", max(1, dur // 120)), ScenarioSegment("vigorous", max(1, min(5, dur // 60))), ScenarioSegment("rest", max(1, dur // 120))],
    "low_confidence": lambda dur: [ScenarioSegment("poor_contact", max(1, dur // 60))],
    "missing_vitals": lambda dur: [ScenarioSegment("poor_contact", max(1, dur // 60))],
    "out_of_range":   lambda dur: [ScenarioSegment("vigorous", max(1, dur // 60))],
}

# Map network conditions to fault schedule
NETWORK_CONDITION_MAP = {
    "normal_sync":     {"fault_profile": "clean",       "fault_schedule": []},
    "gateway_offline": {"fault_profile": "clean",       "fault_schedule": [(60, 300, "WIFI_DOWN")]},
    "wifi_outage":     {"fault_profile": "clean",       "fault_schedule": [(2400, 3600, "WIFI_DOWN")]},
    "ble_failure":     {"fault_profile": "flaky",       "fault_schedule": []},
    "delayed_upload":  {"fault_profile": "flaky",       "fault_schedule": []},
    "duplicate_retry": {"fault_profile": "flaky",       "fault_schedule": []},
    "out_of_order":    {"fault_profile": "lossy",       "fault_schedule": []},
    "auth_failure":    {"fault_profile": "tls_failure", "fault_schedule": []},
    "cloud_delay":          {"fault_profile": "flaky",       "fault_schedule": []},
    "intermittent_network": {"fault_profile": "flaky",       "fault_schedule": [
        (300,  600,  "WIFI_DOWN"),   # offline 5-10 min
        (1200, 1500, "WIFI_DOWN"),   # offline 20-25 min
        (2400, 2700, "WIFI_DOWN"),   # offline 40-45 min
    ]},
}


def build_scenario_from_request(req: RunScenarioRequest, ble_scan_interval: int = 60) -> tuple:
    """
    Translates scenario builder selections into simulation config objects.
    Uses the new PhysiologyEngine when subject_profile + day_schedule are provided.
    Returns: (samples, wearable_config, gateway_config, fault_profile, expected_buffered)
    """

    fw_map = {"1.0.0": FirmwareVersion.V1_0, "1.2.0": FirmwareVersion.V1_2, "2.0.0": FirmwareVersion.V2_0}
    fw = fw_map.get(req.firmware_version, FirmwareVersion.V1_2)

    # Apply wear condition effects to firmware config
    wear_conds   = req.wear_conditions or ["normal"]
    from core.simulators.wearable import FirmwareConfig, FIRMWARE_CONFIGS
    import copy
    fw_cfg = copy.deepcopy(FIRMWARE_CONFIGS.get(req.firmware_version, FIRMWARE_CONFIGS["1.2.0"]))

    for wc_id in wear_conds:
        wc = WEAR_CONDITION_MAP.get(wc_id, WEAR_CONDITION_MAP["normal"])
        # Lower motion artifact threshold = firmware flags more samples as corrupted
        if wc["motion_artifact_threshold"] is not None:
            fw_cfg.motion_artifact_threshold = min(
                fw_cfg.motion_artifact_threshold,
                wc["motion_artifact_threshold"]
            )
        # Raise min PPG amplitude = firmware rejects weaker signals
        if wc["min_ppg_amplitude"] is not None:
            fw_cfg.min_ppg_amplitude = max(
                fw_cfg.min_ppg_amplitude,
                wc["min_ppg_amplitude"]
            )
        # confidence_floor is applied in wearable via ambient_confidence_floor

    # Pick the worst (lowest) confidence floor across all selected wear conditions
    confidence_floor = max(
        wc_data["confidence_floor"]
        for wc_data in [WEAR_CONDITION_MAP.get(w, WEAR_CONDITION_MAP["normal"]) for w in wear_conds]
    )
    # Invert: floor=0.55 means confidence is CAPPED AT 0.55 max
    # Set as the base confidence by making motion_artifact_threshold very sensitive
    if confidence_floor > 0:
        # Clamp signal_confidence base in fw_cfg
        fw_cfg.motion_artifact_threshold = min(
            fw_cfg.motion_artifact_threshold,
            max(0.05, 1.0 - confidence_floor)
        )

    wearable_config = WearableConfig(
        firmware_version=fw,
        initial_battery_pct=req.initial_battery_pct,
        ambient_temp_c=req.ambient_temp_c,
        firmware_config_override=fw_cfg,
        confidence_floor=confidence_floor,
    )

    # ── Physiology: use new engine if subject+schedule provided ──
    # Default subject per schedule if not specified
    SCHEDULE_DEFAULT_SUBJECT = {
        "fever_progression":   "fever_patient",
        "clinical_monitoring": "clinical_patient",
        "sleep_study":         "healthy_adult_m",
        "exercise_session":    "athletic_m",
        "high_motion_wear":    "athletic_m",
        "typical_day":         "healthy_adult_m",
    }
    if req.subject_profile or req.day_schedule:
        sched_id   = req.day_schedule or "typical_day"
        default_subj = SCHEDULE_DEFAULT_SUBJECT.get(sched_id, "healthy_adult_m")
        subj_id    = req.subject_profile or default_subj
        subject    = SUBJECT_PROFILES.get(subj_id, list(SUBJECT_PROFILES.values())[0])
        sched_fn   = NAMED_SCHEDULES.get(sched_id, list(NAMED_SCHEDULES.values())[0])
        schedule   = sched_fn(subject=subject)
        engine     = PhysiologyEngine(schedule, seed=42)
        samples    = list(engine.generate())
    else:
        # Legacy path: build from signal profiles
        duration     = req.duration_seconds or 7200
        sig_profiles = req.signal_profiles  or ["stable"]
        sig_fn       = SIGNAL_PROFILE_MAP.get(sig_profiles[0], SIGNAL_PROFILE_MAP["stable"])
        segments     = sig_fn(duration)
        phys_config  = ScenarioConfig(sample_interval_sec=60, segments=segments)
        samples      = list(PhysiologyGenerator(phys_config).generate())

    # ── Network config ──
    net_conds        = req.network_conditions or ["normal_sync"]
    fault_schedule   = []
    fault_profile_id = "clean"
    for nc in net_conds:
        nc_cfg = NETWORK_CONDITION_MAP.get(nc, NETWORK_CONDITION_MAP["normal_sync"])
        fault_schedule.extend(nc_cfg["fault_schedule"])
        if nc_cfg["fault_profile"] != "clean":
            fault_profile_id = nc_cfg["fault_profile"]

    if req.outage_start_min is not None and req.outage_end_min is not None:
        fault_schedule = [(req.outage_start_min * 60, req.outage_end_min * 60, "WIFI_DOWN")]

    # Trim fault schedule to session length
    session_secs = len(samples) * 60
    fault_schedule = [(s, min(e, session_secs), t) for s, e, t in fault_schedule if s < session_secs]

    # Apply sync interval if specified
    gateway_config   = GatewayConfig(
        fault_schedule=fault_schedule,
        ble_scan_interval_sec=ble_scan_interval,
    )
    fault_prof       = FAULT_PROFILES.get(fault_profile_id, FAULT_PROFILES["clean"])
    expected_buffered = sum((e - s) // 60 for s, e, _ in fault_schedule)

    return samples, wearable_config, gateway_config, fault_prof, expected_buffered


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
def health():
    return {"status": "ok", "service": "meddevice-sim", "version": "0.2.0"}


@app.get("/api/scenarios")
def list_scenarios():
    return {"scenarios": [
        {"id": "GW_WIFI_OUTAGE_01",  "name": "Gateway Wi-Fi outage with delayed upload"},
        {"id": "HIGH_MOTION_01",     "name": "High motion — degraded signal"},
        {"id": "FEVER_TREND_01",     "name": "Fever trend"},
        {"id": "POOR_CONTACT_01",    "name": "Poor sensor contact"},
        {"id": "CUSTOM",             "name": "Custom scenario builder"},
    ]}


@app.post("/api/scenarios/run")
def run_scenario(req: RunScenarioRequest, db: Session = Depends(get_db)):
    try:
        run_id = f"RUN-{uuid.uuid4().hex[:12].upper()}"

        # Sync interval — defined early so both code paths can use it
        ble_scan_interval = req.sync_interval_sec or 60  # default 60s

        # Build config from builder or legacy scenario
        if req.scenario_id == "CUSTOM" or req.subject_profile or req.activity_profiles:
            samples, wearable_config, gateway_config, fault_prof, expected_buffered = \
                build_scenario_from_request(req, ble_scan_interval=ble_scan_interval)
        else:
            if req.scenario_id not in NAMED_SCENARIOS:
                raise HTTPException(404, f"Unknown scenario: {req.scenario_id}")
            phys_config = NAMED_SCENARIOS[req.scenario_id]()
            fw_map = {"1.0.0": FirmwareVersion.V1_0, "1.2.0": FirmwareVersion.V1_2, "2.0.0": FirmwareVersion.V2_0}
            wearable_config = WearableConfig(
                firmware_version=fw_map.get(req.firmware_version, FirmwareVersion.V1_2),
                initial_battery_pct=req.initial_battery_pct,
                ambient_temp_c=req.ambient_temp_c,
            )
            fault_schedule = []
            if req.outage_start_min is not None and req.outage_end_min is not None:
                fault_schedule = [(req.outage_start_min * 60, req.outage_end_min * 60, "WIFI_DOWN")]
            gateway_config    = GatewayConfig(fault_schedule=fault_schedule, ble_scan_interval_sec=ble_scan_interval)
            fault_prof        = FAULT_PROFILES.get(req.fault_profile, FAULT_PROFILES["clean"])
            expected_buffered = (fault_schedule[0][1] - fault_schedule[0][0]) // 60 if fault_schedule else 0
            samples = list(PhysiologyGenerator(phys_config).generate())

        wearable = WearableSimulator(wearable_config)
        gateway  = GatewaySimulator(gateway_config)

        uploaded_packets = []
        seen_ids = set()

        def upload_fn(packets):
            """
            Called by gateway to upload a batch. Always returns accepted=len(packets)
            so the gateway queue drains correctly. Deduplication is handled silently
            by the seen_ids set — duplicates are skipped in DB but not penalised.
            """
            now_str = datetime.now(timezone.utc).isoformat()
            for p in packets:
                uid = f"{run_id}-{p.packet_id}"
                if uid in seen_ids:
                    continue   # skip duplicate silently
                seen_ids.add(uid)
                p.received_at = now_str
                try:
                    s     = datetime.fromisoformat(p.sample_timestamp.replace("Z", "+00:00"))
                    r     = datetime.fromisoformat(now_str.replace("Z", "+00:00"))
                    delay = (r - s).total_seconds()
                except Exception:
                    delay = 0.0
                pd = p.to_dict()
                uploaded_packets.append(pd)
                db.add(IngestedPacket(
                    run_id=run_id, packet_id=uid,
                    device_id=pd["device_id"], firmware_version=pd["firmware_version"],
                    sample_timestamp=pd["sample_timestamp"], received_at=now_str,
                    elapsed_sec=pd["elapsed_sec"], motion=pd["motion"],
                    hr_bpm=pd["hr_bpm"], rr_rpm=pd["rr_rpm"], temp_c=pd["temp_c"],
                    signal_confidence=pd["signal_confidence"], activity_label=pd["activity_label"],
                    battery_pct=pd["battery_pct"], firmware_state=pd["firmware_state"],
                    ambient_temp_c=pd["ambient_temp_c"], ble_rssi_dbm=pd["ble_rssi_dbm"],
                    crc_ok=pd["crc_ok"], retry_count=pd["retry_count"], buffered=pd["buffered"],
                    duplicate=False, ingestion_delay_sec=delay,
                    hr_spike_rejected=pd.get("hr_spike_rejected", False),
                    motion_artifact_active=pd.get("motion_artifact_active", False),
                    alert_triggered=pd.get("alert_triggered", False),
                    alert_type=pd.get("alert_type"),
                    fw_config_snapshot=pd.get("fw_config_snapshot"),
                    gait_cadence=pd.get("gait_cadence"),
                    step_count=pd.get("step_count"),
                    sleep_stage=pd.get("sleep_stage"),
                    hour_of_day=pd.get("hour_of_day"),
                ))
            db.commit()
            # Always return full batch size so gateway queue drains correctly
            return {"success": True, "accepted": len(packets)}

        gw_summary = gateway.run_scenario(wearable, samples, upload_fn=upload_fn)

        sim_result = SimulationResult(
            scenario_id=req.scenario_id,
            run_id=run_id,
            uploaded_packets=uploaded_packets,
            gateway_events=gw_summary["events"],
            gateway_summary=gw_summary,
            fault_profile=fault_prof.__dict__,
            config={
                "fault_schedule":           gateway_config.fault_schedule,
                "expected_buffered_count":  expected_buffered,
                "firmware_version":         req.firmware_version,
                "ambient_temp_c":           req.ambient_temp_c,
                "activity_profiles":        req.activity_profiles,
                "wear_conditions":          req.wear_conditions,
                "network_conditions":       req.network_conditions,
                "duration_seconds":         req.duration_seconds,
                "sync_interval_sec":        ble_scan_interval,
            },
        )

        behavior_checks = req.behavior_checks or []
        min_expected    = max(1, len(samples) // 10)  # expect at least 10% data through
        sim_result.config["min_expected_packets"] = min_expected
        report = ValidationEngine(behavior_checks=behavior_checks or None).run(sim_result)

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
        return JSONResponse(status_code=200, content={
            "status":    "error",
            "error":     str(e),
            "traceback": traceback.format_exc(),
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
         "fw_config_snapshot": p.fw_config_snapshot,
         "gait_cadence": p.gait_cadence,
         "step_count": p.step_count,
         "sleep_stage": p.sleep_stage,
         "hour_of_day": p.hour_of_day}
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
