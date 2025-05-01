from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Annotated, List
from sqlalchemy.orm import Session
from models import Purpose, TravelQuestionResponse
from database import SessionLocal
from starlette import status

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

db_dependency = Annotated[Session, Depends(get_db)]

class TravelPurposeQuestionRequest(BaseModel):
    who: str = Field(..., description="누구와 가는지")
    purpose_category: List[int] = Field(..., description="여행 목적 카테고리 리스트")

class TravelPurposeQuestionResponse(BaseModel):
    message: str
    purpose_list: List[dict]
    travel_question_response: dict


@router.post(
    "/api/travelogue/{travelogue_id}/question/total",
    status_code=status.HTTP_201_CREATED,
    response_model=TravelPurposeQuestionResponse,
    summary="여행 목적/전체 질문 테이블 튜플 생성",
    description="여행 목적과 전체 질문 테이블을 생성합니다."
)
async def create_purpose_and_question(
    travelogue_id: int,
    request: TravelPurposeQuestionRequest,
    db: db_dependency
):
    purpose_list = []
    
    for category_id in request.purpose_category:
        new_purpose = Purpose(
            travelogue_id=travelogue_id,
            purpose_category=category_id
        )
        db.add(new_purpose)
        db.flush()
        purpose_list.append({
            "id": new_purpose.id,
            "travelogue_id": new_purpose.travelogue_id,
            "purpose_category": new_purpose.purpose_category
        })
    
    new_question_response = TravelQuestionResponse(
        travelogue_id=travelogue_id,
        who=request.who
    )
    db.add(new_question_response)
    db.flush()
    
    db.commit()

    return {
        "message": "success",
        "purpose_list": purpose_list,
        "travel_question_response": {
            "id": new_question_response.id,
            "travelogue_id": new_question_response.travelogue_id,
            "who": new_question_response.who
        }
    }