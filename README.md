# PharmaSafe-AIOps 💊
### Real-Time Drug Interaction Checker — Full AIOps Stack

**Built by:** Muhammad Raees | AIOps EduQual Level 6 | Alnafi International College  
**DockerHub:** `mraees1989/pharmasafe-aiops:latest`  
**API Docs:** `http://localhost:8000/docs`

---

## What Is This?

PharmaSafe-AIOps is a production-grade drug interaction checking system for hospitals.  
It uses the **NIH RxNav free API** (no API key required) to check dangerous drug combinations in real time.

**Who uses it:**
- **Pharmacists** — check and manage all patient medications
- **ICU Doctors** — verify prescriptions before ordering
- **Nurses** — view patient profiles and run interaction checks

---

## Architecture

```
Hospital Pharmacy System
         │
         ▼
  Kafka Producer ──────────────────────────────────────────┐
  (sends prescription events)                              │
                                                           │
  Kafka Topic: pharmasafe.prescriptions                    │
         │                                                 │
         ▼                                                 │
  Kafka Consumer                                           │
  (reads events, calls API)                                │
         │                                                 │
         ▼                                                 │
  FastAPI Backend ──────────────────────── RxNav NIH API   │
  (drug_engine.py)      checks drugs →    (free, no key)   │
         │                                                 │
         ▼                                                 │
  PostgreSQL DB                                            │
  (patients, meds, history)                                │
         │                                                 │
         ▼                                                 │
  Alert Service ◄──────────────────────────────────────────┘
  SMS (Twilio) + Email (SMTP)
         │
         ▼
  React Dashboard
  (role-based: Pharmacist / ICU_Doctor / Nurse)
         │
         ▼
  Kubernetes (K3s) ─── OPA (RBAC) ─── Prometheus + Grafana
```

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend API | FastAPI (Python) |
| Drug Database | NIH RxNav API (free, no key needed) |
| Streaming | Apache Kafka |
| Database | PostgreSQL |
| Security | OPA (Open Policy Agent) — Rego RBAC |
| Frontend | React.js |
| Container | Docker |
| Orchestration | Kubernetes (K3s) |
| CI/CD | GitHub Actions |
| Monitoring | Prometheus + Grafana |
| SMS Alerts | Twilio |
| Email Alerts | SMTP (Gmail) |

---

## Project Structure

```
PharmaSafe-AIOps/
├── src/
│   ├── api/
│   │   ├── app.py              # Main FastAPI app — all 11 endpoints
│   │   └── drug_engine.py      # RxNav API calls + severity logic
│   ├── kafka/
│   │   ├── prescription_producer.py  # Sends prescriptions to Kafka
│   │   └── prescription_consumer.py  # Reads Kafka → calls API
│   ├── database/
│   │   └── db.py               # PostgreSQL patient profiles + history
│   └── alerts/
│       └── alert_service.py    # Twilio SMS + SMTP Email alerts
├── security/opa/
│   └── policy.rego             # Role-Based Access Control rules
├── dashboard/src/
│   ├── App.js                  # React dashboard (role-based views)
│   └── App.css                 # Professional medical styling
├── k8s/
│   └── deployment.yaml         # Kubernetes deployments + services
├── .github/workflows/
│   └── docker.yml              # GitHub Actions CI/CD pipeline
├── Dockerfile                  # Container build instructions
├── requirements.txt            # Python dependencies
└── README.md                   # This file
```

---

## API Endpoints

| Method | Path | Description | Who Can Access |
|--------|------|-------------|----------------|
| GET | `/health` | System health check | Everyone |
| GET | `/metrics` | Prometheus metrics | Everyone |
| POST | `/drug-check` | Check interactions for drug list | All roles |
| GET | `/drug/{name}` | Get drug info from RxNorm | All roles |
| POST | `/patient` | Create/update patient | Pharmacist, Doctor, Admin |
| GET | `/patients` | List all patients | All roles |
| GET | `/patient/{id}` | Get patient + medications | All roles |
| POST | `/patient/{id}/medication` | Add medication | Pharmacist, Doctor, Admin |
| DELETE | `/patient/{id}/medication/{drug}` | Remove medication | Pharmacist, Admin |
| POST | `/patient/{id}/check` | Check all patient meds | All roles |
| GET | `/patient/{id}/history` | Interaction check history | All roles |

---

## How To Run (Local Development)

