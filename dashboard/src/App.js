// ============================================================
// FILE: dashboard/src/App.js
// PURPOSE: React frontend for PharmaSafe-AIOps
//          Role-based drug interaction dashboard for
//          Pharmacists, ICU Doctors, and Nurses
// ============================================================

import { useState, useEffect, useCallback } from "react";
import "./App.css";

const API_BASE = process.env.REACT_APP_API_URL || "http://localhost:8000";

// ── SEVERITY COLOR MAP ────────────────────────────────────────
const SEVERITY_STYLE = {
  HIGH:     { bg: "#FEE2E2", border: "#DC2626", text: "#DC2626", label: "🔴 HIGH — CONTRAINDICATED" },
  MODERATE: { bg: "#FEF3C7", border: "#D97706", text: "#D97706", label: "🟡 MODERATE — Use with Caution" },
  LOW:      { bg: "#DCFCE7", border: "#16A34A", text: "#16A34A", label: "🟢 LOW — Routine Monitoring" },
  NONE:     { bg: "#F0FDF4", border: "#86EFAC", text: "#15803D", label: "✅ SAFE — No Interactions Found" },
  UNKNOWN:  { bg: "#F1F5F9", border: "#94A3B8", text: "#475569", label: "⚪ UNKNOWN — Consult Pharmacist" },
};

// ── API HELPERS ───────────────────────────────────────────────
async function apiFetch(path, options = {}, role = "Pharmacist") {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", "X-Role": role },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "API error");
  }
  return res.json();
}

// ── COMPONENT: Severity Badge ─────────────────────────────────
function SeverityBadge({ severity }) {
  const style = SEVERITY_STYLE[severity] || SEVERITY_STYLE.UNKNOWN;
  return (
    <span
      style={{
        background: style.bg,
        border: `2px solid ${style.border}`,
        color: style.text,
        padding: "4px 12px",
        borderRadius: "20px",
        fontWeight: "bold",
        fontSize: "13px",
      }}
    >
      {style.label}
    </span>
  );
}

