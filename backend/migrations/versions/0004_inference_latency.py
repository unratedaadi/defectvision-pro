"""Record measured inference latency for new inspections."""

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("inspections", sa.Column("inference_latency_ms", sa.Float(), nullable=True))


def downgrade():
    op.drop_column("inspections", "inference_latency_ms")
