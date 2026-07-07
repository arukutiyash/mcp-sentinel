"""
Vendor risk scoring and anomaly detection.

This is intentionally simple, transparent, rule-based scoring (not a black
box) so a reviewer or an auditor agent calling the MCP tools can see
exactly why a vendor was flagged. Each signal below is a direct response
to a failure mode identified in real GSD Fraud, Waste & Abuse
investigations (see docs/business_statement.md):

  - HIGH_PREPAYMENT_RATIO  -> vendor is frequently paid before delivery,
                               which is exactly how the $460,972
                               undelivered-lifts payment happened.
  - RECEIVED_QTY_MISMATCH  -> quantity received does not match quantity
                               ordered, a sign of a rushed or fabricated
                               receiving entry.
  - SINGLE_APPROVER_OVERRIDE -> a prepayment reached RELEASED status with
                               fewer than 2 independent approvals, meaning
                               the segregation-of-duties control was
                               bypassed (should not be reachable through
                               the API, but is checked for defense in
                               depth and reported if ever found).
"""
from sqlalchemy.orm import Session as DBSession
from . import models

PREPAYMENT_RATIO_THRESHOLD = 0.5


def vendor_risk(db: DBSession, vendor: models.Vendor):
    pos = db.query(models.PurchaseOrder).filter(models.PurchaseOrder.vendor_id == vendor.id).all()
    po_ids = [p.id for p in pos]
    signals = []
    score = 0

    if po_ids:
        payment_requests = db.query(models.PaymentRequest).filter(
            models.PaymentRequest.po_id.in_(po_ids)
        ).all()
        if payment_requests:
            prepay_count = sum(1 for pr in payment_requests if pr.is_prepayment)
            ratio = prepay_count / len(payment_requests)
            if ratio > PREPAYMENT_RATIO_THRESHOLD:
                score += 40
                signals.append(
                    f"HIGH_PREPAYMENT_RATIO: {prepay_count}/{len(payment_requests)} "
                    f"payment requests ({ratio:.0%}) requested before delivery confirmed"
                )
            for pr in payment_requests:
                if pr.status == models.PaymentStatus.RELEASED and pr.is_prepayment:
                    approvals = [a for a in pr.approvals if a.decision == "APPROVE"]
                    distinct_roles = {a.approver_role for a in approvals}
                    if len(distinct_roles) < 2:
                        score += 50
                        signals.append(
                            f"SINGLE_APPROVER_OVERRIDE: prepayment {pr.id} released with "
                            f"{len(distinct_roles)} approver role(s), expected 2"
                        )

        for po in pos:
            for li in po.line_items:
                received_qty = sum(r.quantity_received for r in li.receiving_records)
                if received_qty and received_qty != li.quantity_ordered:
                    score += 15
                    signals.append(
                        f"RECEIVED_QTY_MISMATCH: line item '{li.item_description}' on "
                        f"{po.po_number} ordered {li.quantity_ordered}, received {received_qty}"
                    )

    score = min(score, 100)
    if not signals:
        signals.append("No anomaly signals detected")
    return score, signals
