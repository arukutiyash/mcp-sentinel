# Technical Implementation Guide — MCP Sentinel (GSD Procurement Integrity Platform)

This document is written to be sufficient, on its own, for an AI coding
agent to regenerate a functionally equivalent application: exact schema,
exact business-rule algorithms, exact API contract, exact frontend
behavior. Follow the sections in order; later sections depend on earlier
ones.

## 0. Stack and conventions

- Backend: Python 3.10+, FastAPI, SQLAlchemy 2.x ORM, Pydantic 2.x, SQLite.
- MCP layer: the `mcp` Python SDK (`FastMCP`), stdio transport, sharing
  the backend's SQLAlchemy models against the same SQLite file.
- Frontend: a single HTML page loading React 18, ReactDOM 18, and
  Babel Standalone from a CDN (cdnjs), with the app written in one
  `app.js` file using in-browser JSX transpilation — no npm build step.
- All entity primary keys are `str` UUID4 values generated with
  `uuid.uuid4()`.
- All timestamps are UTC, `datetime.utcnow()`, stored as SQLite DATETIME.
- Every mutating HTTP endpoint requires a bearer token
  (`Authorization: Bearer <token>`) mapping to exactly one authenticated
  user; there is no concept of an API key or service account anywhere in
  the system.

## 1. Database schema

Create these tables (SQLAlchemy declarative models, one class per
table). Field lists are exhaustive — do not add columns beyond what is
listed; the business logic in section 3 depends on exactly this shape.

**users**: id (PK str), username (str, unique), full_name (str), role
(enum: BUYER, RECEIVING_CLERK, SUPERINTENDENT, FINANCE_APPROVER,
AUDITOR), password_hash (str), password_salt (str), created_at.

**sessions**: token (PK str), user_id (FK users.id), created_at,
expires_at.

**vendors**: id (PK str), name (str), contact_email (str, nullable),
created_at.

**purchase_orders**: id (PK str), po_number (str, unique, format
`GSD-PO-{6 random digits}`), vendor_id (FK vendors.id),
created_by_user_id (FK users.id), description (str), total_amount
(float — sum of `quantity_ordered * unit_price` across all line items
at creation time), status (enum: ISSUED, PARTIALLY_RECEIVED, RECEIVED,
CLOSED, FLAGGED; default ISSUED), expected_delivery_date (datetime,
nullable), created_at.

**line_items**: id (PK str), po_id (FK purchase_orders.id),
item_description (str), quantity_ordered (int), unit_price (float).

**receiving_records**: id (PK str), line_item_id (FK line_items.id),
received_by_user_id (FK users.id), quantity_received (int),
serial_or_asset_tag (str, required, non-blank), evidence_note (str,
required, non-blank), received_at. These rows are never updated or
deleted by the application — corrections are new rows.

**payment_requests**: id (PK str), po_id (FK purchase_orders.id),
requested_by_user_id (FK users.id), amount (float), is_prepayment
(bool, default False), justification (str, nullable), status (enum:
PENDING, APPROVED, REJECTED, RELEASED; default PENDING), created_at.

