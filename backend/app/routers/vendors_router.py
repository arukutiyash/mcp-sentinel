from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession

from .. import schemas, models, auth, analytics
from ..database import get_db

router = APIRouter(prefix="/vendors", tags=["vendors"])


@router.get("", response_model=list[schemas.VendorOut])
def list_vendors(db: DBSession = Depends(get_db), user=Depends(auth.get_current_user)):
    return db.query(models.Vendor).all()


@router.get("/{vendor_id}/risk", response_model=schemas.VendorRiskOut)
def vendor_risk(vendor_id: str, db: DBSession = Depends(get_db), user=Depends(auth.get_current_user)):
    vendor = db.query(models.Vendor).get(vendor_id)
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")
    score, signals = analytics.vendor_risk(db, vendor)
    return schemas.VendorRiskOut(vendor_id=vendor.id, vendor_name=vendor.name, risk_score=score, signals=signals)
