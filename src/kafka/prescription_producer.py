# ============================================================
# FILE: src/kafka/prescription_producer.py
# PURPOSE: Simulates a hospital pharmacy system sending
#          prescription events to Kafka in real time.
#          Each event = a new prescription being entered.
# ============================================================

import json
import time
import random
import logging
from datetime import datetime
from kafka import KafkaProducer

logger = logging.getLogger(__name__)

KAFKA_BROKER = "localhost:9092"
TOPIC        = "pharmasafe.prescriptions"

# ── SIMULATED HOSPITAL DRUG COMBINATIONS ─────────────────────
# These are realistic ICU / ward drug combinations.
# Some have known HIGH severity interactions (warfarin + aspirin)
# Some are safe (metformin + lisinopril)

PATIENT_PRESCRIPTIONS = [
    {
        "patient_id": "PT001",
        "patient_name": "Ahmed Khan",
        "ward": "ICU-A",
        "drugs": ["warfarin", "aspirin", "heparin"],        # HIGH risk
        "prescribed_by": "Dr. Fatima"
    },
    {
        "patient_id": "PT002",
        "patient_name": "Sara Malik",
        "ward": "ICU-B",
        "drugs": ["metformin", "lisinopril", "atorvastatin"],  # LOW risk
        "prescribed_by": "Dr. Hassan"
    },
    {
        "patient_id": "PT003",
        "patient_name": "Bilal Ahmed",
        "ward": "Cardiology",
        "drugs": ["digoxin", "amiodarone", "furosemide"],   # MODERATE/HIGH risk
        "prescribed_by": "Dr. Aisha"
    },
    {
        "patient_id": "PT004",
        "patient_name": "Zainab Sheikh",
        "ward": "Nephrology",
        "drugs": ["captopril", "potassium chloride", "spironolactone"],  # HIGH risk (hyperkalemia)
        "prescribed_by": "Dr. Usman"
    },
    {
        "patient_id": "PT005",
        "patient_name": "Omar Farooq",
        "ward": "ICU-A",
        "drugs": ["clopidogrel", "omeprazole", "aspirin"],  # MODERATE risk
        "prescribed_by": "Dr. Fatima"
    },
]


def create_prescription_event(patient: dict) -> dict:
    """
    Build a Kafka prescription event message.
    This is the JSON object sent to Kafka for each prescription.
    """
    return {
        "event_type":    "prescription_submitted",
        "patient_id":    patient["patient_id"],
        "patient_name":  patient["patient_name"],
        "ward":          patient["ward"],
        "drugs":         patient["drugs"],
        "prescribed_by": patient["prescribed_by"],
        "timestamp":     datetime.now().isoformat(),
        "source":        "hospital_pharmacy_system",
    }


def run_producer():
    """
    Connect to Kafka and continuously send prescription events.
    Simulates real-time pharmacy entries every 5-15 seconds.
    """
    logger.info(f"Connecting to Kafka at {KAFKA_BROKER}...")

    producer = KafkaProducer(
        bootstrap_servers=KAFKA_BROKER,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        key_serializer=lambda k: k.encode("utf-8"),
        acks="all",         # Wait for all replicas to confirm — no message loss
        retries=5,
    )

    logger.info(f"Connected. Sending prescriptions to topic: {TOPIC}")

    try:
        while True:
            # Pick a random patient prescription from our list
            patient = random.choice(PATIENT_PRESCRIPTIONS)
            event   = create_prescription_event(patient)

            # Send to Kafka
            # Key = patient_id (ensures same patient always goes to same partition)
            producer.send(
                topic=TOPIC,
                key=patient["patient_id"],
                value=event
            )

            logger.info(
                f"Sent | Patient: {event['patient_id']} "
                f"({event['patient_name']}) | "
                f"Drugs: {event['drugs']} | "
                f"Ward: {event['ward']}"
            )

            # Wait 5-15 seconds before next prescription (realistic rate)
            delay = random.randint(5, 15)
            time.sleep(delay)

    except KeyboardInterrupt:
        logger.info("Producer stopped by user")
    finally:
        producer.flush()
        producer.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s"
    )
    run_producer()
