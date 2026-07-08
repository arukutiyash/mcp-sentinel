# Logical Structure — MCP Sentinel (GSD Procurement Integrity Platform)

## 1. System ecosystem

Three independent processes share one SQLite database file
(`backend/procurement.db`):

```mermaid
flowchart LR
    subgraph Browser["Browser (any user)"]
        FE["Frontend<br/>index.html + app.js<br/>React (CDN, no build step)"]
    end

    subgraph Backend["FastAPI process :8000"]
        API["REST API<br/>(auth, purchase-orders,<br/>receiving, payment-requests,<br/>vendors, audit)"]
    end

    subgraph MCPProc["MCP Server process (stdio)"]
        MCP["FastMCP tools:<br/>list_purchase_orders,<br/>get_po_detail,<br/>get_vendor_risk_score,<br/>list_flagged_anomalies,<br/>get_audit_trail"]
    end

    DB[("SQLite<br/>procurement.db")]

    Agent["MCP host<br/>(e.g. Claude Desktop,<br/>an auditor's AI agent)"]

    FE -- "fetch() JSON over HTTP,\nBearer token" --> API
    API -- "SQLAlchemy ORM" --> DB
    MCP -- "SQLAlchemy ORM\n(read-only queries)" --> DB
    Agent -- "MCP protocol (stdio)" --> MCP
```

Two independent client surfaces read from and write to the same data:
the FastAPI REST API is the **transactional** surface (buyers, receiving
clerks, and approvers do their day-to-day work through it, via the
React frontend). The MCP server is a **read-only oversight** surface —
an auditor or an AI agent asks it natural-language-adjacent questions
("which vendors look risky?") without needing to know SQL or the REST
API shape.

## 2. Entity-relationship diagram

```mermaid
erDiagram
    USER ||--o{ SESSION : "has"
    USER ||--o{ PURCHASE_ORDER : "creates (created_by_user_id)"
    USER ||--o{ RECEIVING_RECORD : "records (received_by_user_id)"
    USER ||--o{ PAYMENT_REQUEST : "requests (requested_by_user_id)"
    USER ||--o{ APPROVAL : "decides (approver_user_id)"
    USER ||--o{ AUDIT_LOG : "acts as (actor_user_id)"

    VENDOR ||--o{ PURCHASE_ORDER : "supplies"

    PURCHASE_ORDER ||--o{ LINE_ITEM : "contains"
    PURCHASE_ORDER ||--o{ PAYMENT_REQUEST : "is paid via"

    LINE_ITEM ||--o{ RECEIVING_RECORD : "is fulfilled by"

    PAYMENT_REQUEST ||--o{ APPROVAL : "collects"

    USER {
        string id PK
        string username UK
        string full_name
        string role "BUYER | RECEIVING_CLERK | SUPERINTENDENT | FINANCE_APPROVER | AUDITOR"
        string password_hash
        string password_salt
    }
    SESSION {
        string token PK
        string user_id FK
        datetime expires_at
    }
    VENDOR {
        string id PK
        string name
        string contact_email
    }
    PURCHASE_ORDER {
        string id PK
        string po_number UK
        string vendor_id FK
        string created_by_user_id FK
        string description
        float total_amount
        string status "ISSUED | PARTIALLY_RECEIVED | RECEIVED | CLOSED | FLAGGED"
        datetime expected_delivery_date
    }
    LINE_ITEM {
        string id PK
        string po_id FK
        string item_description
        int quantity_ordered
        float unit_price
    }
    RECEIVING_RECORD {
        string id PK
        string line_item_id FK
        string received_by_user_id FK
        int quantity_received
        string serial_or_asset_tag
        string evidence_note
        datetime received_at
    }
    PAYMENT_REQUEST {
        string id PK
        string po_id FK
        string requested_by_user_id FK
        float amount
        bool is_prepayment
        string justification
        string status "PENDING | APPROVED | REJECTED | RELEASED"
    }
    APPROVAL {
        string id PK
        string payment_request_id FK
        string approver_user_id FK
        string approver_role
        string decision "APPROVE | REJECT"
        string comment
    }
    AUDIT_LOG {
        string id PK
        string actor_user_id FK
        string action
        string entity_type
        string entity_id
        string detail "JSON"
        datetime created_at
    }
```

