from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import Base, engine
from .routers import (
    auth_router, vendors_router, purchase_orders_router,
    receiving_router, payments_router, audit_router,
)

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="MCP Sentinel — GSD Procurement Integrity Platform",
    description="Receiving verification, dual-approval prepayments, and an "
                 "immutable audit trail for City of LA General Services "
                 "Department purchase orders.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(vendors_router.router)
app.include_router(purchase_orders_router.router)
app.include_router(receiving_router.router)
app.include_router(payments_router.router)
app.include_router(audit_router.router)


@app.get("/health")
def health():
    return {"status": "ok"}
