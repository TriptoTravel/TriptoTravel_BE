from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, conlist, conint
from typing import Annotated, List
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from models import Purpose, TravelQuestionResponse, Travelogue
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
    who_category: conlist(conint(ge=1, le=6), min_length=1, max_length=6)
    purpose_category: conlist(conint(ge=1, le=4), min_length=1, max_length=4)

class TravelPurposeQuestionResponse(BaseModel):
    purpose_list: List[dict]
    travel_question_response: List[dict]

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
    travelogue = db.get(Travelogue, travelogue_id)
    if not travelogue:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Travelogue ID {travelogue_id} not found"
        )

    purpose_list = []
    question_list = []

    try:
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

        for who_id in request.who_category:
            new_question = TravelQuestionResponse(
                travelogue_id=travelogue_id,
                who_category=who_id
            )
            db.add(new_question)
            db.flush()
            question_list.append({
                "id": new_question.id,
                "travelogue_id": new_question.travelogue_id,
                "who_category": new_question.who_category
            })

        db.commit()

        return {
            "purpose_list": purpose_list,
            "travel_question_response": question_list
        }

    except IntegrityError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Database constraint violated"
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
