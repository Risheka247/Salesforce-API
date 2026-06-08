import csv
import io
import time
import logging
import requests
from dataclasses import dataclass
from typing import Iterator, Optional, List, Dict

logger = logging.getLogger(__name__)

API_VERSION = "v59.0"
JOBS_BASE = f"/services/data/{API_VERSION}/jobs/query"

# Adaptive polling intervals (seconds)
POLL_INTERVALS = [5, 5, 5, 5, 5, 15, 15, 15, 60, 60, 120]


@dataclass
class BulkJobResult:
    job_id: str
    state: str                      # JobComplete | Failed | Aborted
    records_processed: int
    records_failed: int
    error_message: Optional[str]


class SalesforceBulkAPIClient:
    """
    Wrapper for Salesforce Bulk API 2.0 (query operations).
    Handles: job creation, adaptive polling, paginated CSV download, cleanup.
    """

    def __init__(self, token_manager, timeout: int = 30):
        self._tokens = token_manager
        self._timeout = timeout

    def _headers(self) -> dict:
        token, _ = self._tokens.get_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _base_url(self) -> str:
        _, instance_url = self._tokens.get_token()
        return instance_url

    # ── Job lifecycle ────────────────────────────────────────────────────────

    def create_query_job(self, soql: str) -> str:
        """Creates a Bulk API 2.0 query job. Returns job_id."""
        url = f"{self._base_url()}{JOBS_BASE}"
        payload = {
            "operation": "query",
            "query": soql,
            "contentType": "CSV",
            "columnDelimiter": "COMMA",
            "lineEnding": "LF",
        }
        resp = requests.post(url, json=payload, headers=self._headers(),
                             timeout=self._timeout)
        resp.raise_for_status()
        job_id = resp.json()["id"]
        logger.info(f"Created Bulk API query job: {job_id} | SOQL: {soql[:80]}...")
        return job_id

    def poll_until_complete(self, job_id: str) -> BulkJobResult:
        """Blocks until the job reaches a terminal state. Uses adaptive polling."""
        url = f"{self._base_url()}{JOBS_BASE}/{job_id}"
        intervals = iter(POLL_INTERVALS)

        while True:
            resp = requests.get(url, headers=self._headers(), timeout=self._timeout)
            resp.raise_for_status()
            data = resp.json()
            state = data["state"]

            logger.debug(f"Job {job_id} state={state}")

            if state in ("JobComplete", "Failed", "Aborted"):
                return BulkJobResult(
                    job_id=job_id,
                    state=state,
                    records_processed=data.get("numberRecordsProcessed", 0),
                    records_failed=data.get("numberRecordsFailed", 0),
                    error_message=data.get("errorMessage"),
                )

            delay = next(intervals, 120)
            logger.debug(f"Job {job_id} not done yet, waiting {delay}s")
            time.sleep(delay)

    def get_job_status(self, job_id: str) -> dict:
        """Returns current job status dict without blocking."""
        url = f"{self._base_url()}{JOBS_BASE}/{job_id}"
        resp = requests.get(url, headers=self._headers(), timeout=self._timeout)
        resp.raise_for_status()
        return resp.json()

    def iter_results(self, job_id: str,
                     page_size: int = 50000) -> Iterator[List[Dict]]:
        """
        Yields pages of records (each page is a list of dicts).
        Handles Sforce-Locator pagination transparently.
        """
        locator = None
        page_num = 0

        while True:
            url = (f"{self._base_url()}{JOBS_BASE}/{job_id}"
                   f"/results?maxRecords={page_size}")
            if locator:
                url += f"&locator={locator}"

            resp = requests.get(url, headers=self._headers(),
                                timeout=self._timeout * 6)
            resp.raise_for_status()

            # Parse CSV body
            reader = csv.DictReader(io.StringIO(resp.text))
            records = list(reader)
            page_num += 1
            logger.info(f"Job {job_id} page {page_num}: {len(records)} records")
            yield records

            locator = resp.headers.get("Sforce-Locator")
            if not locator or locator == "null":
                break

    def delete_job(self, job_id: str) -> None:
        """Deletes a completed job from Salesforce (cleanup)."""
        url = f"{self._base_url()}{JOBS_BASE}/{job_id}"
        try:
            resp = requests.delete(url, headers=self._headers(),
                                   timeout=self._timeout)
            resp.raise_for_status()
            logger.info(f"Deleted Bulk API job: {job_id}")
        except Exception as e:
            logger.warning(f"Failed to delete job {job_id}: {e}")

    def abort_job(self, job_id: str) -> None:
        """Aborts a running job."""
        url = f"{self._base_url()}{JOBS_BASE}/{job_id}"
        try:
            payload = {"state": "Aborted"}
            resp = requests.patch(url, json=payload, headers=self._headers(),
                                  timeout=self._timeout)
            resp.raise_for_status()
            logger.info(f"Aborted Bulk API job: {job_id}")
        except Exception as e:
            logger.warning(f"Failed to abort job {job_id}: {e}")


