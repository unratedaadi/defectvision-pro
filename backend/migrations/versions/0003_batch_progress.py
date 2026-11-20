"""Store individual batch failures and original upload order."""

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("batch_jobs", sa.Column("errors", sa.JSON(), nullable=True))
    op.add_column("inspections", sa.Column("batch_index", sa.Integer(), nullable=True))


def downgrade():
    op.drop_column("inspections", "batch_index")
    op.drop_column("batch_jobs", "errors")
