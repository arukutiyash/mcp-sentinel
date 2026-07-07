"""
GSD Procurement Integrity MCP Server.

Exposes the platform's procurement-integrity data as MCP tools so an
auditor -- human or AI agent -- can ask natural-language questions like
"which vendors look risky this quarter?" without writing SQL or learning
the REST API. This is the "API/MCP calls" component of the technical
packet: the FastAPI service in backend/ is the transactional web API that
buyers/clerks/approvers use to run the process; this MCP server is a
separate, read-only tool surface for oversight and analysis.

Run with:  python server.py
(stdio transport -- add this as an MCP server in Claude Desktop, or any
other MCP host, pointing at this file.)
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

from mcp.server.fastmcp import FastMCP
from app.database import SessionLocal
from app import models, analytics

mcp = FastMCP("gsd-procurement-integrity")


def _po_summary(po: models.PurchaseOrder) -> dict:
    return {
        "po_number": po.po_number,
        "vendor": po.vendor.name,
        "description": po.description,
        "total_amount": po.total_amount,
        "status": po.status.value,
        "created_at": po.created_at.isoformat(),
        "expected_delivery_date": po.expected_delivery_date.isoformat() if po.expected_delivery_date else None,
    }


@mcp.tool()
def list_purchase_orders(status: str | None = None, vendor_name: str | None = None) -> list[dict]:
    """List purchase orders, optionally filtered by status
    (ISSUED, PARTIALLY_RECEIVED, RECEIVED, CLOSED, FLAGGED) and/or vendor name
    (substring match)."""
    db = SessionLocal()
    try:
        q = db.query(models.PurchaseOrder)
        if status:
            q = q.filter(models.PurchaseOrder.status == status.upper())
        if vendor_name:
            q = q.join(models.Vendor).filter(models.Vendor.name.ilike(f"%{vendor_name}%"))
        return [_po_summary(po) for po in q.order_by(models.PurchaseOrder.created_at.desc()).all()]
    finally:
        db.close()


@mcp.tool()
def get_po_detail(po_number: str) -> dict:
    """Get full detail for one purchase order by its po_number (e.g.
    'GSD-PO-100002'): line items, receiving records (with evidence), and
    every payment request and its approvals."""
    db = SessionLocal()
    try:
        po = db.query(models.PurchaseOrder).filter(models.PurchaseOrder.po_number == po_number).first()
        if not po:
            return {"error": f"No purchase order found with po_number={po_number}"}
        return {
            **_po_summary(po),
            "line_items": [
                {
                    "item_description": li.item_description,
                    "quantity_ordered": li.quantity_ordered,
                    "unit_price": li.unit_price,
                    "receiving_records": [
                        {
                            "quantity_received": r.quantity_received,
                            "serial_or_asset_tag": r.serial_or_asset_tag,
                            "evidence_note": r.evidence_note,
                            "received_by": r.received_by_user_id,
                            "received_at": r.received_at.isoformat(),
                        }
                        for r in li.receiving_records
                    ],
                }
                for li in po.line_items
            ],
            "payment_requests": [
                {
                    "amount": pr.amount,
                    "is_prepayment": pr.is_prepayment,
                    "justification": pr.justification,
                    "status": pr.status.value,
                    "approvals": [
                        {"approver_role": a.approver_role.value, "decision": a.decision, "comment": a.comment}
                        for a in pr.approvals
                    ],
                }
                for pr in po.payment_requests
            ],
        }
    finally:
        db.close()


@mcp.tool()
def get_vendor_risk_score(vendor_name: str) -> dict:
    """Get the rule-based fraud/waste risk score (0-100) and the specific
    signals behind it for a vendor, by name (substring match on the first
    match)."""
    db = SessionLocal()
    try:
        vendor = db.query(models.Vendor).filter(models.Vendor.name.ilike(f"%{vendor_name}%")).first()
        if not vendor:
            return {"error": f"No vendor found matching '{vendor_name}'"}
        score, signals = analytics.vendor_risk(db, vendor)
        return {"vendor_name": vendor.name, "risk_score": score, "signals": signals}
    finally:
        db.close()


@mcp.tool()
def list_flagged_anomalies() -> list[dict]:
    """List every vendor with a non-zero risk score, highest risk first --
    the auditor's daily worklist."""
    db = SessionLocal()
    try:
        results = []
        for vendor in db.query(models.Vendor).all():
            score, signals = analytics.vendor_risk(db, vendor)
            if score > 0:
                results.append({"vendor_name": vendor.name, "risk_score": score, "signals": signals})
        results.sort(key=lambda r: r["risk_score"], reverse=True)
        return results
    finally:
        db.close()


@mcp.tool()
def get_audit_trail(entity_type: str, entity_id: str) -> list[dict]:
    """Get the immutable audit log for a specific entity (entity_type is
    one of PurchaseOrder, LineItem, PaymentRequest; entity_id is that
    row's id, as returned by the other tools/REST API)."""
    db = SessionLocal()
    try:
        rows = db.query(models.AuditLog).filter(
            models.AuditLog.entity_type == entity_type,
            models.AuditLog.entity_id == entity_id,
        ).order_by(models.AuditLog.created_at.asc()).all()
        return [
            {
                "action": r.action,
                "actor_user_id": r.actor_user_id,
                "detail": r.detail,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]
    finally:
        db.close()


if __name__ == "__main__":
    mcp.run()
