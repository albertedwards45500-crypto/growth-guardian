"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-12

@file: migrations/versions/0001_initial_schema.py
@description: 初始数据库结构迁移（审计缺陷 D05）：完整创建业务系统全部 12 张表，
             包括索引、外键（CASCADE/SET NULL）与两个数据库级唯一约束
             （uq_recipe_favorites_user_recipe / uq_meal_plans_slot）。
             该迁移与 app/models 下 ORM 模型元数据保持一致，由 alembic autogenerate
             生成后人工核对修订。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """执行迁移升级：按外键依赖顺序创建全部 12 张业务表（先父表后子表）。

    @return: 无返回值
    """
    # ---- 独立表（无外键依赖） ----
    # 常见问题知识库
    op.create_table('faqs',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False, comment='问题ID'),
    sa.Column('category', sa.String(length=30), nullable=False, comment='问题分类'),
    sa.Column('question', sa.String(length=200), nullable=False, comment='问题标题'),
    sa.Column('answer', sa.Text(), nullable=False, comment='解答内容'),
    sa.Column('keywords', sa.String(length=200), nullable=True, comment='检索关键词'),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False, comment='创建时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_faqs_category'), 'faqs', ['category'], unique=False)
    # 分月龄喂养指南
    op.create_table('guides',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False, comment='指南ID'),
    sa.Column('month_start', sa.Integer(), nullable=False, comment='适用起始月龄'),
    sa.Column('month_end', sa.Integer(), nullable=False, comment='适用结束月龄'),
    sa.Column('title', sa.String(length=100), nullable=False, comment='指南标题'),
    sa.Column('content', sa.Text(), nullable=False, comment='指南正文'),
    sa.Column('food_suggestions', sa.JSON(), nullable=False, comment='推荐食物清单JSON'),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False, comment='创建时间'),
    sa.PrimaryKeyConstraint('id')
    )
    # 辅食食谱
    op.create_table('recipes',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False, comment='食谱ID'),
    sa.Column('title', sa.String(length=100), nullable=False, comment='食谱名称'),
    sa.Column('cover_url', sa.String(length=255), nullable=True, comment='封面图地址'),
    sa.Column('suitable_age_min', sa.Integer(), nullable=False, comment='适合最小月龄'),
    sa.Column('suitable_age_max', sa.Integer(), nullable=False, comment='适合最大月龄'),
    sa.Column('ingredients', sa.JSON(), nullable=False, comment='食材清单JSON'),
    sa.Column('steps', sa.JSON(), nullable=False, comment='制作步骤JSON'),
    sa.Column('nutrition_tags', sa.JSON(), nullable=False, comment='营养标签JSON'),
    sa.Column('tips', sa.Text(), nullable=True, comment='食用注意与贴士'),
    sa.Column('is_active', sa.Boolean(), nullable=False, comment='是否上架'),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False, comment='创建时间'),
    sa.PrimaryKeyConstraint('id')
    )
    # 用户账号
    op.create_table('users',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False, comment='用户ID'),
    sa.Column('phone', sa.String(length=20), nullable=False, comment='手机号（登录账号）'),
    sa.Column('nickname', sa.String(length=50), nullable=False, comment='昵称'),
    sa.Column('password_hash', sa.String(length=128), nullable=False, comment='bcrypt 密码哈希'),
    sa.Column('avatar_url', sa.String(length=255), nullable=True, comment='头像地址'),
    sa.Column('is_active', sa.Boolean(), nullable=False, comment='是否启用'),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False, comment='更新时间'),
    sa.PrimaryKeyConstraint('id')
    )
    # 手机号唯一索引（登录账号）
    op.create_index(op.f('ix_users_phone'), 'users', ['phone'], unique=True)
    # ---- 依赖 users 的子表 ----
    # 宝宝档案
    op.create_table('babies',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False, comment='宝宝档案ID'),
    sa.Column('user_id', sa.Integer(), nullable=False, comment='所属用户ID'),
    sa.Column('name', sa.String(length=50), nullable=False, comment='宝宝昵称'),
    sa.Column('gender', sa.String(length=10), nullable=True, comment='性别 male/female'),
    sa.Column('birth_date', sa.Date(), nullable=False, comment='出生日期'),
    sa.Column('avatar_url', sa.String(length=255), nullable=True, comment='头像地址'),
    sa.Column('is_default', sa.Boolean(), nullable=False, comment='是否默认档案'),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False, comment='更新时间'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_babies_user_id'), 'babies', ['user_id'], unique=False)
    # 站内通知
    op.create_table('notifications',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False, comment='通知ID'),
    sa.Column('user_id', sa.Integer(), nullable=False, comment='接收用户ID'),
    sa.Column('notify_type', sa.String(length=20), nullable=False, comment='通知类型'),
    sa.Column('title', sa.String(length=100), nullable=False, comment='通知标题'),
    sa.Column('content', sa.Text(), nullable=False, comment='通知内容'),
    sa.Column('is_read', sa.Boolean(), nullable=False, comment='是否已读'),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False, comment='创建时间'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_notifications_user_id'), 'notifications', ['user_id'], unique=False)
    # 食谱收藏（含用户-食谱联合唯一约束）
    op.create_table('recipe_favorites',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False, comment='收藏ID'),
    sa.Column('user_id', sa.Integer(), nullable=False, comment='用户ID'),
    sa.Column('recipe_id', sa.Integer(), nullable=False, comment='食谱ID'),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False, comment='收藏时间'),
    sa.ForeignKeyConstraint(['recipe_id'], ['recipes.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'recipe_id', name='uq_recipe_favorites_user_recipe')
    )
    op.create_index(op.f('ix_recipe_favorites_recipe_id'), 'recipe_favorites', ['recipe_id'], unique=False)
    op.create_index(op.f('ix_recipe_favorites_user_id'), 'recipe_favorites', ['user_id'], unique=False)
    # ---- 依赖 babies 的子表 ----
    # 过敏/偏好食材
    op.create_table('allergies',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False, comment='记录ID'),
    sa.Column('baby_id', sa.Integer(), nullable=False, comment='宝宝ID'),
    sa.Column('ingredient', sa.String(length=50), nullable=False, comment='食材名称'),
    sa.Column('severity', sa.String(length=10), nullable=True, comment='严重程度'),
    sa.Column('note', sa.Text(), nullable=True, comment='备注'),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False, comment='创建时间'),
    sa.ForeignKeyConstraint(['baby_id'], ['babies.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_allergies_baby_id'), 'allergies', ['baby_id'], unique=False)
    op.create_index(op.f('ix_allergies_ingredient'), 'allergies', ['ingredient'], unique=False)
    # 饮食记录
    op.create_table('diet_records',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False, comment='记录ID'),
    sa.Column('baby_id', sa.Integer(), nullable=False, comment='宝宝ID'),
    sa.Column('record_date', sa.Date(), nullable=False, comment='记录日期'),
    sa.Column('record_type', sa.String(length=20), nullable=False, comment='记录类型 breast_milk/formula/solid_food'),
    sa.Column('details', sa.JSON(), nullable=True, comment='类型化明细JSON'),
    sa.Column('note', sa.Text(), nullable=True, comment='备注'),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False, comment='创建时间'),
    sa.ForeignKeyConstraint(['baby_id'], ['babies.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_diet_records_baby_id'), 'diet_records', ['baby_id'], unique=False)
    op.create_index(op.f('ix_diet_records_record_date'), 'diet_records', ['record_date'], unique=False)
    # 生长记录
    op.create_table('growth_records',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False, comment='记录ID'),
    sa.Column('baby_id', sa.Integer(), nullable=False, comment='宝宝ID'),
    sa.Column('record_date', sa.Date(), nullable=False, comment='测量日期'),
    sa.Column('weight_kg', sa.Float(), nullable=True, comment='体重（kg）'),
    sa.Column('height_cm', sa.Float(), nullable=True, comment='身高（cm）'),
    sa.Column('head_circumference_cm', sa.Float(), nullable=True, comment='头围（cm）'),
    sa.Column('note', sa.Text(), nullable=True, comment='备注'),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False, comment='创建时间'),
    sa.ForeignKeyConstraint(['baby_id'], ['babies.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_growth_records_baby_id'), 'growth_records', ['baby_id'], unique=False)
    op.create_index(op.f('ix_growth_records_record_date'), 'growth_records', ['record_date'], unique=False)
    # 一周辅食计划（含计划槽位唯一约束，依赖 babies 与 recipes）
    op.create_table('meal_plans',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False, comment='计划ID'),
    sa.Column('baby_id', sa.Integer(), nullable=False, comment='宝宝ID'),
    sa.Column('week_start', sa.Date(), nullable=False, comment='计划周起始日期（周一）'),
    sa.Column('day_of_week', sa.Integer(), nullable=False, comment='星期（0-6）'),
    sa.Column('meal_type', sa.String(length=20), nullable=False, comment='餐次类型'),
    sa.Column('recipe_id', sa.Integer(), nullable=True, comment='食谱ID'),
    sa.Column('note', sa.Text(), nullable=True, comment='备注'),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False, comment='创建时间'),
    sa.ForeignKeyConstraint(['baby_id'], ['babies.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['recipe_id'], ['recipes.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('baby_id', 'week_start', 'day_of_week', 'meal_type', name='uq_meal_plans_slot')
    )
    op.create_index(op.f('ix_meal_plans_baby_id'), 'meal_plans', ['baby_id'], unique=False)
    op.create_index(op.f('ix_meal_plans_week_start'), 'meal_plans', ['week_start'], unique=False)
    # 成长里程碑
    op.create_table('milestones',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False, comment='里程碑ID'),
    sa.Column('baby_id', sa.Integer(), nullable=False, comment='宝宝ID'),
    sa.Column('milestone_type', sa.String(length=30), nullable=False, comment='里程碑类型编码'),
    sa.Column('name', sa.String(length=50), nullable=False, comment='里程碑名称'),
    sa.Column('achieved_at', sa.Date(), nullable=False, comment='达成日期'),
    sa.Column('note', sa.Text(), nullable=True, comment='备注'),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False, comment='创建时间'),
    sa.ForeignKeyConstraint(['baby_id'], ['babies.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_milestones_baby_id'), 'milestones', ['baby_id'], unique=False)


