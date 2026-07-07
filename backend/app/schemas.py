"""Pydantic request/response schemas."""
import datetime as dt
from typing import Optional, List
from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    user_id: str
    full_name: str
    role: str


class VendorOut(BaseModel):
    id: str
    name: str
    contact_email: Optional[str] = None

    class Config:
        from_attributes = True


class LineItemIn(BaseModel):
    item_description: str
    quantity_ordered: int
    unit_price: float


class ReceivingIn(BaseModel):
    line_item_id: str
    quantity_received: int
    serial_or_asset_tag: str
    evidence_note: str


class ReceivingOut(BaseModel):
    id: str
    line_item_id: str
    received_by_user_id: str
    quantity_received: int
    serial_or_asset_tag: str
    evidence_note: str
    received_at: dt.datetime

    class Config:
        from_attributes = True


class LineItemOut(LineItemIn):
    id: str
    receiving_records: List[ReceivingOut] = []

    class Config:
        from_attributes = True


class PurchaseOrderCreate(BaseModel):
    vendor_id: str
    description: str
    expected_delivery_date: Optional[dt.datetime] = None
    line_items: List[LineItemIn]


class PurchaseOrderOut(BaseModel):
    id: str
    po_number: str
    vendor_id: str
    description: str
    total_amount: float
    status: str
    created_at: dt.datetime
    expected_delivery_date: Optional[dt.datetime] = None
    line_items: List[LineItemOut] = []

    class Config:
        from_attributes = True


class PaymentRequestIn(BaseModel):
    po_id: str
    amount: float
    is_prepayment: bool = False
    justification: Optional[str] = None


class ApprovalIn(BaseModel):
    decision: str  # APPROVE | REJECT
    comment: Optional[str] = None


class PaymentRequestOut(BaseModel):
    id: str
    po_id: str
    requested_by_user_id: str
    amount: float
    is_prepayment: bool
    justification: Optional[str] = None
    status: str
    created_at: dt.datetime

    class Config:
        from_attributes = True


class AuditLogOut(BaseModel):
    id: str
    actor_user_id: str
    action: str
    entity_type: str
    entity_id: str
    detail: Optional[str] = None
    created_at: dt.datetime

    class Config:
        from_attributes = True


class VendorRiskOut(BaseModel):
    vendor_id: str
    vendor_name: str
    risk_score: int
    signals: List[str]
