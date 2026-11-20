"""Create and seed the product catalog."""

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    categories = op.create_table(
        "product_categories",
        sa.Column("slug", sa.String(32), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.CheckConstraint("slug IN ('bottle', 'metal_nut', 'tile')", name="category_slug"),
    )
    op.bulk_insert(categories, [
        {"slug": "bottle", "name": "Bottle"},
        {"slug": "metal_nut", "name": "Metal Nut"},
        {"slug": "tile", "name": "Tile"},
    ])


def downgrade():
    op.drop_table("product_categories")
