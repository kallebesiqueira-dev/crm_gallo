"""products (catalog: products + services)

Adds the org-scoped `products` tenant table (RLS ENABLE + FORCE + the standard
GUC policy) and the `producttype` enum. A catalog item the tenant sells;
quote/contract line items referencing it are a follow-up.

Revision ID: d7e8f9a0b1c2
Revises: c5d6e7f8a9b0
Create Date: 2026-06-09 10:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d7e8f9a0b1c2"
down_revision: Union[str, None] = "c5d6e7f8a9b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


GUC_EXPR = "NULLIF(current_setting('app.current_org_id', true), '')::uuid"
_PRODUCT_TYPE = sa.Enum("product", "service", name="producttype")


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("sku", sa.String(length=64), nullable=True),
        sa.Column("type", _PRODUCT_TYPE, nullable=False, server_default="product"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="EUR"),
        sa.Column("unit", sa.String(length=32), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("owner_id", sa.UUID(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_products_organization_id"), "products", ["organization_id"])
    op.create_index(op.f("ix_products_sku"), "products", ["sku"])
    op.create_index(op.f("ix_products_deleted_at"), "products", ["deleted_at"])

    # Tenant table: RLS ENABLE + FORCE + the standard org-GUC isolation policy.
    op.execute("ALTER TABLE products ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE products FORCE ROW LEVEL SECURITY;")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation ON products
          FOR ALL
          USING (organization_id = {GUC_EXPR})
          WITH CHECK (organization_id = {GUC_EXPR});
        """
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON products TO crm_app;")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON products;")
    op.execute("ALTER TABLE products NO FORCE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE products DISABLE ROW LEVEL SECURITY;")
    op.drop_index(op.f("ix_products_deleted_at"), table_name="products")
    op.drop_index(op.f("ix_products_sku"), table_name="products")
    op.drop_index(op.f("ix_products_organization_id"), table_name="products")
    op.drop_table("products")
    op.execute("DROP TYPE IF EXISTS producttype;")