def downgrade() -> None:
    """执行迁移降级：逐表删除，先子表后父表（避免外键依赖阻断删除）。

    @return: 无返回值
    """
    # 先删 babies 的子表
    op.drop_index(op.f('ix_milestones_baby_id'), table_name='milestones')
    op.drop_table('milestones')
    op.drop_index(op.f('ix_meal_plans_week_start'), table_name='meal_plans')
    op.drop_index(op.f('ix_meal_plans_baby_id'), table_name='meal_plans')
    op.drop_table('meal_plans')
    op.drop_index(op.f('ix_growth_records_record_date'), table_name='growth_records')
    op.drop_index(op.f('ix_growth_records_baby_id'), table_name='growth_records')
    op.drop_table('growth_records')
    op.drop_index(op.f('ix_diet_records_record_date'), table_name='diet_records')
    op.drop_index(op.f('ix_diet_records_baby_id'), table_name='diet_records')
    op.drop_table('diet_records')
    op.drop_index(op.f('ix_allergies_ingredient'), table_name='allergies')
    op.drop_index(op.f('ix_allergies_baby_id'), table_name='allergies')
    op.drop_table('allergies')
    # 再删 users / recipes 的子表
    op.drop_index(op.f('ix_recipe_favorites_user_id'), table_name='recipe_favorites')
    op.drop_index(op.f('ix_recipe_favorites_recipe_id'), table_name='recipe_favorites')
    op.drop_table('recipe_favorites')
    op.drop_index(op.f('ix_notifications_user_id'), table_name='notifications')
    op.drop_table('notifications')
    op.drop_index(op.f('ix_babies_user_id'), table_name='babies')
    op.drop_table('babies')
    op.drop_index(op.f('ix_users_phone'), table_name='users')
    op.drop_table('users')
    # 最后删独立表
    op.drop_table('recipes')
    op.drop_table('guides')
    op.drop_index(op.f('ix_faqs_category'), table_name='faqs')
    op.drop_table('faqs')
