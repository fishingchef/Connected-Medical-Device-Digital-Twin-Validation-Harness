"""
Wearable Device Simulator
==========================
Simulates device-side behaviour: firmware state machine, battery drain,
local ring-buffer storage, BLE connection windows, and environmental factors
that affect signal quality before data ever reaches the gateway.

Key design: the device doesn't know about the network. It records → stores →
attempts BLE offload when a gateway is visible. The gateway simulator drives
the connection events.

Firmware states
---------------
    IDLE        → low power, no sampling
    SAMPLING    → active measurement cycle
    STORING     → writing sample to local flash
    BLE_ADVERT  → advertising for gateway pickup
    BLE_CONNECT → connected, offloading data
    LOW_BATTERY → throttled sampling (60 s → 120 s interval)
    FAULT       → hardware/firmware error, requires reboot
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from core.generators.physiology import PhysiologySample


# ---------------------------------------------------------------------------
# Enums + constants
# ---------------------------------------------------------------------------

class FirmwareState(str, Enum):
    IDLE        = "IDLE"
    SAMPLING    = "SAMPLING"
    STORING     = "STORING"
    BLE_ADVERT  = "BLE_ADVERT"
    BLE_CONNECT = "BLE_CONNECT"
    LOW_BATTERY = "LOW_BATTERY"
    FAULT       = "FAULT"


class FirmwareVersion(str, Enum):
    V1_0 = "1.0.0"   # baseline, no retry logic
    V1_2 = "1.2.0"   # adds BLE retry on disconnect
    V2_0 = "2.0.0"   # adds local compression + CRC check


# Battery drain rates (% per hour) by state
BATTERY_DRAIN = {
    FirmwareState.IDLE:        0.5,
    FirmwareState.SAMPLING:    2.0,
    FirmwareState.STORING:     2.5,
    FirmwareState.BLE_ADVERT:  3.0,
    FirmwareState.BLE_CONNECT: 4.5,
    FirmwareState.LOW_BATTERY: 1.2,
    FirmwareState.FAULT:       0.3,
}

LOW_BATTERY_THRESHOLD   = 15.0   # %
CRITICAL_BATTERY_THRESHOLD = 5.0 # %
LOCAL_BUFFER_MAX        = 2880   # 2 days at 1-min sampling


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class DevicePacket:
    """One data packet as it leaves the device toward the gateway."""
    packet_id:         str
    device_id:         str
    firmware_version:  str
    sample_timestamp:  str    # ORIGINAL device timestamp — must survive pipeline
    received_at:       Optional[str] = None   # filled by cloud on ingest
    elapsed_sec:       int = 0
    motion:            float = 0.0
    hr_bpm:            float = 0.0
    rr_rpm:            float = 0.0
    temp_c:            float = 0.0
    signal_confidence: float = 1.0
    activity_label:    str = "rest"
    battery_pct:       float = 100.0
    firmware_state:    str = FirmwareState.SAMPLING
    # Environmental context (affects confidence downstream)
    ambient_temp_c:    float = 22.0
    ble_rssi_dbm:      int = -65          # signal strength during offload
    crc_ok:            bool = True
    retry_count:       int = 0
    buffered:          bool = False       # was this held in local storage?

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class WearableConfig:
    device_id:          str = field(default_factory=lambda: f"WBL-{uuid.uuid4().hex[:8].upper()}")
    firmware_version:   FirmwareVersion = FirmwareVersion.V1_2
    initial_battery_pct: float = 95.0
    sample_interval_sec: int = 60
    ble_advert_interval_sec: int = 10   # how often device advertises
    max_local_buffer:   int = LOCAL_BUFFER_MAX
    ambient_temp_c:     float = 22.0    # room temp — affects sensor calibration
    # Firmware-specific behaviours
    ble_retry_on_disconnect: bool = True
    local_compression:  bool = False    # only V2_0+
    crc_check_enabled:  bool = True


# ---------------------------------------------------------------------------
# Simulator
# ---------------------------------------------------------------------------

class WearableSimulator:
    """
    Wraps a physiology sample stream and adds device-layer behaviour.

    Usage:
        cfg = WearableConfig(firmware_version=FirmwareVersion.V1_2)
        sim = WearableSimulator(cfg)

        for physio_sample in gen.generate():
            packet = sim.process_sample(physio_sample)
            # packet is now in local_buffer, waiting for gateway pickup
    """

    def __init__(self, config: WearableConfig):
        self.config  = config
        self.state   = FirmwareState.SAMPLING
        self.battery = config.initial_battery_pct
        self.local_buffer: List[DevicePacket] = []
        self._prev_state = FirmwareState.SAMPLING

    # ------------------------------------------------------------------
    # Core: consume one physiology sample, produce a buffered packet
    # ------------------------------------------------------------------

    def process_sample(self, sample: PhysiologySample) -> Optional[DevicePacket]:
        """
        Ingest one physiology sample.  Returns a DevicePacket added to the
        local buffer (or None if device is in FAULT state).
        """
        self._drain_battery(seconds=self.config.sample_interval_sec)
        self._update_state()

        if self.state == FirmwareState.FAULT:
            return None

        # Apply environmental + firmware effects to signal quality
        effective_confidence = self._apply_environmental_factors(
            sample.signal_confidence
        )

        packet = DevicePacket(
            packet_id         = f"{self.config.device_id}-{len(self.local_buffer):06d}",
            device_id         = self.config.device_id,
            firmware_version  = self.config.firmware_version.value,
            sample_timestamp  = sample.timestamp,
            elapsed_sec       = sample.elapsed_sec,
            motion            = sample.motion,
            hr_bpm            = sample.hr_bpm,
            rr_rpm            = sample.rr_rpm,
            temp_c            = sample.temp_c,
            signal_confidence = effective_confidence,
            activity_label    = sample.activity_label,
            battery_pct       = round(self.battery, 1),
            firmware_state    = self.state.value,
            ambient_temp_c    = self.config.ambient_temp_c,
            crc_ok            = self._crc_check(),
            buffered          = False,  # marked True when gateway is unavailable
        )

        # Ring buffer — drop oldest if full
        if len(self.local_buffer) >= self.config.max_local_buffer:
            self.local_buffer.pop(0)

        self.local_buffer.append(packet)
        self.state = FirmwareState.STORING
        return packet

    # ------------------------------------------------------------------
    # Gateway interaction
    # ------------------------------------------------------------------

    def offload_to_gateway(self, rssi_dbm: int = -65) -> List[DevicePacket]:
        """
        Called by the gateway simulator when a BLE connection is established.
        Returns all buffered packets and clears the buffer.

        The BLE RSSI affects whether weak-signal packets are marked degraded.
        """
        if self.state == FirmwareState.FAULT:
            return []

        self.state = FirmwareState.BLE_CONNECT
        packets_to_send = list(self.local_buffer)

        for pkt in packets_to_send:
            pkt.ble_rssi_dbm = rssi_dbm
            # Very weak signal → flip CRC for some packets (V1_0 has no retry)
            if rssi_dbm < -85 and not self.config.crc_check_enabled:
                pkt.crc_ok = False

        self.local_buffer.clear()
        self.state = FirmwareState.BLE_ADVERT
        return packets_to_send

    def mark_buffered(self) -> None:
        """Mark all currently stored packets as buffered (gateway unavailable)."""
        for pkt in self.local_buffer:
            pkt.buffered = True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _drain_battery(self, seconds: int) -> None:
        hours = seconds / 3600
        rate  = BATTERY_DRAIN.get(self.state, 2.0)
        self.battery = max(0.0, self.battery - rate * hours)

    def _update_state(self) -> None:
        if self.battery <= CRITICAL_BATTERY_THRESHOLD:
            self.state = FirmwareState.FAULT
        elif self.battery <= LOW_BATTERY_THRESHOLD:
            self.state = FirmwareState.LOW_BATTERY
        elif self.state in (FirmwareState.STORING, FirmwareState.FAULT):
            self.state = FirmwareState.SAMPLING

    def _apply_environmental_factors(self, base_confidence: float) -> float:
        """
        Environmental variables that reduce signal quality:
          - High ambient temp → sensor drift
          - Very cold → adhesive failure
          - Low battery → ADC noise
        """
        conf = base_confidence

        # Ambient temperature effects on skin-contact sensor
        if self.config.ambient_temp_c > 30:
            conf -= 0.05 * ((self.config.ambient_temp_c - 30) / 10)
        elif self.config.ambient_temp_c < 15:
            conf -= 0.08 * ((15 - self.config.ambient_temp_c) / 10)

        # Battery sag → ADC reference voltage instability
        if self.battery < 30:
            conf -= 0.10 * (1 - self.battery / 30)

        # LOW_BATTERY state → throttled sampling → more interpolation noise
        if self.state == FirmwareState.LOW_BATTERY:
            conf -= 0.05

        return round(max(0.05, min(1.0, conf)), 3)

    def _crc_check(self) -> bool:
        """Simulate occasional flash write errors (0.1% failure rate)."""
        if not self.config.crc_check_enabled:
            return True
        import random
        return random.random() > 0.001

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    @property
    def status(self) -> dict:
        return {
            "device_id":        self.config.device_id,
            "firmware_version": self.config.firmware_version.value,
            "state":            self.state.value,
            "battery_pct":      round(self.battery, 1),
            "buffer_depth":     len(self.local_buffer),
            "ambient_temp_c":   self.config.ambient_temp_c,
        }
