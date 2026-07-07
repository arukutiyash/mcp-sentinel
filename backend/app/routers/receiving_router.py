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
