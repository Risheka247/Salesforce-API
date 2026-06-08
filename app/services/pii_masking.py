import logging
from typing import Dict, List
from app.config import settings

logger = logging.getLogger(__name__)

# Fields to mask per Salesforce object
PII_FIELDS = {
    "Contact": ["Email", "Phone", "FirstName", "LastName", "MailingStreet",
                "MailingCity", "MobilePhone", "HomePhone"],
    "Lead": ["Email", "Phone", "FirstName", "LastName", "Street",
             "MobilePhone", "Company"],
    "Account": [],   # Accounts don't have direct PII in standard fields
    "Opportunity": [],
    "User": ["Email", "Phone", "MobilePhone", "FirstName", "LastName"],
    "CampaignMember": ["Email"],
}

MASK_VALUE = "[MASKED]"


def mask_record(record: Dict, object_type: str) -> Dict:
    """
    Masks PII fields in a single record.
    Only applies masking when PII_MASKING_ENABLED=True.
    """
    if not settings.PII_MASKING_ENABLED:
        return record

    fields_to_mask = PII_FIELDS.get(object_type, [])
    masked = record.copy()

    for field in fields_to_mask:
        if field in masked and masked[field]:
            masked[field] = MASK_VALUE

    return masked


def mask_records(records: List[Dict], object_type: str) -> List[Dict]:
    """Masks PII fields across a list of records."""
    if not settings.PII_MASKING_ENABLED:
        return records
    return [mask_record(r, object_type) for r in records]
