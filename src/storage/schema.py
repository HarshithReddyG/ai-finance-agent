"""Phase 3 — Database schema (SQLAlchemy ORM models).

Defines the tables backing the whole project. Source-of-truth ingested
data (accounts, transactions) is kept separate from data that later
phases *derive* by analyzing it (recurring_series from Phase 5,
anomalies from Phase 6) — those derived tables are never written to
during ingestion, only by their own detection logic in later phases.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Shared base class every ORM model below inherits from."""
    pass


class Account(Base):
    __tablename__ = "accounts"

    account_id: Mapped[str] = mapped_column(String, primary_key=True)
    account_type: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)

    transactions: Mapped[list["Transaction"]] = relationship(back_populates="account")


class Transaction(Base):
    __tablename__ = "transactions"

    transaction_id: Mapped[str] = mapped_column(String, primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.account_id"), nullable=False)
    date: Mapped[dt.date] = mapped_column(nullable=False)
    merchant_name: Mapped[str] = mapped_column(String, nullable=False)
    raw_description: Mapped[str | None] = mapped_column(String, nullable=True)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String, default="USD")
    pending: Mapped[bool] = mapped_column(default=False)
    category: Mapped[str | None] = mapped_column(String, nullable=True)  # filled in by Phase 4
    created_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)

    account: Mapped["Account"] = relationship(back_populates="transactions")


class RecurringSeries(Base):
    """Populated by Phase 5's recurring-payment detector, not by ingestion."""
    __tablename__ = "recurring_series"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    merchant_name: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.account_id"), nullable=False)
    cadence: Mapped[str] = mapped_column(String, nullable=False)  # "monthly", "biweekly", etc.
    expected_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    detected_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)


class Anomaly(Base):
    """Populated by Phase 6's anomaly detector, not by ingestion."""
    __tablename__ = "anomalies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    transaction_id: Mapped[str] = mapped_column(ForeignKey("transactions.transaction_id"), nullable=False)
    anomaly_type: Mapped[str] = mapped_column(String, nullable=False)
    detected_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)
    notes: Mapped[str | None] = mapped_column(String, nullable=True)