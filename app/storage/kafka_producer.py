import json
import logging
from datetime import datetime
from typing import Dict, List
from app.config import settings

logger = logging.getLogger(__name__)

TOPIC_MAP = {
    "Contact": settings.KAFKA_SF_CONTACTS_TOPIC,
    "Account": settings.KAFKA_SF_ACCOUNTS_TOPIC,
    "Opportunity": settings.KAFKA_SF_OPPORTUNITIES_TOPIC,
    "Lead": settings.KAFKA_SF_LEADS_TOPIC,
    "Task": settings.KAFKA_SF_ACTIVITIES_TOPIC,
    "Event": settings.KAFKA_SF_ACTIVITIES_TOPIC,
    "User": settings.KAFKA_SF_USERS_TOPIC,
    "CampaignMember": settings.KAFKA_SF_CAMPAIGNS_TOPIC,
}


class KafkaProducer:
    """Publishes Salesforce records to Kafka topics."""

    def __init__(self):
        from kafka import KafkaProducer as KP
        self._producer = KP(
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            acks="all",
            retries=3,
        )

    def publish_records(self, records: List[Dict], object_type: str,
                        org_id: str, scan_id: str, sf_job_id: str, page: int):
        """Publishes records to the appropriate Kafka topic."""
        topic = TOPIC_MAP.get(object_type, f"sf.{object_type.lower()}.dev")
        extracted_at = datetime.utcnow().isoformat()

        for record in records:
            message = {
                "meta": {
                    "source": "salesforce",
                    "object": object_type,
                    "org_id": org_id,
                    "scan_id": scan_id,
                    "sf_job_id": sf_job_id,
                    "page": page,
                    "extracted_at": extracted_at,
                },
                "record": record
            }
            self._producer.send(topic, value=message)

        self._producer.flush()
        logger.info(f"Published {len(records)} {object_type} records to Kafka topic {topic}")

    def close(self):
        self._producer.close()


class MockKafkaProducer:
    """Mock Kafka producer for dev."""

    def publish_records(self, records, object_type, org_id,
                        scan_id, sf_job_id, page):
        topic = TOPIC_MAP.get(object_type, f"sf.{object_type.lower()}.dev")
        logger.info(f"[MOCK Kafka] Would publish {len(records)} {object_type} records to {topic}")

    def close(self):
        pass


def create_kafka_producer():
    """Factory — returns real or mock Kafka producer."""
    if settings.KAFKA_ENABLED:
        try:
            return KafkaProducer()
        except Exception as e:
            logger.warning(f"Kafka unavailable ({e}), using mock producer")
    return MockKafkaProducer()
