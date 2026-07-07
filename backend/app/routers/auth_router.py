from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as DBSession

from .. import schemas, auth
from ..database import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=schemas.LoginResponse)
def login(payload: schemas.LoginRequest, db: DBSession = Depends(get_db)):
    user = auth.authenticate(db, payload.username, payload.password)
    session = auth.issue_session(db, user)
    return schemas.LoginResponse(
        token=session.token, user_id=user.id, full_name=user.full_name, role=user.role.value
    )


@router.get("/me")
def me(user=Depends(auth.get_current_user)):
    return {"id": user.id, "full_name": user.full_name, "role": user.role.value, "username": user.username}
