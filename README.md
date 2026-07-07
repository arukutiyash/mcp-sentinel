# GSD Procurement Integrity Platform

A purchase-order and payment workflow application built for the City of
Los Angeles Department of General Services (DGS/GSD) internship sample
project. It is modeled directly on a real April 2026 LA City Controller
Fraud, Waste and Abuse investigation in which GSD paid a vendor
**$460,972 for two lifts that were never delivered**, after a shared
login made the false "received" entry unattributable to any one person.

This project makes that failure mode structurally impossible: every
action is tied to one authenticated user, goods can't be marked received
without evidence, and payments before delivery require a documented,
dual-approval sign-off instead of one person's verbal say-so.

## Submission packet

| Component | File |
|---|---|
| 1. Business Statement | [`docs/business_statement.md`](docs/business_statement.md) |
| 2. Logical Structure Document | [`docs/logical_structure.md`](docs/logical_structure.md) |
| 3. Technical Implementation Guide | [`docs/technical_implementation_guide.md`](docs/technical_implementation_guide.md) |
| 4. Application Code | [`backend/`](backend), [`mcp_server/`](mcp_server), [`frontend/`](frontend) |

## Quick start

```bash
# 1. Backend API
cd backend
pip install -r requirements.txt
python -m app.seed
uvicorn app.main:app --host 0.0.0.0 --port 8000

# 2. MCP tool server (separate terminal) — natural-language querying
#    of procurement data for an auditor or AI agent
cd mcp_server
pip install -r requirements.txt
python server.py

# 3. Frontend (separate terminal)
cd frontend
python -m http.server 8080
# then open http://localhost:8080
```

Demo logins (password `demo1234` for all): `j.buyer`, `r.clerk`,
`s.superintendent`, `f.approver`, `a.auditor`.

The seed data includes two scenarios: a clean purchase-to-payment flow
(Civic Supply Co.), and a prepayment on hold pending a second approver's
sign-off (Harbor Lift Systems, PO amount matching the real $460,972
incident this project responds to) — log in as `s.superintendent` then
`f.approver` to complete that second scenario and watch the vendor's
risk score and audit trail update.

## Why this stack

SQLite (no external DB server) and a CDN-loaded, build-step-free React
frontend, so the whole thing runs from a clone with nothing beyond
`pip install`. See `docs/technical_implementation_guide.md` for the full
build specification.
