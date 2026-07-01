from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ..orchestrator import get_run, submit_human_answer
from ..state import get_epic_by_id, get_step_by_id, get_story_by_id

router = APIRouter()


class AnswerRequest(BaseModel):
    answer: str


@router.post("/runs/{run_id}/steps/{step_id}/answer")
async def answer_question(run_id: str, step_id: str, req: AnswerRequest):
    ok = await submit_human_answer(run_id, step_id, req.answer)
    return {"status": "answered" if ok else "error"}
