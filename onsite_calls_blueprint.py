from __future__ import annotations

import csv
import io
import os
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from threading import Lock
from urllib.parse import quote_plus, urlencode, urlparse
from uuid import uuid4

from flask import Blueprint, Response, flash, jsonify, redirect, render_template, request, send_from_directory, session
from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text, create_engine, delete, func, inspect, or_, select, text
from sqlalchemy import Column
from sqlalchemy import event
from sqlalchemy import MetaData, Table
from sqlalchemy.orm import Session, declarative_base, relationship, scoped_session, sessionmaker
from time_utils import business_now_naive, format_datetime_display, mysql_session_timezone_value, normalize_display_datetime

Base = declarative_base()

COMPLAINT_TYPES = (
    "Laptop",
    "Desktop",
    "Printer",
    "CCTV",
    "Network",
    "Others",
)
PREFERRED_SERVICES = ("Onsite", "Pickup & Drop")
PRIORITY_LEVELS = ("Urgent", "As earlier", "Flexible")
CALL_TYPES = ("Onsite", "Lead")
CALL_TYPE_BADGE_CLASSES = {
    "Onsite": "text-bg-info",
    "Lead": "text-bg-primary",
}
LEAD_DEFAULT_SERVICE = "Onsite"
LEAD_DEFAULT_PRIORITY = "Flexible"
STATUSES = (
    "New Lead",
    "Open",
    "Assigned",
    "In Progress",
    "Waiting For Cus Approval",
    "Observation",
    "Spare waiting",
    "Completed",
    "Failed",
    "Cancelled",
    "Rescheduled",
)
ALLOWED_TRANSITIONS = {
    "New Lead": {"Open", "Assigned", "Observation", "Waiting For Cus Approval", "Spare waiting", "Cancelled", "Rescheduled"},
    "Open": {"Assigned", "In Progress", "Observation", "Waiting For Cus Approval", "Spare waiting", "Cancelled", "Rescheduled"},
    "Assigned": {"Open", "In Progress", "Observation", "Waiting For Cus Approval", "Spare waiting", "Completed", "Failed", "Cancelled", "Rescheduled"},
    "In Progress": {"Observation", "Waiting For Cus Approval", "Spare waiting", "Completed", "Failed", "Cancelled", "Rescheduled"},
    "Waiting For Cus Approval": {"Open", "Assigned", "In Progress", "Observation", "Spare waiting", "Completed", "Failed", "Cancelled", "Rescheduled"},
    "Observation": {"Open", "Assigned", "In Progress", "Waiting For Cus Approval", "Spare waiting", "Completed", "Failed", "Cancelled", "Rescheduled"},
    "Spare waiting": {"Open", "Assigned", "In Progress", "Observation", "Waiting For Cus Approval", "Completed", "Failed", "Cancelled", "Rescheduled"},
    "Rescheduled": {"Open", "Assigned", "Observation", "Waiting For Cus Approval", "Spare waiting", "Cancelled", "Rescheduled"},
    "Completed": {"Cancelled", "Rescheduled"},
    "Failed": {"Cancelled", "Rescheduled"},
    "Cancelled": set(),
}
STATUS_BADGE_CLASSES = {
    "New Lead": "text-bg-primary",
    "Open": "text-bg-secondary",
    "Assigned": "text-bg-info",
    "In Progress": "text-bg-warning",
    "Waiting For Cus Approval": "text-bg-warning text-dark",
    "Observation": "text-bg-secondary",
    "Spare waiting": "text-bg-warning text-dark",
    "Completed": "text-bg-success",
    "Failed": "text-bg-danger",
    "Cancelled": "text-bg-dark",
    "Rescheduled": "text-bg-light text-dark border",
}
PRIORITY_BADGE_CLASSES = {
    "Urgent": "text-bg-danger",
    "As earlier": "text-bg-warning text-dark",
    "Flexible": "text-bg-success",
}
STATUS_SECTIONS = [
    ("New Lead", "New Leads"),
    ("Open", "Open"),
    ("Assigned", "Assigned"),
    ("In Progress", "In Progress"),
    ("Waiting For Cus Approval", "Waiting For Cus Approval"),
    ("Observation", "Observation"),
    ("Spare waiting", "Spare waiting"),
    ("Completed", "Completed"),
    ("Failed", "Failed"),
    ("Cancelled", "Cancelled"),
    ("Rescheduled", "Rescheduled"),
    ("ALL", "All Calls"),
]
ADMIN_ROLES = {"admin", "super_admin"}
REPORT_ROLES = {"admin", "super_admin"}
ASSIGNABLE_ROLES = {"admin", "super_admin"}
COORDINATOR_ROLES = {"coordinator"}
BRANCH_DROPDOWN_TYPE = "branch"
CACHE_TTL_SECONDS = 45
DEFAULT_PER_PAGE = 20
MAX_PER_PAGE = 50
ENGINEER_USER_ROLES = ("engineer", "coordinator")
FINAL_STATUSES = frozenset({"Completed", "Failed", "Cancelled"})
COMPLETION_TYPES = ("Paid Service", "Warranty Service", "Free Service")
PAID_COMPLETION_TYPE = "Paid Service"
CLOSED_BY_OPTIONS = ("SYSMANTECH", "INSPIRE", "TDH")
PAYMENT_MODE_OPTIONS = ("Credit", "Cash", "Card", "UPI")
PAYMENT_STATUS_ALL = "ALL"
PAYMENT_STATUS_CREDIT_PENDING = "Credit Pending"
PAYMENT_STATUS_RECEIVED = "Received"
PAYMENT_STATUS_FILTERS = (PAYMENT_STATUS_ALL, PAYMENT_STATUS_CREDIT_PENDING)
PAYMENT_STATUS_BADGE_CLASSES = {
    PAYMENT_STATUS_CREDIT_PENDING: "text-bg-warning text-dark",
    PAYMENT_STATUS_RECEIVED: "text-bg-success",
}
MAX_ONSITE_MEDIA_ATTACHMENTS = 3
ONSITE_MEDIA_MAX_BYTES = 10 * 1024 * 1024
ONSITE_MEDIA_RETENTION_DAYS = 30
ONSITE_MEDIA_CLEANUP_INTERVAL_SECONDS = max(300, int(os.getenv("ONSITE_MEDIA_CLEANUP_INTERVAL_SECONDS", "3600") or "3600"))
ALLOWED_ONSITE_IMAGE_EXTENSIONS = {".jpg", ".png", ".gif", ".webp"}
ALLOWED_ONSITE_VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".ogv"}
PUBLIC_CREATE_RATE_LIMIT = max(1, int(os.getenv("ONSITE_PUBLIC_CREATE_LIMIT", "10") or "10"))
PUBLIC_CREATE_RATE_LIMIT_WINDOW_SECONDS = max(60, int(os.getenv("ONSITE_PUBLIC_CREATE_WINDOW_SECONDS", "600") or "600"))
ENGINEER_STATUS_UPDATE_TARGETS = frozenset(
    {
        "In Progress",
        "Waiting For Cus Approval",
        "Observation",
        "Spare waiting",
        "Completed",
        "Failed",
        "Cancelled",
    }
)
_public_create_attempts = {}
_public_create_attempts_lock = Lock()
_onsite_media_cleanup_state = {"last_run": 0.0}
_onsite_media_cleanup_lock = Lock()


def _configure_mysql_session_timezone(dbapi_connection, _connection_record):
    cursor = None
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("SET time_zone = %s", (mysql_session_timezone_value(),))
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass


def status_choices_for_role(current_status, role, is_assigned_engineer=False):
    normalized_status = str(current_status or "").strip()
    normalized_role = str(role or "").strip().lower()

    if normalized_status not in STATUSES:
        return ()

    if normalized_role in ADMIN_ROLES:
        return tuple(status for status in STATUSES if status != normalized_status)

    if normalized_role in ENGINEER_USER_ROLES:
        if not is_assigned_engineer or normalized_status in FINAL_STATUSES:
            return ()
        allowed_targets = ALLOWED_TRANSITIONS.get(normalized_status, set()) & ENGINEER_STATUS_UPDATE_TARGETS
        return tuple(status for status in STATUSES if status in allowed_targets)

    allowed_targets = ALLOWED_TRANSITIONS.get(normalized_status, set())
    return tuple(status for status in STATUSES if status in allowed_targets)


def coordinator_branch_status_choices(current_status):
    normalized_status = str(current_status or "").strip()
    if normalized_status not in STATUSES or normalized_status in FINAL_STATUSES:
        return ()
    allowed_targets = ALLOWED_TRANSITIONS.get(normalized_status, set()) - FINAL_STATUSES
    return tuple(status for status in STATUSES if status in allowed_targets)


def role_can_reschedule(role):
    return str(role or "").strip().lower() in ADMIN_ROLES


def normalize_call_type(raw_value):
    normalized_value = str(raw_value or "").strip().lower()
    if normalized_value == "lead":
        return "Lead"
    if normalized_value in {"onsite", "onsite call", "call"}:
        return "Onsite"
    return ""


def _public_create_client_key():
    return (request.remote_addr or "unknown").strip() or "unknown"


def _prune_public_create_attempts(client_key):
    now = time.time()
    with _public_create_attempts_lock:
        attempts = [
            ts
            for ts in _public_create_attempts.get(client_key, [])
            if now - ts < PUBLIC_CREATE_RATE_LIMIT_WINDOW_SECONDS
        ]
        _public_create_attempts[client_key] = attempts
        return list(attempts)


def _public_create_rate_limited(client_key):
    return len(_prune_public_create_attempts(client_key)) >= PUBLIC_CREATE_RATE_LIMIT


def _record_public_create_attempt(client_key):
    now = time.time()
    with _public_create_attempts_lock:
        attempts = [
            ts
            for ts in _public_create_attempts.get(client_key, [])
            if now - ts < PUBLIC_CREATE_RATE_LIMIT_WINDOW_SECONDS
        ]
        attempts.append(now)
        _public_create_attempts[client_key] = attempts


def _public_create_rate_limit_message():
    window_minutes = max(1, int((PUBLIC_CREATE_RATE_LIMIT_WINDOW_SECONDS + 59) // 60))
    return (
        "Too many onsite requests were submitted from this network. "
        f"Please wait about {window_minutes} minute{'s' if window_minutes != 1 else ''} and try again."
    )


def _measure_upload_size(file_storage):
    stream = getattr(file_storage, "stream", None)
    if stream is None:
        return 0
    try:
        current_position = stream.tell()
        stream.seek(0, os.SEEK_END)
        size = int(stream.tell() or 0)
        stream.seek(current_position)
        return size
    except Exception:
        raw_bytes = file_storage.read()
        try:
            stream.seek(0)
        except Exception:
            pass
        return len(raw_bytes or b"")


def _sniff_onsite_media_type(file_storage):
    stream = getattr(file_storage, "stream", None)
    if stream is None:
        return "", "", ""

    header = stream.read(32)
    stream.seek(0)

    original_name = str(getattr(file_storage, "filename", "") or "")
    provided_extension = os.path.splitext(original_name)[1].lower()
    if provided_extension == ".jpeg":
        provided_extension = ".jpg"
    if provided_extension == ".ogg":
        provided_extension = ".ogv"

    image_matches = {
        ".jpg": header.startswith(b"\xff\xd8\xff"),
        ".png": header.startswith(b"\x89PNG\r\n\x1a\n"),
        ".gif": header.startswith(b"GIF87a") or header.startswith(b"GIF89a"),
        ".webp": header.startswith(b"RIFF") and header[8:12] == b"WEBP",
    }
    for extension, matched in image_matches.items():
        if matched and provided_extension == extension and extension in ALLOWED_ONSITE_IMAGE_EXTENSIONS:
            mime_type = "image/jpeg" if extension == ".jpg" else f"image/{extension.lstrip('.')}"
            return "image", extension, mime_type

    if len(header) >= 12 and header[4:8] == b"ftyp":
        brand = header[8:12]
        if brand == b"qt  " and provided_extension == ".mov":
            return "video", ".mov", "video/quicktime"
        if provided_extension == ".mp4":
            return "video", ".mp4", "video/mp4"

    if header.startswith(b"\x1A\x45\xDF\xA3") and provided_extension == ".webm":
        return "video", ".webm", "video/webm"

    if header.startswith(b"OggS") and provided_extension == ".ogv":
        return "video", ".ogv", "video/ogg"

    return "", "", ""


def compute_onsite_profit_fields(service_charges, product_value, customer_price):
    service_amount = Decimal(str(service_charges or 0)).quantize(Decimal("0.01"))
    product_cost = Decimal(str(product_value or 0)).quantize(Decimal("0.01"))
    sale_amount = Decimal(str(customer_price or 0)).quantize(Decimal("0.01"))
    product_profit = (sale_amount - product_cost).quantize(Decimal("0.01"))
    total_profit = (service_amount + product_profit).quantize(Decimal("0.01"))
    return {
        "product_profit": product_profit,
        "total_profit": total_profit,
    }


def build_profit_sections(profit_rows):
    profit_sections = []
    for call_type in CALL_TYPES:
        service_charge_total = Decimal("0.00")
        product_value_total = Decimal("0.00")
        customer_price_total = Decimal("0.00")
        profit_total = Decimal("0.00")
        section_rows = []
        for row in profit_rows:
            normalized_type = normalize_call_type(getattr(row, "call_type", "")) or "Onsite"
            if normalized_type != call_type:
                continue
            service_charges = Decimal(str(getattr(row, "service_charges", 0) or 0)).quantize(Decimal("0.01"))
            product_value = Decimal(str(getattr(row, "product_value", 0) or 0)).quantize(Decimal("0.01"))
            customer_price = Decimal(str(getattr(row, "customer_price", 0) or 0)).quantize(Decimal("0.01"))
            profit_fields = compute_onsite_profit_fields(service_charges, product_value, customer_price)
            service_charge_total += service_charges
            product_value_total += product_value
            customer_price_total += customer_price
            profit_total += profit_fields["total_profit"]
            section_rows.append(
                {
                    "call_id": int(row.id),
                    "customer_name": str(row.customer_name or "-"),
                    "branch_name": str(getattr(row, "assigned_branch_name", "") or "Unassigned"),
                    "lead_source": str(getattr(row, "lead_source", "") or ""),
                    "closed_at_display": format_datetime_display(getattr(row, "closed_at", None)),
                    "service_charges": float(service_charges),
                    "product_value": float(product_value),
                    "customer_price": float(customer_price),
                    "profit": float(profit_fields["total_profit"]),
                    "closed_by_brand": str(getattr(row, "closed_by_brand", "") or "-"),
                }
            )
        profit_sections.append(
            {
                "call_type": call_type,
                "title": f"{call_type} Profit Report",
                "summary": {
                    "case_count": len(section_rows),
                    "service_charge_total": float(service_charge_total),
                    "product_value_total": float(product_value_total),
                    "customer_price_total": float(customer_price_total),
                    "profit_total": float(profit_total),
                },
                "rows": section_rows,
            }
        )
    return profit_sections


class OnsiteCall(Base):
    __tablename__ = "onsite_calls"

    id = Column(Integer, primary_key=True)
    customer_name = Column(String(255), nullable=False)
    phone = Column(String(50), nullable=False)
    location = Column(String(255), nullable=False)
    district = Column(String(255), nullable=False)
    complaint_type = Column(String(50), nullable=False)
    preferred_service = Column(String(50), nullable=False)
    priority = Column(String(50), nullable=False)
    preferred_datetime = Column(DateTime, nullable=False)
    device_model = Column(String(255), nullable=True)
    complaint_description = Column(Text, nullable=False)
    call_type = Column(String(20), nullable=False, default="Onsite")
    status = Column(String(50), nullable=False, default="New Lead")
    source = Column(String(50), nullable=False)
    lead_source = Column(String(255), nullable=True)
    assigned_branch_id = Column(Integer, nullable=True)
    assigned_engineer_id = Column(Integer, nullable=True)
    assigned_time = Column(DateTime, nullable=True)
    created_by = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, default=business_now_naive)
    updated_at = Column(DateTime, nullable=False, default=business_now_naive, onupdate=business_now_naive)

    attachments = relationship("OnsiteCallAttachment", back_populates="call", cascade="all, delete-orphan")
    closure = relationship("OnsiteCallClosure", back_populates="call", cascade="all, delete-orphan", uselist=False)
    logs = relationship("OnsiteCallLog", back_populates="call", cascade="all, delete-orphan")
    notes = relationship("OnsiteCallNote", back_populates="call", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_onsite_calls_call_type", "call_type"),
        Index("idx_onsite_calls_status", "status"),
        Index("idx_onsite_calls_branch", "assigned_branch_id"),
        Index("idx_onsite_calls_engineer", "assigned_engineer_id"),
        Index("idx_onsite_calls_created_at", "created_at"),
        Index("idx_onsite_calls_status_created", "status", "created_at"),
    )


class OnsiteCallLog(Base):
    __tablename__ = "onsite_call_logs"

    id = Column(Integer, primary_key=True)
    call_id = Column(Integer, ForeignKey("onsite_calls.id", ondelete="CASCADE"), nullable=False, index=True)
    action = Column(String(100), nullable=False)
    description = Column(Text, nullable=False)
    done_by = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, default=business_now_naive)

    call = relationship("OnsiteCall", back_populates="logs")


