"""
Query log model for observability and auditing.
Separate from knowledge base models — this is an operational concern.
"""

from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, Float, String, Text
from sqlalchemy.dialects.postgresql import JSONB

from .connection import Base


class QueryLog(Base):
    """Log of user queries and system responses."""

    __tablename__ = "query_logs"

    id = Column(BigInteger, primary_key=True, index=True)
    session_id = Column(String(100), nullable=True, index=True)
    user_id = Column(String(100), nullable=True, index=True)
    query = Column(Text, nullable=False)
    action = Column(String(50), nullable=True)
    response = Column(JSONB, nullable=True)
    retrieval_time_ms = Column(Float, nullable=True)
    llm_time_ms = Column(Float, nullable=True)
    total_time_ms = Column(Float, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
