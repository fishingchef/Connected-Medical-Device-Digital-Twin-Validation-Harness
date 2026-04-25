"""
Wearable Device Simulator
==========================
Two layers of configurability:
  1. FirmwareConfig  — internal algorithm parameters (sample rates, moving
                       average windows, alert thresholds, spike rejection).
                       Same hardware + different FirmwareConfig = different output.
  2. WearableConfig  — physical/deployment config (device ID, battery, ambient temp).

Firmware states: IDLE | SAMPLING | STORING | BLE_ADVERT | BLE_CONNECT | LOW_BATTERY | FAULT
"""

from __future__ import annotations
import random, uuid
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Deque, List, Optional
from core.generators.physiology import PhysiologySample


class FirmwareState(str, Enum):
    IDLE        = "IDLE"
    SAMPLING    = "SAMPLING"
    STORING     = "STORING"
    BLE_ADVERT  = "BLE_ADVERT"
    BLE_CONNECT = "BLE_CONNECT"
    LOW_BATTERY = "LOW_BATTERY"
    FAULT       = "FAULT"


class FirmwareVersion(str, Enum):
    V1_0 = "1.0.0"
    V1_2 = "1.2.0"
    V2_0 = "2.0.0"


BATTERY_DRAIN = {
    FirmwareState.IDLE: 0.5, FirmwareState.SAMPLING: 2.0,
    FirmwareState.STORING: 2.5, FirmwareState.BLE_ADVERT: 3.0,
    FirmwareState.BLE_CONNECT: 4.5, FirmwareState.LOW_BATTERY: 1.2,
    FirmwareState.FAULT: 0.3,
}

LOW_BATTERY_THRESHOLD      = 15.0
CRITICAL_BATTERY_THRESHOLD = 5.0
LOCAL_BUFFER_MAX           = 2880


@dataclass
class FirmwareConfig:
    """
    Internal firmware algorithm parameters — stored in device NVM.
    These directly affect what data gets reported to the cloud.
    """
    # Sampling & reporting
    hr_sample_rate_hz:          float = 25.0
    rr_sample_rate_hz:          float = 25.0
    temp_sample_rate_hz:        float = 1.0
    report_interval_sec:        int   = 60

    # Signal processing
    hr_moving_avg_window:       int   = 8      # larger = smoother but more lag
    rr_moving_avg_window:       int   = 6
    motion_artifact_threshold:  float = 0.60   # motion above this -> flag HR/RR unreliable
    hr_spike_rejection_pct:     float = 0.20   # reject HR deviating >N% from rolling mean
    min_ppg_amplitude:          float = 0.05   # min signal to attempt HR calc
    rr_algorithm:               str   = "peak_detection"  # peak_detection | impedance | fusion

    # Clinical alert thresholds (device-side, fires before cloud)
    hr_alert_low:               float = 45.0
    hr_alert_high:              float = 130.0
    rr_alert_low:               float = 8.0
    rr_alert_high:              float = 30.0
    temp_alert_low:             float = 35.0
    temp_alert_high:            float = 38.5
    low_confidence_threshold:   float = 0.40   # below this -> suppress device alert

    # Power management
    low_battery_sample_divisor: int   = 2
    ble_tx_power_dbm:           int   = 0
    watchdog_timeout_sec:       int   = 300

    # Data encoding
    hr_precision_decimals:      int   = 1
    temp_precision_decimals:    int   = 2
    enable_delta_encoding:      bool  = False
    enable_rle_compression:     bool  = False

    def to_dict(self) -> dict:
        return self.__dict__.copy()


