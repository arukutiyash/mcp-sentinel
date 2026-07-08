from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession

from .. import schemas, models, auth
from ..database import get_db
from ..audit import log_action

router = APIRouter(prefix="/receiving", tags=["receiving"])


@router.post("", response_model=schemas.ReceivingOut)
def record_receiving(
    payload: schemas.ReceivingIn,
    db: DBSession = Depends(get_db),
    user=Depends(auth.require_role(models.Role.RECEIVING_CLERK)),
):
    """Records physical proof of delivery. This is the direct fix for the
    Controller's finding that GSD staff falsely marked undelivered lifts as
    'received' under a shared login: here, only an authenticated
    RECEIVING_CLERK can write this record, a serial/asset tag and an
    evidence note are mandatory (the API rejects blank values), and the
    record is permanently attributed to that one user id and timestamp."""
    line_item = db.query(models.LineItem).get(payload.line_item_id)
    if not line_item:
        raise HTTPException(status_code=404, detail="Line item not found")
    if not payload.serial_or_asset_tag.strip() or not payload.evidence_note.strip():
        raise HTTPException(status_code=400, detail="Serial/asset tag and evidence note are required")
    if payload.quantity_received <= 0:
        raise HTTPException(status_code=400, detail="quantity_received must be greater than zero")

    # Guard against over-receiving -- whether from an accidental duplicate
    # submission (e.g. a double click) or someone deliberately padding a
    # receiving record. A line item can never accumulate more received
    # quantity than was ordered; that mismatch is exactly the kind of
    # signal analytics.vendor_risk() looks for, so it must never be
    # silently allowed to occur in the first place.
    already_received = sum(r.quantity_received for r in line_item.receiving_records)
    remaining = line_item.quantity_ordered - already_received
    if payload.quantity_received > remaining:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot receive {payload.quantity_received} units: only {remaining} "
                   f"of {line_item.quantity_ordered} ordered remain unreceived "
                   f"({already_received} already recorded). If this delivery was logged "
                   "in error, do not resubmit -- flag it to an auditor instead.",
        )

    record = models.ReceivingRecord(
        line_item_id=line_item.id,
        received_by_user_id=user.id,
        quantity_received=payload.quantity_received,
        serial_or_asset_tag=payload.serial_or_asset_tag,
        evidence_note=payload.evidence_note,
    )
    db.add(record)
    db.flush()

    # Recompute PO status from the full set of line items / receiving records.
    po = line_item.purchase_order
    all_line_items = po.line_items
    fully_received = True
    any_received = False
    for li in all_line_items:
        received_qty = sum(r.quantity_received for r in li.receiving_records) + (
            payload.quantity_received if li.id == line_item.id else 0
        )
        if received_qty > 0:
            any_received = True
        if received_qty < li.quantity_ordered:
            fully_received = False
    po.status = models.POStatus.RECEIVED if fully_received else (
        models.POStatus.PARTIALLY_RECEIVED if any_received else po.status
    )
    db.commit()
    db.refresh(record)

    log_action(db, user.id, "RECORD_RECEIVING", "LineItem", line_item.id, {
        "quantity_received": payload.quantity_received,
        "serial_or_asset_tag": payload.serial_or_asset_tag,
        "po_id": po.id,
    })
    return record