"""
@file: app/schemas/baby.py
@description: 宝宝档案相关 Pydantic Schema。
"""

from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator


class BabyCreateRequest(BaseModel):
    """创建宝宝档案请求模型。

    @param name: 宝宝昵称
    @param gender: 性别 male/female
    @param birth_date: 出生日期（不得晚于今天）
    @param avatar_url: 头像地址（可选）
    """

    name: str = Field(..., min_length=1, max_length=50, description="宝宝昵称")
    gender: str | None = Field(None, pattern="^(male|female)$", description="性别")
    birth_date: date = Field(..., description="出生日期")
    avatar_url: str | None = Field(None, max_length=255, description="头像地址")

    @field_validator("birth_date")
    @classmethod
    def validate_birth_date(cls, v: date) -> date:
        """校验出生日期不能晚于今天。

        @param v: 出生日期
        @return: 校验通过的原值
        @raises ValueError: 出生日期晚于今天时抛出
        """
        from datetime import date as _date

        if v > _date.today():
            raise ValueError("出生日期不能晚于今天")
        return v


class BabyUpdateRequest(BaseModel):
    """更新宝宝档案请求模型（字段均可选）。"""

    name: str | None = Field(None, min_length=1, max_length=50, description="宝宝昵称")
    gender: str | None = Field(None, pattern="^(male|female)$", description="性别")
    birth_date: date | None = Field(None, description="出生日期")
    avatar_url: str | None = Field(None, max_length=255, description="头像地址")
    is_default: bool | None = Field(None, description="是否默认档案")


class BabyResponse(BaseModel):
    """宝宝档案响应模型。"""

    id: int
    name: str
    gender: str | None = None
    birth_date: date
    avatar_url: str | None = None
    is_default: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}
