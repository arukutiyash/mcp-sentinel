"""
Seed the database with demo users, vendors, and two purchase-order
scenarios:

  1. A CLEAN flow: PO issued -> goods received with evidence -> standard
     payment requested -> approved -> released. Vendor ends with a low
     risk score.

  2. A CAUGHT flow: PO issued -> a superintendent requests prepayment
     before anything is received -> the system requires a written
     justification and blocks release until a SECOND, independent
     approver (finance) also signs off -- the exact control that was
     missing in the real April 2026 GSD case this project is modeled on.
     Vendor ends with an elevated risk score and visible signals.

Run with: python -m app.seed
"""
from .database import SessionLocal, Base, engine
from . import models, auth

Base.metadata.create_all(bind=engine)


def run():
    db = SessionLocal()
    if db.query(models.User).first():
        print("Database already seeded, skipping.")
        return

    buyer = auth.create_user(db, "j.buyer", "Jamie Ortiz", models.Role.BUYER, "demo1234")
    clerk = auth.create_user(db, "r.clerk", "Riley Chen", models.Role.RECEIVING_CLERK, "demo1234")
    supt = auth.create_user(db, "s.superintendent", "Sam Alvarez", models.Role.SUPERINTENDENT, "demo1234")
    finance = auth.create_user(db, "f.approver", "Farah Nasser", models.Role.FINANCE_APPROVER, "demo1234")
    auditor = auth.create_user(db, "a.auditor", "Ari Kim", models.Role.AUDITOR, "demo1234")

    reliable_vendor = models.Vendor(name="Civic Supply Co.", contact_email="ap@civicsupply.example")
    risky_vendor = models.Vendor(name="Harbor Lift Systems", contact_email="billing@harborlift.example")
    db.add_all([reliable_vendor, risky_vendor])
    db.commit()

    # --- Scenario 1: clean flow -------------------------------------------------
    po1 = models.PurchaseOrder(
        po_number="GSD-PO-100001", vendor_id=reliable_vendor.id, created_by_user_id=buyer.id,
        description="Office and janitorial supplies restock - City Hall East",
        total_amount=4200.00, status=models.POStatus.ISSUED,
    )
    db.add(po1); db.flush()
    li1 = models.LineItem(po_id=po1.id, item_description="Case of copy paper", quantity_ordered=200, unit_price=21.00)
    db.add(li1); db.commit()

    rr1 = models.ReceivingRecord(
        line_item_id=li1.id, received_by_user_id=clerk.id, quantity_received=200,
        serial_or_asset_tag="PALLET-SC-0091", evidence_note="200 cases counted on pallet, photo logged, matches packing slip #8831.",
    )
    db.add(rr1)
    po1.status = models.POStatus.RECEIVED
    db.commit()

    pr1 = models.PaymentRequest(po_id=po1.id, requested_by_user_id=buyer.id, amount=4200.00, is_prepayment=False)
    db.add(pr1); db.commit()
    a1 = models.Approval(payment_request_id=pr1.id, approver_user_id=supt.id, approver_role=models.Role.SUPERINTENDENT, decision="APPROVE")
    db.add(a1); pr1.status = models.PaymentStatus.APPROVED; db.commit()
    pr1.status = models.PaymentStatus.RELEASED
    db.commit()

    # --- Scenario 2: high-risk prepayment, caught by dual-approval + evidence ---
    po2 = models.PurchaseOrder(
        po_number="GSD-PO-100002", vendor_id=risky_vendor.id, created_by_user_id=buyer.id,
        description="Two hydraulic vehicle lifts - Fleet Services yard",
        total_amount=460972.00, status=models.POStatus.ISSUED,
    )
    db.add(po2); db.flush()
    li2 = models.LineItem(po_id=po2.id, item_description="Hydraulic vehicle lift, heavy duty", quantity_ordered=2, unit_price=230486.00)
    db.add(li2); db.commit()

    # A prepayment is requested before ANY receiving record exists -- this is
    # allowed, but only down the justified, dual-approval path.
    pr2 = models.PaymentRequest(
        po_id=po2.id, requested_by_user_id=supt.id, amount=460972.00, is_prepayment=True,
        justification="Vendor requires payment in advance to begin fabrication; supply chain "
                       "delay risk per email thread #4471. Escalated for dual sign-off per policy.",
    )
    db.add(pr2); db.commit()

    # Superintendent approves first.
    a2 = models.Approval(payment_request_id=pr2.id, approver_user_id=supt.id,
                          approver_role=models.Role.SUPERINTENDENT, decision="APPROVE",
                          comment="Justification reviewed, escalating to Finance for second sign-off.")
    db.add(a2); db.commit()
    # Only ONE distinct approver role so far -> status stays PENDING, cannot be released.
    # (This models the moment the real GSD case failed: a single verbal sign-off.
    #  Here the system will not release funds until Finance also decides.)
    pr2.status = models.PaymentStatus.PENDING
    db.commit()
    db.close()

    # Re-query everything fresh, on a brand-new session, for the summary
    # printout below -- avoids any dependency on the original session's
    # internal state after a long chain of commits/flushes.
    fresh = SessionLocal()
    vendor_rows = [(v.name, v.id) for v in fresh.query(models.Vendor).all()]
    login_rows = [(u.username, u.role.value) for u in fresh.query(models.User).order_by(models.User.username).all()]
    fresh.close()

    print("Seed complete.")
    for name, vid in vendor_rows:
        print(f"  Vendor: {name} ({vid})")
    print("  Demo logins (password 'demo1234' for all):")
    for username, role in login_rows:
        print(f"    {username:20s} role={role}")


if __name__ == "__main__":
    run()