class MockBulkAPIClient:
    """
    Mock Bulk API client for development — simulates the full job lifecycle
    with realistic data when no Salesforce credentials are configured.
    """

    MOCK_DATA = {
        "Contact": [
            {"Id": f"003{i:015d}", "FirstName": fn, "LastName": ln,
             "Email": f"{fn.lower()}@example.com", "Phone": f"+1-555-{1000+i}",
             "AccountId": f"001{i:015d}", "CreatedDate": "2026-01-15T08:00:00.000+0000",
             "LastModifiedDate": "2026-04-30T14:22:00.000+0000"}
            for i, (fn, ln) in enumerate([
                ("James", "Wilson"), ("Sarah", "Johnson"), ("Michael", "Brown"),
                ("Emily", "Davis"), ("David", "Martinez"), ("Lisa", "Anderson"),
                ("Robert", "Taylor"), ("Jennifer", "Thomas"), ("William", "Jackson"),
                ("Amanda", "White")
            ], 1)
        ],
        "Account": [
            {"Id": f"001{i:015d}", "Name": name, "Industry": industry,
             "Type": atype, "AnnualRevenue": str(rev), "NumberOfEmployees": str(emp),
             "BillingCity": city, "CreatedDate": "2026-01-01T00:00:00.000+0000",
             "LastModifiedDate": "2026-05-01T00:00:00.000+0000"}
            for i, (name, industry, atype, rev, emp, city) in enumerate([
                ("Acme Corp", "Technology", "Customer", 5000000, 250, "San Francisco"),
                ("GlobalTech", "Software", "Partner", 12000000, 800, "New York"),
                ("DataSystems", "IT Services", "Customer", 3200000, 150, "Austin"),
                ("CloudWave", "Cloud Computing", "Prospect", 8500000, 400, "Seattle"),
                ("InnovateCo", "Consulting", "Customer", 2100000, 90, "Chicago"),
            ], 1)
        ],
        "Opportunity": [
            {"Id": f"006{i:015d}", "Name": name, "StageName": stage,
             "Amount": str(amount), "CloseDate": close,
             "Probability": str(prob), "AccountId": f"001{i:015d}",
             "CreatedDate": "2026-01-01T00:00:00.000+0000",
             "LastModifiedDate": "2026-05-01T00:00:00.000+0000"}
            for i, (name, stage, amount, close, prob) in enumerate([
                ("Acme Deal", "Proposal/Price Quote", 75000, "2026-06-30", 60),
                ("GlobalTech Renewal", "Closed Won", 120000, "2026-03-31", 100),
                ("DataSystems Expansion", "Needs Analysis", 45000, "2026-07-15", 30),
                ("CloudWave License", "Value Proposition", 90000, "2026-08-01", 50),
                ("InnovateCo Support", "Closed Won", 28000, "2026-06-15", 100),
            ], 1)
        ],
        "Lead": [
            {"Id": f"00Q{i:015d}", "FirstName": fn, "LastName": ln,
             "Email": f"{fn.lower()}@lead.com", "Company": company,
             "Status": status, "LeadSource": source,
             "CreatedDate": "2026-03-01T00:00:00.000+0000",
             "LastModifiedDate": "2026-05-01T00:00:00.000+0000"}
            for i, (fn, ln, company, status, source) in enumerate([
                ("Alice", "Green", "StartupXYZ", "New", "Web"),
                ("Bob", "Harris", "MegaCorp", "Working", "Phone"),
                ("Carol", "Lewis", "TechFirm", "Qualified", "Email"),
                ("Dan", "Clark", "SalesCo", "New", "Partner"),
            ], 1)
        ],
    }

    def create_query_job(self, soql: str) -> str:
        import uuid
        job_id = f"MOCK_{str(uuid.uuid4())[:8].upper()}"
        logger.info(f"[MOCK] Created job {job_id} for: {soql[:60]}")
        return job_id

    def poll_until_complete(self, job_id: str) -> BulkJobResult:
        time.sleep(2)   # Simulate processing time
        return BulkJobResult(
            job_id=job_id,
            state="JobComplete",
            records_processed=10,
            records_failed=0,
            error_message=None,
        )

    def get_job_status(self, job_id: str) -> dict:
        return {"id": job_id, "state": "JobComplete", "numberRecordsProcessed": 10}

    def iter_results(self, job_id: str, page_size: int = 50000):
        # Extract object type from job_id context isn't available here,
        # so we yield Contact data as default mock
        for object_type, records in self.MOCK_DATA.items():
            yield records
            return

    def delete_job(self, job_id: str) -> None:
        logger.info(f"[MOCK] Deleted job {job_id}")

    def abort_job(self, job_id: str) -> None:
        logger.info(f"[MOCK] Aborted job {job_id}")


def create_bulk_client(token_manager):
    """Factory — returns real or mock Bulk API client."""
    from app.auth.salesforce_auth import MockTokenManager
    if isinstance(token_manager, MockTokenManager):
        logger.warning("Using mock Bulk API client (no real Salesforce credentials)")
        return MockBulkAPIClient()
    return SalesforceBulkAPIClient(token_manager)
