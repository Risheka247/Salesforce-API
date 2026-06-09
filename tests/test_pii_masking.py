"""Tests for PII masking service."""
from unittest.mock import patch
from app.services.pii_masking import mask_record, mask_records, MASK_VALUE


def test_mask_record_masks_email_when_enabled():
    """Email should be masked when PII masking is enabled."""
    record = {"Id": "001", "Email": "john@example.com", "FirstName": "John"}
    with patch("app.services.pii_masking.settings") as mock_settings:
        mock_settings.PII_MASKING_ENABLED = True
        result = mask_record(record, "Contact")
    assert result["Email"] == MASK_VALUE


def test_mask_record_masks_phone_when_enabled():
    """Phone should be masked when PII masking is enabled."""
    record = {"Id": "001", "Phone": "+1-555-1234", "FirstName": "John"}
    with patch("app.services.pii_masking.settings") as mock_settings:
        mock_settings.PII_MASKING_ENABLED = True
        result = mask_record(record, "Contact")
    assert result["Phone"] == MASK_VALUE


def test_mask_record_preserves_id():
    """ID field should never be masked."""
    record = {"Id": "003001", "Email": "john@example.com"}
    with patch("app.services.pii_masking.settings") as mock_settings:
        mock_settings.PII_MASKING_ENABLED = True
        result = mask_record(record, "Contact")
    assert result["Id"] == "003001"


def test_mask_record_no_masking_when_disabled():
    """Fields should not be masked when PII masking is disabled."""
    record = {"Id": "001", "Email": "john@example.com", "Phone": "+1-555-1234"}
    with patch("app.services.pii_masking.settings") as mock_settings:
        mock_settings.PII_MASKING_ENABLED = False
        result = mask_record(record, "Contact")
    assert result["Email"] == "john@example.com"
    assert result["Phone"] == "+1-555-1234"


def test_mask_records_masks_all_records():
    """mask_records should mask all records in the list."""
    records = [
        {"Id": "001", "Email": "a@example.com"},
        {"Id": "002", "Email": "b@example.com"},
    ]
    with patch("app.services.pii_masking.settings") as mock_settings:
        mock_settings.PII_MASKING_ENABLED = True
        result = mask_records(records, "Contact")
    assert all(r["Email"] == MASK_VALUE for r in result)


def test_mask_record_account_has_no_pii_fields():
    """Account object should have no PII fields masked."""
    record = {"Id": "001", "Name": "Acme Corp", "Industry": "Tech"}
    with patch("app.services.pii_masking.settings") as mock_settings:
        mock_settings.PII_MASKING_ENABLED = True
        result = mask_record(record, "Account")
    assert result["Name"] == "Acme Corp"


def test_mask_record_does_not_modify_original():
    """mask_record should not modify the original record."""
    record = {"Id": "001", "Email": "john@example.com"}
    original_email = record["Email"]
    with patch("app.services.pii_masking.settings") as mock_settings:
        mock_settings.PII_MASKING_ENABLED = True
        mask_record(record, "Contact")
    assert record["Email"] == original_email
