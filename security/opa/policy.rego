# ============================================================
# FILE: security/opa/policy.rego
# PURPOSE: Open Policy Agent (OPA) - Role-Based Access Control
#          Defines who can do what in PharmaSafe-AIOps
#
# ROLES:
#   Pharmacist  — full access (read + write + alerts + history)
#   ICU_Doctor  — can check interactions, view patients, add meds
#   Nurse       — can view patients and run checks (read-only on patients)
#   Admin       — full system access including user management
# ============================================================

package pharmasafe.authz

import future.keywords.if
import future.keywords.in

# ── DEFAULT: DENY ALL ────────────────────────────────────────
# By default, EVERYTHING is denied unless explicitly allowed.
# This is Zero Trust — we never trust unless proven.
default allow = false


# ── ADMIN: FULL ACCESS ────────────────────────────────────────
allow if {
    input.role == "Admin"
}


# ── PHARMACIST: FULL CLINICAL ACCESS ─────────────────────────
allow if {
    input.role == "Pharmacist"
    input.method in {"GET", "POST", "DELETE"}
    allowed_pharmacist_paths
}

allowed_pharmacist_paths if {
    # Pharmacists can access any drug/patient endpoint
    startswith(input.path, "/drug-check")
}
allowed_pharmacist_paths if {
    startswith(input.path, "/patient")
}
allowed_pharmacist_paths if {
    startswith(input.path, "/patients")
}
allowed_pharmacist_paths if {
    startswith(input.path, "/drug/")
}
allowed_pharmacist_paths if {
    input.path in {"/health", "/docs", "/redoc", "/metrics"}
}


# ── ICU DOCTOR: CLINICAL READ + CHECK ACCESS ─────────────────
allow if {
    input.role == "ICU_Doctor"
    input.method in {"GET", "POST"}
    allowed_doctor_paths
}

allowed_doctor_paths if {
    # Doctors can check interactions
    startswith(input.path, "/drug-check")
}
allowed_doctor_paths if {
    # Doctors can view patient info and history
    startswith(input.path, "/patient")
    input.method == "GET"
}
allowed_doctor_paths if {
    # Doctors can run interaction check on patient
    regex.match("^/patient/[^/]+/check$", input.path)
}
allowed_doctor_paths if {
    # Doctors can add medications
    regex.match("^/patient/[^/]+/medication$", input.path)
    input.method == "POST"
}
allowed_doctor_paths if {
    input.path in {"/patients", "/health", "/drug/"}
}


# ── NURSE: READ ONLY + RUN CHECKS ────────────────────────────
allow if {
    input.role == "Nurse"
    input.method == "GET"
    allowed_nurse_paths
}

# Nurses can also run the patient check (POST) but cannot modify records
allow if {
    input.role == "Nurse"
    regex.match("^/patient/[^/]+/check$", input.path)
    input.method == "POST"
}

allowed_nurse_paths if {
    startswith(input.path, "/patient")
}
allowed_nurse_paths if {
    input.path in {"/patients", "/health", "/drug-check"}
}


# ── PUBLIC PATHS: No auth required ────────────────────────────
allow if {
    input.path in {"/health", "/docs", "/openapi.json", "/redoc"}
}


# ── VIOLATIONS: Explain why access was denied ─────────────────
# This message is returned in the 403 response body.
violation[msg] if {
    not allow
    msg := sprintf(
        "Access denied: role '%v' cannot perform %v on %v",
        [input.role, input.method, input.path]
    )
}