FIRMWARE_CONFIGS: dict[str, FirmwareConfig] = {
    "1.0.0": FirmwareConfig(
        hr_moving_avg_window=4, rr_moving_avg_window=4,
        motion_artifact_threshold=0.85,   # permissive — passes motion-corrupted data
        hr_spike_rejection_pct=0.0,       # no spike rejection
        min_ppg_amplitude=0.02,
        low_confidence_threshold=0.20,    # may alert on poor-quality data
        rr_algorithm="peak_detection",
        ble_tx_power_dbm=-4,
        temp_precision_decimals=1,
    ),
    "1.2.0": FirmwareConfig(
        hr_moving_avg_window=8, rr_moving_avg_window=6,
        motion_artifact_threshold=0.60,
        hr_spike_rejection_pct=0.20,
        min_ppg_amplitude=0.05,
        low_confidence_threshold=0.40,
        rr_algorithm="peak_detection",
        ble_tx_power_dbm=0,
    ),
    "2.0.0": FirmwareConfig(
        hr_moving_avg_window=12, rr_moving_avg_window=8,
        motion_artifact_threshold=0.50,
        hr_spike_rejection_pct=0.25,
        min_ppg_amplitude=0.05,
        low_confidence_threshold=0.40,
        rr_algorithm="fusion",
        enable_delta_encoding=True,
        enable_rle_compression=True,
        ble_tx_power_dbm=4,
        hr_precision_decimals=0,
        low_battery_sample_divisor=3,
    ),
}


@dataclass
class DevicePacket:
    packet_id:              str
    device_id:              str
    firmware_version:       str
    sample_timestamp:       str
    received_at:            Optional[str] = None
    elapsed_sec:            int   = 0
    motion:                 float = 0.0
    hr_bpm:                 float = 0.0
    rr_rpm:                 float = 0.0
    temp_c:                 float = 0.0
    signal_confidence:      float = 1.0
    activity_label:         str   = "rest"
    battery_pct:            float = 100.0
    firmware_state:         str   = FirmwareState.SAMPLING
    ambient_temp_c:         float = 22.0
    ble_rssi_dbm:           int   = -65
    crc_ok:                 bool  = True
    retry_count:            int   = 0
    buffered:               bool  = False
    # Firmware processing metadata
    hr_spike_rejected:      bool  = False
    motion_artifact_active: bool  = False
    alert_triggered:        bool  = False
    alert_type:             Optional[str] = None
    fw_config_snapshot:     Optional[dict] = None
    # Pass-through from PhysiologySample
    gait_cadence:           float = 0.0
    step_count:             int   = 0
    sleep_stage:            str   = "AWAKE"
    hour_of_day:            float = 0.0

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class WearableConfig:
    device_id:                str   = field(default_factory=lambda: f"WBL-{uuid.uuid4().hex[:8].upper()}")
    firmware_version:         FirmwareVersion = FirmwareVersion.V1_2
    initial_battery_pct:      float = 95.0
    ble_advert_interval_sec:  int   = 10
    max_local_buffer:         int   = LOCAL_BUFFER_MAX
    ambient_temp_c:           float = 22.0
    crc_check_enabled:        bool  = True
    firmware_config_override: Optional[FirmwareConfig] = None
    confidence_floor:         float = 0.0  # wear condition cap: 0=none, 0.55=capped at 55%


