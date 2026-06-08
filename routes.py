import uuid
import logging
from datetime import datetime, timedelta
from flask import request
from flask_restx import Api, Resource, Namespace, fields
from app.auth.hmac_auth import require_hmac
from app.models.scan import ScanJob
from app.models.database import get_db
from app.services.extraction_service import (
    start_extraction_worker, SUPPORTED_OBJECTS
)
from app.config import settings

logger = logging.getLogger(__name__)

api = Api(
    title="BD Salesforce Extraction Service",
    version="1.0",
    description="Extracts data from Salesforce CRM using Bulk API 2.0",
    doc="/docs"
)

# ── Namespaces ──────────────────────────────────────────────────────────────

health_ns = Namespace("api", description="Health and key verification")
scan_ns = Namespace("api/scan", description="Scan management")
maintenance_ns = Namespace("api/maintenance", description="Maintenance operations")
objects_ns = Namespace("api", description="Salesforce object info")

api.add_namespace(health_ns)
api.add_namespace(scan_ns)
api.add_namespace(maintenance_ns)
api.add_namespace(objects_ns)

# ── Models ──────────────────────────────────────────────────────────────────

start_scan_model = scan_ns.model("StartScan", {
    "scan_id": fields.String(required=False, description="Optional custom scan ID"),
    "org_id": fields.String(required=False, description="Glynac org identifier"),
    "objects": fields.List(fields.String, required=True,
                           example=["Contact", "Account"],
                           description="Salesforce objects to extract"),
    "filters": fields.Raw(required=False, description="Optional filters e.g. last_modified_after"),
    "output_format": fields.String(required=False, default="parquet"),
})


# ── Health ─────────────────────────────────────────────────────────────────

@health_ns.route("/health")
class Health(Resource):
    def get(self):
        """Health check — no auth required"""
        from app.auth.salesforce_auth import create_token_manager
        token_manager = create_token_manager()

        return {
            "status": "healthy",
            "service": "black-diamond-salesforce-service",
            "version": "1.0.0",
            "environment": settings.ENVIRONMENT,
            "salesforce_connected": token_manager.is_connected,
            "minio_connected": settings.MINIO_ENABLED,
            "kafka_connected": settings.KAFKA_ENABLED,
            "timestamp": datetime.utcnow().isoformat()
        }, 200


@health_ns.route("/key/verify")
class KeyVerify(Resource):
    @require_hmac("core")
    def get(self):
        """Verify HMAC key permissions"""
        return {"success": True, "message": "HMAC key is valid", "key_type": "core"}, 200


# ── Scans ──────────────────────────────────────────────────────────────────

@scan_ns.route("/list")
class ScanList(Resource):
    @require_hmac("core")
    def get(self):
        """List all scans"""
        status_filter = request.args.get("status")
        db = next(get_db())
        try:
            query = db.query(ScanJob)
            if status_filter:
                query = query.filter(ScanJob.status == status_filter)
            scans = query.order_by(ScanJob.created_at.desc()).all()
            return {
                "total": len(scans),
                "scans": [_scan_summary(s) for s in scans]
            }, 200
        finally:
            db.close()


@scan_ns.route("/statistics")
class ScanStatistics(Resource):
    @require_hmac("core")
    def get(self):
        """Aggregate scan statistics"""
        db = next(get_db())
        try:
            all_scans = db.query(ScanJob).all()
            statuses = {}
            for s in all_scans:
                statuses[s.status] = statuses.get(s.status, 0) + 1
            total_records = sum(
                s.total_records for s in all_scans if s.status == "completed"
            )
            return {
                "total_scans": len(all_scans),
                "by_status": statuses,
                "total_records_extracted": total_records
            }, 200
        finally:
            db.close()


