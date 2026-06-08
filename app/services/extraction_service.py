import threading
import logging
from datetime import datetime
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models.scan import ScanJob
from app.services.pii_masking import mask_records

logger = logging.getLogger(__name__)

# Supported Salesforce objects and their default SOQL
SUPPORTED_OBJECTS = {
    "Contact": "SELECT Id, FirstName, LastName, Email, Phone, AccountId, OwnerId, CreatedDate, LastModifiedDate FROM Contact",
    "Account": "SELECT Id, Name, Type, Industry, BillingCity, BillingState, AnnualRevenue, NumberOfEmployees, OwnerId, CreatedDate, LastModifiedDate FROM Account",
    "Opportunity": "SELECT Id, Name, AccountId, OwnerId, StageName, Amount, CloseDate, Probability, Type, CreatedDate, LastModifiedDate FROM Opportunity",
    "Lead": "SELECT Id, FirstName, LastName, Email, Phone, Company, Status, LeadSource, Rating, CreatedDate, LastModifiedDate FROM Lead",
    "User": "SELECT Id, FirstName, LastName, Email, Username, IsActive, CreatedDate, LastModifiedDate FROM User WHERE IsActive = true",
    "Task": "SELECT Id, Subject, Status, Priority, OwnerId, WhoId, WhatId, ActivityDate, CreatedDate, LastModifiedDate FROM Task",
    "Event": "SELECT Id, Subject, StartDateTime, EndDateTime, OwnerId, WhoId, WhatId, CreatedDate, LastModifiedDate FROM Event",
    "CampaignMember": "SELECT Id, CampaignId, ContactId, LeadId, Status, CreatedDate, LastModifiedDate FROM CampaignMember",
}


def _get_fresh_db():
    """Create a fresh DB connection for background threads (avoids SQLite locking on Windows)."""
    try:
        engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
    except Exception:
        engine = create_engine(
            "sqlite:///./salesforce_dev.db",
            connect_args={"check_same_thread": False, "timeout": 30}
        )
    Session = sessionmaker(bind=engine)
    return Session()


def _update_scan(scan_id: str, **kwargs):
    """Update scan record with fresh DB connection."""
    db = _get_fresh_db()
    try:
        scan = db.query(ScanJob).filter(ScanJob.id == scan_id).first()
        if scan:
            for key, value in kwargs.items():
                setattr(scan, key, value)
            scan.updated_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()


def _is_cancelled(scan_id: str) -> bool:
    """Check if a scan has been cancelled."""
    db = _get_fresh_db()
    try:
        scan = db.query(ScanJob).filter(ScanJob.id == scan_id).first()
        return scan is not None and scan.status == "cancelled"
    finally:
        db.close()


