"""成长顾问只读入口，身份固定来自认证依赖。"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.config import settings
from app.core.deps import get_baby_or_404, get_current_user
from app.models.user import User
from app.schemas.advisor import AdvisorAnswer, AdvisorAskRequest, AdvisorCapabilities, advisor_today
from app.services.advisor import ask_advisor

router = APIRouter(tags=["成长顾问"])


@router.get("/babies/{baby_id}/advisor/status", response_model=AdvisorCapabilities, summary="顾问功能配置状态")
def status(baby_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    get_baby_or_404(baby_id, db, current_user.id)
    return AdvisorCapabilities(
        agent="disabled" if not settings.ADVISOR_AGENT_ENABLED else (
            "configured" if settings.OPENAI_API_KEY.get_secret_value() and settings.ADVISOR_MODEL.strip() else "unconfigured"
        ),
        knowledge="disabled" if not settings.RAG_ENABLED else (
            "configured" if settings.RAG_EMBEDDING_API_KEY.get_secret_value() else "unconfigured"
        ),
        today=advisor_today(),
    )


@router.post("/babies/{baby_id}/advisor/ask", response_model=AdvisorAnswer, summary="只读成长与喂养记录顾问")
def ask(
    baby_id: int, payload: AdvisorAskRequest, db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AdvisorAnswer:
    """按问题回顾成长/饮食或筛选食谱；不提供写操作和医疗诊断。"""
    return ask_advisor(db, current_user.id, baby_id, payload)
