"""
Authentication and authorization.

Deliberately dependency-light (stdlib hashlib instead of bcrypt/argon2) so
the whole project runs with nothing beyond the packages in requirements.txt
and is trivial to regenerate/run in a review sandbox. A production
deployment should swap `hash_password` for a proper slow hash (bcrypt /
argon2) -- everything else (token/session model, RBAC) carries over as-is.
"""
import hashlib
import os
import datetime as dt
from fastapi import Depends, HTTPException, Header
from sqlalchemy.orm import Session as DBSession

from .database import get_db
from . import models

TOKEN_TTL_HOURS = 12


def hash_password(password: str, salt: str) -> str:
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


def create_user(db: DBSession, username, full_name, role, password) -> models.User:
    salt = os.urandom(16).hex()
    user = models.User(
        username=username,
        full_name=full_name,
        role=role,
        password_salt=salt,
        password_hash=hash_password(password, salt),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate(db: DBSession, username: str, password: str) -> models.User:
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if hash_password(password, user.password_salt) != user.password_hash:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return user


def issue_session(db: DBSession, user: models.User) -> models.Session:
    session = models.Session(
        user_id=user.id,
        expires_at=dt.datetime.utcnow() + dt.timedelta(hours=TOKEN_TTL_HOURS),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_current_user(
    authorization: str = Header(default=None), db: DBSession = Depends(get_db)
) -> models.User:
    """Every mutating endpoint depends on this. There is no concept of a
    'service account' or shared credential anywhere in the system -- each
    request is tied to exactly one human user id, which is what makes the
    audit log individually attributable."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1]
    session = db.query(models.Session).filter(models.Session.token == token).first()
    if not session or session.expires_at < dt.datetime.utcnow():
        raise HTTPException(status_code=401, detail="Session expired or invalid")
    return session.user


def require_role(*allowed_roles):
    def dependency(user: models.User = Depends(get_current_user)):
        if user.role.value not in [r.value for r in allowed_roles] and user.role not in allowed_roles:
            raise HTTPException(status_code=403, detail=f"Role {user.role} not permitted for this action")
        return user
    return dependency
