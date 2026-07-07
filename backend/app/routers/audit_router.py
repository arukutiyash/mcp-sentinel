from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as DBSession

from .. import schemas, models, auth
from ..database import get_db

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=list[schemas.AuditLogOut])
def get_audit_log(
    entity_type: str | None = None,
    entity_id: str | None = None,
    db: DBSession = Depends(get_db),
    user=Depends(auth.get_current_user),
):
    q = db.query(models.AuditLog)
    if entity_type:
        q = q.filter(models.AuditLog.entity_type == entity_type)
    if entity_id:
        q = q.filter(models.AuditLog.entity_id == entity_id)
    return q.order_by(models.AuditLog.created_at.desc()).all()
