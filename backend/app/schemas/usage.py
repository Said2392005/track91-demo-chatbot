from pydantic import BaseModel


class UsageSummaryResponse(BaseModel):
    company_id: str
    start: str
    end: str
    call_count: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    # How many of call_count had no usage data at all (provider didn't report it) — kept
    # visible rather than silently folded into the totals, since prompt_tokens/completion_tokens
    # above are undercounts whenever this is non-zero.
    calls_missing_usage: int
