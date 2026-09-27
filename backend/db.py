import os
import sqlite3
from datetime import datetime, timezone
from dotenv import load_dotenv
from sqlalchemy import (
    create_engine,
    Column,
    String,
    Text,
    Integer,
    JSON,
    ForeignKey,
    UniqueConstraint,
    event as sqlalchemy_event,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./investoffice.db")
engine = create_engine(
    DATABASE_URL,
    connect_args=(
        {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
    ),
)
Session = sessionmaker(bind=engine, expire_on_commit=False)
Base = declarative_base()


@sqlalchemy_event.listens_for(Engine, "connect")
def enable_sqlite_foreign_keys(connection, connection_record):
    if isinstance(connection, sqlite3.Connection):
        connection.execute("PRAGMA foreign_keys=ON")


def now():
    return datetime.now(timezone.utc).isoformat()


class Case(Base):
    __tablename__ = "cases"
    id = Column(String, primary_key=True)
    owner_id = Column(String, nullable=False)
    profile = Column(JSON, nullable=False)
    status = Column(String, default="draft", nullable=False)
    memo = Column(Text, default="", nullable=False)
    version = Column(Integer, default=1, nullable=False)
    __mapper_args__ = {"version_id_col": version}


class ImportBatch(Base):
    __tablename__ = "imports"
    id = Column(String, primary_key=True)
    case_id = Column(String, ForeignKey("cases.id"), nullable=False)
    kind = Column(String, nullable=False)
    filename = Column(String, nullable=False)
    raw = Column(Text, nullable=False)
    digest = Column(String, nullable=False)
    status = Column(String, nullable=False, default="preview")
    errors = Column(JSON, nullable=False, default=list)
    rows = Column(JSON, nullable=False)
    correction_reason = Column(Text, default="")
    created_by = Column(String, nullable=False)
    created_at = Column(String, default=now)
    __table_args__ = (UniqueConstraint("case_id", "kind", "digest"),)


class Record(Base):
    __tablename__ = "records"
    id = Column(Integer, primary_key=True)
    case_id = Column(String, ForeignKey("cases.id"), nullable=False, index=True)
    kind = Column(String, nullable=False)
    key = Column(String, nullable=False)
    data = Column(JSON, nullable=False)
    import_id = Column(String, ForeignKey("imports.id"), nullable=False)
    revision = Column(Integer, nullable=False, default=1)
    __table_args__ = (UniqueConstraint("case_id", "kind", "key", "revision"),)


class Scenario(Base):
    __tablename__ = "scenarios"
    id = Column(String, primary_key=True)
    case_id = Column(String, ForeignKey("cases.id"), nullable=False)
    name = Column(String, nullable=False)
    assumptions = Column(JSON, nullable=False)
    result = Column(JSON, nullable=False)
    created_at = Column(String, default=now)


class Submission(Base):
    __tablename__ = "submissions"
    id = Column(String, primary_key=True)
    case_id = Column(String, ForeignKey("cases.id"), nullable=False)
    author_id = Column(String, nullable=False)
    memo = Column(Text, nullable=False)
    snapshot = Column(JSON, nullable=False)
    created_at = Column(String, default=now)


class Review(Base):
    __tablename__ = "reviews"
    id = Column(String, primary_key=True)
    submission_id = Column(String, ForeignKey("submissions.id"), nullable=False)
    reviewer_id = Column(String, nullable=False)
    decision = Column(String, nullable=False)
    comment = Column(Text, nullable=False)
    created_at = Column(String, default=now)


class Alert(Base):
    __tablename__ = "alerts"
    id = Column(String, primary_key=True)
    case_id = Column(String, ForeignKey("cases.id"), nullable=False)
    rule_id = Column(String, nullable=False)
    period = Column(String, nullable=False)
    category = Column(String, nullable=False)
    title = Column(String, nullable=False)
    detail = Column(Text, nullable=False)
    status = Column(String, default="open", nullable=False)
    assignee = Column(String, default="analyst", nullable=False)
    notes = Column(Text, default="", nullable=False)
    __table_args__ = (UniqueConstraint("case_id", "rule_id", "period"),)


class Event(Base):
    __tablename__ = "events"
    id = Column(Integer, primary_key=True)
    case_id = Column(String, ForeignKey("cases.id"), nullable=False)
    actor = Column(String, nullable=False)
    action = Column(String, nullable=False)
    detail = Column(JSON, nullable=False, default=dict)
    created_at = Column(String, default=now)


class LoginSession(Base):
    __tablename__ = "sessions"
    token_hash = Column(String, primary_key=True)
    user_id = Column(String, nullable=False)
    expires_at = Column(String, nullable=False)


def records(db, case_id, kind):
    rows = (
        db.query(Record)
        .filter_by(case_id=case_id, kind=kind)
        .order_by(Record.revision, Record.id)
        .all()
    )
    return list({r.key: r.data for r in rows}.values())


def event(db, case_id, user, action, detail=None):
    db.add(Event(case_id=case_id, actor=user, action=action, detail=detail or {}))