class WearableSimulator:

    def __init__(self, config: WearableConfig):
        self.config  = config
        self.state   = FirmwareState.SAMPLING
        self.battery = config.initial_battery_pct
        self.local_buffer: List[DevicePacket] = []
        self.fw_cfg: FirmwareConfig = (
            config.firmware_config_override
            or FIRMWARE_CONFIGS.get(config.firmware_version.value, FirmwareConfig())
        )
        self._hr_window: Deque[float] = deque(maxlen=self.fw_cfg.hr_moving_avg_window)
        self._rr_window: Deque[float] = deque(maxlen=self.fw_cfg.rr_moving_avg_window)
        self._packet_counter: int = 0   # persistent — never resets on buffer clear

    def process_sample(self, sample: PhysiologySample) -> Optional[DevicePacket]:
        self._drain_battery(seconds=self.fw_cfg.report_interval_sec)
        self._update_state()
        if self.state == FirmwareState.FAULT:
            return None

        hr, rr, conf, spike_rejected, artifact_active = self._apply_fw_processing(sample)
        conf  = self._apply_physical_environment(conf)
        hr    = round(hr, self.fw_cfg.hr_precision_decimals)
        temp  = round(sample.temp_c, self.fw_cfg.temp_precision_decimals)
        alert, alert_type = self._check_device_alert(hr, rr, temp, conf)

        packet = DevicePacket(
            packet_id=f"{self.config.device_id}-{self._packet_counter:06d}",
            device_id=self.config.device_id,
            firmware_version=self.config.firmware_version.value,
            sample_timestamp=sample.timestamp,
            elapsed_sec=sample.elapsed_sec,
            motion=sample.motion,
            hr_bpm=hr,
            rr_rpm=round(rr, 1),
            temp_c=temp,
            signal_confidence=conf,
            activity_label=getattr(sample, "activity_label", getattr(sample, "activity", "unknown")),
            battery_pct=round(self.battery, 1),
            firmware_state=self.state.value,
            ambient_temp_c=self.config.ambient_temp_c,
            crc_ok=self._crc_check(),
            buffered=False,
            hr_spike_rejected=spike_rejected,
            motion_artifact_active=artifact_active,
            alert_triggered=alert,
            alert_type=alert_type,
            fw_config_snapshot={
                "hr_sample_rate_hz":       self.fw_cfg.hr_sample_rate_hz,
                "rr_sample_rate_hz":       self.fw_cfg.rr_sample_rate_hz,
                "temp_sample_rate_hz":     self.fw_cfg.temp_sample_rate_hz,
                "report_interval_sec":     self.fw_cfg.report_interval_sec,
                "hr_moving_avg_window":    self.fw_cfg.hr_moving_avg_window,
                "rr_moving_avg_window":    self.fw_cfg.rr_moving_avg_window,
                "motion_artifact_threshold": self.fw_cfg.motion_artifact_threshold,
                "hr_spike_rejection_pct":  self.fw_cfg.hr_spike_rejection_pct,
                "rr_algorithm":            self.fw_cfg.rr_algorithm,
                "hr_alert_low":            self.fw_cfg.hr_alert_low,
                "hr_alert_high":           self.fw_cfg.hr_alert_high,
                "rr_alert_low":            self.fw_cfg.rr_alert_low,
                "rr_alert_high":           self.fw_cfg.rr_alert_high,
                "temp_alert_low":          self.fw_cfg.temp_alert_low,
                "temp_alert_high":         self.fw_cfg.temp_alert_high,
                "low_confidence_threshold": self.fw_cfg.low_confidence_threshold,
                "ble_tx_power_dbm":        self.fw_cfg.ble_tx_power_dbm,
                "enable_delta_encoding":   self.fw_cfg.enable_delta_encoding,
                "enable_rle_compression":  self.fw_cfg.enable_rle_compression,
            },
            gait_cadence  = getattr(sample, "gait_cadence", 0.0),
            step_count    = getattr(sample, "step_count",   0),
            sleep_stage   = getattr(sample, "sleep_stage",  "AWAKE"),
            hour_of_day   = getattr(sample, "hour_of_day",  0.0),
        )

        self._packet_counter += 1
        if len(self.local_buffer) >= self.config.max_local_buffer:
            self.local_buffer.pop(0)
        self.local_buffer.append(packet)
        self.state = FirmwareState.STORING
        return packet

    def _apply_fw_processing(self, sample):
        hr, rr, conf = sample.hr_bpm, sample.rr_rpm, sample.signal_confidence

        artifact_active = sample.motion > self.fw_cfg.motion_artifact_threshold
        if artifact_active:
            conf *= 0.5

        self._hr_window.append(hr)
        self._rr_window.append(rr)
        hr_smooth = sum(self._hr_window) / len(self._hr_window)
        rr_smooth = sum(self._rr_window) / len(self._rr_window)

        spike_rejected = False
        if self.fw_cfg.hr_spike_rejection_pct > 0 and len(self._hr_window) >= 3:
            prev_mean = sum(list(self._hr_window)[:-1]) / (len(self._hr_window) - 1)
            if abs(hr - prev_mean) / max(prev_mean, 1) > self.fw_cfg.hr_spike_rejection_pct:
                hr_smooth = prev_mean
                spike_rejected = True
                conf *= 0.85

        if self.state == FirmwareState.LOW_BATTERY:
            conf *= (1.0 - 0.08 * self.fw_cfg.low_battery_sample_divisor)

        return hr_smooth, rr_smooth, round(max(0.05, min(1.0, conf)), 3), spike_rejected, artifact_active

    def _apply_physical_environment(self, conf: float) -> float:
        if self.config.ambient_temp_c > 30:
            conf -= 0.05 * ((self.config.ambient_temp_c - 30) / 10)
        elif self.config.ambient_temp_c < 15:
            conf -= 0.08 * ((15 - self.config.ambient_temp_c) / 10)
        if self.battery < 30:
            conf -= 0.10 * (1 - self.battery / 30)
        # Apply wear condition confidence floor (caps maximum achievable confidence)
        if self.config.confidence_floor > 0:
            conf = min(conf, 1.0 - self.config.confidence_floor)
        return round(max(0.05, min(1.0, conf)), 3)

    def _check_device_alert(self, hr, rr, temp, conf):
        if conf < self.fw_cfg.low_confidence_threshold:
            return False, None
        if hr > self.fw_cfg.hr_alert_high:    return True, "HR_HIGH"
        if hr < self.fw_cfg.hr_alert_low:     return True, "HR_LOW"
        if rr > self.fw_cfg.rr_alert_high:    return True, "RR_HIGH"
        if rr < self.fw_cfg.rr_alert_low:     return True, "RR_LOW"
        if temp > self.fw_cfg.temp_alert_high: return True, "TEMP_HIGH"
        if temp < self.fw_cfg.temp_alert_low:  return True, "TEMP_LOW"
        return False, None

    def offload_to_gateway(self, rssi_dbm: int = -65) -> List[DevicePacket]:
        if self.state == FirmwareState.FAULT:
            return []
        self.state = FirmwareState.BLE_CONNECT
        packets_to_send = list(self.local_buffer)
        for pkt in packets_to_send:
            pkt.ble_rssi_dbm = rssi_dbm
            if rssi_dbm < -85 and not self.config.crc_check_enabled:
                pkt.crc_ok = False
        self.local_buffer.clear()
        self.state = FirmwareState.BLE_ADVERT
        return packets_to_send

    def mark_buffered(self) -> None:
        for pkt in self.local_buffer:
            pkt.buffered = True

    def _drain_battery(self, seconds: int) -> None:
        self.battery = max(0.0, self.battery - BATTERY_DRAIN.get(self.state, 2.0) * seconds / 3600)

    def _update_state(self) -> None:
        if self.battery <= CRITICAL_BATTERY_THRESHOLD:
            self.state = FirmwareState.FAULT
        elif self.battery <= LOW_BATTERY_THRESHOLD:
            self.state = FirmwareState.LOW_BATTERY
        elif self.state in (FirmwareState.STORING, FirmwareState.FAULT):
            self.state = FirmwareState.SAMPLING

    def _crc_check(self) -> bool:
        return True if not self.config.crc_check_enabled else random.random() > 0.001

    @property
    def status(self) -> dict:
        return {
            "device_id": self.config.device_id,
            "firmware_version": self.config.firmware_version.value,
            "state": self.state.value,
            "battery_pct": round(self.battery, 1),
            "buffer_depth": len(self.local_buffer),
            "fw_config": self.fw_cfg.to_dict(),
        }
