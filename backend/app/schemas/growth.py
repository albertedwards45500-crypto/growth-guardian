"""
@file: app/schemas/growth.py
@description: 成长记录与里程碑相关 Pydantic Schema，含成长印记/曲线等聚合视图。
"""

from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator


class GrowthRecordCreateRequest(BaseModel):
    """新增生长记录请求模型。

    @param record_date: 测量日期
    @param weight_kg: 体重（kg），与身高/头围至少填一项
    @param height_cm: 身高（cm）
    @param head_circumference_cm: 头围（cm）
    @param note: 备注
    """

    record_date: date = Field(..., description="测量日期")
    weight_kg: float | None = Field(None, gt=0, le=50, description="体重(kg)")
    height_cm: float | None = Field(None, gt=0, le=150, description="身高(cm)")
    head_circumference_cm: float | None = Field(None, gt=0, le=100, description="头围(cm)")
    note: str | None = Field(None, max_length=500, description="备注")

    @field_validator("record_date")
    @classmethod
    def validate_date(cls, v: date) -> date:
        """校验测量日期不能晚于今天。

        @param v: 测量日期
        @return: 校验通过的原值
        @raises ValueError: 日期晚于今天时抛出
        """
        from datetime import date as _date

        if v > _date.today():
            raise ValueError("测量日期不能晚于今天")
        return v


class GrowthRecordResponse(BaseModel):
    """生长记录响应模型。"""

    id: int
    baby_id: int
    record_date: date
    weight_kg: float | None = None
    height_cm: float | None = None
    head_circumference_cm: float | None = None
    note: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class MilestoneCreateRequest(BaseModel):
    """新增里程碑请求模型。"""

    milestone_type: str = Field(..., description="里程碑类型编码")
    name: str = Field(..., min_length=1, max_length=50, description="里程碑名称")
    achieved_at: date = Field(..., description="达成日期")
    note: str | None = Field(None, max_length=500, description="备注")


class MilestoneResponse(BaseModel):
    """里程碑响应模型。"""

    id: int
    baby_id: int
    milestone_type: str
    name: str
    achieved_at: date
    note: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class GrowthSummary(BaseModel):
    """成长印记聚合数据模型（对应设计稿首页核心视觉）。"""

    baby_id: int
    baby_name: str
    age_months: int
    age_days: int
    stage_name: str
    latest_weight_kg: float | None = None
    latest_height_cm: float | None = None
    latest_head_circumference_cm: float | None = None
    latest_measure_date: date | None = None
    milestone_progress: dict[str, int] = Field(default_factory=dict, description="阶段里程碑完成数")


class CurvePoint(BaseModel):
    """生长曲线数据点模型。"""

    record_date: date
    age_months: float
    weight_kg: float | None = None
    height_cm: float | None = None
    head_circumference_cm: float | None = None


class WhoReferencePoint(BaseModel):
    """WHO 参考线单月龄分位点模型。"""

    month: int = Field(..., description="月龄")
    p3: float = Field(..., description="第 3 百分位")
    p15: float = Field(..., description="第 15 百分位")
    p50: float = Field(..., description="第 50 百分位（中位数）")
    p85: float = Field(..., description="第 85 百分位")
    p97: float = Field(..., description="第 97 百分位")


class WhoReference(BaseModel):
    """WHO 2006 生长标准参考线（0-24 月，用于前端绘制参考带）。"""

    height: list[WhoReferencePoint] = Field(default_factory=list, description="身长(cm)分位线")
    weight: list[WhoReferencePoint] = Field(default_factory=list, description="体重(kg)分位线")


class GrowthCurveResponse(BaseModel):
    """生长曲线响应模型（含按测量维度分组的数据点与 WHO 参考线）。"""

    baby_id: int
    weight_series: list[CurvePoint]
    height_series: list[CurvePoint]
    head_circumference_series: list[CurvePoint]
    # WHO 2006 参考线：0-24 月龄内的宝宝返回分位数据，超过 24 月龄返回 None（数据范围所限）
    who_reference: WhoReference | None = None