**approvals**: id (PK str), payment_request_id (FK
payment_requests.id), approver_user_id (FK users.id), approver_role
(enum, snapshot of the approver's role at decision time), decision
(str: "APPROVE" or "REJECT"), comment (str, nullable), decided_at.

**audit_log**: id (PK str), actor_user_id (FK users.id), action (str),
entity_type (str), entity_id (str), detail (str, JSON-encoded dict),
created_at. Append-only: no endpoint ever updates or deletes a row here.

Use a single SQLite file (`procurement.db`, in the backend directory)
read from a `DATABASE_URL` environment variable defaulting to that file,
so the same code can point at Postgres later by changing only that
variable. Configure the session factory with `expire_on_commit=False`
so that Python object references remain valid for reading after a
`commit()` without an extra round trip — this matters because several
endpoints read attributes off an object shortly after committing it.

## 2. Authentication and authorization (`auth.py`)

- `hash_password(password, salt)`: `sha256(salt + password)`, hex digest.
  (Documented simplification for a review sandbox — a real deployment
  should use bcrypt/argon2 instead; nothing else in the design changes.)
- `create_user(db, username, full_name, role, password)`: generates a
  random 16-byte hex salt, stores `(salt, hash)`, commits, returns the
  user.
- `authenticate(db, username, password)`: looks up by username, compares
  hash; raises HTTP 401 on any mismatch (do not distinguish "no such
  user" from "wrong password" in the error message).
- `issue_session(db, user)`: creates a `sessions` row with a fresh UUID
  token and a 12-hour expiry; returns it.
- `get_current_user(authorization_header, db)`: FastAPI dependency.
  Requires a `Bearer <token>` header, looks up the session, checks it
  has not expired, returns the associated user. This is the *only* way
  any endpoint identifies a caller — there is no alternate/service-account
  auth path.
- `require_role(*allowed_roles)`: returns a FastAPI dependency that calls
  `get_current_user` and then raises HTTP 403 if the user's role is not
  in `allowed_roles`.

## 3. Core business-rule algorithms

These are the algorithms that encode the fix described in
`business_statement.md`. Implement each exactly as specified — the
control only works if the rules are enforced server-side, not merely
suggested in the UI.

### 3.1 Create purchase order — `POST /purchase-orders` (role: BUYER)

1. Validate the vendor exists and at least one line item was supplied.
2. Generate a unique `po_number` (`GSD-PO-` + 6 random digits, retry on
   collision).
3. `total_amount = sum(qty * unit_price for each line item)`.
4. Insert the PurchaseOrder (status `ISSUED`) and its LineItem rows in
   one transaction.
5. Write an audit log entry: action `CREATE_PO`, entity_type
   `PurchaseOrder`, detail includes po_number, total_amount, vendor_id.

### 3.2 Record receiving — `POST /receiving` (role: RECEIVING_CLERK)

1. Look up the line item; 404 if not found.
2. Reject with HTTP 400 if `serial_or_asset_tag` or `evidence_note` is
   blank after stripping whitespace, or if `quantity_received` is not
   greater than zero — this is the direct fix for the real incident
   where undelivered goods were marked received with no corroborating
   evidence.
3. **Guard against over-receiving.** Sum `quantity_received` across all
   existing ReceivingRecord rows already on this line item to get
   `already_received`. Compute `remaining = quantity_ordered -
   already_received`. If the incoming `quantity_received` exceeds
   `remaining`, reject with HTTP 400 (message should explain how many
   units actually remain outstanding and instruct the caller not to
   simply resubmit, but to flag the discrepancy to an auditor instead).
   This closes off both an accidental duplicate submission (e.g. a
   double-click on "Record receiving") and a deliberate attempt to
   over-report delivered quantity — a line item's recorded received
   quantity must never be allowed to exceed what was actually ordered.
4. Insert a ReceivingRecord attributed to the authenticated clerk
   (`received_by_user_id = current_user.id`), never to a passed-in or
   default identity.
5. Recompute the parent PO's status: for every line item on the PO, sum
   `quantity_received` across all of its receiving records. If every
   line item's summed received quantity is `>=` its `quantity_ordered`,
   set PO status to `RECEIVED`. Otherwise, if at least one unit across
   any line item has been received, set status to `PARTIALLY_RECEIVED`.
   Otherwise leave status unchanged.
6. Write an audit log entry: action `RECORD_RECEIVING`, entity_type
   `LineItem`, detail includes quantity_received, serial_or_asset_tag,
   po_id.

### 3.3 Request payment — `POST /payment-requests` (role: BUYER or SUPERINTENDENT)

1. Look up the PO; 404 if missing.
2. If `is_prepayment` is true: require a non-blank `justification`
   (HTTP 400 "Prepayment requests must include a written justification
   (City Charter compliance)" otherwise). This path is intentionally
   *not* blocked outright — legitimate prepayments happen — it is routed
   through mandatory documentation and (see 3.4) dual approval instead.
3. If `is_prepayment` is false: require every line item on the PO to be
   fully received (same check as 3.2 step 5); HTTP 400 otherwise,
   pointing the caller at the prepayment path.
4. Insert the PaymentRequest with status `PENDING`.
5. Audit log: action `REQUEST_PAYMENT`.

### 3.4 Approve/reject — `POST /payment-requests/{id}/decide` (role: SUPERINTENDENT or FINANCE_APPROVER)

1. Look up the payment request; 404 if missing. Reject (HTTP 400) if its
   status is not PENDING or APPROVED (i.e., already REJECTED or
   RELEASED — decisions are final).
2. Query the `approvals` table directly by `payment_request_id` and
   `approver_user_id` to check whether this user already recorded a
   decision on this request; reject with HTTP 400 if so. **Implementation
   note:** query the database directly rather than relying on an
   in-memory relationship collection on the just-loaded PaymentRequest
   object — an ORM relationship collection populated before this
   request's own not-yet-flushed rows exist will not reflect rows
   inserted earlier in the same function unless it is reloaded, which is
   an easy source of a stale-approval-count bug.
3. Validate `decision` is `APPROVE` or `REJECT`.
4. Insert an Approval row: `approver_role` = the deciding user's *current*
   role (snapshotted, not looked up dynamically later).
5. If `decision == REJECT`: set payment request status to `REJECTED`.
6. If `decision == APPROVE`: re-query all APPROVE-decision approvals for
   this payment request from the database (same reasoning as step 2),
   collect the **distinct set of approver roles** among them. Required
   distinct-role count is **2 if `is_prepayment` is true, else 1**. If
   the distinct-role count meets the requirement, set status to
   `APPROVED`. This is the segregation-of-duties control: a prepayment
   needs sign-off from two *different* roles (e.g., Superintendent and
   Finance) — the same person approving twice, or two people with the
   same role approving, must not satisfy the requirement, since the
   real incident was caused by exactly one person's unilateral say-so.
7. Audit log: action `PAYMENT_APPROVE` or `PAYMENT_REJECT`, detail
   includes resulting status and the approver's role.

### 3.5 Release payment — `POST /payment-requests/{id}/release` (role: FINANCE_APPROVER only)

1. Look up the payment request; 404 if missing.
2. Reject (HTTP 400) unless status is exactly `APPROVED`.
3. Set status to `RELEASED`.
4. Audit log: action `RELEASE_PAYMENT`.

Releasing is deliberately a separate, separately-logged step from
approving, and restricted to Finance only, so that no single approval
action can itself move money — approval and release are two different
people's actions even in the non-prepayment path (a Superintendent can
approve; only Finance can release).

### 3.6 Vendor risk scoring (`analytics.py`)

Rule-based and fully transparent (no black-box model), so the reasoning
is auditable. For a given vendor, gather all of its purchase orders,
then all payment requests against those POs:

- **HIGH_PREPAYMENT_RATIO**: if `prepayment_requests / total_requests`
  for that vendor exceeds 0.5, add 40 to the risk score and emit a
  signal string with the exact ratio.
- **SINGLE_APPROVER_OVERRIDE**: for any RELEASED payment request that
  is a prepayment, check the distinct approver roles among its APPROVE
  decisions; if fewer than 2, add 50 (this should be unreachable through
  the API given section 3.4, but is checked for defense in depth and
  would indicate a bypass).
- **RECEIVED_QTY_MISMATCH**: for each line item across the vendor's POs,
  if the summed received quantity is nonzero and does not equal
  `quantity_ordered`, add 15 per mismatched line item.
- Cap the total score at 100. If no signals fired, report a single
  "No anomaly signals detected" signal and score 0.

## 4. REST API surface

All endpoints below (except `/auth/login` and `/health`) require the
`Authorization: Bearer <token>` header.

| Method | Path | Role required | Body / query | Returns |
|---|---|---|---|---|
| POST | `/auth/login` | none | `{username, password}` | `{token, user_id, full_name, role}` |
| GET | `/auth/me` | any authenticated | — | current user |
| GET | `/vendors` | any authenticated | — | list of vendors |
| GET | `/vendors/{id}/risk` | any authenticated | — | `{vendor_id, vendor_name, risk_score, signals[]}` |
| POST | `/purchase-orders` | BUYER | `{vendor_id, description, expected_delivery_date?, line_items[]}` | created PO with line items |
| GET | `/purchase-orders` | any authenticated | — | list of POs, newest first |
| GET | `/purchase-orders/{id}` | any authenticated | — | PO with line items, each including its `receiving_records[]` |
| POST | `/receiving` | RECEIVING_CLERK | `{line_item_id, quantity_received, serial_or_asset_tag, evidence_note}` | created receiving record |
| POST | `/payment-requests` | BUYER, SUPERINTENDENT | `{po_id, amount, is_prepayment, justification?}` | created payment request |
| GET | `/payment-requests?po_id=` | any authenticated | optional `po_id` filter | list of payment requests |
| POST | `/payment-requests/{id}/decide` | SUPERINTENDENT, FINANCE_APPROVER | `{decision: APPROVE\|REJECT, comment?}` | updated payment request |
| POST | `/payment-requests/{id}/release` | FINANCE_APPROVER | — | updated payment request |
| GET | `/audit?entity_type=&entity_id=` | any authenticated | optional filters | list of audit log entries, newest first |
| GET | `/health` | none | — | `{status: "ok"}` |

Enable permissive CORS (`allow_origins=["*"]`) since the frontend is
served from a different port/origin than the API in local/demo use.

## 5. MCP tool server (`mcp_server/server.py`)

Using `mcp.server.fastmcp.FastMCP`, register these five read-only
tools, each opening its own short-lived SQLAlchemy session against the
same `procurement.db` used by the backend (import the backend's
`database` and `models` modules rather than duplicating the schema):

1. `list_purchase_orders(status?, vendor_name?)` — filter by exact
   status and/or case-insensitive substring vendor name match; return
   summaries (po_number, vendor, description, total_amount, status,
   dates).
2. `get_po_detail(po_number)` — full detail: line items, each with its
   receiving records (quantity, tag, evidence note, who, when), and all
   payment requests with their approvals.
3. `get_vendor_risk_score(vendor_name)` — runs the same `analytics.vendor_risk`
   function the REST API uses, so the two surfaces can never disagree.
4. `list_flagged_anomalies()` — every vendor with risk score > 0, sorted
   descending.
5. `get_audit_trail(entity_type, entity_id)` — the audit log for one
   entity, chronological.

Run this as a separate OS process from the FastAPI server (`python
server.py`, stdio transport) and register it with an MCP host (for
example, as a custom MCP server in Claude Desktop) to query it in
natural language.

## 6. Frontend (`frontend/index.html`, `app.js`, `styles.css`)

Single HTML file loads React 18 UMD, ReactDOM 18 UMD, and Babel
Standalone from `cdnjs.cloudflare.com`, then `app.js` with
`type="text/babel"` so JSX is transpiled in the browser — no build
tooling required to run the frontend.

`app.js` structure (all in one file, functional components with hooks):

- `apiFetch(path, token, options)`: thin wrapper over `fetch` that sets
  `Authorization: Bearer <token>` when present, parses JSON, and throws
  on non-2xx responses using the API's `detail` field as the message.
- `LoginScreen`: username/password form, calls `POST /auth/login`, hands
  `{token, user_id, full_name, role}` up to the root component on
  success. Displays the five demo usernames and shared demo password so
  a reviewer can self-serve every role.
- `Dashboard`: fetches all vendors, then each vendor's risk score in
  parallel, renders a table color-coded by score (>=40 red, >=15 amber,
  else green) with the signal strings underneath.
- `POList`: fetches all purchase orders and a vendor id→name map,
  renders a clickable table; clicking a row opens `PODetail` for that
  PO's id.
- `NewPO`: visible only to BUYER role. Vendor dropdown, description
  field, and a dynamic list of line-item rows (description/qty/unit
  price) with an "add line item" button. Submits to `POST
  /purchase-orders`.
- `PODetail`: fetches one PO plus its payment requests. Renders:
  - a line-items table showing ordered vs. received quantity (summed
    from `receiving_records`) and each receiving record's evidence
    note/tag/date;
  - for RECEIVING_CLERK only, an inline form per line item to submit
    `POST /receiving`;
  - a payment-requests table with Approve/Reject buttons (visible to
    SUPERINTENDENT/FINANCE_APPROVER, only on PENDING requests) and a
    Release button (FINANCE_APPROVER only, only on APPROVED requests);
  - for BUYER/SUPERINTENDENT, a form to submit a new payment request,
    with a "prepayment" checkbox that reveals a required justification
    textarea when checked;
  - an "Audit trail" button per PO and per payment request that switches
    the app to the Audit tab filtered to that entity.
- `AuditView`: fetches `/audit`, optionally filtered by entity, renders
  chronological entries (action, entity, actor id, timestamp, JSON
  detail).
- `Shell`: top bar (title, current user's name/role badge, sign-out) and
  a tab nav (Dashboard / Purchase Orders / New PO / Audit Trail) that
  swaps between the components above.
- `App`: root component. Holds `{token, user}` in React state,
  persisted to `localStorage` under key `gsd_session` so a page refresh
  does not force re-login; renders `LoginScreen` when absent, `Shell`
  otherwise.

Role-based UI visibility (`NewPO` for BUYER; receiving form for
RECEIVING_CLERK; decide/release buttons for SUPERINTENDENT/
FINANCE_APPROVER) is a UX convenience only — the same restrictions are
independently enforced server-side per section 3, so hiding a button
never substitutes for an authorization check.

## 7. Seed data (`backend/app/seed.py`)

Idempotent (checks `if any user exists, skip`). Creates five users, one
per role, all with password `demo1234`, and two vendors/scenarios:

- **Civic Supply Co.** — a clean flow: PO for copy paper, fully received
  with evidence, standard (non-prepayment) payment requested, approved
  by one Superintendent, released by Finance. Ends with risk score 0.
- **Harbor Lift Systems** — modeled directly on the real incident: a PO
  for "Two hydraulic vehicle lifts" totaling **$460,972** (matching the
  real case's dollar figure), with a prepayment requested and justified
  *before* any receiving record exists. Only the Superintendent has
  approved when seeding stops (status remains PENDING) — a reviewer can
  then use the Finance Approver login to supply the second, independent
  sign-off and watch the status move to APPROVED and then RELEASED,
  reproducing the exact control the real case lacked. Because this
  vendor's payment history is 100% prepayment, it appears on the risk
  dashboard immediately with a HIGH_PREPAYMENT_RATIO signal.

## 8. Running the project

```bash
# Backend
cd backend
pip install -r requirements.txt
python -m app.seed          # creates and seeds procurement.db
uvicorn app.main:app --host 0.0.0.0 --port 8000

# MCP server (separate terminal, same machine)
cd mcp_server
pip install -r requirements.txt
python server.py

# Frontend (separate terminal)
cd frontend
python -m http.server 8080
# open http://localhost:8080 in a browser
```

Log in as `s.superintendent` / `demo1234` and `f.approver` / `demo1234`
(in two browser sessions, or sign out/in between) against the Harbor
Lift Systems PO to walk through the dual-approval prepayment path
end-to-end; log in as `j.buyer` and `r.clerk` to walk through the clean
receiving-then-payment path on a new PO.
