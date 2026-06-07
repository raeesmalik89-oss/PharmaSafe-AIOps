# ============================================================
# FILE: src/api/app.py
# PURPOSE: Main FastAPI application — all API endpoints
#          for PharmaSafe-AIOps drug interaction checker
# ============================================================

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import logging
import time
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from fastapi.responses import Response

from src.database.db import (
    init_db, upsert_patient, get_patient, get_all_patients,
    add_medication, remove_medication, save_interaction_check,
    get_patient_history, log_alert
)
from src.api.drug_engine import get_drug_interactions, get_drug_info, get_rxcui
from src.alerts.alert_service import trigger_alerts

# ── LOGGING SETUP ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger(__name__)

# ── PROMETHEUS METRICS ────────────────────────────────────────
drug_checks_total      = Counter("pharmasafe_drug_checks_total",
                                  "Total number of drug interaction checks")
high_severity_total    = Counter("pharmasafe_high_severity_total",
                                  "Number of HIGH severity interactions detected")
alerts_sent_total      = Counter("pharmasafe_alerts_sent_total",
                                  "Number of SMS/Email alerts sent")
check_latency          = Histogram("pharmasafe_check_duration_seconds",
                                    "Drug check request duration")

# ── FASTAPI APP ───────────────────────────────────────────────
app = FastAPI(
    title="PharmaSafe-AIOps",
    description="Real-time drug interaction checking system for Pharmacists, ICU Doctors, and Nurses",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Allow React dashboard to connect (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # In production: set to your React app URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    """Called once when FastAPI starts — initialise database tables."""
    try:
        init_db()
        logger.info("PharmaSafe-AIOps started successfully")
    except Exception as e:
        logger.warning(f"DB init failed (running without DB): {e}")


# ── REQUEST / RESPONSE MODELS ─────────────────────────────────

class DrugCheckRequest(BaseModel):
    drugs: list[str] = Field(..., min_items=2, example=["warfarin", "aspirin"])
    patient_id: Optional[str] = None
    checked_by: Optional[str] = "Anonymous"

class PatientRequest(BaseModel):
    patient_id: str  = Field(..., example="PT001")
    name:        str  = Field(..., example="Ahmed Khan")
    age:         int  = Field(..., example=55)
    ward:        str  = Field(..., example="ICU-A")

class MedicationRequest(BaseModel):
    drug_name:  str = Field(..., example="warfarin")
    dose:       str = Field(..., example="5mg")
    frequency:  str = Field(..., example="once daily")


# ── HELPER: Role check from OPA header ───────────────────────

def get_role(x_role: Optional[str] = Header(default="Nurse")) -> str:
    """
    Read the X-Role header sent by the React frontend.
    OPA (Open Policy Agent) validates this in production.
    Allowed: Pharmacist, ICU_Doctor, Nurse, Admin
    """
    allowed = {"Pharmacist", "ICU_Doctor", "Nurse", "Admin"}
    if x_role not in allowed:
        raise HTTPException(status_code=403, detail=f"Role '{x_role}' not authorized")
    return x_role


# ════════════════════════════════════════════════════════════
# ENDPOINT 1: Health Check
# GET /health
# ════════════════════════════════════════════════════════════

@app.get("/health")
def health():
    """System health check — used by Kubernetes liveness probe."""
    return {
        "status":  "healthy",
        "service": "PharmaSafe-AIOps",
        "version": "1.0.0"
    }


# ════════════════════════════════════════════════════════════
# ENDPOINT 2: Prometheus Metrics
# GET /metrics
# ════════════════════════════════════════════════════════════

@app.get("/metrics")
def metrics():
    """Expose Prometheus metrics — scraped by Grafana."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# ════════════════════════════════════════════════════════════
# ENDPOINT 3: Quick Drug Interaction Check (no patient)
# POST /drug-check
# ════════════════════════════════════════════════════════════

@app.post("/drug-check")
def drug_check(request: DrugCheckRequest, role: str = Depends(get_role)):
    """
    Check interactions between a list of drugs.
    Does NOT require a patient profile — useful for quick lookups.

    Example request body:
        {"drugs": ["warfarin", "aspirin", "ibuprofen"]}

    Example response:
        {
          "resolved_drugs": ["warfarin", "aspirin", "ibuprofen"],
          "unresolved_drugs": [],
          "interactions": [
            {
              "drug_1": "warfarin",
              "drug_2": "aspirin",
              "severity": "HIGH",
              "description": "...",
              "recommendation": "CONTRAINDICATED..."
            }
          ],
          "highest_severity": "HIGH"
        }
    """
    start = time.time()
    drug_checks_total.inc()

    result = get_drug_interactions(request.drugs)

    # Track high severity in Prometheus
    if result["highest_severity"] == "HIGH":
        high_severity_total.inc()

    # If patient ID provided, save to history and send alerts
    if request.patient_id:
        try:
            save_interaction_check(
                patient_id=request.patient_id,
                drugs=request.drugs,
                result=result,
                checked_by=request.checked_by or role
            )

            if result["highest_severity"] in ["HIGH", "MODERATE"]:
                patient = get_patient(request.patient_id)
                patient_name = patient["name"] if patient else request.patient_id
                alert_result = trigger_alerts(
                    patient_id=request.patient_id,
                    patient_name=patient_name,
                    severity=result["highest_severity"],
                    interactions=result["interactions"]
                )
                result["alerts_sent"] = alert_result
                alerts_sent_total.inc()
        except Exception as e:
            logger.warning(f"Could not save check or send alert: {e}")

    duration = time.time() - start
    check_latency.observe(duration)
    result["check_duration_ms"] = round(duration * 1000, 1)
    return result


# ════════════════════════════════════════════════════════════
# ENDPOINT 4: Get Drug Info
# GET /drug/{drug_name}
# ════════════════════════════════════════════════════════════

@app.get("/drug/{drug_name}")
def drug_info(drug_name: str, role: str = Depends(get_role)):
    """Look up a drug's RxCUI and basic properties from RxNorm."""
    info = get_drug_info(drug_name)
    if "error" in info:
        raise HTTPException(status_code=404, detail=info["error"])
    return info


# ════════════════════════════════════════════════════════════
# ENDPOINT 5: Create / Update Patient Profile
# POST /patient
# ════════════════════════════════════════════════════════════

@app.post("/patient", status_code=201)
def create_patient(request: PatientRequest, role: str = Depends(get_role)):
    """
    Create or update a patient record.
    Only Pharmacists, Doctors, and Admins can create patients.
    """
    if role == "Nurse":
        raise HTTPException(status_code=403,
                            detail="Nurses cannot create patient profiles")
    try:
        upsert_patient(request.patient_id, request.name,
                       request.age, request.ward)
        return {"message": "Patient saved", "patient_id": request.patient_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ════════════════════════════════════════════════════════════
# ENDPOINT 6: Get Patient Profile
# GET /patient/{patient_id}
# ════════════════════════════════════════════════════════════

@app.get("/patient/{patient_id}")
def get_patient_endpoint(patient_id: str, role: str = Depends(get_role)):
    """Get a patient's profile and their current medication list."""
    patient = get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404,
                            detail=f"Patient '{patient_id}' not found")
    return patient


# ════════════════════════════════════════════════════════════
# ENDPOINT 7: Add Medication to Patient
# POST /patient/{patient_id}/medication
# ════════════════════════════════════════════════════════════

@app.post("/patient/{patient_id}/medication", status_code=201)
def add_patient_medication(patient_id: str,
                            request: MedicationRequest,
                            role: str = Depends(get_role)):
    """
    Add a medication to a patient's profile.
    Automatically resolves drug name to RxCUI code.
    """
    # Verify patient exists
    patient = get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail=f"Patient '{patient_id}' not found")

    # Resolve RxCUI
    rxcui = get_rxcui(request.drug_name) or ""

    try:
        add_medication(patient_id, request.drug_name,
                       rxcui, request.dose, request.frequency)
        return {
            "message":   "Medication added",
            "drug_name": request.drug_name,
            "rxcui":     rxcui
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ════════════════════════════════════════════════════════════
# ENDPOINT 8: Remove Medication from Patient
# DELETE /patient/{patient_id}/medication/{drug_name}
# ════════════════════════════════════════════════════════════

@app.delete("/patient/{patient_id}/medication/{drug_name}")
def remove_patient_medication(patient_id: str,
                               drug_name: str,
                               role: str = Depends(get_role)):
    """
    Remove (soft-delete) a medication from a patient's profile.
    Only Pharmacists and Admins can remove medications.
    """
    if role in ["Nurse"]:
        raise HTTPException(status_code=403,
                            detail="Nurses cannot remove medications")
    try:
        remove_medication(patient_id, drug_name)
        return {"message": f"Medication '{drug_name}' removed from {patient_id}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ════════════════════════════════════════════════════════════
# ENDPOINT 9: Check All Current Patient Medications
# POST /patient/{patient_id}/check
# ════════════════════════════════════════════════════════════

@app.post("/patient/{patient_id}/check")
def check_patient_medications(patient_id: str,
                               checked_by: str = "system",
                               role: str = Depends(get_role)):
    """
    Run a drug interaction check on ALL of a patient's active medications.
    This is the main clinical use — press 'Check Interactions' for a patient.
    Automatically sends SMS/Email alert if HIGH or MODERATE severity found.
    """
    patient = get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail=f"Patient '{patient_id}' not found")

    medications = patient.get("medications", [])
    if len(medications) < 2:
        return {
            "patient_id":   patient_id,
            "patient_name": patient["name"],
            "message":      "Patient has fewer than 2 active medications — no interactions to check",
            "highest_severity": "NONE"
        }

    drug_names = [m["drug_name"] for m in medications]
    drug_checks_total.inc()

    result = get_drug_interactions(drug_names)

    # Save to history
    try:
        save_interaction_check(patient_id, drug_names, result, checked_by or role)
    except Exception as e:
        logger.warning(f"Could not save history: {e}")

    # Send alerts for HIGH / MODERATE
    if result["highest_severity"] in ["HIGH", "MODERATE"]:
        high_severity_total.inc()
        try:
            alert_result = trigger_alerts(
                patient_id=patient_id,
                patient_name=patient["name"],
                severity=result["highest_severity"],
                interactions=result["interactions"]
            )
            result["alerts_sent"] = alert_result
            alerts_sent_total.inc()
        except Exception as e:
            logger.warning(f"Alert failed: {e}")

    result["patient_id"]   = patient_id
    result["patient_name"] = patient["name"]
    result["ward"]         = patient["ward"]
    return result


# ════════════════════════════════════════════════════════════
# ENDPOINT 10: Get Patient Interaction History
# GET /patient/{patient_id}/history
# ════════════════════════════════════════════════════════════

@app.get("/patient/{patient_id}/history")
def patient_history(patient_id: str,
                    limit: int = 20,
                    role: str = Depends(get_role)):
    """Return the last N interaction checks for a patient."""
    try:
        history = get_patient_history(patient_id, limit)
        return {"patient_id": patient_id, "history": history}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ════════════════════════════════════════════════════════════
# ENDPOINT 11: List All Patients
# GET /patients
# ════════════════════════════════════════════════════════════

@app.get("/patients")
def list_patients(role: str = Depends(get_role)):
    """Return all patient profiles with medication count."""
    try:
        return {"patients": get_all_patients()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ════════════════════════════════════════════════════════════
# RUN DIRECTLY (for local development)
# ════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
