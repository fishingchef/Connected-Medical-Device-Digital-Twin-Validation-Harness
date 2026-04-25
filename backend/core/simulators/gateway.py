"""
Gateway Simulator
=================
Simulates a BioHub-style Wi-Fi gateway that:
  - Scans BLE and connects to wearables in range
  - Maintains an upload queue with retry logic
  - Handles Wi-Fi outages (device keeps recording; gateway buffers locally)
  - Simulates auth failures, gateway reboots, and partial uploads

State machine
-------------
    ONLINE      → BLE scanning + uploading normally
    WIFI_DOWN   → BLE still works; data queued locally
    REBOOTING   → all connections dropped; resumes after reboot_duration_sec
    AUTH_FAIL   → Wi-Fi connected but cloud auth rejected; retrying with backoff
    OFFLINE     → fully unreachable (power loss, etc.)
"""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, List, Optional

from core.simulators.wearable import DevicePacket, WearableSimulator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class GatewayState(str, Enum):
    ONLINE    = "ONLINE"
    WIFI_DOWN = "WIFI_DOWN"
    REBOOTING = "REBOOTING"
    AUTH_FAIL = "AUTH_FAIL"
    OFFLINE   = "OFFLINE"


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class GatewayConfig:
    gateway_id:            str = "GW-MAIN-001"
    ble_scan_interval_sec: int = 30      # how often to scan for devices
    ble_rssi_threshold:    int = -80     # minimum RSSI to attempt connect
    max_queue_depth:       int = 10000   # local upload queue size
    upload_batch_size:     int = 50      # packets per upload attempt
    retry_base_delay_sec:  int = 10      # exponential backoff base
    retry_max_attempts:    int = 5
    reboot_duration_sec:   int = 45
    # Fault schedule: list of (start_sec, end_sec, fault_type)
    fault_schedule: List[tuple] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Upload queue entry
# ---------------------------------------------------------------------------

@dataclass
class QueueEntry:
    packet:        DevicePacket
    enqueued_at:   float = field(default_factory=time.time)
    attempts:      int = 0
    last_attempt:  Optional[float] = None


# ---------------------------------------------------------------------------
# Gateway event log entry
# ---------------------------------------------------------------------------

@dataclass
class GatewayEvent:
    elapsed_sec:  int
    event_type:   str   # "STATE_CHANGE" | "BLE_CONNECT" | "UPLOAD_OK" |
                        # "UPLOAD_FAIL" | "QUEUE_FLUSH" | "REBOOT"
    detail:       str
    state:        str
    queue_depth:  int


# ---------------------------------------------------------------------------
# Simulator
# ---------------------------------------------------------------------------