## 3. Data flow — the control this project exists to enforce

```mermaid
sequenceDiagram
    actor Buyer
    actor Clerk as Receiving Clerk
    actor Supt as Superintendent
    actor Fin as Finance Approver

    Buyer->>API: POST /purchase-orders (vendor, line items)
    API-->>Buyer: PO { status: ISSUED }

    alt Standard path (goods arrive first)
        Clerk->>API: POST /receiving (line_item_id, qty, tag, evidence_note)
        API->>API: recompute PO status -> RECEIVED
        Buyer->>API: POST /payment-requests (is_prepayment=false)
        API->>API: reject unless PO fully RECEIVED
        Supt->>API: POST /payment-requests/{id}/decide APPROVE
        API->>API: 1 approval role suffices -> status APPROVED
        Fin->>API: POST /payment-requests/{id}/release
        API-->>Fin: status RELEASED
    else Prepayment path (payment must precede delivery)
        Supt->>API: POST /payment-requests (is_prepayment=true, justification=required)
        API->>API: reject if justification blank
        Supt->>API: POST /payment-requests/{id}/decide APPROVE
        API->>API: only 1 distinct approver role -> stays PENDING
        Fin->>API: POST /payment-requests/{id}/release
        API-->>Fin: 400 "Only APPROVED requests can be released"
        Fin->>API: POST /payment-requests/{id}/decide APPROVE
        API->>API: 2 distinct approver roles -> status APPROVED
        Fin->>API: POST /payment-requests/{id}/release
        API-->>Fin: status RELEASED
    end

    Note over API: Every step above also writes one AuditLog row,<br/>attributed to the authenticated caller.
```

## 4. Module layout

```
gsd-procurement-integrity/
  backend/
    requirements.txt
    procurement.db              (created at first run)
    app/
      __init__.py
      main.py                   FastAPI app, router registration, CORS, table creation
      database.py                SQLAlchemy engine/session (SQLite by default)
      models.py                  ORM models (see ERD above)
      schemas.py                 Pydantic request/response models
      auth.py                    password hashing, session tokens, RBAC dependency
      audit.py                   log_action() helper -- append-only audit writes
      analytics.py                vendor_risk() rule-based scoring
      seed.py                    demo data: one clean flow, one caught-fraud flow
      routers/
        auth_router.py            POST /auth/login, GET /auth/me
        vendors_router.py         GET /vendors, GET /vendors/{id}/risk
        purchase_orders_router.py  POST/GET /purchase-orders, GET /purchase-orders/{id}
        receiving_router.py        POST /receiving
        payments_router.py         POST /payment-requests, POST .../decide, POST .../release
        audit_router.py            GET /audit
  mcp_server/
    requirements.txt
    server.py                    FastMCP tools reading the same DB read-only
  frontend/
    index.html                   loads React/ReactDOM/Babel from CDN, then app.js
    app.js                       single-file React app (Login, Dashboard, PO List/Detail,
                                  New PO form, Audit Trail view)
    styles.css
  docs/
    business_statement.md
    logical_structure.md          (this file)
    technical_implementation_guide.md
```

## 5. Why SQLite + no build step

The project intentionally avoids infrastructure that a reviewer (or an
LLM regenerating it from these docs) would need to stand up separately:
one SQLite file instead of a Postgres server, and a CDN-loaded,
Babel-in-browser React setup instead of a Vite/webpack build pipeline.
`database.py` reads `DATABASE_URL` from the environment, so pointing the
same code at Postgres in a real deployment is a one-line change, not a
rewrite.