### Step 1: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 2: Start PostgreSQL
```bash
docker run -d --name pharmasafe-db \
  -e POSTGRES_DB=pharmasafe \
  -e POSTGRES_USER=pharmasafe \
  -e POSTGRES_PASSWORD=pharmasafe123 \
  -p 5432:5432 \
  postgres:15
```

### Step 3: Start Kafka
```bash
docker run -d --name zookeeper -p 2181:2181 \
  -e ZOOKEEPER_CLIENT_PORT=2181 confluentinc/cp-zookeeper:7.4.0

docker run -d --name kafka -p 9092:9092 \
  -e KAFKA_BROKER_ID=1 \
  -e KAFKA_ZOOKEEPER_CONNECT=host.docker.internal:2181 \
  -e KAFKA_ADVERTISED_LISTENERS=PLAINTEXT://localhost:9092 \
  -e KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR=1 \
  confluentinc/cp-kafka:7.4.0
```

### Step 4: Start the API
```bash
uvicorn src.api.app:app --host 0.0.0.0 --port 8000 --reload
```

### Step 5: Open API Docs
```
http://localhost:8000/docs
```

### Step 6: Start Kafka Producer (new terminal)
```bash
python src/kafka/prescription_producer.py
```

### Step 7: Start Kafka Consumer (new terminal)
```bash
python src/kafka/prescription_consumer.py
```

### Step 8: Start React Dashboard
```bash
cd dashboard
npm install
npm start
# Opens at http://localhost:3000
```

---

## How To Run (Docker)

```bash
# Pull from DockerHub
docker pull mraees1989/pharmasafe-aiops:latest

# Run the API
docker run -p 8000:8000 \
  -e DB_HOST=host.docker.internal \
  mraees1989/pharmasafe-aiops:latest
```

---

## How To Deploy on Kubernetes (K3s)

```bash
# Apply all resources
kubectl apply -f k8s/deployment.yaml

# Check pods are running
kubectl get pods -n pharmasafe

# Access API at
http://<your-server-ip>:30392/docs
```

---

## Example: Check Drug Interactions via API

```bash
curl -X POST http://localhost:8000/drug-check \
  -H "Content-Type: application/json" \
  -H "X-Role: Pharmacist" \
  -d '{"drugs": ["warfarin", "aspirin", "heparin"]}'
```

**Response:**
```json
{
  "resolved_drugs": ["warfarin", "aspirin", "heparin"],
  "unresolved_drugs": [],
  "interactions": [
    {
      "drug_1": "warfarin",
      "drug_2": "aspirin",
      "severity": "HIGH",
      "description": "Increased risk of bleeding...",
      "recommendation": "CONTRAINDICATED — Do not administer together."
    }
  ],
  "highest_severity": "HIGH",
  "alerts_sent": {
    "sms_sent": true,
    "email_sent": true
  }
}
```

---

## Environment Variables

Set in Kubernetes Secret or `.env` file:

| Variable | Description |
|----------|-------------|
| `DB_HOST` | PostgreSQL host |
| `DB_PASSWORD` | Database password |
| `TWILIO_ACCOUNT_SID` | Twilio account SID |
| `TWILIO_AUTH_TOKEN` | Twilio auth token |
| `TWILIO_PHONE` | Your Twilio phone number |
| `PHARMACIST_PHONE` | Alert SMS recipient |
| `PHARMACIST_EMAIL` | Alert email recipient |
| `SMTP_USER` | Gmail address for alerts |
| `SMTP_PASS` | Gmail app password |

---

## Severity Levels

| Severity | Meaning | Action |
|----------|---------|--------|
| HIGH 🔴 | Contraindicated — dangerous combination | Do NOT administer. Alert sent immediately. |
| MODERATE 🟡 | Use with caution | Monitor patient closely. Alert sent. |
| LOW 🟢 | Minor interaction | Routine monitoring. No alert. |
| NONE ✅ | No interaction found | Safe to proceed. |

---

## CI/CD Pipeline

Every push to `main` branch automatically:
1. Runs tests with pytest
2. Builds Docker image
3. Pushes to `mraees1989/pharmasafe-aiops:latest` on DockerHub
4. Tags image with git commit SHA for rollback

---

## Drug Interaction Data Source

All drug interaction data comes from the **NIH National Library of Medicine RxNav API**:
- URL: `https://rxnav.nlm.nih.gov/REST/`
- **Free** — no API key required
- Used by hospitals, pharmacies, and clinical systems worldwide
- Updated regularly by the NLM

---

*PharmaSafe-AIOps — AIOps EduQual Level 6 Final Project | Alnafi International College*
