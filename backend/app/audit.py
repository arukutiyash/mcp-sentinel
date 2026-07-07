"""Append-only audit logging helper. Every state-changing router calls
`log_action` exactly once, inside the same DB transaction as the write it
is describing, so the audit trail can never drift out of sync with the
data it is auditing."""
import json
from sqlalchemy.orm import Session as DBSession
from . import models


def log_action(db: DBSession, actor_user_id: str, action: str, entity_type: str,
                entity_id: str, detail: dict | None = None):
    entry = models.AuditLog(
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        detail=json.dumps(detail or {}),
    )
    db.add(entry)
    db.commit()
