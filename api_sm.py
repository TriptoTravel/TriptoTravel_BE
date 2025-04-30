from fastapi import APIRouter, Depends, HTTPException, Response, Form, File, UploadFile
from pydantic import BaseModel, Field
from datetime import datetime
from database import SessionLocal
from typing import Annotated, List
from sqlalchemy.orm import Session
from models import Travelogue, Image, TravelogueImage
from starlette import status
from sqlalchemy.exc import IntegrityError
from gcs_utils import upload_image_to_gcs, delete_image_from_gcs, generate_signed_url

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



class ImageResponse(BaseModel):
    id: int
    travelogue_image_id: int
    uri: str
    importance: float | None = None
    caption: str | None = None
    draft: str | None = None
    final: str | None = None
    is_in_travelogue: bool

class TravelogueImageResponse(BaseModel):
    travelogue_id: int
    image_id: int

class CombinedResponse(BaseModel):
    mapping_list: List[TravelogueImageResponse]
    image_list: List[ImageResponse]


@router.post(
    "/api/image/upload",
    status_code=status.HTTP_201_CREATED,
    response_model=CombinedResponse,
    summary="이미지 튜플 생성 및 업로드",
    description="입력된 이미지를 기반으로 튜플을 생성하고, GCP Storage에 업로드합니다."
)
async def create_image(db:db_dependency, travelogue_id: int = Form(...), images: List[UploadFile] = File(...)):
    travelogue = db.get(Travelogue, travelogue_id)
    if not travelogue:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Travelogue id : {travelogue_id} not found"
        )
    try:
        result_mapping = []
        result_image = []
        uploaded_files = []
        for i, image in enumerate(images, start=1):
            file_name = f"{travelogue_id}_{i}.jpg"
            file_bytes = await image.read()
            uri = upload_image_to_gcs(file_bytes, file_name, content_type=image.content_type)
            uploaded_files.append(file_name)

            image = Image(
                travelogue_image_id=i,
                uri=uri,
                is_in_travelogue=True
            )
            db.add(image)
            db.flush()

            mapping = TravelogueImage(
                travelogue_id=travelogue_id,
                image_id=image.id
            )
            db.add(mapping)

            result_image.append(image)
            result_mapping.append(mapping)
        db.commit()
        return {"mapping_list": result_mapping, "image_list": result_image}
    except IntegrityError as e:
        db.rollback()
        for file_name in uploaded_files:
            delete_image_from_gcs(file_name)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Foreign key constraint failed: {str(e.orig)}"
        )
    except Exception as e:
        db.rollback()
        for file_name in uploaded_files:
            delete_image_from_gcs(file_name)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {str(e)}"
        )


@router.get(
    "/api/image/{travelogue_id}/activated",
    status_code=status.HTTP_200_OK,
    summary="is_in_travelogue가 true인 image url 및 draft 확인",
    description="travelogue_id에 해당하는 image 튜플 중 is_in_travelogue가 true인 image의 Signed URL과 draft를 확인합니다."
)
async def get_used_image_url_and_draft(db: db_dependency, travelogue_id: int):
    mappings = db.query(TravelogueImage).filter(TravelogueImage.travelogue_id == travelogue_id).all()
    if not mappings:
        raise HTTPException(  
                status_code=status.HTTP_404_NOT_FOUND,  
                detail=f"Travelogue id : {travelogue_id} not found"  
            )
    
    try:
        image_ids = [mapping.image_id for mapping in mappings]
        images = db.query(Image).filter(
            Image.id.in_(image_ids),
            Image.is_in_travelogue == True
        ).all()

        result = []
        for image in images:
            signed_url = generate_signed_url(image.uri)

            result.append({
                "id": image.id,
                "image_url": signed_url,
                "draft": image.draft
            })
        return result
    except Exception as e:
        raise HTTPException(  
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,  
            detail=f"Unexpected error: {str(e)}"
        )