@scan_ns.route("/start")
class ScanStart(Resource):
    @require_hmac("core")
    @scan_ns.expect(start_scan_model)
    def post(self):
        """Start a new Salesforce extraction scan"""
        data = request.get_json() or {}
        objects = data.get("objects", [])

        if not objects:
            return {"error": "At least one Salesforce object is required"}, 400

        # Validate objects
        invalid = [o for o in objects if o not in SUPPORTED_OBJECTS]
        if invalid:
            return {
                "error": f"Unsupported objects: {invalid}",
                "supported": list(SUPPORTED_OBJECTS.keys())
            }, 400

        scan_id = data.get("scan_id") or str(uuid.uuid4())
        org_id = data.get("org_id", "default-org")
        filters = data.get("filters", {})
        output_format = data.get("output_format", "parquet")

        db = next(get_db())
        try:
            scan = ScanJob(
                id=scan_id,
                org_id=org_id,
                status="pending",
                objects=objects,
                filters=filters,
                output_format=output_format,
                created_at=datetime.utcnow()
            )
            db.add(scan)
            db.commit()
        finally:
            db.close()

        # Launch background extraction
        start_extraction_worker(scan_id, objects, org_id, filters, output_format)

        return {
            "success": True,
            "scan_id": scan_id,
            "org_id": org_id,
            "status": "pending",
            "objects": objects,
            "message": f"{len(objects)} object(s) queued. Poll /api/scan/{scan_id}/status for progress."
        }, 202


@scan_ns.route("/<string:scan_id>/status")
class ScanStatus(Resource):
    @require_hmac("core")
    def get(self, scan_id):
        """Get scan status and per-object progress"""
        db = next(get_db())
        try:
            scan = db.query(ScanJob).filter(ScanJob.id == scan_id).first()
            if not scan:
                return {"error": f"Scan {scan_id} not found"}, 404
            return _scan_detail(scan), 200
        finally:
            db.close()


@scan_ns.route("/<string:scan_id>/cancel")
class ScanCancel(Resource):
    @require_hmac("core")
    def post(self, scan_id):
        """Cancel an in-progress scan"""
        db = next(get_db())
        try:
            scan = db.query(ScanJob).filter(ScanJob.id == scan_id).first()
            if not scan:
                return {"error": f"Scan {scan_id} not found"}, 404
            if scan.status in ("completed", "cancelled", "failed"):
                return {"error": f"Cannot cancel — scan already {scan.status}"}, 400
            scan.status = "cancelled"
            scan.updated_at = datetime.utcnow()
            db.commit()
            return {"success": True, "scan_id": scan_id, "status": "cancelled"}, 200
        finally:
            db.close()


@scan_ns.route("/<string:scan_id>/resume")
class ScanResume(Resource):
    @require_hmac("core")
    def post(self, scan_id):
        """Resume a failed scan"""
        db = next(get_db())
        try:
            scan = db.query(ScanJob).filter(ScanJob.id == scan_id).first()
            if not scan:
                return {"error": f"Scan {scan_id} not found"}, 404
            if scan.status != "failed":
                return {"error": f"Only failed scans can be resumed. Current: {scan.status}"}, 400
            scan.status = "pending"
            scan.error_message = None
            scan.updated_at = datetime.utcnow()
            db.commit()

            start_extraction_worker(
                scan_id, scan.objects, scan.org_id,
                scan.filters or {}, scan.output_format or "parquet"
            )
            return {"success": True, "scan_id": scan_id, "status": "pending",
                    "message": "Scan resumed"}, 200
        finally:
            db.close()


@scan_ns.route("/<string:scan_id>/remove")
class ScanRemove(Resource):
    @require_hmac("core")
    def delete(self, scan_id):
        """Remove a scan record"""
        db = next(get_db())
        try:
            scan = db.query(ScanJob).filter(ScanJob.id == scan_id).first()
            if not scan:
                return {"error": f"Scan {scan_id} not found"}, 404
            db.delete(scan)
            db.commit()
            return {"success": True, "scan_id": scan_id,
                    "message": "Scan removed"}, 200
        finally:
            db.close()


