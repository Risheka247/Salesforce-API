from sqlalchemy import Column, String, DateTime, Integer, Text, JSON
from sqlalchemy.orm import DeclarativeBase
from datetime import datetime
import uuid


class Base(DeclarativeBase):
    pass


class ScanJob(Base):
    __tablename__ = "scan_jobs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id = Column(String, nullable=True)
    status = Column(String, default="pending")
    objects = Column(JSON, nullable=True)           # list of SF objects e.g. ["Contact", "Account"]
    filters = Column(JSON, nullable=True)           # e.g. {"last_modified_after": "2026-01-01"}
    output_format = Column(String, default="parquet")
    sf_jobs = Column(JSON, nullable=True)           # {object: sf_job_id}
    progress = Column(JSON, nullable=True)          # per-object progress
    total_records = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    result_path = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
