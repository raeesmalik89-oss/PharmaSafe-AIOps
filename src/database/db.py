# ============================================================
# FILE: src/database/db.py
# PURPOSE: PostgreSQL connection and patient profile management
# ============================================================

import os
import psycopg2
import psycopg2.extras
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Read DB credentials from environment variables
DB_CONFIG = {
    "host":     os.getenv("DB_HOST", "localhost"),
    "port":     int(os.getenv("DB_PORT", 5432)),
    "database": os.getenv("DB_NAME", "pharmasafe"),
    "user":     os.getenv("DB_USER", "pharmasafe"),
    "password": os.getenv("DB_PASSWORD", "pharmasafe123"),
}


def get_connection():
    """Open and return a database connection."""
    return psycopg2.connect(**DB_CONFIG)


def init_db():
    """
    Create all tables on startup if they don't exist.
    Called once when FastAPI starts.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:

            # Patient profiles table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS patients (
                    patient_id   VARCHAR(50) PRIMARY KEY,
                    name         VARCHAR(100) NOT NULL,
                    age          INTEGER,
                    ward         VARCHAR(50),
                    created_at   TIMESTAMP DEFAULT NOW(),
                    updated_at   TIMESTAMP DEFAULT NOW()
                )
            """)

            # Patient medications table (many medications per patient)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS patient_medications (
                    id           SERIAL PRIMARY KEY,
                    patient_id   VARCHAR(50) REFERENCES patients(patient_id),
                    drug_name    VARCHAR(100) NOT NULL,
                    rxcui        VARCHAR(20),
                    dose         VARCHAR(50),
                    frequency    VARCHAR(50),
                    added_at     TIMESTAMP DEFAULT NOW(),
                    active       BOOLEAN DEFAULT TRUE
                )
            """)

            # Interaction check history table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS interaction_checks (
                    id               SERIAL PRIMARY KEY,
                    patient_id       VARCHAR(50),
                    drugs_checked    TEXT[],
                    total_interactions INTEGER,
                    highest_severity VARCHAR(20),
                    result_json      JSONB,
                    checked_by       VARCHAR(50),
                    checked_at       TIMESTAMP DEFAULT NOW()
                )
            """)

            # Alerts table (SMS/Email alerts sent)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS alerts_sent (
                    id           SERIAL PRIMARY KEY,
                    patient_id   VARCHAR(50),
                    alert_type   VARCHAR(20),    -- SMS, EMAIL
                    severity     VARCHAR(20),
                    message      TEXT,
                    sent_to      VARCHAR(100),
                    sent_at      TIMESTAMP DEFAULT NOW(),
                    success      BOOLEAN
                )
            """)

        conn.commit()
    logger.info("Database tables initialised successfully")


# ── PATIENT OPERATIONS ────────────────────────────────────────

def upsert_patient(patient_id: str, name: str, age: int, ward: str):
    """Create or update a patient record."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO patients (patient_id, name, age, ward, updated_at)
                VALUES (%s, %s, %s, %s, NOW())
                ON CONFLICT (patient_id) DO UPDATE
                SET name=%s, age=%s, ward=%s, updated_at=NOW()
            """, (patient_id, name, age, ward, name, age, ward))
        conn.commit()


def get_patient(patient_id: str) -> dict | None:
    """Fetch a patient and their active medications."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM patients WHERE patient_id=%s", (patient_id,))
            patient = cur.fetchone()
            if not patient:
                return None

            cur.execute("""
                SELECT drug_name, rxcui, dose, frequency, added_at
                FROM patient_medications
                WHERE patient_id=%s AND active=TRUE
                ORDER BY added_at DESC
            """, (patient_id,))
            medications = cur.fetchall()

            return {**dict(patient), "medications": [dict(m) for m in medications]}


def get_all_patients() -> list:
    """Return all patients with their medication count."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT p.*, COUNT(m.id) as medication_count
                FROM patients p
                LEFT JOIN patient_medications m
                    ON p.patient_id = m.patient_id AND m.active = TRUE
                GROUP BY p.patient_id
                ORDER BY p.updated_at DESC
            """)
            return [dict(row) for row in cur.fetchall()]


def add_medication(patient_id: str, drug_name: str, rxcui: str, dose: str, frequency: str):
    """Add a new medication to a patient's profile."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO patient_medications
                    (patient_id, drug_name, rxcui, dose, frequency)
                VALUES (%s, %s, %s, %s, %s)
            """, (patient_id, drug_name, rxcui, dose, frequency))
        conn.commit()


def remove_medication(patient_id: str, drug_name: str):
    """Mark a medication as inactive (soft delete)."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE patient_medications
                SET active=FALSE
                WHERE patient_id=%s AND drug_name=%s
            """, (patient_id, drug_name))
        conn.commit()


# ── INTERACTION CHECK HISTORY ─────────────────────────────────

def save_interaction_check(patient_id: str, drugs: list,
                            result: dict, checked_by: str):
    """Save every interaction check to history for audit trail."""
    import json
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO interaction_checks
                    (patient_id, drugs_checked, total_interactions,
                     highest_severity, result_json, checked_by)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                patient_id,
                drugs,
                len(result.get("interactions", [])),
                result.get("highest_severity", "NONE"),
                json.dumps(result),
                checked_by,
            ))
        conn.commit()


def get_patient_history(patient_id: str, limit: int = 20) -> list:
    """Return last N interaction checks for a patient."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT id, drugs_checked, total_interactions,
                       highest_severity, checked_by, checked_at
                FROM interaction_checks
                WHERE patient_id=%s
                ORDER BY checked_at DESC
                LIMIT %s
            """, (patient_id, limit))
            return [dict(row) for row in cur.fetchall()]


# ── ALERT LOGGING ─────────────────────────────────────────────

def log_alert(patient_id: str, alert_type: str,
              severity: str, message: str, sent_to: str, success: bool):
    """Log every SMS/Email alert sent."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO alerts_sent
                    (patient_id, alert_type, severity, message, sent_to, success)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (patient_id, alert_type, severity, message, sent_to, success))
        conn.commit()
