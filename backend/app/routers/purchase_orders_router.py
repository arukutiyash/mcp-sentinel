import random
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession

from .. import schemas, models, auth
from ..database import get_db
from ..audit import log_action

router = APIRouter(prefix="/purchase-orders", tags=["purchase_orders"])


def _generate_po_number(db: DBSession) -> str:
    while True:
        candidate = f"GSD-PO-{random.randint(100000, 999999)}"
        if not db.query(models.PurchaseOrder).filter(models.PurchaseOrder.po_number == candidate).first():
            return candidate


@router.post("", response_model=schemas.PurchaseOrderOut)
def create_po(
    payload: schemas.PurchaseOrderCreate,
    db: DBSession = Depends(get_db),
    user=Depends(auth.require_role(models.Role.BUYER)),
):
    vendor = db.query(models.Vendor).get(payload.vendor_id)
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")
    if not payload.line_items:
        raise HTTPException(status_code=400, detail="A purchase order needs at least one line item")

    total = sum(li.quantity_ordered * li.unit_price for li in payload.line_items)
    po = models.PurchaseOrder(
        po_number=_generate_po_number(db),
        vendor_id=vendor.id,
        created_by_user_id=user.id,
        description=payload.description,
        total_amount=total,
        expected_delivery_date=payload.expected_delivery_date,
    )
    db.add(po)
    db.flush()
    for li in payload.line_items:
        db.add(models.LineItem(
            po_id=po.id,
            item_description=li.item_description,
            quantity_ordered=li.quantity_ordered,
            unit_price=li.unit_price,
        ))
    db.commit()
    db.refresh(po)
    log_action(db, user.id, "CREATE_PO", "PurchaseOrder", po.id,
               {"po_number": po.po_number, "total_amount": total, "vendor_id": vendor.id})
    return po


@router.get("", response_model=list[schemas.PurchaseOrderOut])
def list_pos(db: DBSession = Depends(get_db), user=Depends(auth.get_current_user)):
    return db.query(models.PurchaseOrder).order_by(models.PurchaseOrder.created_at.desc()).all()


@router.get("/{po_id}", response_model=schemas.PurchaseOrderOut)
def get_po(po_id: str, db: DBSession = Depends(get_db), user=Depends(auth.get_current_user)):
    po = db.query(models.PurchaseOrder).get(po_id)
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    return po
