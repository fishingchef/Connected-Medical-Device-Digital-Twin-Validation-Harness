"""
Physiology / Activity Generator
================================
Produces synthetic patient vital-sign time-series without full physiological
modeling. Designed to be realistic enough to exercise the downstream pipeline.

Output schema per sample:
    timestamp         ISO-8601 string (device local time)
    elapsed_sec       int — seconds since scenario start
    motion            float 0.0–1.0 (0=rest, 1=vigorous)
    hr_bpm            float — heart rate
    rr_rpm            float — respiratory rate
    temp_c            float — skin temperature
    signal_confidence float 0.0–1.0 — wearable's own quality estimate
    activity_label    str  — "rest" | "light" | "moderate" | "vigorous"
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Iterator, List

import numpy as np


# ---------------------------------------------------------------------------
# Activity profiles
# ---------------------------------------------------------------------------

ACTIVITY_PROFILES = {
    "rest": dict(
        motion_mean=0.02, motion_std=0.01,
        hr_base=62,  hr_std=2,  hr_motion_gain=0,
        rr_base=14,  rr_std=0.5,
        temp_base=36.6, temp_std=0.05,
        confidence_base=0.95,
    ),
    "light": dict(
        motion_mean=0.25, motion_std=0.05,
        hr_base=80,  hr_std=4,  hr_motion_gain=15,
        rr_base=16,  rr_std=1.0,
        temp_base=36.8, temp_std=0.1,
        confidence_base=0.85,
    ),
    "moderate": dict(
        motion_mean=0.55, motion_std=0.08,
        hr_base=110, hr_std=6,  hr_motion_gain=30,
        rr_base=22,  rr_std=2.0,
        temp_base=37.1, temp_std=0.15,
        confidence_base=0.70,
    ),
    "vigorous": dict(
        motion_mean=0.85, motion_std=0.07,
        hr_base=155, hr_std=8,  hr_motion_gain=40,
        rr_base=30,  rr_std=3.0,
        temp_base=37.5, temp_std=0.2,
        confidence_base=0.45,   # heavy motion → poor PPG signal
    ),
    "poor_contact": dict(
        motion_mean=0.10, motion_std=0.03,
        hr_base=70,  hr_std=15, hr_motion_gain=5,   # high variance = noisy
        rr_base=15,  rr_std=4.0,
        temp_base=35.5, temp_std=0.8,               # poor thermal contact
        confidence_base=0.20,
    ),
    "fever": dict(
        motion_mean=0.05, motion_std=0.02,
        hr_base=98,  hr_std=3,  hr_motion_gain=0,   # tachycardia at rest
        rr_base=20,  rr_std=1.5,
        temp_base=38.2, temp_std=0.1,               # fever baseline
        confidence_base=0.88,
    ),
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class PhysiologySample:
    timestamp: str
    elapsed_sec: int
    motion: float
    hr_bpm: float
    rr_rpm: float
    temp_c: float
    signal_confidence: float
    activity_label: str

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "elapsed_sec": self.elapsed_sec,
            "motion": round(self.motion, 4),
            "hr_bpm": round(self.hr_bpm, 1),
            "rr_rpm": round(self.rr_rpm, 1),
            "temp_c": round(self.temp_c, 2),
            "signal_confidence": round(self.signal_confidence, 3),
            "activity_label": self.activity_label,
        }


@dataclass
class ScenarioSegment:
    """One time window with a fixed activity profile."""
    activity: str          # key into ACTIVITY_PROFILES
    duration_minutes: int
    # optional overrides for fever ramp, etc.
    temp_ramp_per_min: float = 0.0   # e.g. 0.01 °C/min for gradual fever


@dataclass
class ScenarioConfig:
    start_time: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    sample_interval_sec: int = 60
    segments: List[ScenarioSegment] = field(default_factory=list)
    seed: int = 42


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

class PhysiologyGenerator:
    """
    Generates a synthetic vital-sign time-series from a ScenarioConfig.

    Usage:
        config = ScenarioConfig(segments=[
            ScenarioSegment("rest", 30),
            ScenarioSegment("vigorous", 20),
            ScenarioSegment("rest", 10),
        ])
        gen = PhysiologyGenerator(config)
        samples = list(gen.generate())
    """

    def __init__(self, config: ScenarioConfig):
        self.config = config
        self._rng = np.random.default_rng(config.seed)

    # ------------------------------------------------------------------
    def generate(self) -> Iterator[PhysiologySample]:
        elapsed = 0
        ts = self.config.start_time

        for seg in self.config.segments:
            profile = ACTIVITY_PROFILES[seg.activity]
            n_samples = (seg.duration_minutes * 60) // self.config.sample_interval_sec
            temp_offset = 0.0

            for i in range(n_samples):
                motion = float(np.clip(
                    self._rng.normal(profile["motion_mean"], profile["motion_std"]),
                    0.0, 1.0
                ))

                hr = float(self._rng.normal(
                    profile["hr_base"] + motion * profile["hr_motion_gain"],
                    profile["hr_std"]
                ))

                rr = float(self._rng.normal(profile["rr_base"], profile["rr_std"]))

                temp_offset += seg.temp_ramp_per_min * (self.config.sample_interval_sec / 60)
                temp = float(self._rng.normal(
                    profile["temp_base"] + temp_offset, profile["temp_std"]
                ))

                # Signal confidence degrades with motion, recovers with rest
                noise = float(self._rng.normal(0, 0.03))
                confidence = float(np.clip(
                    profile["confidence_base"] - 0.3 * motion + noise,
                    0.05, 1.0
                ))

                yield PhysiologySample(
                    timestamp=ts.isoformat(),
                    elapsed_sec=elapsed,
                    motion=motion,
                    hr_bpm=max(30, hr),
                    rr_rpm=max(4, rr),
                    temp_c=temp,
                    signal_confidence=confidence,
                    activity_label=seg.activity,
                )

                elapsed += self.config.sample_interval_sec
                ts += timedelta(seconds=self.config.sample_interval_sec)


# ---------------------------------------------------------------------------
# Pre-built named scenarios
# ---------------------------------------------------------------------------

def scenario_gateway_wifi_outage(start: datetime | None = None) -> ScenarioConfig:
    """
    2-hour rest session. Gateway outage min 40–60.
    Tests: data buffering, timestamp preservation, no duplicate on retry.
    """
    return ScenarioConfig(
        start_time=start or datetime.now(timezone.utc),
        sample_interval_sec=60,
        segments=[
            ScenarioSegment("rest", 39),
            ScenarioSegment("rest", 21),   # outage window — device keeps recording
            ScenarioSegment("rest", 60),
        ],
    )


def scenario_high_motion_degraded_signal(start: datetime | None = None) -> ScenarioConfig:
    """30 min high motion → low confidence HR/RR. Tests alert suppression."""
    return ScenarioConfig(
        start_time=start or datetime.now(timezone.utc),
        sample_interval_sec=60,
        segments=[
            ScenarioSegment("rest", 10),
            ScenarioSegment("vigorous", 30),
            ScenarioSegment("rest", 20),
        ],
    )


def scenario_fever_trend(start: datetime | None = None) -> ScenarioConfig:
    """Gradual fever over 90 min. Tests alert trigger at threshold."""
    return ScenarioConfig(
        start_time=start or datetime.now(timezone.utc),
        sample_interval_sec=60,
        segments=[
            ScenarioSegment("rest", 30),
            ScenarioSegment("fever", 60, temp_ramp_per_min=0.02),  # +1.2°C over 60 min
        ],
    )


def scenario_poor_contact(start: datetime | None = None) -> ScenarioConfig:
    """Poor sensor contact. Tests low-confidence data handling."""
    return ScenarioConfig(
        start_time=start or datetime.now(timezone.utc),
        sample_interval_sec=60,
        segments=[
            ScenarioSegment("rest", 15),
            ScenarioSegment("poor_contact", 30),
            ScenarioSegment("rest", 15),
        ],
    )


NAMED_SCENARIOS = {
    "GW_WIFI_OUTAGE_01": scenario_gateway_wifi_outage,
    "HIGH_MOTION_01": scenario_high_motion_degraded_signal,
    "FEVER_TREND_01": scenario_fever_trend,
    "POOR_CONTACT_01": scenario_poor_contact,
}
