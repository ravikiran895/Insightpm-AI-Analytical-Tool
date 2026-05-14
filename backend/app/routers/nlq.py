from fastapi import APIRouter

from ..models.schemas import NLQRequest
from ..services import nlq_service

router = APIRouter()


@router.post("/nlq")
def nlq(req: NLQRequest):
    return nlq_service.answer(req.question)
