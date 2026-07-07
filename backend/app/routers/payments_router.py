from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession

from .. import schemas, models, auth
from ..database import get_db
from ..audit import log_action

router = APIRouter(prefix="/payment-requests", tags=["payments"])

APPROVER_ROLES = (models.Role.SUPERINTENDENT, models.Role.FINANCE_APPROVER)


def _po_fully_received(po: models.PurchaseOrder) -> bool:
    for li in po.line_items:
        if sum(r.quantity_received for r in li.receiving_records) < li.quantity_ordered:
            return False
    return True


@router.post("", response_model=schemas.PaymentRequestOut)
def create_payment_request(
    payload: schemas.PaymentRequestIn,
    db: DBSession = Depends(get_db),
    user=Depends(auth.require_role(models.Role.BUYER, models.Role.SUPERINTENDENT)),
):
    po = db.query(models.PurchaseOrder).get(payload.po_id)
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")

    if payload.is_prepayment:
        # This is the exact scenario the April 2026 GSD FWA investigation
        # flagged: paying before goods are confirmed received. It is not
        # blocked outright (legitimate prepayments do happen), but it is
        # forced through a documented, dual-approval path instead of a
        # verbal go-ahead from a single superintendent.
        if not payload.justification or not payload.justification.strip():
            raise HTTPException(
                status_code=400,
                detail="Prepayment requests must include a written justification (City Charter compliance)",
            )
    else:
        if not _po_fully_received(po):
            raise HTTPException(
                status_code=400,
                detail="Cannot request standard payment before all line items are received. "
                       "Set is_prepayment=true with a justification if payment must precede delivery.",
            )

    pr = models.PaymentRequest(
        po_id=po.id,
        requested_by_user_id=user.id,
        amount=payload.amount,
        is_prepayment=payload.is_prepayment,
        justification=payload.justification,
    )
    db.add(pr)
    db.commit()
    db.refresh(pr)
    log_action(db, user.id, "REQUEST_PAYMENT", "PaymentRequest", pr.id, {
        "po_id": po.id, "amount": payload.amount, "is_prepayment": payload.is_prepayment
    })
    return pr


@router.get("", response_model=list[schemas.PaymentRequestOut])
def list_payment_requests(po_id: str | None = None, db: DBSession = Depends(get_db),
                           user=Depends(auth.get_current_user)):
    q = db.query(models.PaymentRequest)
    if po_id:
        q = q.filter(models.PaymentRequest.po_id == po_id)
    return q.order_by(models.PaymentRequest.created_at.desc()).all()


@router.post("/{pr_id}/decide", response_model=schemas.PaymentRequestOut)
def decide_payment_request(
    pr_id: str,
    payload: schemas.ApprovalIn,
    db: DBSession = Depends(get_db),
    user=Depends(auth.require_role(*APPROVER_ROLES)),
):
    pr = db.query(models.PaymentRequest).get(pr_id)
    if not pr:
        raise HTTPException(status_code=404, detail="Payment request not found")
    if pr.status not in (models.PaymentStatus.PENDING, models.PaymentStatus.APPROVED):
        raise HTTPException(status_code=400, detail=f"Payment request already {pr.status.value}")

    existing = db.query(models.Approval).filter(
        models.Approval.payment_request_id == pr.id,
        models.Approval.approver_user_id == user.id,
    ).all()
    if existing:
        raise HTTPException(status_code=400, detail="You have already recorded a decision on this request")

    decision = payload.decision.upper()
    if decision not in ("APPROVE", "REJECT"):
        raise HTTPException(status_code=400, detail="decision must be APPROVE or REJECT")

    approval = models.Approval(
        payment_request_id=pr.id, approver_user_id=user.id,
        approver_role=user.role, decision=decision, comment=payload.comment,
    )
    db.add(approval)
    db.flush()

    if decision == "REJECT":
        pr.status = models.PaymentStatus.REJECTED
    else:
        approvals = db.query(models.Approval).filter(
            models.Approval.payment_request_id == pr.id,
            models.Approval.decision == "APPROVE",
        ).all()
        distinct_roles = {a.approver_role for a in approvals}
        required = 2 if pr.is_prepayment else 1
        # Segregation of duties: a prepayment needs sign-off from two
        # DIFFERENT approver roles -- one person cannot satisfy both.
        if len(distinct_roles) >= required:
            pr.status = models.PaymentStatus.APPROVED

    db.commit()
    db.refresh(pr)
    log_action(db, user.id, f"PAYMENT_{decision}", "PaymentRequest", pr.id, {
        "resulting_status": pr.status.value, "approver_role": user.role.value
    })
    return pr


@router.post("/{pr_id}/release", response_model=schemas.PaymentRequestOut)
def release_payment(
    pr_id: str,
    db: DBSession = Depends(get_db),
    user=Depends(auth.require_role(models.Role.FINANCE_APPROVER)),
):
    """Releasing funds is a distinct, separately-logged step from approving
    them -- the same control gap (one person's verbal say-so moving money)
    cannot happen here because release requires the request to already be
    in APPROVED status, which itself required the dual sign-off above."""
    pr = db.query(models.PaymentRequest).get(pr_id)
    if not pr:
        raise HTTPException(status_code=404, detail="Payment request not found")
    if pr.status != models.PaymentStatus.APPROVED:
        raise HTTPException(status_code=400, detail="Only APPROVED payment requests can be released")
    pr.status = models.PaymentStatus.RELEASED
    db.commit()
    db.refresh(pr)
    log_action(db, user.id, "RELEASE_PAYMENT", "PaymentRequest", pr.id, {"amount": pr.amount})
    return pr
