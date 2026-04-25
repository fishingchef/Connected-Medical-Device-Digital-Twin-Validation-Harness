"""
Synthetic Human Subject — Physiological Signal Generator
=========================================================
Models a coherent 24-hour person with coupled physiological signals.

Signals modeled:
  - Heart rate (HR)          — bpm
  - Respiratory rate (RR)    — rpm
  - Skin temperature (Temp)  — °C
  - Motion / acceleration    — g (0.0–1.0 normalized)
  - Gait cadence             — steps/min (0 when not walking)
  - Step count               — cumulative
  - Sleep stage              — AWAKE | LIGHT | DEEP | REM

Signal coupling:
  - HR rises with motion (linear), peaks in exercise
  - RR correlates with HR (HR/4 + noise)
  - Temp follows circadian rhythm + activity heat
  - Gait cadence drives step accumulation
  - Sleep stage modulates HR/RR baselines overnight
  - All signals have realistic noise + physiological drift

Architecture:
  SubjectProfile   — who the person is (age, fitness, baseline vitals)
  ActivityState    — what they are doing right now
  DaySchedule      — sequence of activity blocks over time
  PhysiologyEngine — tick-by-tick signal generator
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Iterator, List, Optional

import numpy as np


# ── Enums ─────────────────────────────────────────────────────────────────────

class ActivityState(str, Enum):
    SLEEPING_DEEP   = "sleeping_deep"
    SLEEPING_LIGHT  = "sleeping_light"
    SLEEPING_REM    = "sleeping_rem"
    LYING_AWAKE     = "lying_awake"
    RESTING_SITTING = "resting_sitting"
    STANDING        = "standing"
    WALKING_SLOW    = "walking_slow"
    WALKING_NORMAL  = "walking_normal"
    WALKING_FAST    = "walking_fast"
    JOGGING         = "jogging"
    RUNNING         = "running"
    CLIMBING_STAIRS = "climbing_stairs"
    CLINICAL_REST   = "clinical_rest"    # supine in bed, monitored


class SleepStage(str, Enum):
    AWAKE = "AWAKE"
    LIGHT = "LIGHT"
    DEEP  = "DEEP"
    REM   = "REM"


# ── Activity physiological parameters ─────────────────────────────────────────

@dataclass
class ActivityParams:
    """Physiological parameters for one activity state."""
    motion_mean:       float   # normalized 0–1
    motion_std:        float
    hr_above_rest:     float   # bpm above resting HR
    hr_std:            float
    rr_above_rest:     float   # rpm above resting RR
    rr_std:            float
    temp_above_base:   float   # °C above basal temp
    cadence_mean:      float   # steps/min (0 if not walking)
    cadence_std:       float
    signal_confidence: float   # base PPG quality (0–1)
    sleep_stage:       SleepStage = SleepStage.AWAKE


ACTIVITY_PARAMS: dict[ActivityState, ActivityParams] = {
    ActivityState.SLEEPING_DEEP: ActivityParams(
        motion_mean=0.01, motion_std=0.005,
        hr_above_rest=-8,  hr_std=1.5,
        rr_above_rest=-2,  rr_std=0.5,
        temp_above_base=-0.3, cadence_mean=0, cadence_std=0,
        signal_confidence=0.95, sleep_stage=SleepStage.DEEP,
    ),
    ActivityState.SLEEPING_LIGHT: ActivityParams(
        motion_mean=0.04, motion_std=0.02,
        hr_above_rest=-4,  hr_std=2.0,
        rr_above_rest=-1,  rr_std=0.8,
        temp_above_base=-0.2, cadence_mean=0, cadence_std=0,
        signal_confidence=0.92, sleep_stage=SleepStage.LIGHT,
    ),
    ActivityState.SLEEPING_REM: ActivityParams(
        motion_mean=0.02, motion_std=0.01,
        hr_above_rest=+2,  hr_std=4.0,   # REM HR is variable
        rr_above_rest=+1,  rr_std=2.0,
        temp_above_base=-0.1, cadence_mean=0, cadence_std=0,
        signal_confidence=0.93, sleep_stage=SleepStage.REM,
    ),
    ActivityState.LYING_AWAKE: ActivityParams(
        motion_mean=0.05, motion_std=0.02,
        hr_above_rest=+0,  hr_std=2.5,
        rr_above_rest=+0,  rr_std=0.8,
        temp_above_base=0.0, cadence_mean=0, cadence_std=0,
        signal_confidence=0.94,
    ),
    ActivityState.RESTING_SITTING: ActivityParams(
        motion_mean=0.06, motion_std=0.03,
        hr_above_rest=+3,  hr_std=3.0,
        rr_above_rest=+1,  rr_std=1.0,
        temp_above_base=0.0, cadence_mean=0, cadence_std=0,
        signal_confidence=0.93,
    ),
    ActivityState.STANDING: ActivityParams(
        motion_mean=0.10, motion_std=0.04,
        hr_above_rest=+8,  hr_std=3.5,
        rr_above_rest=+2,  rr_std=1.0,
        temp_above_base=0.1, cadence_mean=0, cadence_std=0,
        signal_confidence=0.90,
    ),
    ActivityState.WALKING_SLOW: ActivityParams(
        motion_mean=0.30, motion_std=0.06,
        hr_above_rest=+18, hr_std=4.0,
        rr_above_rest=+4,  rr_std=1.5,
        temp_above_base=0.2, cadence_mean=88,  cadence_std=6,
        signal_confidence=0.78,
    ),
    ActivityState.WALKING_NORMAL: ActivityParams(
        motion_mean=0.45, motion_std=0.07,
        hr_above_rest=+28, hr_std=5.0,
        rr_above_rest=+6,  rr_std=2.0,
        temp_above_base=0.3, cadence_mean=110, cadence_std=8,
        signal_confidence=0.68,
    ),
    ActivityState.WALKING_FAST: ActivityParams(
        motion_mean=0.60, motion_std=0.08,
        hr_above_rest=+42, hr_std=6.0,
        rr_above_rest=+9,  rr_std=2.5,
        temp_above_base=0.5, cadence_mean=130, cadence_std=10,
        signal_confidence=0.58,
    ),
    ActivityState.JOGGING: ActivityParams(
        motion_mean=0.72, motion_std=0.08,
        hr_above_rest=+68, hr_std=7.0,
        rr_above_rest=+14, rr_std=3.0,
        temp_above_base=0.9, cadence_mean=160, cadence_std=12,
        signal_confidence=0.45,
    ),
    ActivityState.RUNNING: ActivityParams(
        motion_mean=0.88, motion_std=0.06,
        hr_above_rest=+88, hr_std=8.0,
        rr_above_rest=+18, rr_std=3.5,
        temp_above_base=1.4, cadence_mean=185, cadence_std=14,
        signal_confidence=0.32,
    ),
    ActivityState.CLIMBING_STAIRS: ActivityParams(
        motion_mean=0.65, motion_std=0.10,
        hr_above_rest=+55, hr_std=7.0,
        rr_above_rest=+12, rr_std=3.0,
        temp_above_base=0.7, cadence_mean=100, cadence_std=15,
        signal_confidence=0.50,
    ),
    ActivityState.CLINICAL_REST: ActivityParams(
        motion_mean=0.02, motion_std=0.01,
        hr_above_rest=+0,  hr_std=2.0,
        rr_above_rest=+0,  rr_std=0.5,
        temp_above_base=0.0, cadence_mean=0, cadence_std=0,
        signal_confidence=0.97,
    ),
}


# ── Subject profile ────────────────────────────────────────────────────────────

@dataclass
class SubjectProfile:
    """
    Who the synthetic person is.
    Defines their baseline physiology which all signals are relative to.
    """
    subject_id:        str   = "SBJ-001"
    age:               int   = 35
    sex:               str   = "M"       # M | F
    weight_kg:         float = 78.0
    height_cm:         float = 178.0
    fitness_level:     str   = "moderate" # sedentary | moderate | athletic

    # Baseline vitals (resting, seated, 22°C, morning)
    hr_rest:           float = 65.0      # bpm
    rr_rest:           float = 14.0      # rpm
    temp_basal:        float = 36.6      # °C skin temperature
    hr_max:            float = 185.0     # bpm (220 - age approx)

    # Circadian parameters
    temp_circadian_amp: float = 0.4      # °C amplitude of circadian temp swing
    hr_circadian_amp:   float = 5.0      # bpm amplitude of circadian HR swing

    # Physiological variability
    hr_noise_std:      float = 1.5       # beat-to-beat noise
    rr_noise_std:      float = 0.6
    temp_noise_std:    float = 0.04

    def __post_init__(self):
        # Adjust baselines by fitness level
        if self.fitness_level == "athletic":
            self.hr_rest       = max(45, self.hr_rest - 12)
            self.hr_max        = 195.0
            self.temp_basal   -= 0.1
        elif self.fitness_level == "sedentary":
            self.hr_rest       = min(80, self.hr_rest + 8)
            self.hr_max        = 175.0

        # Adjust by age
        self.hr_max = max(150, 220 - self.age)

        # Sex-based adjustments
        if self.sex == "F":
            self.hr_rest  += 3
            self.temp_basal += 0.1


# Pre-built subject profiles
SUBJECT_PROFILES = {
    "healthy_adult_m": SubjectProfile(
        subject_id="SBJ-001", age=35, sex="M",
        fitness_level="moderate",
    ),
    "healthy_adult_f": SubjectProfile(
        subject_id="SBJ-002", age=32, sex="F",
        fitness_level="moderate",
        hr_rest=68, temp_basal=36.7,
    ),
    "athletic_m": SubjectProfile(
        subject_id="SBJ-003", age=28, sex="M",
        fitness_level="athletic",
        hr_rest=52, hr_max=195,
    ),
    "elderly_f": SubjectProfile(
        subject_id="SBJ-004", age=72, sex="F",
        fitness_level="sedentary",
        hr_rest=74, temp_basal=36.4,
        hr_circadian_amp=3.0,
    ),
    "clinical_patient": SubjectProfile(
        subject_id="SBJ-005", age=58, sex="M",
        fitness_level="sedentary",
        hr_rest=78, temp_basal=37.2,   # slightly elevated baseline
        hr_noise_std=3.0,              # more variability
    ),
    "fever_patient": SubjectProfile(
        subject_id="SBJ-006", age=34, sex="F",
        fitness_level="moderate",
        hr_rest=90,                    # tachycardia from fever
        temp_basal=38.4,               # febrile baseline
        rr_rest=20,                    # tachypnea
    ),
}


# ── Activity schedule block ────────────────────────────────────────────────────

@dataclass
class ScheduleBlock:
    """One continuous period of a single activity."""
    activity:         ActivityState
    duration_minutes: int
    # Optional physiological modifiers for this block
    temp_ramp_per_min:  float = 0.0     # gradual temp change (fever, exercise warmup)
    hr_ramp_per_min:    float = 0.0     # gradual HR change (fatigue, medication)
    label:              str   = ""      # human-readable label for reports


@dataclass
class DaySchedule:
    """
    Full sequence of activity blocks describing a subject's day.
    Total duration = sum of all block durations.
    """
    subject_profile:    SubjectProfile
    blocks:             List[ScheduleBlock]
    start_time:         datetime = field(
        default_factory=lambda: datetime.now(timezone.utc).replace(
            hour=22, minute=0, second=0, microsecond=0
        )
    )
    sample_interval_sec: int = 60


# ── Sample output ──────────────────────────────────────────────────────────────

@dataclass
class PhysiologySample:
    """One time-point of physiological data from the subject."""
    timestamp:          str
    elapsed_sec:        int
    # Core vitals
    hr_bpm:             float
    rr_rpm:             float
    temp_c:             float
    # Motion
    motion:             float       # normalized 0–1
    gait_cadence:       float       # steps/min
    step_count:         int         # cumulative
    # State
    activity:           str
    sleep_stage:        str
    signal_confidence:  float
    # Circadian context
    hour_of_day:        float       # 0–24 float

    def to_dict(self) -> dict:
        return {
            "timestamp":         self.timestamp,
            "elapsed_sec":       self.elapsed_sec,
            "hr_bpm":            round(self.hr_bpm, 1),
            "rr_rpm":            round(self.rr_rpm, 1),
            "temp_c":            round(self.temp_c, 2),
            "motion":            round(self.motion, 4),
            "gait_cadence":      round(self.gait_cadence, 1),
            "step_count":        self.step_count,
            "activity":          self.activity,
            "sleep_stage":       self.sleep_stage,
            "signal_confidence": round(self.signal_confidence, 3),
            "hour_of_day":       round(self.hour_of_day, 2),
        }


# ── Physiology engine ──────────────────────────────────────────────────────────

class PhysiologyEngine:
    """
    Generates a coherent physiological time-series from a DaySchedule.

    Signal coupling model:
      HR  = hr_rest + circadian(t) + activity_delta + hr_ramp + noise
      RR  = rr_rest + 0.18 * (HR - hr_rest) + activity_delta + noise
      Temp= temp_basal + circadian(t) + activity_heat + temp_ramp + noise
      Motion = activity_mean + noise
      Cadence= activity_cadence + noise (0 if not ambulating)
      Steps  = cumulative cadence * interval / 60
    """

    def __init__(self, schedule: DaySchedule, seed: int = 42):
        self.schedule = schedule
        self.rng      = np.random.default_rng(seed)
        self._steps   = 0

    def generate(self) -> Iterator[PhysiologySample]:
        subj     = self.schedule.subject_profile
        ts       = self.schedule.start_time
        elapsed  = 0
        interval = self.schedule.sample_interval_sec

        for block in self.schedule.blocks:
            params    = ACTIVITY_PARAMS[block.activity]
            n_samples = max(1, (block.duration_minutes * 60) // interval)
            temp_offset = 0.0
            hr_offset   = 0.0

            for i in range(n_samples):
                hour = (ts.hour + ts.minute / 60 + ts.second / 3600) % 24

                # ── Circadian modulation ──────────────────────────────────
                # Temp: nadir ~4am, peak ~6pm
                circ_temp = subj.temp_circadian_amp * math.sin(
                    2 * math.pi * (hour - 4) / 24
                )
                # HR: slightly elevated in afternoon
                circ_hr = subj.hr_circadian_amp * math.sin(
                    2 * math.pi * (hour - 6) / 24
                )

                # ── Ramps (fever, fatigue, exercise warmup) ───────────────
                temp_offset += block.temp_ramp_per_min * (interval / 60)
                hr_offset   += block.hr_ramp_per_min   * (interval / 60)

                # ── Motion ───────────────────────────────────────────────
                motion = float(np.clip(
                    self.rng.normal(params.motion_mean, params.motion_std),
                    0.0, 1.0
                ))

                # ── Heart rate ────────────────────────────────────────────
                hr_target = (
                    subj.hr_rest
                    + circ_hr
                    + params.hr_above_rest
                    + hr_offset
                    + motion * 15   # extra motion coupling
                )
                hr_target = np.clip(hr_target, 30, subj.hr_max)
                hr = float(self.rng.normal(hr_target, params.hr_std + subj.hr_noise_std))
                hr = float(np.clip(hr, 25, subj.hr_max))

                # ── Respiratory rate ──────────────────────────────────────
                # Coupled to HR: higher HR → higher RR
                rr_from_hr = 0.18 * max(0, hr - subj.hr_rest)
                rr_target  = subj.rr_rest + params.rr_above_rest + rr_from_hr
                rr = float(self.rng.normal(rr_target, params.rr_std + subj.rr_noise_std))
                rr = float(np.clip(rr, 4, 60))

                # ── Temperature ───────────────────────────────────────────
                temp_target = (
                    subj.temp_basal
                    + circ_temp
                    + params.temp_above_base
                    + temp_offset
                )
                temp = float(self.rng.normal(temp_target, subj.temp_noise_std))
                temp = float(np.clip(temp, 34.0, 42.0))

                # ── Gait + steps ──────────────────────────────────────────
                if params.cadence_mean > 0:
                    cadence = float(np.clip(
                        self.rng.normal(params.cadence_mean, params.cadence_std),
                        0, 220
                    ))
                    new_steps = int(cadence * interval / 60)
                else:
                    cadence   = 0.0
                    new_steps = 0
                self._steps += new_steps

                # ── Signal confidence ─────────────────────────────────────
                # Degrades with motion, recovers at rest
                conf_motion_penalty = 0.45 * motion
                confidence = float(np.clip(
                    params.signal_confidence
                    - conf_motion_penalty
                    + self.rng.normal(0, 0.02),
                    0.05, 1.0
                ))

                yield PhysiologySample(
                    timestamp          = ts.isoformat(),
                    elapsed_sec        = elapsed,
                    hr_bpm             = round(hr,   1),
                    rr_rpm             = round(rr,   1),
                    temp_c             = round(temp, 2),
                    motion             = round(motion, 4),
                    gait_cadence       = round(cadence, 1),
                    step_count         = self._steps,
                    activity           = block.activity.value,
                    sleep_stage        = params.sleep_stage.value,
                    signal_confidence  = round(confidence, 3),
                    hour_of_day        = round(hour, 2),
                )

                elapsed += interval
                ts      += timedelta(seconds=interval)


# ── Pre-built day schedules ────────────────────────────────────────────────────

def schedule_typical_day(
    subject: Optional[SubjectProfile] = None,
    start_time: Optional[datetime] = None,
) -> DaySchedule:
    """
    Typical 24h day: sleep → morning routine → work → evening → sleep.
    Start time: 10pm (beginning of overnight sleep period).
    """
    subj = subject or SUBJECT_PROFILES["healthy_adult_m"]
    return DaySchedule(
        subject_profile=subj,
        start_time=start_time or datetime.now(timezone.utc).replace(hour=22, minute=0, second=0, microsecond=0),
        sample_interval_sec=60,
        blocks=[
            # Night sleep (10pm–6am = 8h)
            ScheduleBlock(ActivityState.SLEEPING_LIGHT,  30, label="sleep_onset"),
            ScheduleBlock(ActivityState.SLEEPING_DEEP,   90, label="deep_sleep_1"),
            ScheduleBlock(ActivityState.SLEEPING_REM,    30, label="rem_1"),
            ScheduleBlock(ActivityState.SLEEPING_DEEP,   60, label="deep_sleep_2"),
            ScheduleBlock(ActivityState.SLEEPING_REM,    45, label="rem_2"),
            ScheduleBlock(ActivityState.SLEEPING_LIGHT,  30, label="light_sleep"),
            ScheduleBlock(ActivityState.SLEEPING_REM,    30, label="rem_3"),
            ScheduleBlock(ActivityState.SLEEPING_LIGHT,  45, label="wake_transition"),
            ScheduleBlock(ActivityState.LYING_AWAKE,     20, label="waking_up"),
            # Morning (6–9am)
            ScheduleBlock(ActivityState.RESTING_SITTING, 20, label="breakfast"),
            ScheduleBlock(ActivityState.WALKING_NORMAL,  15, label="morning_walk"),
            ScheduleBlock(ActivityState.CLIMBING_STAIRS, 5,  label="stairs"),
            ScheduleBlock(ActivityState.RESTING_SITTING, 40, label="commute_sit"),
            # Work morning (9am–12pm)
            ScheduleBlock(ActivityState.RESTING_SITTING, 90, label="desk_work_am"),
            ScheduleBlock(ActivityState.STANDING,        15, label="standing_meeting"),
            ScheduleBlock(ActivityState.WALKING_SLOW,    15, label="coffee_walk"),
            # Lunch (12–1pm)
            ScheduleBlock(ActivityState.WALKING_NORMAL,  10, label="walk_to_lunch"),
            ScheduleBlock(ActivityState.RESTING_SITTING, 30, label="lunch"),
            ScheduleBlock(ActivityState.WALKING_NORMAL,  10, label="post_lunch_walk"),
            # Work afternoon (1–5pm)
            ScheduleBlock(ActivityState.RESTING_SITTING, 90, label="desk_work_pm"),
            ScheduleBlock(ActivityState.WALKING_SLOW,    10, label="afternoon_break"),
            ScheduleBlock(ActivityState.RESTING_SITTING, 50, label="desk_work_end"),
            # Evening exercise (5–6pm)
            ScheduleBlock(ActivityState.WALKING_FAST,    10, label="warmup_walk"),
            ScheduleBlock(ActivityState.JOGGING,         25, label="jog"),
            ScheduleBlock(ActivityState.WALKING_SLOW,    10, label="cooldown"),
            # Evening (6–10pm)
            ScheduleBlock(ActivityState.RESTING_SITTING, 30, label="dinner"),
            ScheduleBlock(ActivityState.RESTING_SITTING, 90, label="evening_relax"),
            ScheduleBlock(ActivityState.LYING_AWAKE,     30, label="pre_sleep"),
        ],
    )


def schedule_clinical_monitoring(
    subject: Optional[SubjectProfile] = None,
    duration_hours: int = 24,
    start_time: Optional[datetime] = None,
) -> DaySchedule:
    """Patient in hospital bed — minimal activity, continuous monitoring."""
    subj = subject or SUBJECT_PROFILES["clinical_patient"]
    blocks = [
        ScheduleBlock(ActivityState.CLINICAL_REST, 120, label="baseline"),
        ScheduleBlock(ActivityState.LYING_AWAKE,    20, label="vitals_check"),
        ScheduleBlock(ActivityState.CLINICAL_REST,  60, label="post_check"),
        ScheduleBlock(ActivityState.SLEEPING_LIGHT, 60, label="nap"),
        ScheduleBlock(ActivityState.CLINICAL_REST,  80, label="afternoon"),
        ScheduleBlock(ActivityState.LYING_AWAKE,    20, label="meal"),
        ScheduleBlock(ActivityState.SLEEPING_DEEP,  60, label="evening_sleep"),
    ] * max(1, duration_hours // 8)
    return DaySchedule(
        subject_profile=subj,
        start_time=start_time or datetime.now(timezone.utc),
        sample_interval_sec=60,
        blocks=blocks[:duration_hours * 60 // 10],  # approximate
    )


def schedule_fever_progression(
    subject: Optional[SubjectProfile] = None,
    start_time: Optional[datetime] = None,
) -> DaySchedule:
    """Subject developing fever over 8 hours."""
    subj = subject or SUBJECT_PROFILES["fever_patient"]
    return DaySchedule(
        subject_profile=subj,
        start_time=start_time or datetime.now(timezone.utc),
        sample_interval_sec=60,
        blocks=[
            ScheduleBlock(ActivityState.RESTING_SITTING, 60, label="pre_fever_normal"),
            ScheduleBlock(ActivityState.LYING_AWAKE,     60, temp_ramp_per_min=0.008, label="fever_onset"),
            ScheduleBlock(ActivityState.LYING_AWAKE,     60, temp_ramp_per_min=0.012, hr_ramp_per_min=0.3, label="fever_rising"),
            ScheduleBlock(ActivityState.CLINICAL_REST,   60, temp_ramp_per_min=0.005, label="fever_plateau"),
            ScheduleBlock(ActivityState.SLEEPING_LIGHT,  60, temp_ramp_per_min=-0.01, label="fever_breaking"),
        ],
    )


def schedule_sleep_study(
    subject: Optional[SubjectProfile] = None,
    start_time: Optional[datetime] = None,
) -> DaySchedule:
    """8-hour sleep study with full sleep architecture."""
    subj = subject or SUBJECT_PROFILES["healthy_adult_m"]
    return DaySchedule(
        subject_profile=subj,
        start_time=start_time or datetime.now(timezone.utc).replace(hour=23, minute=0, second=0, microsecond=0),
        sample_interval_sec=60,
        blocks=[
            ScheduleBlock(ActivityState.LYING_AWAKE,     15, label="pre_sleep"),
            ScheduleBlock(ActivityState.SLEEPING_LIGHT,  25, label="n1_n2"),
            ScheduleBlock(ActivityState.SLEEPING_DEEP,   60, label="n3_first"),
            ScheduleBlock(ActivityState.SLEEPING_REM,    20, label="rem_1"),
            ScheduleBlock(ActivityState.SLEEPING_LIGHT,  30, label="n2_cycle2"),
            ScheduleBlock(ActivityState.SLEEPING_DEEP,   45, label="n3_second"),
            ScheduleBlock(ActivityState.SLEEPING_REM,    30, label="rem_2"),
            ScheduleBlock(ActivityState.SLEEPING_LIGHT,  25, label="n2_cycle3"),
            ScheduleBlock(ActivityState.SLEEPING_REM,    40, label="rem_3"),
            ScheduleBlock(ActivityState.SLEEPING_LIGHT,  20, label="n2_cycle4"),
            ScheduleBlock(ActivityState.SLEEPING_REM,    45, label="rem_4"),
            ScheduleBlock(ActivityState.LYING_AWAKE,     25, label="wake"),
        ],
    )


def schedule_exercise_session(
    subject: Optional[SubjectProfile] = None,
    start_time: Optional[datetime] = None,
) -> DaySchedule:
    """60-minute exercise session with warmup, peak, and cooldown."""
    subj = subject or SUBJECT_PROFILES["athletic_m"]
    return DaySchedule(
        subject_profile=subj,
        start_time=start_time or datetime.now(timezone.utc),
        sample_interval_sec=60,
        blocks=[
            ScheduleBlock(ActivityState.RESTING_SITTING, 5,  label="pre_exercise"),
            ScheduleBlock(ActivityState.WALKING_SLOW,    5,  label="warmup_walk"),
            ScheduleBlock(ActivityState.WALKING_FAST,    5,  label="warmup_fast"),
            ScheduleBlock(ActivityState.JOGGING,         10, label="jog_buildup"),
            ScheduleBlock(ActivityState.RUNNING,         20, label="peak_run"),
            ScheduleBlock(ActivityState.JOGGING,         10, label="jog_down"),
            ScheduleBlock(ActivityState.WALKING_NORMAL,  5,  label="cooldown_walk"),
        ],
    )


def schedule_high_motion_wear(
    subject: Optional[SubjectProfile] = None,
    start_time: Optional[datetime] = None,
) -> DaySchedule:
    """Tests device signal quality under high motion conditions."""
    subj = subject or SUBJECT_PROFILES["athletic_m"]
    return DaySchedule(
        subject_profile=subj,
        start_time=start_time or datetime.now(timezone.utc),
        sample_interval_sec=60,
        blocks=[
            ScheduleBlock(ActivityState.RESTING_SITTING, 10, label="baseline"),
            ScheduleBlock(ActivityState.WALKING_NORMAL,  10, label="walk"),
            ScheduleBlock(ActivityState.CLIMBING_STAIRS, 5,  label="stairs"),
            ScheduleBlock(ActivityState.RUNNING,         15, label="run"),
            ScheduleBlock(ActivityState.WALKING_SLOW,    5,  label="recovery_walk"),
            ScheduleBlock(ActivityState.RESTING_SITTING, 10, label="recovery_rest"),
        ],
    )


# ── Named schedules registry ───────────────────────────────────────────────────

NAMED_SCHEDULES = {
    "typical_day":          schedule_typical_day,
    "clinical_monitoring":  schedule_clinical_monitoring,
    "fever_progression":    schedule_fever_progression,
    "sleep_study":          schedule_sleep_study,
    "exercise_session":     schedule_exercise_session,
    "high_motion_wear":     schedule_high_motion_wear,
}


# ── Legacy compatibility shim ──────────────────────────────────────────────────
# Keep NAMED_SCENARIOS working so main.py doesn't break

@dataclass
class ScenarioSegment:
    activity:          str
    duration_minutes:  int
    temp_ramp_per_min: float = 0.0


@dataclass
class ScenarioConfig:
    sample_interval_sec: int = 60
    segments:            List[ScenarioSegment] = field(default_factory=list)
    start_time:          datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    seed:                int = 42


class PhysiologyGenerator:
    """Legacy wrapper — converts old ScenarioConfig to new PhysiologyEngine."""

    # Map old activity names to new ActivityState
    ACTIVITY_REMAP = {
        "rest":         ActivityState.RESTING_SITTING,
        "light":        ActivityState.WALKING_SLOW,
        "moderate":     ActivityState.WALKING_NORMAL,
        "vigorous":     ActivityState.RUNNING,
        "poor_contact": ActivityState.RESTING_SITTING,
        "fever":        ActivityState.LYING_AWAKE,
    }

    def __init__(self, config: ScenarioConfig):
        self.config = config

    def generate(self) -> Iterator[PhysiologySample]:
        subj = SUBJECT_PROFILES["healthy_adult_m"]
        blocks = []
        for seg in self.config.segments:
            activity = self.ACTIVITY_REMAP.get(seg.activity, ActivityState.RESTING_SITTING)
            blocks.append(ScheduleBlock(
                activity=activity,
                duration_minutes=max(1, seg.duration_minutes),
                temp_ramp_per_min=seg.temp_ramp_per_min,
            ))

        if not blocks:
            blocks = [ScheduleBlock(ActivityState.RESTING_SITTING, 60)]

        schedule = DaySchedule(
            subject_profile=subj,
            start_time=self.config.start_time,
            sample_interval_sec=self.config.sample_interval_sec,
            blocks=blocks,
        )
        engine = PhysiologyEngine(schedule, seed=self.config.seed)
        yield from engine.generate()


def _make_legacy_scenario(blocks):
    def factory(start=None):
        cfg = ScenarioConfig(
            sample_interval_sec=60,
            segments=blocks,
            start_time=start or datetime.now(timezone.utc),
        )
        return cfg
    return factory


NAMED_SCENARIOS = {
    "GW_WIFI_OUTAGE_01": _make_legacy_scenario([
        ScenarioSegment("rest", 39),
        ScenarioSegment("rest", 21),
        ScenarioSegment("rest", 60),
    ]),
    "HIGH_MOTION_01": _make_legacy_scenario([
        ScenarioSegment("rest", 10),
        ScenarioSegment("vigorous", 30),
        ScenarioSegment("rest", 20),
    ]),
    "FEVER_TREND_01": _make_legacy_scenario([
        ScenarioSegment("rest", 30),
        ScenarioSegment("fever", 60, temp_ramp_per_min=0.02),
    ]),
    "POOR_CONTACT_01": _make_legacy_scenario([
        ScenarioSegment("rest", 15),
        ScenarioSegment("poor_contact", 30),
        ScenarioSegment("rest", 15),
    ]),
}
