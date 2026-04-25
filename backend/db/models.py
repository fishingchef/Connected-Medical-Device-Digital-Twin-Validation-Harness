"""
Database — SQLAlchemy models + async engine setup.
Uses SQLite for local dev, PostgreSQL in production (set DATABASE_URL env var).
"""

from __future__ import annotations

import os
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, Float, Integer, String, Text, DateTime, JSON,
    create_engine, text
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./meddevice.db")

# SQLite needs check_same_thread=False for FastAPI
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class SimulationRun(Base):
    __tablename__ = "simulation_runs"

    id               = Column(Integer, primary_key=True, index=True)
    run_id           = Column(String, unique=True, index=True)
    scenario_id      = Column(String, index=True)
    created_at       = Column(DateTime, default=datetime.utcnow)
    status           = Column(String, default="running")   # running|complete|failed
    config_json      = Column(JSON)
    summary_json     = Column(JSON)


class IngestedPacket(Base):
    __tablename__ = "ingested_packets"

    id                 = Column(Integer, primary_key=True, index=True)
    run_id             = Column(String, index=True)
    packet_id          = Column(String, unique=True, index=True)
    device_id          = Column(String, index=True)
    firmware_version   = Column(String)
    # Timestamps — the critical data integrity check
    sample_timestamp   = Column(String)   # original device time (must be preserved)
    received_at        = Column(String)   # cloud ingest time
    elapsed_sec        = Column(Integer)
    # Vitals
    motion             = Column(Float)
    hr_bpm             = Column(Float)
    rr_rpm             = Column(Float)
    temp_c             = Column(Float)
    signal_confidence  = Column(Float)
    activity_label     = Column(String)
    # Device state
    battery_pct        = Column(Float)
    firmware_state     = Column(String)
    ambient_temp_c     = Column(Float)
    ble_rssi_dbm       = Column(Integer)
    crc_ok             = Column(Boolean)
    retry_count        = Column(Integer)
    buffered           = Column(Boolean)
    # Ingestion metadata
    duplicate          = Column(Boolean, default=False)
    ingestion_delay_sec = Column(Float)   # received_at − sample_timestamp


class ValidationResult(Base):
    __tablename__ = "validation_results"

    id              = Column(Integer, primary_key=True, index=True)
    run_id          = Column(String, index=True)
    scenario_id     = Column(String)
    requirement_id  = Column(String)
    risk_id         = Column(String)
    check_name      = Column(String)
    expected        = Column(Text)
    actual          = Column(Text)
    passed          = Column(Boolean)
    evidence        = Column(JSON)
    created_at      = Column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------

def create_tables():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