def run_extraction(scan_id: str, objects: List[str],
                   org_id: str, filters: Dict,
                   output_format: str = "parquet"):
    """
    Main extraction function — runs in a background thread.
    Lifecycle: pending → connecting → running → completed / failed
    """
    from app.auth.salesforce_auth import create_token_manager
    from app.clients.bulk_api_client import create_bulk_client, MockBulkAPIClient
    from app.storage.minio_client import create_storage
    from app.storage.kafka_producer import create_kafka_producer

    logger.info(f"Starting extraction scan {scan_id} for objects: {objects}")

    try:
        # ── Step 1: Connect to Salesforce ────────────────────────────────
        _update_scan(scan_id, status="connecting")
        token_manager = create_token_manager()
        bulk_client = create_bulk_client(token_manager)
        storage = create_storage()
        kafka = create_kafka_producer()
        logger.info(f"Scan {scan_id}: connected to Salesforce")

        if _is_cancelled(scan_id):
            return

        # ── Step 2: Create jobs for each object ──────────────────────────
        _update_scan(scan_id, status="running")
        sf_jobs = {}
        progress = {}

        for obj in objects:
            soql = _build_soql(obj, filters)
            job_id = bulk_client.create_query_job(soql)
            sf_jobs[obj] = job_id
            progress[obj] = {
                "sf_job_id": job_id,
                "state": "UploadComplete",
                "records_processed": 0,
                "records_failed": 0,
                "pages_downloaded": 0,
                "minio_path": None
            }

        _update_scan(scan_id, sf_jobs=sf_jobs, progress=progress)

        # ── Step 3: Poll and download results for each object ────────────
        total_records = 0

        for obj in objects:
            if _is_cancelled(scan_id):
                # Abort all running SF jobs
                for o, jid in sf_jobs.items():
                    bulk_client.abort_job(jid)
                return

            job_id = sf_jobs[obj]
            logger.info(f"Scan {scan_id}: polling job {job_id} for {obj}")

            # If mock client, use mock data directly
            if isinstance(bulk_client, MockBulkAPIClient):
                mock_records = bulk_client.MOCK_DATA.get(obj, [])
                if mock_records:
                    masked = mask_records(mock_records, obj)
                    minio_path = storage.upload_parquet(masked, org_id, scan_id, obj, 1)
                    kafka.publish_records(masked, obj, org_id, scan_id, job_id, 1)
                    total_records += len(mock_records)
                    progress[obj].update({
                        "state": "JobComplete",
                        "records_processed": len(mock_records),
                        "pages_downloaded": 1,
                        "minio_path": minio_path
                    })
                continue

            # Real Salesforce: poll until complete
            result = bulk_client.poll_until_complete(job_id)
            progress[obj]["state"] = result.state
            progress[obj]["records_processed"] = result.records_processed

            if result.state == "Failed":
                progress[obj]["error"] = result.error_message
                logger.error(f"Job {job_id} failed: {result.error_message}")
                continue

            # Download paginated results
            page = 0
            for page_records in bulk_client.iter_results(job_id):
                if _is_cancelled(scan_id):
                    bulk_client.abort_job(job_id)
                    return

                page += 1
                masked = mask_records(page_records, obj)
                minio_path = storage.upload_parquet(masked, org_id, scan_id, obj, page)
                kafka.publish_records(masked, obj, org_id, scan_id, job_id, page)
                total_records += len(page_records)
                progress[obj]["pages_downloaded"] = page
                progress[obj]["minio_path"] = minio_path
                _update_scan(scan_id, progress=progress, total_records=total_records)

            # Upload metadata
            storage.upload_metadata({
                "object": obj, "scan_id": scan_id, "org_id": org_id,
                "total_records": result.records_processed,
                "pages": page, "soql": _build_soql(obj, filters),
                "extracted_at": datetime.utcnow().isoformat()
            }, org_id, scan_id, obj)

            # Cleanup SF job
            bulk_client.delete_job(job_id)

        _update_scan(
            scan_id,
            status="completed",
            progress=progress,
            total_records=total_records,
            completed_at=datetime.utcnow(),
            error_message=None
        )
        logger.info(f"Scan {scan_id} completed. Total records: {total_records}")

    except Exception as e:
        logger.exception(f"Scan {scan_id} failed: {e}")
        _update_scan(scan_id, status="failed", error_message=str(e))


def _build_soql(object_type: str, filters: Dict) -> str:
    """Builds SOQL query with optional filters."""
    base = SUPPORTED_OBJECTS.get(
        object_type,
        f"SELECT Id, Name, CreatedDate, LastModifiedDate FROM {object_type}"
    )
    last_modified = filters.get("last_modified_after") if filters else None
    if last_modified:
        if "WHERE" in base.upper():
            base += f" AND LastModifiedDate >= {last_modified}"
        else:
            base += f" WHERE LastModifiedDate >= {last_modified}"
    return base


def start_extraction_worker(scan_id: str, objects: List[str],
                             org_id: str, filters: Dict,
                             output_format: str = "parquet"):
    """Launch extraction in a background thread."""
    thread = threading.Thread(
        target=run_extraction,
        args=(scan_id, objects, org_id, filters, output_format),
        daemon=True
    )
    thread.start()
    return thread
