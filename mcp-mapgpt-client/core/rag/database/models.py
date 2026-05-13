"""
Knowledge base models for the RAG vector store.
Defines kb_layers, kb_fields, and kb_query_patterns tables.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector

from .connection import Base
from core.config import settings

_EMBEDDING_DIM = settings.embedding_dimension


class KBLayer(Base):
    """GIS layer registry with semantic embeddings for layer resolution."""

    __tablename__ = "kb_layers"

    id = Column(BigInteger, primary_key=True, index=True)
    layer_name = Column(String(100), unique=True, nullable=False, index=True)
    url = Column(String(1000), nullable=False)
    purpose = Column(Text, nullable=False)
    description = Column(Text, nullable=False)
    embedding = Column(Vector(_EMBEDDING_DIM), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    fields = relationship(
        "KBField", back_populates="layer", cascade="all, delete-orphan"
    )


class KBField(Base):
    """Field catalog per layer with semantic embeddings for field-level matching."""

    __tablename__ = "kb_fields"
    __table_args__ = (
        UniqueConstraint("layer_id", "field_name", name="uq_kb_fields_layer_field"),
    )

    id = Column(BigInteger, primary_key=True, index=True)
    layer_id = Column(
        BigInteger, ForeignKey("kb_layers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    field_name = Column(String(200), nullable=False)
    field_description = Column(Text, nullable=False)
    embedding = Column(Vector(_EMBEDDING_DIM), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    layer = relationship("KBLayer", back_populates="fields")


class KBQueryPattern(Base):
    """Few-shot query pattern examples with semantic embeddings."""

    __tablename__ = "kb_query_patterns"

    id = Column(BigInteger, primary_key=True, index=True)
    prompt = Column(Text, nullable=False)
    query_json = Column(JSONB, nullable=False)
    operations = Column(JSONB, nullable=False, default=[])
    embedding = Column(Vector(_EMBEDDING_DIM), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
