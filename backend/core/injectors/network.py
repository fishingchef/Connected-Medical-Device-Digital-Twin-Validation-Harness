"""
Network Fault Injector
======================
Wraps upload calls with configurable network faults.
Can be used as a middleware layer between gateway and mock cloud.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from core.simulators.wearable import DevicePacket


@dataclass
class FaultProfile:
    name:              str = "clean"
    latency_ms_min:    int = 10
    latency_ms_max:    int = 80
    packet_loss_pct:   float = 0.0      # 0.0–1.0
    outage_start_sec:  Optional[int] = None
    outage_end_sec:    Optional[int] = None
    tls_fail_rate:     float = 0.0      # probability per upload call
    dns_fail_rate:     float = 0.0


# Pre-built fault profiles
FAULT_PROFILES = {
    "clean": FaultProfile(name="clean"),
    "flaky": FaultProfile(
        name="flaky",
        latency_ms_min=50, latency_ms_max=500,
        packet_loss_pct=0.05,
    ),
    "lossy": FaultProfile(
        name="lossy",
        latency_ms_min=100, latency_ms_max=300,
        packet_loss_pct=0.15,
    ),
    "outage_20min": FaultProfile(
        name="outage_20min",
        outage_start_sec=2400, outage_end_sec=3600,
    ),
    "tls_failure": FaultProfile(
        name="tls_failure",
        tls_fail_rate=0.30,
    ),
}


class NetworkFaultInjector:
    """
    Wraps an upload callable with simulated network faults.

    Usage:
        injector = NetworkFaultInjector(FAULT_PROFILES["flaky"])
        result = injector.inject(elapsed_sec=500, upload_fn=real_upload, packets=packets)
    """

    def __init__(self, profile: FaultProfile):
        self.profile = profile
        self.stats   = {"dropped": 0, "delayed_ms": 0, "tls_fail": 0, "dns_fail": 0, "passed": 0}

    def inject(
        self,
        elapsed_sec: int,
        upload_fn: Callable[[List[DevicePacket]], dict],
        packets: List[DevicePacket],
    ) -> dict:

        # Hard outage window
        if (self.profile.outage_start_sec is not None
                and self.profile.outage_start_sec <= elapsed_sec < self.profile.outage_end_sec):
            return {"success": False, "error": "NETWORK_OUTAGE", "accepted": 0}

        # DNS failure
        if random.random() < self.profile.dns_fail_rate:
            self.stats["dns_fail"] += 1
            return {"success": False, "error": "DNS_FAILURE", "accepted": 0}

        # TLS failure
        if random.random() < self.profile.tls_fail_rate:
            self.stats["tls_fail"] += 1
            return {"success": False, "error": "TLS_HANDSHAKE_FAILURE", "accepted": 0}

        # Latency
        delay_ms = random.randint(self.profile.latency_ms_min, self.profile.latency_ms_max)
        self.stats["delayed_ms"] += delay_ms
        time.sleep(delay_ms / 1000.0)

        # Packet loss — randomly drop some packets from the batch
        surviving = [p for p in packets if random.random() > self.profile.packet_loss_pct]
        dropped = len(packets) - len(surviving)
        self.stats["dropped"] += dropped

        if not surviving:
            return {"success": False, "error": "ALL_PACKETS_LOST", "accepted": 0}

        result = upload_fn(surviving)
        self.stats["passed"] += len(surviving)
        return result
