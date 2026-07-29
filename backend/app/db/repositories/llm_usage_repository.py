"""LLM usage repository — backs per-call token tracking (app/llm/usage_tracking.py) and the
GET /usage/summary endpoint. ADR 001 (repository pattern) / ADR 004 (company_id required)."""

from datetime import datetime

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase


class LLMUsageRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._db = db

    async def record(
        self,
        company_id: ObjectId,
        user_id: ObjectId,
        session_id: ObjectId,
        provider: str,
        model: str,
        call_type: str,
        prompt_tokens: int | None,
        completion_tokens: int | None,
        now: datetime,
    ) -> None:
        await self._db.llm_usage.insert_one(
            {
                "company_id": company_id,
                "user_id": user_id,
                "session_id": session_id,
                "provider": provider,
                "model": model,
                "call_type": call_type,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "created_at": now,
            }
        )

    async def summarize(self, company_id: ObjectId, start: datetime, end: datetime) -> dict:
        """Sums usage for a company across [start, end). Rows with no reported token counts
        (prompt_tokens/completion_tokens both null — a provider that doesn't report usage at
        all) are counted toward call_count but contribute 0 to the token sums, not excluded —
        the call still happened and cost something, even if this system can't measure it."""
        pipeline = [
            {"$match": {"company_id": company_id, "created_at": {"$gte": start, "$lt": end}}},
            {
                "$group": {
                    "_id": None,
                    "call_count": {"$sum": 1},
                    "prompt_tokens": {"$sum": {"$ifNull": ["$prompt_tokens", 0]}},
                    "completion_tokens": {"$sum": {"$ifNull": ["$completion_tokens", 0]}},
                    "calls_missing_usage": {
                        "$sum": {
                            "$cond": [{"$and": [{"$eq": ["$prompt_tokens", None]}, {"$eq": ["$completion_tokens", None]}]}, 1, 0]
                        }
                    },
                }
            },
        ]
        results = await self._db.llm_usage.aggregate(pipeline).to_list(length=1)
        if not results:
            return {"call_count": 0, "prompt_tokens": 0, "completion_tokens": 0, "calls_missing_usage": 0}
        r = results[0]
        return {
            "call_count": r["call_count"],
            "prompt_tokens": r["prompt_tokens"],
            "completion_tokens": r["completion_tokens"],
            "calls_missing_usage": r["calls_missing_usage"],
        }
