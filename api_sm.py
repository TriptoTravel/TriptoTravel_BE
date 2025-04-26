from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from datetime import datetime
from database import SessionLocal
from typing import Annotated, List
from sqlalchemy.orm import Session
from models import Travelogue
from starlette import status

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


db_dependency = Annotated[Session, Depends(get_db)]


class TravelogueUpdate(BaseModel):
    style_category: int = Field(ge=1, le=3)

class TravelogueResponse(BaseModel):
    id: int
    style_category: int | None = None 
    created_at: datetime


@router.get(
    "/api/travelogue/all",
    status_code=status.HTTP_200_OK,
    response_model=List[TravelogueResponse],
    summary="모든 여행기 튜플 확인",
    description="현재 데이터베이스에 저장된 모든 여행기 튜플을 확인합니다"
)
async def get_travelogue(db: db_dependency):
    return db.query(Travelogue).all()


@router.get(
    "/api/travelogue/{travelogue_id}",
    status_code=status.HTTP_200_OK,
    response_model=TravelogueResponse,
    summary="특정 id 여행기 튜플 확인",
    description="현재 데이터베이스에 저장된 특정 id 여행기 튜플을 확인합니다"
)
async def get_travelogue(travelogue_id: int, db: db_dependency):
    db_travelogue = db.query(Travelogue).filter(Travelogue.id == travelogue_id).first()
    if not db_travelogue:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail={"error": "Travelogue not found"})
    return db_travelogue


@router.post(
    "/api/travelogue",
    status_code=status.HTTP_201_CREATED,
    response_model=TravelogueResponse,
    summary="여행기 튜플 생성",
    description="새로운 여행기 튜플을 생성합니다. style_category의 초기값은 Null로 생성됩니다."
)
async def create_travelogue(db: db_dependency):
    db_travelogue = Travelogue()
    db.add(db_travelogue)
    db.commit()
    db.refresh(db_travelogue)
    return db_travelogue


@router.patch(
    "/api/travelogue/{travelogue_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="여행기 튜플 수정",
    description="지정된 여행기의 style_category를 업데이트합니다."
)
async def update_travelogue(travelogue_id: int, update: TravelogueUpdate, db: db_dependency):
    db_travelogue = db.query(Travelogue).filter(Travelogue.id == travelogue_id).first()
    if not db_travelogue:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail={"error": "Travelogue not found"})
    db_travelogue.style_category = update.style_category
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)