# ── Maintenance ─────────────────────────────────────────────────────────────

@maintenance_ns.route("/cleanup")
class Cleanup(Resource):
    @require_hmac("engineer")
    def post(self):
        """Purge old scan records older than CLEANUP_DAYS"""
        db = next(get_db())
        try:
            cutoff = datetime.utcnow() - timedelta(days=settings.CLEANUP_DAYS)
            old_scans = db.query(ScanJob).filter(
                ScanJob.created_at < cutoff,
                ScanJob.status.in_(["completed", "failed", "cancelled"])
            ).all()
            count = len(old_scans)
            for scan in old_scans:
                db.delete(scan)
            db.commit()
            return {"success": True, "deleted": count,
                    "message": f"Deleted {count} scans older than {settings.CLEANUP_DAYS} days"}, 200
        finally:
            db.close()


# ── Objects & Batch Info ────────────────────────────────────────────────────

@objects_ns.route("/objects")
class ObjectList(Resource):
    @require_hmac("core")
    def get(self):
        """List supported Salesforce objects with SOQL templates"""
        return {
            "supported_objects": [
                {
                    "name": obj,
                    "soql_template": soql,
                    "supports_incremental": True
                }
                for obj, soql in SUPPORTED_OBJECTS.items()
            ]
        }, 200


@objects_ns.route("/batch/info")
class BatchInfo(Resource):
    @require_hmac("core")
    def get(self):
        """Get Salesforce org metadata and API quota info"""
        from app.auth.salesforce_auth import create_token_manager, MockTokenManager
        token_manager = create_token_manager()

        if isinstance(token_manager, MockTokenManager):
            instance_url = "https://mock-org.salesforce.com"
            mode = "mock"
        else:
            try:
                _, instance_url = token_manager.get_token()
                mode = "live"
            except Exception as e:
                return {"error": f"Could not connect to Salesforce: {str(e)}"}, 503

        return {
            "org": {
                "instance_url": instance_url,
                "api_version": settings.SF_API_VERSION,
                "username": settings.SF_USERNAME or "mock-user@example.com",
                "login_url": settings.SF_LOGIN_URL,
                "mode": mode,
            },
            "service": {
                "max_concurrent_scans": settings.MAX_CONCURRENT_SCANS,
                "bulk_page_size": settings.SF_BULK_PAGE_SIZE,
                "pii_masking_enabled": settings.PII_MASKING_ENABLED,
                "minio_enabled": settings.MINIO_ENABLED,
                "kafka_enabled": settings.KAFKA_ENABLED,
            }
        }, 200


# ── Helpers ─────────────────────────────────────────────────────────────────

def _scan_summary(scan: ScanJob) -> dict:
    return {
        "scan_id": scan.id,
        "org_id": scan.org_id,
        "status": scan.status,
        "objects": scan.objects,
        "total_records": scan.total_records,
        "created_at": scan.created_at.isoformat() if scan.created_at else None,
    }


def _scan_detail(scan: ScanJob) -> dict:
    progress = scan.progress or {}
    objects_total = len(scan.objects) if scan.objects else 0
    objects_complete = sum(
        1 for p in progress.values()
        if p.get("state") == "JobComplete"
    )
    return {
        "scan_id": scan.id,
        "org_id": scan.org_id,
        "status": scan.status,
        "objects": scan.objects,
        "filters": scan.filters,
        "started_at": scan.created_at.isoformat() if scan.created_at else None,
        "updated_at": scan.updated_at.isoformat() if scan.updated_at else None,
        "completed_at": scan.completed_at.isoformat() if scan.completed_at else None,
        "progress": progress,
        "totals": {
            "objects_total": objects_total,
            "objects_complete": objects_complete,
            "records_extracted": scan.total_records,
        },
        "error_message": scan.error_message,
    }
