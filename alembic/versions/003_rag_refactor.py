"""RAG refactor: kb_layers, kb_fields, kb_query_patterns; drop documents

Revision ID: 003_rag_refactor
Revises: 002_add_layers
Create Date: 2026-04-27

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

revision = "003_rag_refactor"
down_revision = "002_add_layers"
branch_labels = None
depends_on = None

_EMBEDDING_DIM = 1536


def upgrade() -> None:
    # --- Create kb_layers ---
    op.create_table(
        "kb_layers",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=True),
            nullable=False,
        ),
        sa.Column("layer_name", sa.String(100), nullable=False),
        sa.Column("url", sa.String(1000), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(_EMBEDDING_DIM), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("layer_name", name="kb_layers_layer_name_key"),
    )
    op.create_index(
        "ix_kb_layers_layer_name", "kb_layers", ["layer_name"], unique=True
    )
    op.execute(
        "CREATE INDEX ix_kb_layers_embedding ON kb_layers "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 10)"
    )

    # --- Create kb_fields ---
    op.create_table(
        "kb_fields",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=True),
            nullable=False,
        ),
        sa.Column("layer_id", sa.BigInteger(), nullable=False),
        sa.Column("field_name", sa.String(200), nullable=False),
        sa.Column("field_description", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(_EMBEDDING_DIM), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["layer_id"],
            ["kb_layers.id"],
            name="kb_fields_layer_id_fkey",
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "layer_id", "field_name", name="kb_fields_layer_id_field_name_key"
        ),
    )
    op.create_index("ix_kb_fields_layer_id", "kb_fields", ["layer_id"])
    op.execute(
        "CREATE INDEX ix_kb_fields_embedding ON kb_fields "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 10)"
    )

    # --- Create kb_query_patterns ---
    op.create_table(
        "kb_query_patterns",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=True),
            nullable=False,
        ),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("query_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "operations",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("embedding", Vector(_EMBEDDING_DIM), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        "CREATE INDEX ix_kb_query_patterns_operations ON kb_query_patterns "
        "USING gin (operations)"
    )
    op.execute(
        "CREATE INDEX ix_kb_query_patterns_embedding ON kb_query_patterns "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 10)"
    )

    # --- Drop old documents table ---
    op.drop_table("documents")


def downgrade() -> None:
    # --- Recreate documents table (empty) ---
    op.create_table(
        "documents",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(_EMBEDDING_DIM), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("doc_type", sa.String(50), nullable=False),
        sa.Column(
            "layers",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "operations",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "parameters",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("source_file", sa.String(500), nullable=True),
        sa.Column("source_url", sa.String(1000), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("search_keywords", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_documents_id", "documents", ["id"])
    op.create_index("ix_documents_doc_type", "documents", ["doc_type"])

    # --- Drop kb_* tables ---
    op.drop_table("kb_query_patterns")
    op.drop_table("kb_fields")
    op.drop_table("kb_layers")
