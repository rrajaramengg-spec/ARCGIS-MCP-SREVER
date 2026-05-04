"""Initial migration - create tables with pgvector support

Revision ID: 001
Revises: 
Create Date: 2024-01-15 10:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')
    
    # Create documents table
    op.create_table(
        'documents',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('embedding', Vector(1536), nullable=False),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('doc_type', sa.String(length=50), nullable=False),
        sa.Column('layers', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='[]'),
        sa.Column('operations', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='[]'),
        sa.Column('parameters', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='[]'),
        sa.Column('source_file', sa.String(length=500), nullable=True),
        sa.Column('source_url', sa.String(length=1000), nullable=True),
        sa.Column('chunk_index', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('search_keywords', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_documents_doc_type'), 'documents', ['doc_type'], unique=False)
    op.create_index(op.f('ix_documents_id'), 'documents', ['id'], unique=False)
    
    # Create vector index for cosine similarity
    op.execute("""
        CREATE INDEX idx_documents_embedding_cosine 
        ON documents USING ivfflat (embedding vector_cosine_ops) 
        WITH (lists = 100)
    """)
    
    # Create query_logs table
    op.create_table(
        'query_logs',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('session_id', sa.String(length=100), nullable=True),
        sa.Column('user_id', sa.String(length=100), nullable=True),
        sa.Column('query', sa.Text(), nullable=False),
        sa.Column('query_embedding', Vector(1536), nullable=True),
        sa.Column('retrieved_docs', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='[]'),
        sa.Column('context_used', sa.Text(), nullable=True),
        sa.Column('action', sa.String(length=50), nullable=True),
        sa.Column('response', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('retrieval_time_ms', sa.Float(), nullable=True),
        sa.Column('llm_time_ms', sa.Float(), nullable=True),
        sa.Column('total_time_ms', sa.Float(), nullable=True),
        sa.Column('user_feedback', sa.Integer(), nullable=True),
        sa.Column('feedback_text', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_query_logs_id'), 'query_logs', ['id'], unique=False)
    op.create_index(op.f('ix_query_logs_session_id'), 'query_logs', ['session_id'], unique=False)
    op.create_index(op.f('ix_query_logs_user_id'), 'query_logs', ['user_id'], unique=False)
    
    # Create uploaded_files table
    op.create_table(
        'uploaded_files',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('filename', sa.String(length=500), nullable=False),
        sa.Column('file_path', sa.String(length=1000), nullable=False),
        sa.Column('file_size', sa.BigInteger(), nullable=False),
        sa.Column('file_type', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='pending'),
        sa.Column('chunks_created', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('user_id', sa.String(length=100), nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='{}'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('processed_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_uploaded_files_id'), 'uploaded_files', ['id'], unique=False)
    op.create_index(op.f('ix_uploaded_files_user_id'), 'uploaded_files', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_uploaded_files_user_id'), table_name='uploaded_files')
    op.drop_index(op.f('ix_uploaded_files_id'), table_name='uploaded_files')
    op.drop_table('uploaded_files')
    
    op.drop_index(op.f('ix_query_logs_user_id'), table_name='query_logs')
    op.drop_index(op.f('ix_query_logs_session_id'), table_name='query_logs')
    op.drop_index(op.f('ix_query_logs_id'), table_name='query_logs')
    op.drop_table('query_logs')
    
    op.execute('DROP INDEX IF EXISTS idx_documents_embedding_cosine')
    op.drop_index(op.f('ix_documents_id'), table_name='documents')
    op.drop_index(op.f('ix_documents_doc_type'), table_name='documents')
    op.drop_table('documents')