class GatewaySimulator:
    """
    Drives the gateway through a scenario tick-by-tick.

    Usage (synchronous, for testing):
        gw = GatewaySimulator(GatewayConfig(
            fault_schedule=[(2400, 3600, "WIFI_DOWN")]  # outage min 40–60
        ))
        events = gw.run_scenario(wearable_sim, total_seconds=7200)
    """

    def __init__(self, config: GatewayConfig):
        self.config      = config
        self.state       = GatewayState.ONLINE
        self.queue:      List[QueueEntry] = []
        self.events:     List[GatewayEvent] = []
        self.uploaded:   List[DevicePacket] = []
        self._elapsed    = 0
        self._reboot_end = 0

    # ------------------------------------------------------------------
    # Main simulation loop (synchronous)
    # ------------------------------------------------------------------

    def run_scenario(
        self,
        wearable: WearableSimulator,
        physiology_samples: list,
        upload_fn: Optional[Callable[[List[DevicePacket]], dict]] = None,
    ) -> dict:
        """
        Runs through all physiology_samples, ticking the gateway state machine.
        upload_fn is called with a batch of packets; defaults to mock accept-all.
        Returns a summary dict.
        """
        upload_fn = upload_fn or self._mock_upload

        for sample in physiology_samples:
            self._elapsed = sample.elapsed_sec
            self._apply_fault_schedule()

            # Device records regardless of gateway state
            packet = wearable.process_sample(sample)
            if packet is None:
                self._log("DEVICE_FAULT", "Device in FAULT state — no sample", 0)
                continue

            if self.state in (GatewayState.ONLINE, GatewayState.AUTH_FAIL):
                # BLE scan window — attempt offload
                if self._elapsed % self.config.ble_scan_interval_sec == 0:
                    rssi = self._ble_rssi()
                    if rssi >= self.config.ble_rssi_threshold:
                        packets = wearable.offload_to_gateway(rssi_dbm=rssi)
                        self._log("BLE_CONNECT", f"{len(packets)} packets offloaded, RSSI {rssi} dBm", len(packets))
                        for p in packets:
                            self._enqueue(p)
                    # Try uploading queued data
                    self._flush_queue(upload_fn)

            elif self.state == GatewayState.WIFI_DOWN:
                # Can still do BLE; mark device packets as buffered
                wearable.mark_buffered()
                self._log("WIFI_DOWN", "Gateway offline — device buffering locally", len(self.queue))

            elif self.state == GatewayState.REBOOTING:
                if self._elapsed >= self._reboot_end:
                    self._transition(GatewayState.ONLINE, "Reboot complete")

            elif self.state == GatewayState.OFFLINE:
                wearable.mark_buffered()

        # End-of-scenario: reconnect and flush any remaining buffer
        if wearable.local_buffer:
            packets = wearable.offload_to_gateway(rssi_dbm=-60)
            for p in packets:
                self._enqueue(p)
            self._log("QUEUE_FLUSH", f"Final flush: {len(packets)} packets", len(self.queue))
            self._flush_queue(upload_fn)

        return self._summary()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _apply_fault_schedule(self) -> None:
        for (start, end, fault) in self.config.fault_schedule:
            if start <= self._elapsed < end:
                target = GatewayState[fault]
                if self.state != target:
                    self._transition(target, f"Scheduled fault: {fault} [{start}–{end}s]")
                return
            elif self._elapsed == end and self.state == GatewayState[fault]:
                self._transition(GatewayState.ONLINE, f"Fault {fault} cleared at {end}s")

    def _enqueue(self, packet: DevicePacket) -> None:
        if len(self.queue) >= self.config.max_queue_depth:
            self.queue.pop(0)   # drop oldest (ring buffer)
        self.queue.append(QueueEntry(packet=packet))

    def _flush_queue(self, upload_fn: Callable) -> None:
        if not self.queue or self.state != GatewayState.ONLINE:
            return

        batch = [e for e in self.queue[:self.config.upload_batch_size]]
        packets = [e.packet for e in batch]

        result = upload_fn(packets)

        if result.get("success"):
            accepted = result.get("accepted", len(packets))
            self.uploaded.extend(packets[:accepted])
            self.queue = self.queue[accepted:]
            self._log("UPLOAD_OK", f"{accepted} packets uploaded, {len(self.queue)} remaining", len(self.queue))
        else:
            # Increment retry count; drop if over max
            kept = []
            for entry in batch:
                entry.attempts += 1
                entry.last_attempt = time.time()
                if entry.attempts <= self.config.retry_max_attempts:
                    kept.append(entry)
                else:
                    self._log("UPLOAD_DROP", f"Packet {entry.packet.packet_id} dropped after max retries", 0)
            self._log("UPLOAD_FAIL", f"Upload failed: {result.get('error', 'unknown')}", len(self.queue))

    def _ble_rssi(self) -> int:
        """Simulate BLE RSSI with some natural variation."""
        return random.randint(-75, -55)

    def _mock_upload(self, packets: List[DevicePacket]) -> dict:
        """Default: accept everything. Replace with real FastAPI call in integration."""
        return {"success": True, "accepted": len(packets)}

    def _transition(self, new_state: GatewayState, reason: str) -> None:
        self._log("STATE_CHANGE", f"{self.state} → {new_state}: {reason}", len(self.queue))
        if new_state == GatewayState.REBOOTING:
            self._reboot_end = self._elapsed + self.config.reboot_duration_sec
        self.state = new_state

    def _log(self, event_type: str, detail: str, queue_depth: int) -> None:
        self.events.append(GatewayEvent(
            elapsed_sec=self._elapsed,
            event_type=event_type,
            detail=detail,
            state=self.state.value,
            queue_depth=queue_depth,
        ))

    def _summary(self) -> dict:
        total_produced  = sum(1 for e in self.events if e.event_type == "BLE_CONNECT")
        upload_ok       = [e for e in self.events if e.event_type == "UPLOAD_OK"]
        upload_fail     = [e for e in self.events if e.event_type == "UPLOAD_FAIL"]

        return {
            "gateway_id":        self.config.gateway_id,
            "total_uploaded":    len(self.uploaded),
            "queue_remaining":   len(self.queue),
            "upload_ok_events":  len(upload_ok),
            "upload_fail_events": len(upload_fail),
            "events":            [e.__dict__ for e in self.events],
            "uploaded_packets":  [p.to_dict() for p in self.uploaded],
        }