// ── COMPONENT: Quick Drug Check ────────────────────────────────
function QuickDrugCheck({ role }) {
  const [drugs, setDrugs]       = useState("");
  const [result, setResult]     = useState(null);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState("");

  const handleCheck = async () => {
    const drugList = drugs.split(",").map((d) => d.trim()).filter(Boolean);
    if (drugList.length < 2) {
      setError("Enter at least 2 drug names separated by commas");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const data = await apiFetch("/drug-check", {
        method: "POST",
        body: JSON.stringify({ drugs: drugList }),
      }, role);
      setResult(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="card">
      <h2>💊 Quick Drug Interaction Check</h2>
      <p className="subtitle">Enter drug names separated by commas</p>

      <div className="input-row">
        <input
          type="text"
          placeholder="e.g. warfarin, aspirin, heparin"
          value={drugs}
          onChange={(e) => setDrugs(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleCheck()}
          className="drug-input"
        />
        <button onClick={handleCheck} disabled={loading} className="btn-primary">
          {loading ? "Checking..." : "Check Interactions"}
        </button>
      </div>

      {error && <div className="error-box">{error}</div>}

      {result && (
        <div className="result-box">
          <div className="severity-header">
            <SeverityBadge severity={result.highest_severity} />
            <span className="check-time">{result.check_duration_ms}ms</span>
          </div>

          {result.unresolved_drugs?.length > 0 && (
            <div className="warning-box">
              ⚠️ Unrecognised drugs: {result.unresolved_drugs.join(", ")}
            </div>
          )}

          {result.interactions?.length === 0 ? (
            <p className="no-interactions">No drug interactions found.</p>
          ) : (
            <table className="interaction-table">
              <thead>
                <tr>
                  <th>Drug 1</th>
                  <th>Drug 2</th>
                  <th>Severity</th>
                  <th>Description</th>
                  <th>Recommendation</th>
                </tr>
              </thead>
              <tbody>
                {result.interactions.map((i, idx) => (
                  <tr
                    key={idx}
                    style={{
                      background: SEVERITY_STYLE[i.severity]?.bg || "#fff",
                    }}
                  >
                    <td><strong>{i.drug_1}</strong></td>
                    <td><strong>{i.drug_2}</strong></td>
                    <td>
                      <span style={{ color: SEVERITY_STYLE[i.severity]?.text, fontWeight: "bold" }}>
                        {i.severity}
                      </span>
                    </td>
                    <td className="description-cell">{i.description}</td>
                    <td className="recommendation-cell">{i.recommendation}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {result.alerts_sent && (
            <div className="alert-status">
              📲 SMS Alert: {result.alerts_sent.sms_sent ? "✅ Sent" : "❌ Failed"} |{" "}
              📧 Email Alert: {result.alerts_sent.email_sent ? "✅ Sent" : "❌ Failed"}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── COMPONENT: Patient Panel ───────────────────────────────────
function PatientPanel({ role }) {
  const [patients, setPatients]       = useState([]);
  const [selected, setSelected]       = useState(null);
  const [checkResult, setCheckResult] = useState(null);
  const [loading, setLoading]         = useState(false);
  const [newDrug, setNewDrug]         = useState({ drug_name: "", dose: "", frequency: "" });

  const loadPatients = useCallback(async () => {
    try {
      const data = await apiFetch("/patients", {}, role);
      setPatients(data.patients || []);
    } catch (e) {
      console.error("Could not load patients:", e);
    }
  }, [role]);

  const selectPatient = async (patientId) => {
    try {
      const data = await apiFetch(`/patient/${patientId}`, {}, role);
      setSelected(data);
      setCheckResult(null);
    } catch (e) {
      console.error("Could not load patient:", e);
    }
  };

  const checkPatientMeds = async () => {
    if (!selected) return;
    setLoading(true);
    try {
      const data = await apiFetch(
        `/patient/${selected.patient_id}/check?checked_by=${role}`,
        { method: "POST" }, role
      );
      setCheckResult(data);
    } catch (e) {
      console.error("Check failed:", e);
    } finally {
      setLoading(false);
    }
  };

  const addMedication = async () => {
    if (!selected || !newDrug.drug_name) return;
    try {
      await apiFetch(`/patient/${selected.patient_id}/medication`, {
        method: "POST",
        body: JSON.stringify(newDrug),
      }, role);
      setNewDrug({ drug_name: "", dose: "", frequency: "" });
      await selectPatient(selected.patient_id);
    } catch (e) {
      alert(e.message);
    }
  };

  const removeMedication = async (drugName) => {
    if (!window.confirm(`Remove ${drugName} from this patient?`)) return;
    try {
      await apiFetch(`/patient/${selected.patient_id}/medication/${drugName}`,
        { method: "DELETE" }, role);
      await selectPatient(selected.patient_id);
    } catch (e) {
      alert(e.message);
    }
  };

  useEffect(() => { loadPatients(); }, [loadPatients]);

  return (
    <div className="patient-panel">
      {/* Patient List */}
      <div className="patient-list">
        <h3>👥 Patients</h3>
        <button onClick={loadPatients} className="btn-secondary">Refresh</button>
        {patients.map((p) => (
          <div
            key={p.patient_id}
            className={`patient-card ${selected?.patient_id === p.patient_id ? "selected" : ""}`}
            onClick={() => selectPatient(p.patient_id)}
          >
            <div className="patient-name">{p.name}</div>
            <div className="patient-meta">
              {p.patient_id} | {p.ward} | {p.medication_count} meds
            </div>
          </div>
        ))}
        {patients.length === 0 && (
          <p className="empty-state">No patients found. Add via API POST /patient</p>
        )}
      </div>

      {/* Patient Detail */}
      {selected && (
        <div className="patient-detail">
          <h3>🏥 {selected.name}</h3>
          <p>
            <strong>ID:</strong> {selected.patient_id} |{" "}
            <strong>Age:</strong> {selected.age} |{" "}
            <strong>Ward:</strong> {selected.ward}
          </p>

          {/* Medications */}
          <h4>💊 Current Medications</h4>
          {selected.medications?.length === 0 ? (
            <p className="empty-state">No active medications</p>
          ) : (
            <table className="med-table">
              <thead>
                <tr><th>Drug</th><th>Dose</th><th>Frequency</th>{role !== "Nurse" && <th>Action</th>}</tr>
              </thead>
              <tbody>
                {selected.medications.map((m) => (
                  <tr key={m.drug_name}>
                    <td>{m.drug_name}</td>
                    <td>{m.dose}</td>
                    <td>{m.frequency}</td>
                    {role !== "Nurse" && (
                      <td>
                        <button className="btn-danger-sm"
                          onClick={() => removeMedication(m.drug_name)}>
                          Remove
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {/* Add Medication (Pharmacist / Doctor only) */}
          {role !== "Nurse" && (
            <div className="add-med-form">
              <h4>➕ Add Medication</h4>
              <div className="form-row">
                <input placeholder="Drug name" value={newDrug.drug_name}
                  onChange={(e) => setNewDrug({...newDrug, drug_name: e.target.value})} />
                <input placeholder="Dose (e.g. 5mg)" value={newDrug.dose}
                  onChange={(e) => setNewDrug({...newDrug, dose: e.target.value})} />
                <input placeholder="Frequency (e.g. once daily)" value={newDrug.frequency}
                  onChange={(e) => setNewDrug({...newDrug, frequency: e.target.value})} />
                <button onClick={addMedication} className="btn-primary">Add</button>
              </div>
            </div>
          )}

          {/* Check Interactions Button */}
          <button
            onClick={checkPatientMeds}
            disabled={loading || (selected.medications?.length || 0) < 2}
            className="btn-check"
          >
            {loading ? "Checking..." : "🔍 Check All Medications"}
          </button>

          {/* Results */}
          {checkResult && (
            <div className="result-box" style={{ marginTop: "16px" }}>
              <SeverityBadge severity={checkResult.highest_severity} />
              {checkResult.interactions?.length > 0 && (
                <table className="interaction-table" style={{ marginTop: "12px" }}>
                  <thead>
                    <tr><th>Drug 1</th><th>Drug 2</th><th>Severity</th><th>Recommendation</th></tr>
                  </thead>
                  <tbody>
                    {checkResult.interactions.map((i, idx) => (
                      <tr key={idx} style={{ background: SEVERITY_STYLE[i.severity]?.bg }}>
                        <td>{i.drug_1}</td>
                        <td>{i.drug_2}</td>
                        <td style={{ color: SEVERITY_STYLE[i.severity]?.text, fontWeight: "bold" }}>
                          {i.severity}
                        </td>
                        <td>{i.recommendation}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {checkResult.alerts_sent && (
                <div className="alert-status">
                  📲 SMS: {checkResult.alerts_sent.sms_sent ? "✅ Sent" : "—"} |
                  📧 Email: {checkResult.alerts_sent.email_sent ? "✅ Sent" : "—"}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── MAIN APP ──────────────────────────────────────────────────
export default function App() {
  const [role, setRole]   = useState("Pharmacist");
  const [tab, setTab]     = useState("check");

  const roles = ["Pharmacist", "ICU_Doctor", "Nurse", "Admin"];

  return (
    <div className="app">
      {/* Header */}
      <header className="app-header">
        <div className="header-left">
          <span className="logo">💊</span>
          <div>
            <h1>PharmaSafe-AIOps</h1>
            <p>Real-Time Drug Interaction Checker</p>
          </div>
        </div>
        <div className="header-right">
          <label>Role:</label>
          <select
            value={role}
            onChange={(e) => setRole(e.target.value)}
            className="role-select"
          >
            {roles.map((r) => (
              <option key={r} value={r}>{r}</option>
            ))}
          </select>
          <span className={`role-badge role-${role.toLowerCase().replace("_", "-")}`}>
            {role}
          </span>
        </div>
      </header>

      {/* Navigation Tabs */}
      <nav className="tab-nav">
        <button
          className={tab === "check" ? "tab active" : "tab"}
          onClick={() => setTab("check")}
        >
          🔍 Drug Check
        </button>
        <button
          className={tab === "patients" ? "tab active" : "tab"}
          onClick={() => setTab("patients")}
        >
          👥 Patients
        </button>
      </nav>

      {/* Tab Content */}
      <main className="app-main">
        {tab === "check"    && <QuickDrugCheck role={role} />}
        {tab === "patients" && <PatientPanel role={role} />}
      </main>

      <footer className="app-footer">
        PharmaSafe-AIOps | Powered by NIH RxNav API | AIOps Level 6 Project
      </footer>
    </div>
  );
}