class OnsiteCallNote(Base):
    __tablename__ = "onsite_call_notes"

    id = Column(Integer, primary_key=True)
    call_id = Column(Integer, ForeignKey("onsite_calls.id", ondelete="CASCADE"), nullable=False, index=True)
    note = Column(Text, nullable=False)
    created_by = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, default=business_now_naive)

    call = relationship("OnsiteCall", back_populates="notes")


class OnsiteCallAttachment(Base):
    __tablename__ = "onsite_call_attachments"

    id = Column(Integer, primary_key=True)
    call_id = Column(Integer, ForeignKey("onsite_calls.id", ondelete="CASCADE"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    media_kind = Column(String(16), nullable=False)
    mime_type = Column(String(64), nullable=False)
    uploaded_at = Column(DateTime, nullable=False, default=business_now_naive)

    call = relationship("OnsiteCall", back_populates="attachments")


class OnsiteCallClosure(Base):
    __tablename__ = "onsite_call_closures"

    id = Column(Integer, primary_key=True)
    call_id = Column(Integer, ForeignKey("onsite_calls.id", ondelete="CASCADE"), nullable=False, index=True, unique=True)
    final_status = Column(String(50), nullable=False)
    close_reason = Column(Text, nullable=True)
    completion_type = Column(String(32), nullable=True)
    narration = Column(Text, nullable=True)
    service_charges = Column(Numeric(12, 2), nullable=False, default=0)
    engineer_id = Column(Integer, nullable=True)
    product_value = Column(Numeric(12, 2), nullable=False, default=0)
    customer_price = Column(Numeric(12, 2), nullable=False, default=0)
    closed_by_brand = Column(String(32), nullable=True)
    payment_mode = Column(String(16), nullable=True)
    payment_status = Column(String(32), nullable=True)
    closed_by_user = Column(String(255), nullable=True)
    closed_at = Column(DateTime, nullable=False, default=business_now_naive)
    updated_at = Column(DateTime, nullable=False, default=business_now_naive, onupdate=business_now_naive)

    call = relationship("OnsiteCall", back_populates="closure")

    __table_args__ = (
        Index("idx_onsite_call_closures_payment_status", "payment_status"),
    )


class TTLMemoryCache:
    def __init__(self, ttl_seconds: int = CACHE_TTL_SECONDS):
        self.ttl_seconds = max(5, int(ttl_seconds or CACHE_TTL_SECONDS))
        self._lock = Lock()
        self._store = {}

    def get(self, key):
        now = datetime.utcnow().timestamp()
        with self._lock:
            item = self._store.get(key)
            if not item:
                return None
            expires_at, value = item
            if expires_at < now:
                self._store.pop(key, None)
                return None
            return value

    def set(self, key, value):
        expires_at = datetime.utcnow().timestamp() + self.ttl_seconds
        with self._lock:
            self._store[key] = (expires_at, value)

    def clear(self):
        with self._lock:
            self._store.clear()


class OnsiteCallService:
    def __init__(self, app, config):
        self.app = app
        self.default_branches = [branch for branch in (config.get("default_branches") or []) if branch and branch != "ALL"]
        self.media_folder = os.path.join(self.app.instance_path, "onsite_call_media")
        os.makedirs(self.media_folder, exist_ok=True)
        self.engine = create_engine(
            self._build_database_url(config),
            future=True,
            pool_pre_ping=True,
            pool_size=max(5, int(config.get("pool_size") or 8)),
            max_overflow=max(10, int(config.get("max_overflow") or 20)),
            pool_recycle=1800,
        )
        event.listen(self.engine, "connect", _configure_mysql_session_timezone)
        self.SessionLocal = scoped_session(
            sessionmaker(bind=self.engine, autoflush=False, autocommit=False, expire_on_commit=False)
        )
        self.cache = TTLMemoryCache()
        self._external_metadata = MetaData()
        self._users_table = None
        self._dropdown_options_table = None
        self._user_branches_table = None
        Base.metadata.create_all(self.engine)
        self._ensure_onsite_call_columns()
        self._reflect_external_tables()
        self._ensure_branch_dropdown_options()

    def _build_database_url(self, config):
        user = quote_plus(str(config.get("db_user") or "root"))
        password = quote_plus(str(config.get("db_password") or ""))
        host = str(config.get("db_host") or "localhost")
        name = quote_plus(str(config.get("db_name") or "crm_system"))
        return f"mysql+mysqlconnector://{user}:{password}@{host}/{name}"

    def _ensure_onsite_call_columns(self):
        try:
            inspector = inspect(self.engine)
            existing_columns = {str(column.get("name") or "").strip() for column in inspector.get_columns("onsite_calls")}
            existing_indexes = {str(index.get("name") or "").strip() for index in inspector.get_indexes("onsite_calls")}
        except Exception:
            self.app.logger.exception("Failed to inspect onsite_calls schema")
            return

        statements = []
        if "call_type" not in existing_columns:
            statements.append("ALTER TABLE onsite_calls ADD COLUMN call_type VARCHAR(20) NOT NULL DEFAULT 'Onsite'")
        if "lead_source" not in existing_columns:
            statements.append("ALTER TABLE onsite_calls ADD COLUMN lead_source VARCHAR(255) NULL")

        if not statements and "idx_onsite_calls_call_type" in existing_indexes:
            return

        try:
            with self.engine.begin() as connection:
                for statement in statements:
                    connection.execute(text(statement))
                connection.execute(text("UPDATE onsite_calls SET call_type = 'Onsite' WHERE call_type IS NULL OR TRIM(call_type) = ''"))
                if "idx_onsite_calls_call_type" not in existing_indexes:
                    connection.execute(text("CREATE INDEX idx_onsite_calls_call_type ON onsite_calls (call_type)"))
        except Exception:
            self.app.logger.exception("Failed to ensure onsite lead columns")

    def _reflect_external_tables(self):
        try:
            self._users_table = Table("users", self._external_metadata, autoload_with=self.engine)
        except Exception:
            self._users_table = None
        try:
            self._dropdown_options_table = Table("dropdown_options", self._external_metadata, autoload_with=self.engine)
        except Exception:
            self._dropdown_options_table = None
        try:
            self._user_branches_table = Table("user_branches", self._external_metadata, autoload_with=self.engine)
        except Exception:
            self._user_branches_table = None

    @contextmanager
    def session_scope(self):
        db_session = self.SessionLocal()
        try:
            yield db_session
            db_session.commit()
        except Exception:
            db_session.rollback()
            raise
        finally:
            db_session.close()
            self.SessionLocal.remove()

    def invalidate_cache(self):
        self.cache.clear()

    def _ensure_branch_dropdown_options(self):
        if self._dropdown_options_table is None:
            return
        with self.session_scope() as db_session:
            existing = {
                str(row.value or "").strip().upper()
                for row in db_session.execute(
                    select(self._dropdown_options_table.c.value).where(self._dropdown_options_table.c.type == BRANCH_DROPDOWN_TYPE)
                )
            }
            max_order = db_session.execute(
                select(func.max(self._dropdown_options_table.c["order"])).where(
                    self._dropdown_options_table.c.type == BRANCH_DROPDOWN_TYPE
                )
            ).scalar_one_or_none() or 0
            next_order = int(max_order)
            for branch_name in self.default_branches:
                if branch_name.strip().upper() in existing:
                    continue
                next_order += 1
                db_session.execute(
                    self._dropdown_options_table.insert().values(
                        type=BRANCH_DROPDOWN_TYPE,
                        value=branch_name,
                        **{"order": next_order},
                    )
                )

    def is_authenticated(self):
        return bool(str(session.get("username") or "").strip())

    def actor(self):
        username = str(session.get("username") or "").strip()
        role = str(session.get("role") or "").strip().lower()
        branch = str(session.get("branch") or "").strip()
        return {
            "username": username,
            "role": role,
            "branch": branch,
            "is_authenticated": bool(username),
            "has_global_scope": role == "super_admin" or (role == "admin" and branch.upper() == "ALL"),
        }

    def branch_options(self, actor):
        branch_names = list(self.default_branches)
        if self._dropdown_options_table is not None:
            with self.session_scope() as db_session:
                branch_names.extend(
                    [
                        str(row.value or "").strip()
                        for row in db_session.execute(
                            select(self._dropdown_options_table.c.value)
                            .where(self._dropdown_options_table.c.type == BRANCH_DROPDOWN_TYPE)
                            .order_by(self._dropdown_options_table.c.value.asc())
                        )
                    ]
                )
        deduped = []
        seen = set()
        for branch_name in branch_names:
            normalized = str(branch_name or "").strip()
            if not normalized:
                continue
            key = normalized.upper()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(normalized)
        if actor["has_global_scope"]:
            return deduped
        branch_name = actor["branch"]
        return [branch_name] if branch_name else []

    def engineer_options(self, actor, branch_name="", query="", limit=25):
        if self._users_table is None:
            return []
        normalized_branch = str(branch_name or "").strip()
        normalized_query = str(query or "").strip()
        safe_limit = max(1, min(50, int(limit or 25)))
        role_column = func.lower(self._users_table.c.role)
        with self.session_scope() as db_session:
            users_stmt = select(self._users_table.c.id, self._users_table.c.username).where(role_column.in_(ENGINEER_USER_ROLES))
            if normalized_branch and self._user_branches_table is not None:
                users_stmt = (
                    select(self._users_table.c.id, self._users_table.c.username)
                    .select_from(
                        self._users_table.join(
                            self._user_branches_table,
                            self._users_table.c.username == self._user_branches_table.c.username,
                        )
                    )
                    .where(role_column.in_(ENGINEER_USER_ROLES))
                    .where(func.upper(self._user_branches_table.c.branch_name) == normalized_branch.upper())
                )
            if normalized_query:
                users_stmt = users_stmt.where(func.lower(self._users_table.c.username).like(f"%{normalized_query.lower()}%"))
            rows = db_session.execute(
                users_stmt.distinct().order_by(self._users_table.c.username.asc()).limit(safe_limit)
            ).all()
            return [{"id": int(row.id), "username": str(row.username)} for row in rows]

    def admin_usernames(self):
        if self._users_table is None:
            return []
        with self.session_scope() as db_session:
            rows = db_session.execute(
                select(self._users_table.c.username).where(self._users_table.c.role.in_(["admin", "super_admin"]))
            )
            return [str(row.username or "").strip() for row in rows if str(row.username or "").strip()]

    def branch_id_from_name(self, db_session: Session, branch_name: str):
        if self._dropdown_options_table is None:
            return None
        normalized = str(branch_name or "").strip()
        if not normalized:
            return None
        row = db_session.execute(
            select(self._dropdown_options_table.c.id)
            .where(self._dropdown_options_table.c.type == BRANCH_DROPDOWN_TYPE)
            .where(func.upper(self._dropdown_options_table.c.value) == normalized.upper())
            .limit(1)
        ).first()
        return int(row.id) if row else None

    def branch_name_from_id(self, branch_id):
        if self._dropdown_options_table is None or not branch_id:
            return ""
        with self.session_scope() as db_session:
            row = db_session.execute(
                select(self._dropdown_options_table.c.value).where(self._dropdown_options_table.c.id == branch_id).limit(1)
            ).first()
            return str(row.value or "") if row else ""

    def can_assign(self, actor, call_like=None):
        if actor["role"] in ASSIGNABLE_ROLES:
            return True
        if call_like is None:
            return False
        return self._can_coordinator_manage_branch_call(actor, call_like)

    def can_view_reports(self, actor):
        return actor["role"] in REPORT_ROLES

    def can_delete(self, actor):
        return actor["role"] in ADMIN_ROLES

    def can_edit(self, actor, call_like):
        if self._call_value(call_like, "has_closure_record"):
            return False
        current_status = str(self._call_value(call_like, "status") or "").strip()
        if current_status in FINAL_STATUSES:
            return False
        if actor["role"] in ADMIN_ROLES:
            return True
        if self._is_assigned_engineer(actor, call_like):
            return True
        return self._can_coordinator_manage_branch_call(actor, call_like)

    def can_close(self, actor, call_like):
        return bool(self.close_status_choices(actor, call_like))

    def can_update_credit_payment(self, actor, call_like, closure_like):
        if not closure_like or self._call_value(closure_like, "payment_status") != PAYMENT_STATUS_CREDIT_PENDING:
            return False
        role = str(actor.get("role") or "").strip().lower()
        return role in ADMIN_ROLES or self._is_assigned_engineer(actor, call_like)

    def _call_value(self, call_like, field_name):
        if isinstance(call_like, dict):
            return call_like.get(field_name)
        return getattr(call_like, field_name, None)

    def _is_assigned_engineer(self, actor, call_like):
        role = str(actor.get("role") or "").strip().lower()
        if role not in ENGINEER_USER_ROLES:
            return False
        actor_username = str(actor.get("username") or "").strip().lower()
        assigned_engineer_name = str(self._call_value(call_like, "assigned_engineer_name") or "").strip().lower()
        return bool(actor_username and assigned_engineer_name and actor_username == assigned_engineer_name)

    def _is_coordinator(self, actor):
        return str(actor.get("role") or "").strip().lower() in COORDINATOR_ROLES

    def _can_coordinator_manage_branch_call(self, actor, call_like):
        if not self._is_coordinator(actor):
            return False
        actor_branch = str(actor.get("branch") or "").strip()
        assigned_branch_name = str(self._call_value(call_like, "assigned_branch_name") or "").strip()
        if not actor_branch or not assigned_branch_name or actor_branch.upper() != assigned_branch_name.upper():
            return False
        if self._call_value(call_like, "has_closure_record"):
            return False
        assigned_engineer_name = str(self._call_value(call_like, "assigned_engineer_name") or "").strip()
        assigned_engineer_id = self._call_value(call_like, "assigned_engineer_id")
        try:
            has_engineer_id = int(assigned_engineer_id or 0) > 0
        except (TypeError, ValueError):
            has_engineer_id = bool(assigned_engineer_id)
        return not assigned_engineer_name and not has_engineer_id

    def can_add_note(self, actor, call_like):
        role = str(actor.get("role") or "").strip().lower()
        if role in ADMIN_ROLES:
            return True
        if role == "engineer":
            return self._is_assigned_engineer(actor, call_like)
        if self._is_coordinator(actor):
            return self._is_assigned_engineer(actor, call_like) or self._can_coordinator_manage_branch_call(actor, call_like)
        return True

    def assignment_message(self, actor, call_like):
        if self.can_assign(actor, call_like):
            return ""
        if self._is_coordinator(actor):
            assigned_branch_name = str(self._call_value(call_like, "assigned_branch_name") or "").strip()
            actor_branch = str(actor.get("branch") or "").strip()
            if not assigned_branch_name:
                return "Coordinator can fill engineer only after the case is assigned to a branch."
            if assigned_branch_name.upper() != actor_branch.upper():
                return "Coordinator can fill engineer only for cases assigned to their own branch."
            return "Coordinator can fill engineer only while no specific engineer is assigned to this case."
        return "Only admin or super admin can assign branches or reassign engineers."

    def note_message(self, actor, call_like):
        if self.can_add_note(actor, call_like):
            return ""
        role = str(actor.get("role") or "").strip().lower()
        if role == "engineer":
            return "Engineers can add notes only when the case is assigned to their own name."
        if self._is_coordinator(actor):
            return "Coordinator can add notes only for branch-assigned cases without a named engineer, or cases assigned to their own name."
        return "You cannot add notes to this case."

    def available_status_choices(self, actor, call_like):
        if self._can_coordinator_manage_branch_call(actor, call_like):
            return coordinator_branch_status_choices(self._call_value(call_like, "status"))
        return status_choices_for_role(
            self._call_value(call_like, "status"),
            actor.get("role"),
            is_assigned_engineer=self._is_assigned_engineer(actor, call_like),
        )

    def close_status_choices(self, actor, call_like):
        if self._call_value(call_like, "has_closure_record"):
            return ()
        current_status = str(self._call_value(call_like, "status") or "").strip()
        if current_status in FINAL_STATUSES:
            return ()
        return tuple(status for status in self.available_status_choices(actor, call_like) if status in FINAL_STATUSES)

    def available_nonfinal_status_choices(self, actor, call_like):
        if self._call_value(call_like, "has_closure_record"):
            return ()
        return tuple(status for status in self.available_status_choices(actor, call_like) if status not in FINAL_STATUSES)

    def can_update_status(self, actor, call_like):
        return bool(self.available_nonfinal_status_choices(actor, call_like))

    def can_reschedule(self, actor):
        return role_can_reschedule(actor.get("role"))

    def status_update_message(self, actor, call_like):
        if self.can_update_status(actor, call_like):
            return ""
        if self._call_value(call_like, "has_closure_record"):
            return "This case is already closed. Use the credit payment section if payment is still pending."
        role = str(actor.get("role") or "").strip().lower()
        current_status = str(self._call_value(call_like, "status") or "").strip()
        if role == "engineer":
            if current_status in FINAL_STATUSES:
                return "Engineers cannot update status after a case is Completed, Cancelled, or Failed."
            return "Only the assigned engineer can update this case status."
        if self._is_coordinator(actor):
            if current_status in FINAL_STATUSES:
                return "Coordinators cannot update status after a case is Completed, Cancelled, or Failed."
            if self._call_value(call_like, "assigned_engineer_id") or self._call_value(call_like, "assigned_engineer_name"):
                return "Once an engineer is assigned, only that assigned engineer can continue status updates."
            return "Coordinator can update status only for cases assigned to their own branch."
        if current_status == "Cancelled":
            return "This case is cancelled and has no further status updates."
        return "No further status updates are available for this case."

    def close_message(self, actor, call_like):
        if self.can_close(actor, call_like):
            return ""
        if self._call_value(call_like, "has_closure_record"):
            return "This case is already closed."
        current_status = str(self._call_value(call_like, "status") or "").strip()
        if current_status in FINAL_STATUSES:
            return "This case is already in a final status."
        role = str(actor.get("role") or "").strip().lower()
        if self._is_coordinator(actor) and self._can_coordinator_manage_branch_call(actor, call_like):
            return "Coordinator can update working status now. Close case becomes available after assigning an engineer or assigning the case to their own name."
        if role in ENGINEER_USER_ROLES and not self._is_assigned_engineer(actor, call_like):
            return "Only the assigned engineer can close this case."
        return "You cannot close this case from the current status."

    def credit_payment_message(self, actor, call_like, closure_like):
        if self.can_update_credit_payment(actor, call_like, closure_like):
            return ""
        if not closure_like or self._call_value(closure_like, "payment_status") != PAYMENT_STATUS_CREDIT_PENDING:
            return "This case does not have any pending credit payment."
        return "Only admin, super admin, or the assigned engineer can settle this credit payment."

    def reschedule_message(self, actor):
        if self.can_reschedule(actor):
            return ""
        return "Only admin or super admin can reschedule this case."

    def _parse_datetime(self, raw_value):
        text_value = str(raw_value or "").strip()
        if not text_value:
            return None
        for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(text_value, fmt)
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(text_value)
        except ValueError:
            return None

    def _normalize_phone(self, raw_value):
        digits = "".join(ch for ch in str(raw_value or "") if ch.isdigit())
        return digits

    def _parse_money(self, raw_value, field_label, required=False):
        text_value = str(raw_value or "").strip()
        if not text_value:
            if required:
                return None, f"{field_label} is required"
            return Decimal("0.00"), None
        try:
            amount = Decimal(text_value)
        except (InvalidOperation, ValueError):
            return None, f"{field_label} must be a valid amount"
        if amount < 0:
            return None, f"{field_label} cannot be negative"
        return amount.quantize(Decimal("0.01")), None

    def _serialize_closure(self, db_session: Session, closure):
        if not closure:
            return None
        service_charges = Decimal(str(closure.service_charges or 0)).quantize(Decimal("0.01"))
        product_value = Decimal(str(closure.product_value or 0)).quantize(Decimal("0.01"))
        customer_price = Decimal(str(closure.customer_price or 0)).quantize(Decimal("0.01"))
        profit_fields = compute_onsite_profit_fields(service_charges, product_value, customer_price)
        engineer_name = self._engineer_name_by_id(db_session, int(closure.engineer_id or 0)) if closure.engineer_id else ""
        payment_status = str(closure.payment_status or "").strip()
        payment_mode = str(closure.payment_mode or "").strip()
        return {
            "final_status": str(closure.final_status or "").strip(),
            "close_reason": str(closure.close_reason or "").strip(),
            "completion_type": str(closure.completion_type or "").strip(),
            "narration": str(closure.narration or "").strip(),
            "service_charges": float(service_charges),
            "product_value": float(product_value),
            "customer_price": float(customer_price),
            "product_profit": float(profit_fields["product_profit"]),
            "total_profit": float(profit_fields["total_profit"]),
            "engineer_id": int(closure.engineer_id or 0) if closure.engineer_id else 0,
            "engineer_name": engineer_name,
            "closed_by_brand": str(closure.closed_by_brand or "").strip(),
            "payment_mode": payment_mode,
            "payment_status": payment_status,
            "payment_status_badge_class": PAYMENT_STATUS_BADGE_CLASSES.get(payment_status, "text-bg-secondary"),
            "is_credit_pending": payment_status == PAYMENT_STATUS_CREDIT_PENDING,
            "closed_by_user": str(closure.closed_by_user or "").strip(),
            "closed_at": closure.closed_at,
            "closed_at_display": format_datetime_display(closure.closed_at),
            "updated_at": closure.updated_at,
            "updated_at_display": format_datetime_display(closure.updated_at),
        }

    def _closure_map(self, db_session: Session, call_ids):
        safe_call_ids = [int(call_id) for call_id in call_ids if int(call_id or 0)]
        if not safe_call_ids:
            return {}
        rows = db_session.execute(
            select(OnsiteCallClosure).where(OnsiteCallClosure.call_id.in_(safe_call_ids))
        ).scalars()
        return {
            int(closure.call_id): self._serialize_closure(db_session, closure)
            for closure in rows
        }

    def _validate_payload(self, payload, public_mode=False):
        customer_name = str(payload.get("customer_name") or "").strip()
        phone = self._normalize_phone(payload.get("phone"))
        location = str(payload.get("location") or "").strip()
        district = str(payload.get("district") or "").strip()
        complaint_type = str(payload.get("complaint_type") or "").strip()
        raw_call_type = "Onsite" if public_mode else payload.get("call_type")
        call_type = "Onsite" if public_mode else normalize_call_type(raw_call_type)
        lead_source = "" if public_mode else str(payload.get("lead_source") or "").strip()
        preferred_service = str(payload.get("preferred_service") or "").strip()
        priority = str(payload.get("priority") or "").strip()
        preferred_datetime = self._parse_datetime(payload.get("preferred_datetime"))
        device_model = str(payload.get("device_model") or "").strip()
        complaint_description = str(payload.get("complaint_description") or "").strip()

        errors = []
        if not public_mode and call_type not in CALL_TYPES:
            errors.append("Select a valid entry type")
            call_type = "Onsite"
        if not customer_name:
            errors.append("Customer name is required")
        if len(phone) < 10:
            errors.append("Phone number must contain at least 10 digits")
        if not district:
            errors.append("District is required")
        if complaint_type not in COMPLAINT_TYPES:
            errors.append("Select a valid complaint type")
        if not complaint_description:
            errors.append("Complaint description is required")
        if len(lead_source) > 255:
            errors.append("Lead source must be 255 characters or fewer")

        if call_type == "Lead":
            if not lead_source:
                errors.append("Lead source is required")
            preferred_service = LEAD_DEFAULT_SERVICE
            priority = LEAD_DEFAULT_PRIORITY
            preferred_datetime = preferred_datetime or business_now_naive()
        else:
            if not location:
                errors.append("Location is required")
            if preferred_service not in PREFERRED_SERVICES:
                errors.append("Select a valid preferred service")
            if priority not in PRIORITY_LEVELS:
                errors.append("Select a valid priority")
            if not preferred_datetime:
                errors.append("Preferred date and time is required")

        return {
            "is_valid": not errors,
            "errors": errors,
            "values": {
                "customer_name": customer_name,
                "phone": phone,
                "location": location,
                "district": district,
                "complaint_type": complaint_type,
                "preferred_service": preferred_service,
                "priority": priority,
                "preferred_datetime": preferred_datetime,
                "device_model": device_model,
                "complaint_description": complaint_description,
                "call_type": call_type,
                "lead_source": lead_source,
            },
        }

    def _allowed_scope_clause(self, actor, branch_column):
        if actor["has_global_scope"]:
            return None
        if not actor["branch"]:
            return branch_column.is_(None)
        return branch_column == actor["branch"]

    def _base_listing_select(self):
        calls_table = OnsiteCall.__table__
        branch_alias = self._dropdown_options_table.alias("assigned_branch") if self._dropdown_options_table is not None else None
        engineer_alias = self._users_table.alias("assigned_engineer") if self._users_table is not None else None
        select_from = calls_table
        columns = [
            OnsiteCall.id,
            OnsiteCall.customer_name,
            OnsiteCall.phone,
            OnsiteCall.location,
            OnsiteCall.district,
            OnsiteCall.complaint_type,
            OnsiteCall.preferred_service,
            OnsiteCall.priority,
            OnsiteCall.preferred_datetime,
            OnsiteCall.device_model,
            OnsiteCall.complaint_description,
            OnsiteCall.call_type,
            OnsiteCall.status,
            OnsiteCall.source,
            OnsiteCall.lead_source,
            OnsiteCall.assigned_branch_id,
            OnsiteCall.assigned_engineer_id,
            OnsiteCall.assigned_time,
            OnsiteCall.created_by,
            OnsiteCall.created_at,
            OnsiteCall.updated_at,
        ]
        if branch_alias is not None:
            select_from = select_from.outerjoin(branch_alias, branch_alias.c.id == OnsiteCall.assigned_branch_id)
            columns.append(branch_alias.c.value.label("assigned_branch_name"))
        if engineer_alias is not None:
            select_from = select_from.outerjoin(engineer_alias, engineer_alias.c.id == OnsiteCall.assigned_engineer_id)
            columns.append(engineer_alias.c.username.label("assigned_engineer_name"))
        return select(*columns).select_from(select_from), branch_alias, engineer_alias

    def _apply_listing_filters(self, stmt, branch_alias, actor, filters):
        if branch_alias is not None:
            scope_clause = self._allowed_scope_clause(actor, branch_alias.c.value)
            if scope_clause is not None:
                stmt = stmt.where(scope_clause)
        elif not actor["has_global_scope"] and actor["branch"]:
            stmt = stmt.where(OnsiteCall.created_by == actor["username"])

        date_from = self._parse_datetime(filters.get("from_date") + "T00:00" if filters.get("from_date") else "")
        date_to = self._parse_datetime(filters.get("to_date") + "T23:59" if filters.get("to_date") else "")
        status = str(filters.get("status") or "").strip()
        branch = str(filters.get("branch") or "").strip()
        engineer = str(filters.get("engineer") or "").strip()
        call_type = normalize_call_type(filters.get("call_type"))
        complaint_type = str(filters.get("complaint_type") or "").strip()
        priority = str(filters.get("priority") or "").strip()
        payment_status = str(filters.get("payment_status") or "").strip()
        search = str(filters.get("search") or "").strip()

        if date_from:
            stmt = stmt.where(OnsiteCall.created_at >= date_from)
        if date_to:
            stmt = stmt.where(OnsiteCall.created_at <= date_to)
        if status and status != "ALL":
            stmt = stmt.where(OnsiteCall.status == status)
        if branch and branch != "ALL" and branch_alias is not None:
            stmt = stmt.where(branch_alias.c.value == branch)
        if engineer and engineer != "ALL":
            try:
                engineer_id = int(engineer)
            except (TypeError, ValueError):
                engineer_id = 0
            if engineer_id:
                stmt = stmt.where(OnsiteCall.assigned_engineer_id == engineer_id)
        if call_type:
            stmt = stmt.where(OnsiteCall.call_type == call_type)
        if complaint_type and complaint_type != "ALL":
            stmt = stmt.where(OnsiteCall.complaint_type == complaint_type)
        if priority and priority != "ALL":
            stmt = stmt.where(OnsiteCall.priority == priority)
        if payment_status == PAYMENT_STATUS_CREDIT_PENDING:
            stmt = stmt.where(
                OnsiteCall.id.in_(
                    select(OnsiteCallClosure.call_id).where(OnsiteCallClosure.payment_status == PAYMENT_STATUS_CREDIT_PENDING)
                )
            )
        if search:
            token = f"%{search}%"
            stmt = stmt.where(or_(OnsiteCall.customer_name.like(token), OnsiteCall.phone.like(token)))
        return stmt

    def _cache_key(self, prefix, actor, filters):
        safe_filters = {key: str(value or "") for key, value in sorted(filters.items())}
        return f"{prefix}:{actor['role']}:{actor['branch']}:{urlencode(safe_filters)}"

    def _serialize_call_row(self, row, closure_data=None):
        preferred_datetime = normalize_display_datetime(row.preferred_datetime)
        assigned_time = normalize_display_datetime(row.assigned_time)
        created_at = normalize_display_datetime(row.created_at)
        updated_at = normalize_display_datetime(row.updated_at)
        branch_name = getattr(row, "assigned_branch_name", "") or ""
        engineer_name = getattr(row, "assigned_engineer_name", "") or ""
        call_type = normalize_call_type(getattr(row, "call_type", "")) or "Onsite"
        phone_digits = self._normalize_phone(row.phone)
        call_data = {
            "id": int(row.id),
            "customer_name": row.customer_name,
            "phone": row.phone,
            "phone_call_url": f"tel:{phone_digits}" if phone_digits else "",
            "location": row.location,
            "district": row.district,
            "complaint_type": row.complaint_type,
            "preferred_service": row.preferred_service,
            "priority": row.priority,
            "priority_badge_class": PRIORITY_BADGE_CLASSES.get(row.priority, "text-bg-secondary"),
            "preferred_datetime": preferred_datetime,
            "preferred_datetime_value": preferred_datetime.strftime("%Y-%m-%dT%H:%M") if preferred_datetime else "",
            "preferred_datetime_display": format_datetime_display(preferred_datetime),
            "device_model": row.device_model,
            "complaint_description": row.complaint_description,
            "call_type": call_type,
            "type_badge_class": CALL_TYPE_BADGE_CLASSES.get(call_type, "text-bg-secondary"),
            "is_lead": call_type == "Lead",
            "status": row.status,
            "status_badge_class": STATUS_BADGE_CLASSES.get(row.status, "text-bg-secondary"),
            "source": row.source,
            "lead_source": getattr(row, "lead_source", "") or "",
            "assigned_branch_id": row.assigned_branch_id,
            "assigned_branch_name": branch_name,
            "assigned_engineer_id": row.assigned_engineer_id,
            "assigned_engineer_name": engineer_name,
            "assigned_time": assigned_time,
            "assigned_time_display": format_datetime_display(assigned_time),
            "created_by": row.created_by,
            "created_at": created_at,
            "created_at_display": format_datetime_display(created_at),
            "updated_at": updated_at,
            "updated_at_display": format_datetime_display(updated_at),
        }
        closure_data = closure_data or {}
        call_data.update(
            {
                "has_closure_record": bool(closure_data),
                "completion_type": closure_data.get("completion_type", ""),
                "closure_closed_by_brand": closure_data.get("closed_by_brand", ""),
                "closure_service_charges": closure_data.get("service_charges", ""),
                "closure_product_value": closure_data.get("product_value", ""),
                "closure_customer_price": closure_data.get("customer_price", ""),
                "closure_product_profit": closure_data.get("product_profit", ""),
                "closure_total_profit": closure_data.get("total_profit", ""),
                "payment_mode": closure_data.get("payment_mode", ""),
                "payment_status": closure_data.get("payment_status", ""),
                "payment_status_badge_class": closure_data.get("payment_status_badge_class", "text-bg-secondary"),
                "is_credit_pending": bool(closure_data.get("is_credit_pending")),
            }
        )
        return call_data

    def list_calls(self, actor, filters):
        page = max(1, int(filters.get("page") or 1))
        per_page = max(1, min(MAX_PER_PAGE, int(filters.get("per_page") or DEFAULT_PER_PAGE)))
        with self.session_scope() as db_session:
            stmt, branch_alias, _engineer_alias = self._base_listing_select()
            stmt = self._apply_listing_filters(stmt, branch_alias, actor, filters)
            count_stmt = select(func.count()).select_from(stmt.subquery())
            total_count = int(db_session.execute(count_stmt).scalar_one() or 0)
            total_pages = max(1, (total_count + per_page - 1) // per_page)
            page = min(page, total_pages)
            rows = db_session.execute(
                stmt.order_by(
                    func.coalesce(OnsiteCall.assigned_time, OnsiteCall.created_at).desc(),
                    OnsiteCall.created_at.desc(),
                    OnsiteCall.id.desc(),
                ).offset((page - 1) * per_page).limit(per_page)
            ).all()
            closure_map = self._closure_map(db_session, [row.id for row in rows])
            items = [self._serialize_call_row(row, closure_map.get(int(row.id))) for row in rows]
        return {
            "items": items,
            "page": page,
            "per_page": per_page,
            "total_count": total_count,
            "total_pages": total_pages,
        }

    def export_calls(self, actor, filters):
        with self.session_scope() as db_session:
            stmt, branch_alias, _engineer_alias = self._base_listing_select()
            stmt = self._apply_listing_filters(stmt, branch_alias, actor, filters)
            rows = db_session.execute(
                stmt.order_by(
                    func.coalesce(OnsiteCall.assigned_time, OnsiteCall.created_at).desc(),
                    OnsiteCall.created_at.desc(),
                    OnsiteCall.id.desc(),
                )
            ).all()
            closure_map = self._closure_map(db_session, [row.id for row in rows])
            return [self._serialize_call_row(row, closure_map.get(int(row.id))) for row in rows]

    def credit_pending_count(self, actor, filters):
        applied_filters = {key: value for key, value in (filters or {}).items() if key not in {"status", "page", "per_page", "payment_status"}}
        applied_filters["payment_status"] = PAYMENT_STATUS_CREDIT_PENDING
        with self.session_scope() as db_session:
            stmt, branch_alias, _engineer_alias = self._base_listing_select()
            stmt = self._apply_listing_filters(stmt, branch_alias, actor, applied_filters)
            return int(db_session.execute(select(func.count()).select_from(stmt.subquery())).scalar_one() or 0)

    def dashboard_counts(self, actor, filters, use_cache=True):
        cache_key = self._cache_key("dashboard-counts", actor, {key: value for key, value in filters.items() if key != "status"})
        if use_cache:
            cached = self.cache.get(cache_key)
            if cached is not None:
                return cached
        with self.session_scope() as db_session:
            stmt, branch_alias, _engineer_alias = self._base_listing_select()
            stmt = self._apply_listing_filters(stmt, branch_alias, actor, {key: value for key, value in filters.items() if key != "status"})
            filtered_calls = stmt.subquery()
            grouped_stmt = (
                select(filtered_calls.c.status, func.count().label("count"))
                .group_by(filtered_calls.c.status)
            )
            grouped_rows = db_session.execute(grouped_stmt).all()
        counts = {label: 0 for label, _title in STATUS_SECTIONS if label != "ALL"}
        total_count = 0
        for row in grouped_rows:
            counts[str(row.status)] = int(row.count or 0)
            total_count += int(row.count or 0)
        counts["ALL"] = total_count
        if use_cache:
            self.cache.set(cache_key, counts)
        return counts

    def _call_in_scope(self, db_session: Session, call_id: int, actor, lock_row=False):
        stmt, branch_alias, engineer_alias = self._base_listing_select()
        stmt = stmt.where(OnsiteCall.id == call_id)
        stmt = self._apply_listing_filters(stmt, branch_alias, actor, {})
        if lock_row:
            stmt = stmt.with_for_update()
        row = db_session.execute(stmt).first()
        return row

    def _prepare_media_uploads(self, upload_files):
        files = [upload for upload in (upload_files or []) if upload and str(upload.filename or "").strip()]
        if len(files) > MAX_ONSITE_MEDIA_ATTACHMENTS:
            return [], [f"You can upload up to {MAX_ONSITE_MEDIA_ATTACHMENTS} complaint or device files only"]

        prepared_uploads = []
        errors = []
        max_size_mb = ONSITE_MEDIA_MAX_BYTES // (1024 * 1024)
        for index, upload in enumerate(files, start=1):
            file_size = _measure_upload_size(upload)
            if file_size <= 0:
                errors.append(f"File {index} is empty")
                continue
            if file_size > ONSITE_MEDIA_MAX_BYTES:
                errors.append(f"Each uploaded image or video must be {max_size_mb} MB or smaller")
                continue

            media_kind, extension, mime_type = _sniff_onsite_media_type(upload)
            if not extension:
                errors.append("Only JPG, PNG, GIF, WEBP, MP4, MOV, WEBM, and OGV files are allowed")
                continue

            prepared_uploads.append(
                {
                    "file_storage": upload,
                    "media_kind": media_kind,
                    "extension": extension,
                    "mime_type": mime_type,
                }
            )

        return prepared_uploads, errors

    def _remove_saved_media_files(self, filenames):
        for filename in filenames or []:
            normalized_filename = str(filename or "").strip()
            if not normalized_filename:
                continue
            try:
                file_path = os.path.join(self.media_folder, normalized_filename)
                if os.path.exists(file_path):
                    os.remove(file_path)
            except OSError:
                self.app.logger.warning("Could not remove onsite media file %s", normalized_filename)

    def _store_media_uploads(self, db_session: Session, call_id: int, prepared_uploads):
        saved_filenames = []
        try:
            for index, upload in enumerate(prepared_uploads, start=1):
                stored_name = f"onsite_call_{call_id}_{index}_{uuid4().hex}{upload['extension']}"
                upload_file = upload["file_storage"]
                upload_file.stream.seek(0)
                upload_file.save(os.path.join(self.media_folder, stored_name))
                saved_filenames.append(stored_name)
                db_session.add(
                    OnsiteCallAttachment(
                        call_id=call_id,
                        filename=stored_name,
                        media_kind=upload["media_kind"],
                        mime_type=upload["mime_type"],
                    )
                )
        except Exception:
            self._remove_saved_media_files(saved_filenames)
            raise
        return saved_filenames

    def purge_expired_attachments(self, force=False):
        now = time.time()
        with _onsite_media_cleanup_lock:
            last_run = float(_onsite_media_cleanup_state.get("last_run") or 0.0)
            if not force and now - last_run < ONSITE_MEDIA_CLEANUP_INTERVAL_SECONDS:
                return
            _onsite_media_cleanup_state["last_run"] = now

        cutoff = business_now_naive() - timedelta(days=ONSITE_MEDIA_RETENTION_DAYS)
        filenames_to_remove = []
        with self.session_scope() as db_session:
            rows = db_session.execute(
                select(OnsiteCallAttachment.id, OnsiteCallAttachment.filename)
                .join(OnsiteCall, OnsiteCall.id == OnsiteCallAttachment.call_id)
                .where(OnsiteCall.status.in_(tuple(FINAL_STATUSES)))
                .where(OnsiteCall.updated_at <= cutoff)
            ).all()
            if not rows:
                return

            attachment_ids = [int(row.id) for row in rows]
            filenames_to_remove = [str(row.filename or "").strip() for row in rows if str(row.filename or "").strip()]
            db_session.execute(delete(OnsiteCallAttachment).where(OnsiteCallAttachment.id.in_(attachment_ids)))

        self._remove_saved_media_files(filenames_to_remove)

    def get_attachment(self, actor, call_id: int, attachment_id: int):
        with self.session_scope() as db_session:
            row = self._call_in_scope(db_session, call_id, actor, lock_row=False)
            if not row:
                return None
            attachment = db_session.execute(
                select(OnsiteCallAttachment)
                .where(OnsiteCallAttachment.id == attachment_id)
                .where(OnsiteCallAttachment.call_id == call_id)
                .limit(1)
            ).scalar_one_or_none()
            if not attachment:
                return None
            return {
                "filename": attachment.filename,
                "media_kind": attachment.media_kind,
                "mime_type": attachment.mime_type,
            }

    def get_call_detail(self, actor, call_id: int):
        with self.session_scope() as db_session:
            row = self._call_in_scope(db_session, call_id, actor, lock_row=False)
            if not row:
                return None
            closure_record = db_session.execute(
                select(OnsiteCallClosure).where(OnsiteCallClosure.call_id == call_id).limit(1)
            ).scalar_one_or_none()
            closure_data = self._serialize_closure(db_session, closure_record)
            call_data = self._serialize_call_row(row, closure_data)
            attachments = [
                {
                    "id": int(attachment.id),
                    "media_kind": attachment.media_kind,
                    "mime_type": attachment.mime_type,
                    "uploaded_at": attachment.uploaded_at,
                    "uploaded_at_display": format_datetime_display(attachment.uploaded_at),
                }
                for attachment in db_session.execute(
                    select(OnsiteCallAttachment)
                    .where(OnsiteCallAttachment.call_id == call_id)
                    .order_by(OnsiteCallAttachment.id.asc())
                ).scalars()
            ]
            notes = [
                {
                    "id": int(note.id),
                    "note": note.note,
                    "created_by": note.created_by,
                    "created_at": note.created_at,
                    "created_at_display": format_datetime_display(note.created_at),
                }
                for note in db_session.execute(
                    select(OnsiteCallNote).where(OnsiteCallNote.call_id == call_id).order_by(OnsiteCallNote.created_at.desc())
                ).scalars()
            ]
            logs = [
                {
                    "id": int(log.id),
                    "action": log.action,
                    "description": log.description,
                    "done_by": log.done_by,
                    "created_at": log.created_at,
                    "created_at_display": format_datetime_display(log.created_at),
                }
                for log in db_session.execute(
                    select(OnsiteCallLog).where(OnsiteCallLog.call_id == call_id).order_by(OnsiteCallLog.created_at.desc())
                ).scalars()
            ]
        timeline = [
            {
                "entry_type": "log",
                "title": log["action"],
                "description": log["description"],
                "done_by": log["done_by"],
                "created_at": log["created_at"],
                "created_at_display": log["created_at_display"],
            }
            for log in logs
        ] + [
            {
                "entry_type": "note",
                "title": "Note added",
                "description": note["note"],
                "done_by": note["created_by"],
                "created_at": note["created_at"],
                "created_at_display": note["created_at_display"],
            }
            for note in notes
        ]
        timeline.sort(key=lambda item: item["created_at"] or datetime.min, reverse=True)
        return {
            "call": call_data,
            "closure": closure_data,
            "attachments": attachments,
            "notes": notes,
            "logs": logs,
            "timeline": timeline,
        }

    def _log(self, db_session: Session, call_id: int, action: str, description: str, done_by: str | None = None):
        db_session.add(
            OnsiteCallLog(
                call_id=call_id,
                action=action,
                description=description,
                done_by=done_by,
            )
        )

    def _notify(self, db_session: Session, call_id: int, action: str, description: str, done_by: str | None = None):
        self._log(db_session, call_id, action, description, done_by)
        self.app.logger.info("Onsite call notification | call_id=%s | %s", call_id, description)

    def _internal_source(self, actor):
        return "Admin" if actor["role"] in ADMIN_ROLES else "Staff"

    def create_public_call(self, payload, upload_files=None):
        validated = self._validate_payload(payload, public_mode=True)
        prepared_uploads, upload_errors = self._prepare_media_uploads(upload_files)
        combined_errors = list(validated["errors"])
        combined_errors.extend(upload_errors)
        if combined_errors:
            return None, combined_errors

        values = dict(validated["values"])
        values.pop("call_type", None)
        values.pop("lead_source", None)

        saved_filenames = []
        try:
            with self.session_scope() as db_session:
                onsite_call = OnsiteCall(
                    **values,
                    call_type="Onsite",
                    status="New Lead",
                    source="Customer",
                    lead_source=None,
                    created_by=None,
                )
                db_session.add(onsite_call)
                db_session.flush()
                saved_filenames = self._store_media_uploads(db_session, onsite_call.id, prepared_uploads)
                self._log(db_session, onsite_call.id, "Created", "Call Created by Customer", "Customer")
                if saved_filenames:
                    self._log(
                        db_session,
                        onsite_call.id,
                        "Media Uploaded",
                        f"{len(saved_filenames)} complaint or device file(s) uploaded",
                        "Customer",
                    )
                admin_targets = self.admin_usernames()
                if admin_targets:
                    self._notify(
                        db_session,
                        onsite_call.id,
                        "Notification",
                        "Admin notified: " + ", ".join(admin_targets),
                        "System",
                    )
                call_id = onsite_call.id
        except Exception:
            self._remove_saved_media_files(saved_filenames)
            raise
        self.invalidate_cache()
        return call_id, []

    def create_internal_call(self, actor, payload, upload_files=None):
        validated = self._validate_payload(payload, public_mode=False)
        prepared_uploads, upload_errors = self._prepare_media_uploads(upload_files)
        combined_errors = list(validated["errors"])
        combined_errors.extend(upload_errors)
        if combined_errors:
            return None, combined_errors
        call_type = str(validated["values"].get("call_type") or "Onsite").strip() or "Onsite"
        branch_name = str(payload.get("branch_name") or actor["branch"] or "").strip()
        engineer_id = str(payload.get("assigned_engineer_id") or "").strip()
        assigned_branch_id = None
        assigned_engineer_id = None
        assigned_now = None
        source = self._internal_source(actor)
        if engineer_id and not self.can_assign(actor):
            return None, ["Only admin or super admin can assign engineers"]
        if not branch_name:
            return None, ["Assign branch is required"]
        saved_filenames = []
        try:
            with self.session_scope() as db_session:
                if branch_name:
                    if not actor["has_global_scope"] and branch_name != actor["branch"]:
                        return None, ["You do not have access to this branch"]
                    assigned_branch_id = self.branch_id_from_name(db_session, branch_name)
                    if assigned_branch_id is None:
                        return None, ["Select a valid branch"]
                if engineer_id:
                    try:
                        assigned_engineer_id = int(engineer_id)
                    except (TypeError, ValueError):
                        return None, ["Select a valid engineer"]
                    assigned_now = business_now_naive()
                created_status = "Assigned" if assigned_engineer_id else ("New Lead" if call_type == "Lead" else "Open")
                onsite_call = OnsiteCall(
                    **validated["values"],
                    status=created_status,
                    source=source,
                    assigned_branch_id=assigned_branch_id,
                    assigned_engineer_id=assigned_engineer_id,
                    assigned_time=assigned_now,
                    created_by=actor["username"],
                )
                db_session.add(onsite_call)
                db_session.flush()
                saved_filenames = self._store_media_uploads(db_session, onsite_call.id, prepared_uploads)
                self._log(
                    db_session,
                    onsite_call.id,
                    "Created",
                    f"{'Lead' if call_type == 'Lead' else 'Onsite Call'} Created by {source}",
                    actor["username"],
                )
                if call_type == "Lead" and validated["values"].get("lead_source"):
                    self._log(
                        db_session,
                        onsite_call.id,
                        "Lead Source",
                        f"Lead source recorded as {validated['values']['lead_source']}",
                        actor["username"],
                    )
                if saved_filenames:
                    self._log(
                        db_session,
                        onsite_call.id,
                        "Media Uploaded",
                        f"{len(saved_filenames)} complaint or device file(s) uploaded",
                        actor["username"],
                    )
                if assigned_engineer_id:
                    engineer_name = self._engineer_name_by_id(db_session, assigned_engineer_id)
                    self._log(
                        db_session,
                        onsite_call.id,
                        "Assigned",
                        f"Assigned during creation to {engineer_name or 'Engineer'}",
                        actor["username"],
                    )
                    self._notify(
                        db_session,
                        onsite_call.id,
                        "Notification",
                        f"Engineer notified: {engineer_name or assigned_engineer_id} | Branch notified: {branch_name}",
                        "System",
                    )
                elif branch_name:
                    self._notify(
                        db_session,
                        onsite_call.id,
                        "Notification",
                        f"Branch notified: {branch_name}",
                        "System",
                    )
                call_id = onsite_call.id
        except Exception:
            self._remove_saved_media_files(saved_filenames)
            raise
        self.invalidate_cache()
        return call_id, []

    def update_call_details(self, actor, payload):
        try:
            call_id = int(payload.get("call_id") or 0)
        except (TypeError, ValueError):
            return None, ["Call is required"]
        if not call_id:
            return None, ["Call is required"]

        validated = self._validate_payload(payload, public_mode=False)
        if not validated["is_valid"]:
            return None, validated["errors"]

        with self.session_scope() as db_session:
            row = self._call_in_scope(db_session, call_id, actor, lock_row=True)
            if not row:
                return None, ["Call not found or access denied"]

            closure_record = db_session.execute(
                select(OnsiteCallClosure).where(OnsiteCallClosure.call_id == call_id).limit(1)
            ).scalar_one_or_none()
            closure_data = self._serialize_closure(db_session, closure_record)
            call_data = self._serialize_call_row(row, closure_data)
            if not self.can_edit(actor, call_data):
                return None, ["You do not have permission to edit this case"]

            onsite_call = db_session.get(OnsiteCall, call_id, with_for_update=True)
            previous_call_type = str(onsite_call.call_type or "Onsite").strip() or "Onsite"
            previous_status = str(onsite_call.status or "").strip()

            for field_name, field_value in validated["values"].items():
                setattr(onsite_call, field_name, field_value)

            new_call_type = str(validated["values"].get("call_type") or previous_call_type).strip() or previous_call_type
            if previous_call_type != new_call_type:
                if new_call_type == "Lead" and previous_status == "Open":
                    onsite_call.status = "New Lead"
                elif previous_call_type == "Lead" and new_call_type == "Onsite" and previous_status == "New Lead":
                    onsite_call.status = "Assigned" if onsite_call.assigned_engineer_id else "Open"

            onsite_call.updated_at = business_now_naive()
            self._log(
                db_session,
                call_id,
                "Details Updated",
                f"Call details updated by {actor['username']}",
                actor["username"],
            )

        self.invalidate_cache()
        return call_id, []

    def _engineer_name_by_id(self, db_session: Session, engineer_id: int):
        if self._users_table is None:
            return ""
        row = db_session.execute(
            select(self._users_table.c.username).where(self._users_table.c.id == engineer_id).limit(1)
        ).first()
        return str(row.username or "") if row else ""

    def engineer_name_by_id(self, engineer_id):
        try:
            resolved_id = int(engineer_id or 0)
        except (TypeError, ValueError):
            resolved_id = 0
        if not resolved_id:
            return ""
        with self.session_scope() as db_session:
            return self._engineer_name_by_id(db_session, resolved_id)

    def assign_call(self, actor, payload):
        try:
            call_id = int(payload.get("call_id") or 0)
            engineer_id = int(payload.get("assigned_engineer_id") or 0)
        except (TypeError, ValueError):
            return None, ["Call is required"]
        if not call_id:
            return None, ["Call is required"]
        with self.session_scope() as db_session:
            row = self._call_in_scope(db_session, call_id, actor, lock_row=True)
            if not row:
                return None, ["Call not found or access denied"]
            if not self.can_assign(actor, row):
                return None, [self.assignment_message(actor, row) or "Only admin or super admin can assign calls"]
            current_status = row.status
            existing_engineer_id = int(row.assigned_engineer_id or 0) if row.assigned_engineer_id else 0
            if existing_engineer_id and current_status not in {"Open", "Assigned", "Rescheduled"}:
                return None, ["Only Open, Assigned or Rescheduled calls can be reassigned once an engineer is already set"]
            if not existing_engineer_id and current_status in FINAL_STATUSES:
                return None, ["Closed cases cannot receive a new engineer assignment"]
            branch_name = str(payload.get("branch_name") or self._call_value(row, "assigned_branch_name") or actor["branch"] or "").strip()
            if not branch_name:
                return None, ["Branch is required"]
            if self._is_coordinator(actor):
                current_branch_name = str(self._call_value(row, "assigned_branch_name") or "").strip()
                if not current_branch_name:
                    return None, ["Coordinator can fill engineer only after the case is assigned to a branch"]
                if branch_name.upper() != current_branch_name.upper():
                    return None, ["Coordinator cannot change the assigned branch"]
                if not engineer_id:
                    return None, ["Coordinator must choose an engineer for this branch-assigned case"]
            if not actor["has_global_scope"] and branch_name != actor["branch"]:
                return None, ["You do not have access to this branch"]
            branch_id = self.branch_id_from_name(db_session, branch_name)
            if branch_id is None:
                return None, ["Select a valid branch"]
            engineer_name = self._engineer_name_by_id(db_session, engineer_id) if engineer_id else ""
            if engineer_id and not engineer_name:
                return None, ["Select a valid engineer"]
            onsite_call = db_session.get(OnsiteCall, call_id, with_for_update=True)
            existing_assigned_engineer_id = int(onsite_call.assigned_engineer_id or 0) if onsite_call.assigned_engineer_id else 0
            action = "Reassigned" if existing_assigned_engineer_id and engineer_id else "Assigned"
            onsite_call.assigned_branch_id = branch_id
            onsite_call.assigned_engineer_id = engineer_id or None
            onsite_call.assigned_time = business_now_naive() if engineer_id else None
            if engineer_id:
                onsite_call.status = "Assigned"
            onsite_call.updated_at = business_now_naive()
            if engineer_id:
                self._log(
                    db_session,
                    call_id,
                    action,
                    f"Call assigned to {engineer_name} under {branch_name}",
                    actor["username"],
                )
                self._notify(
                    db_session,
                    call_id,
                    "Notification",
                    f"Engineer notified: {engineer_name} | Branch notified: {branch_name}",
                    "System",
                )
            else:
                onsite_call.status = onsite_call.status or "Open"
                self._log(
                    db_session,
                    call_id,
                    "Branch Assigned",
                    f"Case assigned to branch {branch_name} without selecting a named engineer",
                    actor["username"],
                )
                self._notify(
                    db_session,
                    call_id,
                    "Notification",
                    f"Branch notified: {branch_name}",
                    "System",
                )
        self.invalidate_cache()
        return call_id, []

    def update_status(self, actor, payload):
        try:
            call_id = int(payload.get("call_id") or 0)
        except (TypeError, ValueError):
            return None, ["Call is required"]
        new_status = str(payload.get("status") or "").strip()
        status_note = str(payload.get("note") or payload.get("status_note") or "").strip()
        if new_status not in STATUSES:
            return None, ["Select a valid status"]
        if new_status in FINAL_STATUSES:
            return None, ["Use Close Case to mark a case as Completed, Failed, or Cancelled"]
        with self.session_scope() as db_session:
            row = self._call_in_scope(db_session, call_id, actor, lock_row=True)
            if not row:
                return None, ["Call not found or access denied"]
            existing_closure = db_session.execute(
                select(OnsiteCallClosure.id).where(OnsiteCallClosure.call_id == call_id).limit(1)
            ).scalar_one_or_none()
            if existing_closure:
                return None, ["This case is already closed. Credit payments can still be settled from the detail page."]
            current_status = row.status
            role = str(actor.get("role") or "").strip().lower()
            available_status_choices = self.available_nonfinal_status_choices(actor, row)
            if new_status == current_status:
                return None, ["Status is already set to that value"]
            if new_status not in available_status_choices:
                if role == "engineer":
                    if current_status in FINAL_STATUSES:
                        return None, ["Engineers cannot update status after a case is Completed, Cancelled, or Failed."]
                    if not self._is_assigned_engineer(actor, row):
                        return None, ["Only the assigned engineer can update this case status."]
                if self._is_coordinator(actor):
                    if self._call_value(row, "assigned_engineer_id") or self._call_value(row, "assigned_engineer_name"):
                        return None, ["Once an engineer is assigned, only that assigned engineer can continue status updates."]
                    return None, ["Coordinator can update status only for cases assigned to their own branch."]
                return None, [f"Invalid transition: {current_status} -> {new_status}"]
            onsite_call = db_session.get(OnsiteCall, call_id, with_for_update=True)
            onsite_call.status = new_status
            onsite_call.updated_at = business_now_naive()
            self._log(
                db_session,
                call_id,
                "Status Updated",
                f"Status changed from {current_status} to {new_status}" + (f" | {status_note}" if status_note else ""),
                actor["username"],
            )
        self.invalidate_cache()
        return call_id, []

    def close_call(self, actor, payload):
        try:
            call_id = int(payload.get("call_id") or 0)
        except (TypeError, ValueError):
            return None, ["Call is required"]
        final_status = str(payload.get("final_status") or payload.get("status") or "").strip()
        if final_status not in FINAL_STATUSES:
            return None, ["Select a valid final status"]

        with self.session_scope() as db_session:
            row = self._call_in_scope(db_session, call_id, actor, lock_row=True)
            if not row:
                return None, ["Call not found or access denied"]
            if row.status in FINAL_STATUSES:
                return None, ["This case is already in a final status"]
            available_close_choices = tuple(status for status in self.available_status_choices(actor, row) if status in FINAL_STATUSES)
            if final_status not in available_close_choices:
                return None, [f"Invalid transition: {row.status} -> {final_status}"]
            existing_closure = db_session.execute(
                select(OnsiteCallClosure).where(OnsiteCallClosure.call_id == call_id).limit(1)
            ).scalar_one_or_none()
            if existing_closure:
                return None, ["This case is already closed"]

            close_reason = str(payload.get("close_reason") or payload.get("reason") or "").strip()
            completion_type = str(payload.get("completion_type") or "").strip()
            narration = str(payload.get("narration") or "").strip()
            closed_by_brand = str(payload.get("closed_by_brand") or "").strip()
            payment_mode = str(payload.get("payment_mode") or "").strip()
            service_charges = Decimal("0.00")
            product_value = Decimal("0.00")
            customer_price = Decimal("0.00")
            engineer_id = 0
            engineer_name = ""
            payment_status = ""
            validation_errors = []

            if final_status in {"Failed", "Cancelled"}:
                if not close_reason:
                    validation_errors.append("Reason is required to close a case as Failed or Cancelled")
            elif final_status == "Completed":
                if completion_type not in COMPLETION_TYPES:
                    validation_errors.append("Select a valid completion type")
                elif completion_type in {"Warranty Service", "Free Service"}:
                    if not narration:
                        validation_errors.append("Narration is required for Warranty Service or Free Service")
                elif completion_type == PAID_COMPLETION_TYPE:
                    service_charges, error = self._parse_money(payload.get("service_charges"), "Service charges", required=True)
                    if error:
                        validation_errors.append(error)
                    product_value, error = self._parse_money(payload.get("product_value"), "Product value", required=True)
                    if error:
                        validation_errors.append(error)
                    customer_price, error = self._parse_money(payload.get("customer_price"), "Customer price", required=True)
                    if error:
                        validation_errors.append(error)
                    if closed_by_brand not in CLOSED_BY_OPTIONS:
                        validation_errors.append("Select who closed this paid service")
                    if payment_mode not in PAYMENT_MODE_OPTIONS:
                        validation_errors.append("Select a valid mode of payment")
                    try:
                        engineer_id = int(payload.get("closure_engineer_id") or payload.get("engineer_id") or 0)
                    except (TypeError, ValueError):
                        engineer_id = 0
                    if not engineer_id:
                        validation_errors.append("Engineer name is required for paid service closure")
                    else:
                        engineer_name = self._engineer_name_by_id(db_session, engineer_id)
                        if not engineer_name:
                            validation_errors.append("Select an engineer from the list for paid service closure")
                    payment_status = PAYMENT_STATUS_CREDIT_PENDING if payment_mode == "Credit" else PAYMENT_STATUS_RECEIVED

            if validation_errors:
                return None, validation_errors

            onsite_call = db_session.get(OnsiteCall, call_id, with_for_update=True)
            onsite_call.status = final_status
            onsite_call.updated_at = business_now_naive()
            db_session.add(
                OnsiteCallClosure(
                    call_id=call_id,
                    final_status=final_status,
                    close_reason=close_reason or None,
                    completion_type=completion_type or None,
                    narration=narration or None,
                    service_charges=service_charges,
                    engineer_id=engineer_id or None,
                    product_value=product_value,
                    customer_price=customer_price,
                    closed_by_brand=closed_by_brand or None,
                    payment_mode=payment_mode or None,
                    payment_status=payment_status or None,
                    closed_by_user=actor["username"],
                )
            )
            if final_status in {"Failed", "Cancelled"}:
                log_message = f"Case closed as {final_status} | Reason: {close_reason}"
            elif completion_type in {"Warranty Service", "Free Service"}:
                log_message = f"Case completed under {completion_type}" + (f" | {narration}" if narration else "")
            else:
                profit_fields = compute_onsite_profit_fields(service_charges, product_value, customer_price)
                log_message = (
                    f"Case completed as Paid Service | Service charges: {service_charges:.2f} | "
                    f"Product profit: {profit_fields['product_profit']:.2f} | Payment: {payment_mode}"
                )
                if closed_by_brand:
                    log_message += f" | Closed by: {closed_by_brand}"
                if engineer_name:
                    log_message += f" | Engineer: {engineer_name}"
                if payment_status == PAYMENT_STATUS_CREDIT_PENDING:
                    log_message += " | Credit pending"
            self._log(db_session, call_id, "Case Closed", log_message, actor["username"])
        self.invalidate_cache()
        return call_id, []

    def add_note(self, actor, payload):
        try:
            call_id = int(payload.get("call_id") or 0)
        except (TypeError, ValueError):
            return None, ["Call is required"]
        note_text = str(payload.get("note") or "").strip()
        if not note_text:
            return None, ["Note is required"]
        with self.session_scope() as db_session:
            row = self._call_in_scope(db_session, call_id, actor, lock_row=True)
            if not row:
                return None, ["Call not found or access denied"]
            if not self.can_add_note(actor, row):
                return None, [self.note_message(actor, row) or "You cannot add notes to this case."]
            db_session.add(OnsiteCallNote(call_id=call_id, note=note_text, created_by=actor["username"]))
            self._log(db_session, call_id, "Note added", note_text, actor["username"])
        return call_id, []

    def reschedule_call(self, actor, payload):
        try:
            call_id = int(payload.get("call_id") or 0)
        except (TypeError, ValueError):
            return None, ["Call is required"]
        if not self.can_reschedule(actor):
            return None, ["Only admin or super admin can reschedule this case."]
        preferred_datetime = self._parse_datetime(payload.get("preferred_datetime"))
        if not preferred_datetime:
            return None, ["Preferred date and time is required"]
        note_text = str(payload.get("reason") or payload.get("note") or "").strip()
        with self.session_scope() as db_session:
            row = self._call_in_scope(db_session, call_id, actor, lock_row=True)
            if not row:
                return None, ["Call not found or access denied"]
            existing_closure = db_session.execute(
                select(OnsiteCallClosure.id).where(OnsiteCallClosure.call_id == call_id).limit(1)
            ).scalar_one_or_none()
            if existing_closure or row.status in FINAL_STATUSES:
                return None, ["Closed cases cannot be rescheduled"]
            onsite_call = db_session.get(OnsiteCall, call_id, with_for_update=True)
            onsite_call.preferred_datetime = preferred_datetime
            onsite_call.status = "Rescheduled"
            onsite_call.updated_at = business_now_naive()
            self._log(
                db_session,
                call_id,
                "Rescheduled",
                "Preferred service time updated to "
                + format_datetime_display(preferred_datetime)
                + (f" | {note_text}" if note_text else ""),
                actor["username"],
            )
        self.invalidate_cache()
        return call_id, []

    def settle_credit_payment(self, actor, payload):
        try:
            call_id = int(payload.get("call_id") or 0)
        except (TypeError, ValueError):
            return None, ["Call is required"]
        payment_mode = str(payload.get("payment_mode") or "").strip()
        if payment_mode not in {"Cash", "Card", "UPI"}:
            return None, ["Select Cash, Card, or UPI to settle the credit payment"]
        payment_note = str(payload.get("payment_note") or payload.get("note") or "").strip()
        with self.session_scope() as db_session:
            row = self._call_in_scope(db_session, call_id, actor, lock_row=True)
            if not row:
                return None, ["Call not found or access denied"]
            closure = db_session.execute(
                select(OnsiteCallClosure).where(OnsiteCallClosure.call_id == call_id).limit(1)
            ).scalar_one_or_none()
            if not closure or closure.payment_status != PAYMENT_STATUS_CREDIT_PENDING:
                return None, ["This case does not have any pending credit payment"]
            closure_like = self._serialize_closure(db_session, closure)
            call_like = self._serialize_call_row(row, closure_like)
            if not self.can_update_credit_payment(actor, call_like, closure_like):
                return None, ["You do not have permission to settle this credit payment"]
            closure.payment_mode = payment_mode
            closure.payment_status = PAYMENT_STATUS_RECEIVED
            closure.updated_at = business_now_naive()
            self._log(
                db_session,
                call_id,
                "Credit Settled",
                f"Credit payment settled via {payment_mode}" + (f" | {payment_note}" if payment_note else ""),
                actor["username"],
            )
        self.invalidate_cache()
        return call_id, []

    def delete_call(self, actor, payload):
        try:
            call_id = int(payload.get("call_id") or 0)
        except (TypeError, ValueError):
            return None, ["Call is required"]
        if not self.can_delete(actor):
            return None, ["Only admin or super admin can delete this case."]

        filenames_to_remove = []
        customer_name = ""
        with self.session_scope() as db_session:
            row = self._call_in_scope(db_session, call_id, actor, lock_row=True)
            if not row:
                return None, ["Call not found or access denied"]
            onsite_call = db_session.get(OnsiteCall, call_id, with_for_update=True)
            if not onsite_call:
                return None, ["Call not found or access denied"]
            customer_name = str(onsite_call.customer_name or "").strip()
            filenames_to_remove = [
                str(attachment.filename or "").strip()
                for attachment in onsite_call.attachments
                if str(attachment.filename or "").strip()
            ]
            db_session.delete(onsite_call)

        self._remove_saved_media_files(filenames_to_remove)
        self.invalidate_cache()
        self.app.logger.warning(
            "Onsite call deleted | call_id=%s | customer=%s | deleted_by=%s",
            call_id,
            customer_name or "-",
            actor.get("username") or "unknown",
        )
        return call_id, []

    def report_summary(self, actor, filters):
        cache_key = self._cache_key("reports", actor, filters)
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
        closed_by_brand = str(filters.get("closed_by_brand") or "").strip()
        profit_filters = {
            key: value
            for key, value in filters.items()
            if key not in {"closed_by_brand", "from_date", "to_date"}
        }
        profit_from = self._parse_datetime(f"{filters.get('from_date')}T00:00" if filters.get("from_date") else "")
        profit_to = self._parse_datetime(f"{filters.get('to_date')}T23:59" if filters.get("to_date") else "")
        with self.session_scope() as db_session:
            stmt, branch_alias, engineer_alias = self._base_listing_select()
            stmt = self._apply_listing_filters(stmt, branch_alias, actor, profit_filters)
            subquery = stmt.subquery()
            daily_rows = db_session.execute(
                select(func.date(subquery.c.created_at).label("day_label"), func.count().label("count_value"))
                .group_by(func.date(subquery.c.created_at))
                .order_by(func.date(subquery.c.created_at).desc())
                .limit(30)
            ).all()
            outcome_rows = db_session.execute(
                select(subquery.c.status, func.count().label("count_value"))
                .where(subquery.c.status.in_(["Completed", "Failed"]))
                .group_by(subquery.c.status)
            ).all()
            engineer_rows = db_session.execute(
                select(subquery.c.assigned_engineer_name, func.count().label("total_calls"))
                .where(subquery.c.assigned_engineer_name.is_not(None))
                .group_by(subquery.c.assigned_engineer_name)
                .order_by(func.count().desc())
            ).all()
            branch_rows = db_session.execute(
                select(subquery.c.assigned_branch_name, func.count().label("total_calls"))
                .where(subquery.c.assigned_branch_name.is_not(None))
                .group_by(subquery.c.assigned_branch_name)
                .order_by(func.count().desc())
            ).all()
            complaint_rows = db_session.execute(
                select(subquery.c.complaint_type, func.count().label("total_calls"))
                .group_by(subquery.c.complaint_type)
                .order_by(func.count().desc())
            ).all()
            profit_rows = db_session.execute(
                select(
                    subquery.c.id,
                    subquery.c.customer_name,
                    subquery.c.call_type,
                    subquery.c.assigned_branch_name,
                    subquery.c.lead_source,
                    OnsiteCallClosure.closed_at,
                    OnsiteCallClosure.service_charges,
                    OnsiteCallClosure.product_value,
                    OnsiteCallClosure.customer_price,
                    OnsiteCallClosure.closed_by_brand,
                )
                .select_from(subquery.join(OnsiteCallClosure, OnsiteCallClosure.call_id == subquery.c.id))
                .where(OnsiteCallClosure.final_status == "Completed")
                .where(OnsiteCallClosure.completion_type == PAID_COMPLETION_TYPE)
                .where(
                    OnsiteCallClosure.closed_by_brand == closed_by_brand
                    if closed_by_brand in CLOSED_BY_OPTIONS
                    else True
                )
                .where(OnsiteCallClosure.closed_at >= profit_from if profit_from else True)
                .where(OnsiteCallClosure.closed_at <= profit_to if profit_to else True)
                .order_by(OnsiteCallClosure.closed_at.desc(), subquery.c.id.desc())
            ).all()
        profit_sections = build_profit_sections(profit_rows)
        report_data = {
            "daily_rows": [
                {"day": str(row.day_label), "count": int(row.count_value or 0)} for row in daily_rows
            ],
            "outcome_rows": [
                {"status": str(row.status), "count": int(row.count_value or 0)} for row in outcome_rows
            ],
            "engineer_rows": [
                {"engineer_name": str(row.assigned_engineer_name or "Unassigned"), "count": int(row.total_calls or 0)}
                for row in engineer_rows
            ],
            "branch_rows": [
                {"branch_name": str(row.assigned_branch_name or "Unassigned"), "count": int(row.total_calls or 0)}
                for row in branch_rows
            ],
            "complaint_rows": [
                {"complaint_type": str(row.complaint_type or "Others"), "count": int(row.total_calls or 0)}
                for row in complaint_rows
            ],
            "profit_sections": profit_sections,
        }
        self.cache.set(cache_key, report_data)
        return report_data

    def profit_report_section(self, actor, filters, call_type):
        normalized_call_type = normalize_call_type(call_type)
        if not normalized_call_type:
            return None
        report_data = self.report_summary(actor, filters)
        for section in report_data.get("profit_sections", []):
            if str(section.get("call_type") or "") == normalized_call_type:
                return section
        return None

def create_onsite_calls_blueprint(app, config):
    service = OnsiteCallService(app, config)
    blueprint = Blueprint("onsite_calls", __name__)
    app.extensions.setdefault("onsite_calls_service", service)

    @blueprint.before_app_request
    def onsite_call_media_cleanup():
        if request.endpoint == "static":
            return None
        service.purge_expired_attachments()
        return None

    def wants_json_response():
        if request.args.get("format") == "json":
            return True
        if request.is_json:
            return True
        accept = request.accept_mimetypes
        return accept.best == "application/json" and accept[accept.best] >= accept["text/html"]

    def payload_from_request():
        if request.is_json:
            return request.get_json(silent=True) or {}
        return request.form.to_dict(flat=True)

    def safe_redirect_target(default_path):
        candidate = str(request.form.get("return_url") or request.args.get("return_url") or "").strip()
        if not candidate:
            return default_path
        parsed = urlparse(candidate)
        if parsed.scheme or parsed.netloc:
            return default_path
        if not candidate.startswith("/"):
            return default_path
        return candidate

    def json_or_redirect(success, message, default_path, extra_payload=None, status_code=200):
        payload = {"success": success, "message": message}
        if extra_payload:
            payload.update(extra_payload)
        if wants_json_response():
            return jsonify(payload), status_code
        flash(message, "success" if success else "danger")
        return redirect(safe_redirect_target(default_path))

    def require_login(default_path="/login"):
        if service.is_authenticated():
            return None
        if wants_json_response():
            return jsonify({"success": False, "message": "Authentication required"}), 401
        flash("Login required", "danger")
        return redirect(default_path)

    def render_form_context(public_mode, form_values=None, errors=None, extra_context=None):
        actor = service.actor()
        branch_options = service.branch_options(actor)
        active_branch = ""
        selected_call_type = "Onsite" if public_mode else (normalize_call_type((form_values or {}).get("call_type")) or "Onsite")
        selected_engineer_name = str((form_values or {}).get("assigned_engineer_name") or "").strip()
        public_request_registered = False
        public_request_id = ""
        if public_mode:
            engineer_options = []
            public_request_registered = str(request.args.get("submitted") or "").strip() == "1"
            public_request_id = str(request.args.get("request_id") or "").strip()
        else:
            active_branch = str((form_values or {}).get("branch_name") or actor["branch"] or "").strip()
            engineer_options = service.engineer_options(actor, active_branch)
            if not selected_engineer_name:
                selected_engineer_name = service.engineer_name_by_id((form_values or {}).get("assigned_engineer_id") or 0)
        context = {
            "public_mode": public_mode,
            "form_values": form_values or {},
            "errors": errors or [],
            "complaint_types": COMPLAINT_TYPES,
            "preferred_services": PREFERRED_SERVICES,
            "priority_levels": PRIORITY_LEVELS,
            "call_type_choices": CALL_TYPES,
            "branch_options": branch_options,
            "engineer_options": engineer_options,
            "selected_engineer_name": selected_engineer_name,
            "selected_call_type": selected_call_type,
            "can_assign_on_create": service.can_assign(actor),
            "active_branch": active_branch,
            "public_request_registered": public_request_registered,
            "public_request_id": public_request_id,
            "page_title": "Onsite Service Request" if public_mode else "Create Call or Lead",
        }
        if extra_context:
            context.update(extra_context)
        return context

    def status_sections_with_counts(counts):
        return [
            {"value": value, "title": title, "count": int(counts.get(value) or 0)}
            for value, title in STATUS_SECTIONS
        ]

    @blueprint.route("/onsite-call/request", methods=["GET"])
    def onsite_call_public_form():
        return render_template("onsite_call_form.html", **render_form_context(True))

    @blueprint.route("/onsite-calls/new", methods=["GET"])
    def onsite_call_new_page():
        auth_response = require_login()
        if auth_response is not None:
            return auth_response
        return render_template("onsite_call_form.html", **render_form_context(False))

    @blueprint.route("/onsite-calls/<int:call_id>/edit", methods=["GET"])
    def onsite_call_edit_page(call_id):
        auth_response = require_login()
        if auth_response is not None:
            return auth_response
        actor = service.actor()
        detail = service.get_call_detail(actor, call_id)
        if detail is None:
            flash("Call not found or access denied", "danger")
            return redirect("/onsite-calls")
        if not service.can_edit(actor, detail["call"]):
            flash("You do not have permission to edit this case", "danger")
            return redirect(f"/onsite-calls/{call_id}")

        form_values = {
            "call_id": detail["call"]["id"],
            "call_type": detail["call"].get("call_type", "Onsite"),
            "customer_name": detail["call"].get("customer_name", ""),
            "phone": detail["call"].get("phone", ""),
            "location": detail["call"].get("location", ""),
            "district": detail["call"].get("district", ""),
            "complaint_type": detail["call"].get("complaint_type", ""),
            "preferred_service": detail["call"].get("preferred_service", ""),
            "priority": detail["call"].get("priority", ""),
            "preferred_datetime": detail["call"].get("preferred_datetime_value", ""),
            "device_model": detail["call"].get("device_model", ""),
            "lead_source": detail["call"].get("lead_source", ""),
            "complaint_description": detail["call"].get("complaint_description", ""),
            "branch_name": detail["call"].get("assigned_branch_name", ""),
            "assigned_engineer_id": detail["call"].get("assigned_engineer_id", ""),
            "assigned_engineer_name": detail["call"].get("assigned_engineer_name", ""),
        }
        return_url = safe_redirect_target(f"/onsite-calls/{call_id}")
        return render_template(
            "onsite_call_form.html",
            **render_form_context(
                False,
                form_values,
                [],
                {
                    "page_title": "Edit Call or Lead",
                    "form_mode": "edit",
                    "edit_call_id": call_id,
                    "form_action": "/api/onsite-call/update",
                    "submit_button_label": "Save Changes",
                    "cancel_url": return_url,
                },
            ),
        )

    @blueprint.route("/api/onsite-call/create-public", methods=["POST"])
    def onsite_call_create_public():
        payload = payload_from_request()
        client_key = _public_create_client_key()
        if _public_create_rate_limited(client_key):
            message = _public_create_rate_limit_message()
            if wants_json_response():
                return jsonify({"success": False, "message": message}), 429
            return render_template("onsite_call_form.html", **render_form_context(True, payload, [message])), 429
        upload_files = [] if request.is_json else request.files.getlist("complaint_media")
        call_id, errors = service.create_public_call(payload, upload_files)
        if errors:
            if wants_json_response():
                return jsonify({"success": False, "message": errors[0], "errors": errors}), 400
            return render_template("onsite_call_form.html", **render_form_context(True, payload, errors)), 400
        _record_public_create_attempt(client_key)
        success_message = "Your request has been successfully registered with Sysmantech. Our support team will get in touch with you at the earliest"
        if wants_json_response():
            return jsonify({"success": True, "message": success_message, "call_id": call_id, "status": "New Lead", "source": "Customer"})
        return redirect(f"/onsite-call/request?submitted=1&request_id={call_id}")

    @blueprint.route("/api/onsite-call/create", methods=["POST"])
    def onsite_call_create_internal():
        auth_response = require_login()
        if auth_response is not None:
            return auth_response
        payload = payload_from_request()
        actor = service.actor()
        upload_files = [] if request.is_json else request.files.getlist("complaint_media")
        call_id, errors = service.create_internal_call(actor, payload, upload_files)
        if errors:
            if wants_json_response():
                return jsonify({"success": False, "message": errors[0], "errors": errors}), 400
            return render_template("onsite_call_form.html", **render_form_context(False, payload, errors)), 400
        created_label = "Lead" if normalize_call_type(payload.get("call_type")) == "Lead" else "Onsite call"
        return json_or_redirect(
            True,
            f"{created_label} created successfully. Call ID: {call_id}",
            f"/onsite-calls/{call_id}",
            {"call_id": call_id},
        )

    @blueprint.route("/api/onsite-call/update", methods=["POST"])
    def onsite_call_update_internal():
        auth_response = require_login()
        if auth_response is not None:
            return auth_response
        payload = payload_from_request()
        actor = service.actor()
        call_id, errors = service.update_call_details(actor, payload)
        if errors:
            if wants_json_response():
                return jsonify({"success": False, "message": errors[0], "errors": errors}), 400
            redirect_call_id = int(payload.get("call_id") or 0) if str(payload.get("call_id") or "").isdigit() else 0
            extra_context = {
                "page_title": "Edit Call or Lead",
                "form_mode": "edit",
                "edit_call_id": redirect_call_id,
                "form_action": "/api/onsite-call/update",
                "submit_button_label": "Save Changes",
                "cancel_url": safe_redirect_target(f"/onsite-calls/{redirect_call_id}" if redirect_call_id else "/onsite-calls"),
            }
            return render_template("onsite_call_form.html", **render_form_context(False, payload, errors, extra_context)), 400
        return json_or_redirect(
            True,
            f"Call ID {call_id} updated successfully",
            f"/onsite-calls/{call_id}",
            {"call_id": call_id},
        )

    @blueprint.route("/onsite-calls", methods=["GET"])
    def onsite_calls_dashboard():
        auth_response = require_login()
        if auth_response is not None:
            return auth_response
        actor = service.actor()
        default_status = "New Lead" if actor["role"] in ADMIN_ROLES else "ALL"
        filters = {
            "status": request.args.get("status", default_status),
            "branch": request.args.get("branch", "ALL"),
            "engineer": request.args.get("engineer", "ALL"),
            "call_type": request.args.get("call_type", "ALL"),
            "complaint_type": request.args.get("complaint_type", "ALL"),
            "priority": request.args.get("priority", "ALL"),
            "payment_status": request.args.get("payment_status", PAYMENT_STATUS_ALL),
            "search": request.args.get("search", ""),
            "from_date": request.args.get("from_date", ""),
            "to_date": request.args.get("to_date", ""),
            "page": request.args.get("page", "1"),
            "per_page": request.args.get("per_page", str(DEFAULT_PER_PAGE)),
        }
        listing = service.list_calls(actor, filters)
        counts = service.dashboard_counts(actor, filters)
        credit_pending_count = service.credit_pending_count(actor, filters)
        branch_options = service.branch_options(actor)
        selected_branch = str(filters.get("branch") or "ALL")
        selected_branch_name = actor["branch"] if not actor["has_global_scope"] else (selected_branch if selected_branch != "ALL" else "")
        engineer_options = service.engineer_options(actor, selected_branch_name)
        if wants_json_response():
            return jsonify(
                {
                    "success": True,
                    "items": listing["items"],
                    "pagination": {
                        "page": listing["page"],
                        "per_page": listing["per_page"],
                        "total_count": listing["total_count"],
                        "total_pages": listing["total_pages"],
                    },
                    "counts": counts,
                }
            )
        return render_template(
            "onsite_calls.html",
            actor=actor,
            calls=listing["items"],
            can_delete=service.can_delete(actor),
            pagination=listing,
            filters=filters,
            default_status=default_status,
            counts=counts,
            credit_pending_count=credit_pending_count,
            status_sections=status_sections_with_counts(counts),
            status_choices=("ALL",) + STATUSES,
            call_type_choices=("ALL",) + CALL_TYPES,
            payment_status_choices=PAYMENT_STATUS_FILTERS,
            branch_options=branch_options,
            engineer_options=engineer_options,
            complaint_types=("ALL",) + COMPLAINT_TYPES,
            priority_levels=("ALL",) + PRIORITY_LEVELS,
        )

    @blueprint.route("/onsite-calls/export", methods=["GET"])
    def onsite_calls_export():
        auth_response = require_login()
        if auth_response is not None:
            return auth_response
        actor = service.actor()
        default_status = "New Lead" if actor["role"] in ADMIN_ROLES else "ALL"
        filters = {
            "status": request.args.get("status", default_status),
            "branch": request.args.get("branch", "ALL"),
            "engineer": request.args.get("engineer", "ALL"),
            "call_type": request.args.get("call_type", "ALL"),
            "complaint_type": request.args.get("complaint_type", "ALL"),
            "priority": request.args.get("priority", "ALL"),
            "payment_status": request.args.get("payment_status", PAYMENT_STATUS_ALL),
            "search": request.args.get("search", ""),
            "from_date": request.args.get("from_date", ""),
            "to_date": request.args.get("to_date", ""),
        }
        rows = service.export_calls(actor, filters)

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            [
                "Call ID",
                "Customer Name",
                "Phone",
                "Location",
                "District",
                "Type",
                "Complaint Type",
                "Preferred Service",
                "Priority",
                "Payment Status",
                "Payment Mode",
                "Completion Type",
                "Closed By Brand",
                "Service Charges",
                "Product Value",
                "Customer Price",
                "Product Profit",
                "Total Profit",
                "Preferred Time",
                "Status",
                "Source",
                "Lead Source",
                "Assigned Branch",
                "Assigned Engineer",
                "Assigned Time",
                "Created By",
                "Created At",
                "Updated At",
                "Device Model",
                "Complaint Description",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row.get("id", ""),
                    row.get("customer_name", ""),
                    row.get("phone", ""),
                    row.get("location", ""),
                    row.get("district", ""),
                    row.get("call_type", ""),
                    row.get("complaint_type", ""),
                    row.get("preferred_service", ""),
                    row.get("priority", ""),
                    row.get("payment_status", ""),
                    row.get("payment_mode", ""),
                    row.get("completion_type", ""),
                    row.get("closure_closed_by_brand", ""),
                    row.get("closure_service_charges", ""),
                    row.get("closure_product_value", ""),
                    row.get("closure_customer_price", ""),
                    row.get("closure_product_profit", ""),
                    row.get("closure_total_profit", ""),
                    row.get("preferred_datetime_display", ""),
                    row.get("status", ""),
                    row.get("source", ""),
                    row.get("lead_source", ""),
                    row.get("assigned_branch_name", ""),
                    row.get("assigned_engineer_name", ""),
                    row.get("assigned_time_display", ""),
                    row.get("created_by", ""),
                    row.get("created_at_display", ""),
                    row.get("updated_at_display", ""),
                    row.get("device_model", ""),
                    row.get("complaint_description", ""),
                ]
            )

        status_slug = str(filters.get("status") or "all").strip().lower().replace(" ", "_")
        filename = f"onsite_calls_{status_slug}_{business_now_naive().strftime('%Y%m%d_%H%M')}.csv"
        return Response(
            buffer.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    @blueprint.route("/onsite-calls/<int:call_id>", methods=["GET"])
    def onsite_call_detail(call_id):
        auth_response = require_login()
        if auth_response is not None:
            return auth_response
        actor = service.actor()
        detail = service.get_call_detail(actor, call_id)
        if not detail:
            return json_or_redirect(False, "Onsite call not found", "/onsite-calls", status_code=404)
        current_branch_name = detail["call"].get("assigned_branch_name") or actor["branch"]
        return render_template(
            "onsite_call_detail.html",
            actor=actor,
            detail=detail,
            status_choices=service.available_nonfinal_status_choices(actor, detail["call"]),
            close_status_choices=service.close_status_choices(actor, detail["call"]),
            completion_types=COMPLETION_TYPES,
            closed_by_options=CLOSED_BY_OPTIONS,
            payment_mode_options=PAYMENT_MODE_OPTIONS,
            branch_options=service.branch_options(actor),
            engineer_options=service.engineer_options(actor, current_branch_name),
            selected_engineer_name=detail["call"].get("assigned_engineer_name") or "",
            can_assign=service.can_assign(actor, detail["call"]) and not detail["call"].get("has_closure_record"),
            assign_message=service.assignment_message(actor, detail["call"]),
            can_update_status=service.can_update_status(actor, detail["call"]),
            status_update_message=service.status_update_message(actor, detail["call"]),
            can_close=service.can_close(actor, detail["call"]),
            close_message=service.close_message(actor, detail["call"]),
            can_update_credit_payment=service.can_update_credit_payment(actor, detail["call"], detail.get("closure")),
            credit_payment_message=service.credit_payment_message(actor, detail["call"], detail.get("closure")),
            can_reschedule=service.can_reschedule(actor) and not detail["call"].get("has_closure_record"),
            reschedule_message=service.reschedule_message(actor),
            can_add_note=service.can_add_note(actor, detail["call"]),
            note_message=service.note_message(actor, detail["call"]),
        )

    @blueprint.route("/onsite-calls/<int:call_id>/media/<int:attachment_id>", methods=["GET"])
    def onsite_call_attachment(call_id, attachment_id):
        auth_response = require_login()
        if auth_response is not None:
            return auth_response
        actor = service.actor()
        attachment = service.get_attachment(actor, call_id, attachment_id)
        if not attachment:
            return json_or_redirect(False, "Media not found", "/onsite-calls", status_code=404)
        return send_from_directory(service.media_folder, attachment["filename"], mimetype=attachment["mime_type"])

    @blueprint.route("/api/onsite-call/engineers", methods=["GET"])
    def onsite_call_engineers():
        auth_response = require_login()
        if auth_response is not None:
            return auth_response
        actor = service.actor()
        raw_branch_name = request.args.get("branch")
        branch_name = str(raw_branch_name or "").strip()
        search_query = str(request.args.get("q") or "").strip()
        limit = request.args.get("limit") or 25
        if not actor["has_global_scope"]:
            branch_name = actor["branch"]
        elif branch_name.upper() == "ALL":
            branch_name = ""
        items = service.engineer_options(actor, branch_name, query=search_query, limit=limit)
        return jsonify({"success": True, "items": items})

    @blueprint.route("/api/onsite-call/assign", methods=["POST"])
    def onsite_call_assign():
        auth_response = require_login()
        if auth_response is not None:
            return auth_response
        actor = service.actor()
        payload = payload_from_request()
        call_id, errors = service.assign_call(actor, payload)
        if errors:
            return json_or_redirect(False, errors[0], f"/onsite-calls/{payload.get('call_id') or ''}", {"errors": errors}, 400)
        return json_or_redirect(True, "Call assignment updated", f"/onsite-calls/{call_id}", {"call_id": call_id})

    @blueprint.route("/api/onsite-call/update-status", methods=["POST"])
    def onsite_call_update_status():
        auth_response = require_login()
        if auth_response is not None:
            return auth_response
        actor = service.actor()
        payload = payload_from_request()
        call_id, errors = service.update_status(actor, payload)
        if errors:
            return json_or_redirect(False, errors[0], f"/onsite-calls/{payload.get('call_id') or ''}", {"errors": errors}, 400)
        return json_or_redirect(True, "Call status updated", f"/onsite-calls/{call_id}", {"call_id": call_id})

    @blueprint.route("/api/onsite-call/add-note", methods=["POST"])
    def onsite_call_add_note():
        auth_response = require_login()
        if auth_response is not None:
            return auth_response
        actor = service.actor()
        payload = payload_from_request()
        call_id, errors = service.add_note(actor, payload)
        if errors:
            return json_or_redirect(False, errors[0], f"/onsite-calls/{payload.get('call_id') or ''}", {"errors": errors}, 400)
        return json_or_redirect(True, "Note saved", f"/onsite-calls/{call_id}", {"call_id": call_id})

    @blueprint.route("/api/onsite-call/reschedule", methods=["POST"])
    def onsite_call_reschedule():
        auth_response = require_login()
        if auth_response is not None:
            return auth_response
        actor = service.actor()
        payload = payload_from_request()
        call_id, errors = service.reschedule_call(actor, payload)
        if errors:
            return json_or_redirect(False, errors[0], f"/onsite-calls/{payload.get('call_id') or ''}", {"errors": errors}, 400)
        return json_or_redirect(True, "Call rescheduled", f"/onsite-calls/{call_id}", {"call_id": call_id})

    @blueprint.route("/api/onsite-call/close", methods=["POST"])
    def onsite_call_close():
        auth_response = require_login()
        if auth_response is not None:
            return auth_response
        actor = service.actor()
        payload = payload_from_request()
        call_id, errors = service.close_call(actor, payload)
        if errors:
            return json_or_redirect(False, errors[0], f"/onsite-calls/{payload.get('call_id') or ''}", {"errors": errors}, 400)
        return json_or_redirect(True, "Case closed", f"/onsite-calls/{call_id}", {"call_id": call_id})

    @blueprint.route("/api/onsite-call/update-payment", methods=["POST"])
    def onsite_call_update_payment():
        auth_response = require_login()
        if auth_response is not None:
            return auth_response
        actor = service.actor()
        payload = payload_from_request()
        call_id, errors = service.settle_credit_payment(actor, payload)
        if errors:
            return json_or_redirect(False, errors[0], f"/onsite-calls/{payload.get('call_id') or ''}", {"errors": errors}, 400)
        return json_or_redirect(True, "Credit payment updated", f"/onsite-calls/{call_id}", {"call_id": call_id})

    @blueprint.route("/api/onsite-call/delete", methods=["POST"])
    def onsite_call_delete():
        auth_response = require_login()
        if auth_response is not None:
            return auth_response
        actor = service.actor()
        if not service.can_delete(actor):
            return json_or_redirect(False, "Access denied", "/onsite-calls", status_code=403)
        payload = payload_from_request()
        call_id, errors = service.delete_call(actor, payload)
        if errors:
            status_code = 404 if errors[0] == "Call not found or access denied" else 400
            return json_or_redirect(False, errors[0], "/onsite-calls", {"errors": errors}, status_code)
        return json_or_redirect(True, f"Case ID {call_id} deleted", "/onsite-calls", {"call_id": call_id})

    @blueprint.route("/onsite-calls/reports", methods=["GET"])
    def onsite_call_reports():
        auth_response = require_login()
        if auth_response is not None:
            return auth_response
        actor = service.actor()
        if not service.can_view_reports(actor):
            return json_or_redirect(False, "Access denied", "/onsite-calls", status_code=403)
        today = business_now_naive()
        current_month_start = today.replace(day=1).strftime("%Y-%m-%d")
        current_day = today.strftime("%Y-%m-%d")
        default_branch_filter = "ALL" if actor["has_global_scope"] else (actor["branch"] or "ALL")
        default_filters = {
            "branch": default_branch_filter,
            "engineer": "ALL",
            "complaint_type": "ALL",
            "priority": "ALL",
            "closed_by_brand": "ALL",
            "from_date": current_month_start,
            "to_date": current_day,
        }
        filters = {
            "branch": request.args.get("branch", default_filters["branch"]),
            "engineer": request.args.get("engineer", default_filters["engineer"]),
            "complaint_type": request.args.get("complaint_type", default_filters["complaint_type"]),
            "priority": request.args.get("priority", default_filters["priority"]),
            "closed_by_brand": request.args.get("closed_by_brand", default_filters["closed_by_brand"]),
            "from_date": request.args.get("from_date", default_filters["from_date"]),
            "to_date": request.args.get("to_date", default_filters["to_date"]),
        }
        if not actor["has_global_scope"] and actor["branch"]:
            filters["branch"] = actor["branch"]
        report_data = service.report_summary(actor, filters)
        if wants_json_response():
            return jsonify({"success": True, **report_data})
        selected_branch = str(filters.get("branch") or "ALL")
        selected_branch_name = actor["branch"] if not actor["has_global_scope"] else (selected_branch if selected_branch != "ALL" else "")
        return render_template(
            "onsite_call_reports.html",
            actor=actor,
            filters=filters,
            branch_options=service.branch_options(actor),
            engineer_options=service.engineer_options(actor, selected_branch_name),
            complaint_types=("ALL",) + COMPLAINT_TYPES,
            priority_levels=("ALL",) + PRIORITY_LEVELS,
            closed_by_options=("ALL",) + CLOSED_BY_OPTIONS,
            default_filters=default_filters,
            report_data=report_data,
        )

    @blueprint.route("/onsite-calls/reports/export-profit", methods=["GET"])
    def onsite_call_reports_export_profit():
        auth_response = require_login()
        if auth_response is not None:
            return auth_response
        actor = service.actor()
        if not service.can_view_reports(actor):
            return json_or_redirect(False, "Access denied", "/onsite-calls", status_code=403)
        today = business_now_naive()
        current_month_start = today.replace(day=1).strftime("%Y-%m-%d")
        current_day = today.strftime("%Y-%m-%d")
        default_branch_filter = "ALL" if actor["has_global_scope"] else (actor["branch"] or "ALL")
        filters = {
            "branch": request.args.get("branch", default_branch_filter),
            "engineer": request.args.get("engineer", "ALL"),
            "complaint_type": request.args.get("complaint_type", "ALL"),
            "priority": request.args.get("priority", "ALL"),
            "closed_by_brand": request.args.get("closed_by_brand", "ALL"),
            "from_date": request.args.get("from_date", current_month_start),
            "to_date": request.args.get("to_date", current_day),
        }
        if not actor["has_global_scope"] and actor["branch"]:
            filters["branch"] = actor["branch"]
        call_type = normalize_call_type(request.args.get("call_type")) or "Onsite"
        section = service.profit_report_section(actor, filters, call_type) or {"rows": []}

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            [
                "Call ID",
                "Customer Name",
                "Branch",
                "Lead Source",
                "Closed At",
                "Service Charges",
                "Product Value",
                "Customer Price",
                "Profit",
                "Closed By",
            ]
        )
        for row in section.get("rows", []):
            writer.writerow(
                [
                    row.get("call_id", ""),
                    row.get("customer_name", ""),
                    row.get("branch_name", ""),
                    row.get("lead_source", ""),
                    row.get("closed_at_display", ""),
                    row.get("service_charges", ""),
                    row.get("product_value", ""),
                    row.get("customer_price", ""),
                    row.get("profit", ""),
                    row.get("closed_by_brand", ""),
                ]
            )
        filename = f"onsite_profit_{call_type.lower()}_{business_now_naive().strftime('%Y%m%d_%H%M')}.csv"
        return Response(
            buffer.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    csrf_registrar = config.get("csrf_registrar")
    if callable(csrf_registrar):
        csrf_registrar(
            "onsite_calls.onsite_call_create_public",
            "onsite_calls.onsite_call_create_internal",
            "onsite_calls.onsite_call_update_internal",
            "onsite_calls.onsite_call_assign",
            "onsite_calls.onsite_call_update_status",
            "onsite_calls.onsite_call_add_note",
            "onsite_calls.onsite_call_reschedule",
        )

    return blueprint
