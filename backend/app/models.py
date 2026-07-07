"""
ORM models for the GSD Procurement Integrity Platform.

Entity map (see docs/logical_structure.md for the full ERD):
  User            -- one row per human, individually authenticated (no shared logins)
  Session         -- login token issued to exactly one User
  Vendor          -- external supplier the City pays
  PurchaseOrder   -- a City commitment to buy goods/services from a Vendor
  LineItem        -- one purchased item/quantity on a PurchaseOrder
  ReceivingRecord -- physical proof that a LineItem was actually delivered
  PaymentRequest  -- a request to pay a Vendor against a PurchaseOrder
  Approval        -- one approver's decision on a PaymentRequest
  AuditLog        -- append-only log of every state-changing action in the system
"""
import enum
import uuid
import datetime as dt

from sqlalchemy import (
    Column, Integer, String, Float, Boolean, ForeignKey, DateTime, Text, Enum
)
from sqlalchemy.orm import relationship

from .database import Base


def now():
    return dt.datetime.utcnow()


def new_id():
    return str(uuid.uuid4())


class Role(str, enum.Enum):
    BUYER = "BUYER"                        # creates purchase orders
    RECEIVING_CLERK = "RECEIVING_CLERK"    # confirms physical delivery
    SUPERINTENDENT = "SUPERINTENDENT"      # first-line approver on prepayments
    FINANCE_APPROVER = "FINANCE_APPROVER"  # second, independent approver on prepayments
    AUDITOR = "AUDITOR"                    # read-only, full visibility


class POStatus(str, enum.Enum):
    ISSUED = "ISSUED"
    PARTIALLY_RECEIVED = "PARTIALLY_RECEIVED"
    RECEIVED = "RECEIVED"
    CLOSED = "CLOSED"
    FLAGGED = "FLAGGED"


class PaymentStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    RELEASED = "RELEASED"


class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, default=new_id)
    username = Column(String, unique=True, nullable=False, index=True)
    full_name = Column(String, nullable=False)
    role = Column(Enum(Role), nullable=False)
    password_hash = Column(String, nullable=False)
    password_salt = Column(String, nullable=False)
    created_at = Column(DateTime, default=now)

    sessions = relationship("Session", back_populates="user")


class Session(Base):
    """One row per active login token. A token maps to exactly one user_id,
    which is what makes every downstream write individually attributable --
    this is the structural fix for the shared-login gap identified by the
    Controller's Office (see docs/business_statement.md)."""
    __tablename__ = "sessions"
    token = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=now)
    expires_at = Column(DateTime, nullable=False)

    user = relationship("User", back_populates="sessions")


class Vendor(Base):
    __tablename__ = "vendors"
    id = Column(String, primary_key=True, default=new_id)
    name = Column(String, nullable=False)
    contact_email = Column(String)
    created_at = Column(DateTime, default=now)

    purchase_orders = relationship("PurchaseOrder", back_populates="vendor")


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    id = Column(String, primary_key=True, default=new_id)
    po_number = Column(String, unique=True, nullable=False)
    vendor_id = Column(String, ForeignKey("vendors.id"), nullable=False)
    created_by_user_id = Column(String, ForeignKey("users.id"), nullable=False)
    description = Column(String, nullable=False)
    total_amount = Column(Float, nullable=False)
    status = Column(Enum(POStatus), default=POStatus.ISSUED, nullable=False)
    expected_delivery_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=now)

    vendor = relationship("Vendor", back_populates="purchase_orders")
    line_items = relationship("LineItem", back_populates="purchase_order")
    payment_requests = relationship("PaymentRequest", back_populates="purchase_order")


class LineItem(Base):
    __tablename__ = "line_items"
    id = Column(String, primary_key=True, default=new_id)
    po_id = Column(String, ForeignKey("purchase_orders.id"), nullable=False)
    item_description = Column(String, nullable=False)
    quantity_ordered = Column(Integer, nullable=False)
    unit_price = Column(Float, nullable=False)

    purchase_order = relationship("PurchaseOrder", back_populates="line_items")
    receiving_records = relationship("ReceivingRecord", back_populates="line_item")


class ReceivingRecord(Base):
    """Physical proof of delivery. Cannot be created except by an
    authenticated RECEIVING_CLERK, must include a serial/asset tag or
    evidence note, and is immutable once written (corrections are new rows,
    never edits) so it can serve as a trustworthy audit artifact."""
    __tablename__ = "receiving_records"
    id = Column(String, primary_key=True, default=new_id)
    line_item_id = Column(String, ForeignKey("line_items.id"), nullable=False)
    received_by_user_id = Column(String, ForeignKey("users.id"), nullable=False)
    quantity_received = Column(Integer, nullable=False)
    serial_or_asset_tag = Column(String, nullable=False)
    evidence_note = Column(Text, nullable=False)
    received_at = Column(DateTime, default=now)

    line_item = relationship("LineItem", back_populates="receiving_records")


class PaymentRequest(Base):
    __tablename__ = "payment_requests"
    id = Column(String, primary_key=True, default=new_id)
    po_id = Column(String, ForeignKey("purchase_orders.id"), nullable=False)
    requested_by_user_id = Column(String, ForeignKey("users.id"), nullable=False)
    amount = Column(Float, nullable=False)
    is_prepayment = Column(Boolean, default=False, nullable=False)
    justification = Column(Text, nullable=True)
    status = Column(Enum(PaymentStatus), default=PaymentStatus.PENDING, nullable=False)
    created_at = Column(DateTime, default=now)

    purchase_order = relationship("PurchaseOrder", back_populates="payment_requests")
    approvals = relationship("Approval", back_populates="payment_request")


class Approval(Base):
    __tablename__ = "approvals"
    id = Column(String, primary_key=True, default=new_id)
    payment_request_id = Column(String, ForeignKey("payment_requests.id"), nullable=False)
    approver_user_id = Column(String, ForeignKey("users.id"), nullable=False)
    approver_role = Column(Enum(Role), nullable=False)
    decision = Column(String, nullable=False)  # "APPROVE" | "REJECT"
    comment = Column(Text, nullable=True)
    decided_at = Column(DateTime, default=now)

    payment_request = relationship("PaymentRequest", back_populates="approvals")


class AuditLog(Base):
    """Append-only. Every state-changing endpoint writes exactly one row
    here before returning. Nothing in this table is ever updated or
    deleted by the application layer."""
    __tablename__ = "audit_log"
    id = Column(String, primary_key=True, default=new_id)
    actor_user_id = Column(String, ForeignKey("users.id"), nullable=False)
    action = Column(String, nullable=False)
    entity_type = Column(String, nullable=False)
    entity_id = Column(String, nullable=False)
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime, default=now)
