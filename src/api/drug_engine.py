# ============================================================
# FILE: src/api/drug_engine.py
# PURPOSE: Drug interaction engine using RxNav NIH API (FREE)
# No API key required — public NIH service
# ============================================================

import requests
import logging
from functools import lru_cache

logger = logging.getLogger(__name__)

RXNAV_BASE = "https://rxnav.nlm.nih.gov/REST"

# Severity mapping from RxNav codes to our labels
SEVERITY_MAP = {
    "high":          "HIGH",
    "moderate":      "MODERATE",
    "low":           "LOW",
    "N/A":           "UNKNOWN",
}

SEVERITY_COLOR = {
    "HIGH":          "CRITICAL",   # maps to red in dashboard
    "MODERATE":      "WARNING",    # maps to orange
    "LOW":           "CAUTION",    # maps to yellow
    "UNKNOWN":       "INFO",
}


@lru_cache(maxsize=512)
def get_rxcui(drug_name: str) -> str | None:
    """
    Convert a drug name (e.g. 'warfarin') to an RxCUI code (e.g. '202421').
    RxCUI = RxNorm Concept Unique Identifier — the standard drug ID.
    Results are cached so the same drug name is never looked up twice.
    """
    url = f"{RXNAV_BASE}/rxcui.json"
    params = {"name": drug_name.strip().lower(), "search": 1}
    try:
        resp = requests.get(url, params=params, timeout=8)
        resp.raise_for_status()
        data = resp.json()
        rxcui = data["idGroup"]["rxnormId"][0]
        logger.info(f"Resolved '{drug_name}' → RxCUI {rxcui}")
        return rxcui
    except Exception as e:
        logger.warning(f"Could not resolve drug '{drug_name}': {e}")
        return None


def get_drug_interactions(drug_names: list[str]) -> dict:
    """
    Main function — takes a list of drug names, resolves them to RxCUI codes,
    calls the RxNav interaction API, and returns structured results.

    Returns:
        {
          "resolved_drugs": [...],
          "unresolved_drugs": [...],
          "interactions": [...],
          "highest_severity": "HIGH" / "MODERATE" / "LOW" / "NONE"
        }
    """
    resolved   = {}   # drug_name → rxcui
    unresolved = []

    # Step 1: Resolve all drug names to RxCUI codes
    for name in drug_names:
        rxcui = get_rxcui(name)
        if rxcui:
            resolved[name] = rxcui
        else:
            unresolved.append(name)

    if len(resolved) < 2:
        return {
            "resolved_drugs":   list(resolved.keys()),
            "unresolved_drugs": unresolved,
            "interactions":     [],
            "highest_severity": "NONE",
            "message":          "Need at least 2 identifiable drugs to check interactions"
        }

    # Step 2: Call RxNav interaction list API
    rxcui_string = "+".join(resolved.values())
    url = f"{RXNAV_BASE}/interaction/list.json"
    params = {"rxcuis": rxcui_string}

    interactions = []
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        # Step 3: Parse interaction groups
        groups = data.get("fullInteractionTypeGroup", [])
        for group in groups:
            for itype in group.get("fullInteractionType", []):
                for pair in itype.get("interactionPair", []):
                    concepts = pair.get("interactionConcept", [])
                    if len(concepts) < 2:
                        continue

                    drug1 = concepts[0]["minConceptItem"]["name"]
                    drug2 = concepts[1]["minConceptItem"]["name"]
                    severity_raw = pair.get("severity", "N/A").lower()
                    severity     = SEVERITY_MAP.get(severity_raw, "UNKNOWN")
                    description  = pair.get("description", "No description available")

                    interactions.append({
                        "drug_1":      drug1,
                        "drug_2":      drug2,
                        "severity":    severity,
                        "alert_color": SEVERITY_COLOR.get(severity, "INFO"),
                        "description": description,
                        "recommendation": get_recommendation(severity),
                    })

    except Exception as e:
        logger.error(f"RxNav API error: {e}")

    # Step 4: Determine highest severity found
    severity_order = ["HIGH", "MODERATE", "LOW", "UNKNOWN", "NONE"]
    found_severities = [i["severity"] for i in interactions]
    highest = "NONE"
    for s in severity_order:
        if s in found_severities:
            highest = s
            break

    return {
        "resolved_drugs":   list(resolved.keys()),
        "unresolved_drugs": unresolved,
        "interactions":     interactions,
        "highest_severity": highest,
    }


def get_recommendation(severity: str) -> str:
    """Return a clinical recommendation based on severity level."""
    recs = {
        "HIGH":     "CONTRAINDICATED — Do not administer together. Contact prescriber immediately.",
        "MODERATE": "Use with caution. Monitor patient closely. Consider alternative drug.",
        "LOW":      "Minor interaction. Routine monitoring recommended.",
        "UNKNOWN":  "Insufficient data. Consult clinical pharmacist.",
    }
    return recs.get(severity, "Consult pharmacist for guidance.")


def get_drug_info(drug_name: str) -> dict:
    """Get basic drug information from RxNorm."""
    rxcui = get_rxcui(drug_name)
    if not rxcui:
        return {"error": f"Drug '{drug_name}' not found"}

    url = f"{RXNAV_BASE}/rxcui/{rxcui}/properties.json"
    try:
        resp = requests.get(url, timeout=8)
        data = resp.json()
        props = data.get("properties", {})
        return {
            "name":     props.get("name", drug_name),
            "rxcui":    rxcui,
            "synonym":  props.get("synonym", ""),
            "tty":      props.get("tty", ""),    # term type: IN=ingredient, BN=brand
        }
    except Exception as e:
        return {"error": str(e)}
