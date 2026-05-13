"""Public baseline schema for the current runtime database.

Revision ID: 001_public_baseline
Revises:
Create Date: 2026-05-13

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector


revision: str = "001_public_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_EMBEDDING_DIM = 1536


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "kb_layers",
        sa.Column(
            "id", sa.BigInteger(), sa.Identity(always=True), nullable=False
        ),
        sa.Column("layer_name", sa.String(length=100), nullable=False),
        sa.Column("url", sa.String(length=1000), nullable=False),
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
    op.create_index("ix_kb_layers_id", "kb_layers", ["id"], unique=False)
    op.create_index(
        "ix_kb_layers_layer_name", "kb_layers", ["layer_name"], unique=True
    )
    op.execute(
        "CREATE INDEX ix_kb_layers_embedding ON kb_layers "
        "USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )

    op.create_table(
        "kb_fields",
        sa.Column(
            "id", sa.BigInteger(), sa.Identity(always=True), nullable=False
        ),
        sa.Column("layer_id", sa.BigInteger(), nullable=False),
        sa.Column("field_name", sa.String(length=200), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["layer_id"],
            ["kb_layers.id"],
            name="kb_fields_layer_id_fkey",
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "layer_id", "field_name", name="kb_fields_layer_id_field_name_key"
        ),
    )
    op.create_index("ix_kb_fields_id", "kb_fields", ["id"], unique=False)
    op.create_index(
        "ix_kb_fields_layer_id", "kb_fields", ["layer_id"], unique=False
    )
    op.execute(
        "CREATE INDEX ix_kb_fields_embedding ON kb_fields "
        "USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )

    op.create_table(
        "kb_query_patterns",
        sa.Column(
            "id", sa.BigInteger(), sa.Identity(always=True), nullable=False
        ),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column(
            "query_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
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
    op.create_index(
        "ix_kb_query_patterns_id", "kb_query_patterns", ["id"], unique=False
    )
    op.execute(
        "CREATE INDEX ix_kb_query_patterns_operations ON kb_query_patterns "
        "USING gin (operations)"
    )
    op.execute(
        "CREATE INDEX ix_kb_query_patterns_embedding ON kb_query_patterns "
        "USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )

    op.create_table(
        "query_logs",
        sa.Column(
            "id", sa.BigInteger(), sa.Identity(always=True), nullable=False
        ),
        sa.Column("session_id", sa.String(length=100), nullable=True),
        sa.Column("user_id", sa.String(length=100), nullable=True),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=True),
        sa.Column(
            "response",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("retrieval_time_ms", sa.Float(), nullable=True),
        sa.Column("llm_time_ms", sa.Float(), nullable=True),
        sa.Column("total_time_ms", sa.Float(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_query_logs_id", "query_logs", ["id"], unique=False)
    op.create_index(
        "ix_query_logs_session_id", "query_logs", ["session_id"], unique=False
    )
    op.create_index(
        "ix_query_logs_user_id", "query_logs", ["user_id"], unique=False
    )

    op.execute(
        """
CREATE OR REPLACE FUNCTION rag_unified_search(
    query_embedding vector(1536),
    query_text text,
    layer_top_k int DEFAULT 10,
    pattern_top_k int DEFAULT 5,
    layer_min_score float DEFAULT 0.3,
    pattern_min_score float DEFAULT 0.5,
    alpha float DEFAULT 0.7
)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    result jsonb;
    layers_json jsonb;
    patterns_json jsonb;
BEGIN
    WITH ranked_layers AS (
        SELECT
            l.id,
            l.layer_name,
            l.url,
            l.purpose,
            l.description,
            1.0 - (l.embedding <=> query_embedding) / 2.0 AS cosine_score,
            ts_rank(
                to_tsvector('english', l.layer_name || ' ' || l.purpose),
                plainto_tsquery('english', query_text)
            ) AS keyword_score
        FROM kb_layers l
        ORDER BY l.embedding <=> query_embedding
        LIMIT layer_top_k * 2
    ),
    scored_layers AS (
        SELECT
            rl.*,
            (
                alpha * rl.cosine_score + (1.0 - alpha) * rl.keyword_score
            ) AS combined_score
        FROM ranked_layers rl
    ),
    filtered_layers AS (
        SELECT *
        FROM scored_layers
        WHERE combined_score >= layer_min_score
        ORDER BY combined_score DESC
        LIMIT layer_top_k
    ),
    layers_with_fields AS (
        SELECT
            fl.id,
            fl.layer_name,
            fl.url,
            fl.purpose,
            fl.description,
            fl.combined_score AS score,
            COALESCE(
                (
                    SELECT jsonb_agg(
                        jsonb_build_object(
                            'field_name', f.field_name,
                            'field_description', f.field_description
                        )
                        ORDER BY f.field_name
                    )
                    FROM kb_fields f
                    WHERE f.layer_id = fl.id
                ),
                '[]'::jsonb
            ) AS fields
        FROM filtered_layers fl
    )
    SELECT COALESCE(
        jsonb_agg(
            jsonb_build_object(
                'id', lwf.id,
                'layer_name', lwf.layer_name,
                'url', lwf.url,
                'purpose', lwf.purpose,
                'description', lwf.description,
                'score', lwf.score,
                'fields', lwf.fields
            )
            ORDER BY lwf.score DESC
        ),
        '[]'::jsonb
    )
    INTO layers_json
    FROM layers_with_fields lwf;

    WITH ranked_patterns AS (
        SELECT
            p.prompt,
            p.query_json,
            p.operations,
            1.0 - (p.embedding <=> query_embedding) / 2.0 AS score
        FROM kb_query_patterns p
        ORDER BY p.embedding <=> query_embedding
        LIMIT pattern_top_k * 2
    )
    SELECT COALESCE(
        jsonb_agg(
            jsonb_build_object(
                'prompt', rp.prompt,
                'query_json', rp.query_json,
                'operations', rp.operations,
                'score', rp.score
            )
            ORDER BY rp.score DESC
        ),
        '[]'::jsonb
    )
    INTO patterns_json
    FROM ranked_patterns rp
    WHERE rp.score >= pattern_min_score;

    result := jsonb_build_object(
        'layers', layers_json,
        'patterns', patterns_json
    );

    RETURN result;
END;
$$;
"""
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS rag_unified_search")
    op.drop_index("ix_query_logs_user_id", table_name="query_logs")
    op.drop_index("ix_query_logs_session_id", table_name="query_logs")
    op.drop_index("ix_query_logs_id", table_name="query_logs")
    op.drop_table("query_logs")

    op.drop_index(
        "ix_kb_query_patterns_embedding", table_name="kb_query_patterns"
    )
    op.execute("DROP INDEX IF EXISTS ix_kb_query_patterns_operations")
    op.drop_index("ix_kb_query_patterns_id", table_name="kb_query_patterns")
    op.drop_table("kb_query_patterns")

    op.drop_index("ix_kb_fields_embedding", table_name="kb_fields")
    op.drop_index("ix_kb_fields_layer_id", table_name="kb_fields")
    op.drop_index("ix_kb_fields_id", table_name="kb_fields")
    op.drop_table("kb_fields")

    op.drop_index("ix_kb_layers_embedding", table_name="kb_layers")
    op.drop_index("ix_kb_layers_layer_name", table_name="kb_layers")
    op.drop_index("ix_kb_layers_id", table_name="kb_layers")
    op.drop_table("kb_layers")
