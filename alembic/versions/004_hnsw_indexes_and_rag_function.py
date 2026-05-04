"""HNSW indexes replacing IVFFlat + rag_unified_search stored function

Revision ID: 004_hnsw_indexes_and_rag_function
Revises: 003_rag_refactor
Create Date: 2026-04-30

"""

from alembic import op

revision = "004_hnsw_rag_func"
down_revision = "003_rag_refactor"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Drop IVFFlat indexes ---
    op.drop_index("ix_kb_layers_embedding", table_name="kb_layers")
    op.drop_index("ix_kb_fields_embedding", table_name="kb_fields")
    op.drop_index("ix_kb_query_patterns_embedding", table_name="kb_query_patterns")

    # --- Create HNSW indexes (vector_cosine_ops, m=16, ef_construction=64) ---
    op.execute(
        "CREATE INDEX ix_kb_layers_embedding ON kb_layers "
        "USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )
    op.execute(
        "CREATE INDEX ix_kb_fields_embedding ON kb_fields "
        "USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )
    op.execute(
        "CREATE INDEX ix_kb_query_patterns_embedding ON kb_query_patterns "
        "USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )

    # --- Create rag_unified_search() stored function ---
    op.execute("""
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
    -- Layer search with hybrid scoring: cosine similarity + ts_rank keyword matching
    WITH ranked_layers AS (
        SELECT
            l.id,
            l.layer_name,
            l.url,
            l.purpose,
            l.description,
            -- Preserved production cosine formula: 1 - distance/2, range [0,1]
            1.0 - (l.embedding <=> query_embedding) / 2.0 AS cosine_score,
            -- ts_rank keyword scoring with English stop-word filtering
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
            (alpha * rl.cosine_score + (1.0 - alpha) * rl.keyword_score) AS combined_score
        FROM ranked_layers rl
    ),
    filtered_layers AS (
        SELECT *
        FROM scored_layers
        WHERE combined_score >= layer_min_score
        ORDER BY combined_score DESC
        LIMIT layer_top_k
    ),
    -- Field enrichment via FK join, nested under each layer
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

    -- Pattern search via cosine similarity
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

    -- Compose final result
    result := jsonb_build_object(
        'layers', layers_json,
        'patterns', patterns_json
    );

    RETURN result;
END;
$$;
""")


def downgrade() -> None:
    # --- Drop stored function ---
    op.execute("DROP FUNCTION IF EXISTS rag_unified_search")

    # --- Drop HNSW indexes ---
    op.drop_index("ix_kb_layers_embedding", table_name="kb_layers")
    op.drop_index("ix_kb_fields_embedding", table_name="kb_fields")
    op.drop_index("ix_kb_query_patterns_embedding", table_name="kb_query_patterns")

    # --- Restore IVFFlat indexes ---
    op.execute(
        "CREATE INDEX ix_kb_layers_embedding ON kb_layers "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 10)"
    )
    op.execute(
        "CREATE INDEX ix_kb_fields_embedding ON kb_fields "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 10)"
    )
    op.execute(
        "CREATE INDEX ix_kb_query_patterns_embedding ON kb_query_patterns "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 10)"
    )
