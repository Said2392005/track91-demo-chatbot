from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import CurrentUser, get_current_user, get_llm_usage_repo
from app.db.repositories.llm_usage_repository import LLMUsageRepository
from app.schemas.usage import UsageSummaryResponse

router = APIRouter(prefix="/usage", tags=["usage"])


@router.get("/summary", response_model=UsageSummaryResponse)
async def get_usage_summary(
    start: datetime = Query(..., description="Inclusive start of the period (ISO 8601)"),
    end: datetime = Query(..., description="Exclusive end of the period (ISO 8601)"),
    current_user: CurrentUser = Depends(get_current_user),
    usage_repo: LLMUsageRepository = Depends(get_llm_usage_repo),
) -> UsageSummaryResponse:
    if end <= start:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="end must be after start")

    summary = await usage_repo.summarize(current_user.company_object_id, start, end)
    return UsageSummaryResponse(
        company_id=current_user.company_id,
        start=start.isoformat(),
        end=end.isoformat(),
        call_count=summary["call_count"],
        prompt_tokens=summary["prompt_tokens"],
        completion_tokens=summary["completion_tokens"],
        total_tokens=summary["prompt_tokens"] + summary["completion_tokens"],
        calls_missing_usage=summary["calls_missing_usage"],
    )
