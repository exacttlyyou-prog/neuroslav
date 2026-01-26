"""Initial database schema

Revision ID: 0001_20260124_000000
Revises: 
Create Date: 2026-01-24 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

# revision identifiers, used by Alembic.
revision = '0001_20260124_000000'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create initial database schema."""
    
    # Создаем таблицу meetings
    op.create_table(
        'meetings',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('title', sa.String(), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('participants', sa.JSON(), nullable=True),
        sa.Column('action_items', sa.JSON(), nullable=True),
        sa.Column('key_decisions', sa.JSON(), nullable=True),
        sa.Column('insights', sa.JSON(), nullable=True),
        sa.Column('next_steps', sa.JSON(), nullable=True),
        sa.Column('draft_message', sa.Text(), nullable=True),
        sa.Column('status', sa.String(), nullable=True, server_default='processing'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('notion_page_id', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Создаем индексы для оптимизации запросов
    op.create_index('ix_meetings_status', 'meetings', ['status'])
    op.create_index('ix_meetings_created_at', 'meetings', ['created_at'])
    op.create_index('ix_meetings_notion_page_id', 'meetings', ['notion_page_id'])


def downgrade() -> None:
    """Drop initial database schema."""
    
    # Удаляем индексы
    op.drop_index('ix_meetings_notion_page_id', table_name='meetings')
    op.drop_index('ix_meetings_created_at', table_name='meetings')
    op.drop_index('ix_meetings_status', table_name='meetings')
    
    # Удаляем таблицу
    op.drop_table('meetings')