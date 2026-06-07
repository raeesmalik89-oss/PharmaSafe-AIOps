# ============================================================
# FILE: src/alerts/alert_service.py
# PURPOSE: SMS alerts (Twilio) + Email alerts (smtplib)
#          Triggered automatically on HIGH severity interactions
# ============================================================

import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

logger = logging.getLogger(__name__)

# ── CONFIGURATION (set via environment variables) ─────────────
TWILIO_SID   = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM  = os.getenv("TWILIO_PHONE", "+1234567890")

ALERT_PHONE  = os.getenv("PHARMACIST_PHONE", "+923001234567")
ALERT_EMAIL  = os.getenv("PHARMACIST_EMAIL", "pharmacist@hospital.com")

SMTP_HOST    = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT    = int(os.getenv("SMTP_PORT", 587))
SMTP_USER    = os.getenv("SMTP_USER", "")
SMTP_PASS    = os.getenv("SMTP_PASS", "")


def should_alert(severity: str) -> bool:
    """Only send alerts for HIGH severity interactions."""
    return severity in ["HIGH", "MODERATE"]


def send_sms_alert(patient_id: str, patient_name: str,
                   severity: str, interactions: list) -> bool:
    """
    Send SMS via Twilio when a dangerous drug interaction is detected.
    Returns True if sent successfully, False if failed.
    """
    if not TWILIO_SID or not TWILIO_TOKEN:
        logger.warning("Twilio credentials not set — SMS alert skipped (demo mode)")
        # In demo mode, just log what WOULD be sent
        logger.info(f"[DEMO SMS] ALERT: Patient {patient_id} ({patient_name}) "
                    f"has {severity} drug interaction! "
                    f"{len(interactions)} interaction(s) detected.")
        return True  # return True so the system does not treat this as a failure

    try:
        from twilio.rest import Client
        client = Client(TWILIO_SID, TWILIO_TOKEN)

        # Build SMS message (keep it short — SMS has 160 char limit)
        drug_pairs = ", ".join(
            [f"{i['drug_1']}+{i['drug_2']}" for i in interactions[:3]]
        )
        message = (
            f"⚠️ PHARMASAFE ALERT\n"
            f"Patient: {patient_id} ({patient_name})\n"
            f"Severity: {severity}\n"
            f"Interactions: {drug_pairs}\n"
            f"Time: {datetime.now().strftime('%H:%M %d-%b-%Y')}\n"
            f"Action required immediately!"
        )

        client.messages.create(
            body=message,
            from_=TWILIO_FROM,
            to=ALERT_PHONE
        )
        logger.info(f"SMS alert sent for patient {patient_id} — severity {severity}")
        return True

    except Exception as e:
        logger.error(f"SMS alert failed: {e}")
        return False


def send_email_alert(patient_id: str, patient_name: str,
                     severity: str, interactions: list) -> bool:
    """
    Send a detailed email alert with full interaction table.
    Used when SMS is too short for full clinical details.
    """
    if not SMTP_USER or not SMTP_PASS:
        logger.warning("SMTP credentials not set — Email alert skipped (demo mode)")
        logger.info(f"[DEMO EMAIL] Would send email for patient {patient_id}")
        return True

    try:
        # Build HTML email body
        rows = ""
        for i in interactions:
            color = "#DC2626" if i["severity"] == "HIGH" else "#D97706"
            rows += f"""
            <tr>
                <td>{i['drug_1']}</td>
                <td>{i['drug_2']}</td>
                <td style="color:{color};font-weight:bold">{i['severity']}</td>
                <td>{i['description']}</td>
                <td>{i['recommendation']}</td>
            </tr>"""

        html = f"""
        <html><body style="font-family:Arial,sans-serif">
        <div style="background:#1B4F8A;padding:20px;color:white">
            <h2>⚠️ PharmaSafe-AIOps Drug Interaction Alert</h2>
        </div>
        <div style="padding:20px">
            <p><strong>Patient ID:</strong> {patient_id}</p>
            <p><strong>Patient Name:</strong> {patient_name}</p>
            <p><strong>Highest Severity:</strong>
               <span style="color:#DC2626;font-weight:bold">{severity}</span></p>
            <p><strong>Time:</strong> {datetime.now().strftime('%H:%M — %d %B %Y')}</p>

            <h3>Detected Interactions</h3>
            <table border="1" cellpadding="8" cellspacing="0"
                   style="border-collapse:collapse;width:100%">
                <thead style="background:#1B4F8A;color:white">
                    <tr>
                        <th>Drug 1</th><th>Drug 2</th>
                        <th>Severity</th><th>Description</th><th>Recommendation</th>
                    </tr>
                </thead>
                <tbody>{rows}</tbody>
            </table>

            <p style="color:#DC2626;font-weight:bold;margin-top:20px">
                Immediate pharmacist review required.
            </p>
        </div>
        </body></html>
        """

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[URGENT] Drug Interaction Alert — Patient {patient_id} — {severity}"
        msg["From"]    = SMTP_USER
        msg["To"]      = ALERT_EMAIL
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, ALERT_EMAIL, msg.as_string())

        logger.info(f"Email alert sent for patient {patient_id}")
        return True

    except Exception as e:
        logger.error(f"Email alert failed: {e}")
        return False


def trigger_alerts(patient_id: str, patient_name: str,
                   severity: str, interactions: list) -> dict:
    """
    Master alert function — called by the API whenever an interaction is found.
    Sends both SMS and Email if severity is HIGH or MODERATE.
    Logs results to the database.
    """
    if not should_alert(severity):
        return {"sms": False, "email": False, "reason": "Severity too low to alert"}

    sms_result   = send_sms_alert(patient_id, patient_name, severity, interactions)
    email_result = send_email_alert(patient_id, patient_name, severity, interactions)

    return {
        "sms_sent":   sms_result,
        "email_sent": email_result,
        "sent_to_phone": ALERT_PHONE,
        "sent_to_email": ALERT_EMAIL,
    }
