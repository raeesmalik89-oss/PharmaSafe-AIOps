# ============================================================
# FILE: src/kafka/prescription_consumer.py
# PURPOSE: Reads prescription events from Kafka and
#          automatically calls the drug interaction API.
#          This is the real-time AIOps loop:
#          Kafka → Consumer → FastAPI → RxNav → Alert
# ============================================================

import json
import logging
import requests
from kafka import KafkaConsumer

logger = logging.getLogger(__name__)

KAFKA_BROKER  = "localhost:9092"
TOPIC         = "pharmasafe.prescriptions"
GROUP_ID      = "pharmasafe-interaction-checker"
FASTAPI_URL   = "http://localhost:8000"


def check_interactions_via_api(patient_id: str,
                                drugs: list[str],
                                checked_by: str) -> dict:
    """
    Call the FastAPI /drug-check endpoint with the drugs from Kafka.
    Returns the interaction result.
    """
    payload = {
        "drugs":      drugs,
        "patient_id": patient_id,
        "checked_by": checked_by,
    }
    try:
        resp = requests.post(
            f"{FASTAPI_URL}/drug-check",
            json=payload,
            headers={"X-Role": "Pharmacist"},
            timeout=15
        )
        resp.raise_for_status()
        return resp.json()

    except requests.exceptions.RequestException as e:
        logger.error(f"FastAPI call failed: {e}")
        return {"error": str(e), "highest_severity": "UNKNOWN"}


def process_event(event: dict):
    """
    Process a single prescription event from Kafka.
    1. Log the incoming prescription
    2. Call the drug check API
    3. Log the result (alerts are sent automatically by the API)
    """
    patient_id   = event.get("patient_id", "UNKNOWN")
    patient_name = event.get("patient_name", "Unknown")
    drugs        = event.get("drugs", [])
    ward         = event.get("ward", "Unknown")
    prescribed_by = event.get("prescribed_by", "Unknown")

    logger.info(
        f"Processing prescription | "
        f"Patient: {patient_id} ({patient_name}) | "
        f"Ward: {ward} | "
        f"Drugs: {drugs}"
    )

    if len(drugs) < 2:
        logger.info(f"Patient {patient_id} has only 1 drug — no interaction check needed")
        return

    # Call the interaction API
    result = check_interactions_via_api(
        patient_id=patient_id,
        drugs=drugs,
        checked_by=f"kafka-consumer ({prescribed_by})"
    )

    # Log outcome
    severity     = result.get("highest_severity", "UNKNOWN")
    interactions = result.get("interactions", [])

    if severity == "HIGH":
        logger.critical(
            f"🔴 HIGH SEVERITY INTERACTION | "
            f"Patient: {patient_id} ({patient_name}) | "
            f"Ward: {ward} | "
            f"{len(interactions)} interaction(s) found!"
        )
        for i in interactions:
            logger.critical(
                f"   ⚠️  {i['drug_1']} + {i['drug_2']}: {i['description']}"
            )

    elif severity == "MODERATE":
        logger.warning(
            f"🟡 MODERATE INTERACTION | "
            f"Patient: {patient_id} | {len(interactions)} interaction(s)"
        )

    elif severity == "LOW":
        logger.info(
            f"🟢 LOW INTERACTION | Patient: {patient_id} | Routine monitoring"
        )

    else:
        logger.info(f"✅ No interactions found for patient {patient_id}")

    # Log alert status
    alerts = result.get("alerts_sent", {})
    if alerts:
        logger.info(f"Alerts sent: SMS={alerts.get('sms_sent')} Email={alerts.get('email_sent')}")


def run_consumer():
    """
    Start Kafka consumer loop.
    Reads every prescription event and processes it.
    """
    logger.info(f"Connecting to Kafka at {KAFKA_BROKER}...")

    consumer = KafkaConsumer(
        TOPIC,
        bootstrap_servers=KAFKA_BROKER,
        group_id=GROUP_ID,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        auto_offset_reset="latest",     # Only process new messages
        enable_auto_commit=True,        # Auto-commit offset after processing
        consumer_timeout_ms=1000,       # Allow graceful shutdown
    )

    logger.info(f"Listening on topic: {TOPIC} | Group: {GROUP_ID}")
    logger.info("Waiting for prescription events...")

    try:
        while True:
            # Poll for messages (1 second timeout per poll)
            message_batch = consumer.poll(timeout_ms=1000)

            for topic_partition, messages in message_batch.items():
                for message in messages:
                    try:
                        event = message.value
                        process_event(event)
                    except Exception as e:
                        logger.error(f"Error processing event: {e}")

    except KeyboardInterrupt:
        logger.info("Consumer stopped by user")
    finally:
        consumer.close()
        logger.info("Kafka consumer closed")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s"
    )
    run_consumer()
