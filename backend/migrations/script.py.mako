"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

@description: Alembic 迁移脚本（由 alembic revision 命令生成后人工核对修订）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision: str = ${repr(up_revision)}
down_revision: Union[str, Sequence[str], None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    """执行迁移升级。

    @return: 无返回值
    """
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    """执行迁移降级（回滚）。

    @return: 无返回值
    """
    ${downgrades if downgrades else "pass"}
