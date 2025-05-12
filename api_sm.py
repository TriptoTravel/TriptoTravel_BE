from fastapi import APIRouter, Depends, HTTPException, Response, Form, File, UploadFile
from pydantic import BaseModel, Field
from datetime import datetime
from database import SessionLocal
from typing import Annotated, List
from sqlalchemy.orm import Session
from models import *
from starlette import status
from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_, asc
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


class ActivatedResponse(BaseModel):
    id: int
    image_url: str
    draft: str | None = None

class ActivatedListResponse(BaseModel):
    image_draft_list: List[ActivatedResponse]

@router.get(
    "/api/image/{travelogue_id}/activated",
    response_model=ActivatedListResponse,
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
        return {"image_draft_list": result}
    except Exception as e:
        raise HTTPException(  
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,  
            detail=f"Unexpected error: {str(e)}"
        )



class MetadataResponse(BaseModel):
    image_id: int
    created_at: datetime | None = None
    location: str | None = None

class ImageMetadataResponse(BaseModel):
    image_metadata_list: List[MetadataResponse]

@router.get(
    "/api/image/{travelogue_id}/none/metadata",
    status_code=status.HTTP_200_OK,
    response_model=ImageMetadataResponse,
    summary="메타데이터가 없는 이미지 확인",
    description="travelogue_id가 true인 이미지 중 메타데이터 누락 사항이 있는 것을 확인합니다."
)
async def get_none_metadata_image(db: db_dependency, travelogue_id: int):
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
        
        image_id_list = [image.id for image in images]
        if not image_id_list:
            return []

        metadatas = db.query(Metadata.image_id, Metadata.created_at, Metadata.location).filter(
            Metadata.image_id.in_(image_id_list),
            or_(
                Metadata.created_at == None,
                Metadata.location == None
            )
        ).all()

        return {"image_metadata_list": metadatas}
    except Exception as e:
        raise HTTPException(  
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,  
            detail=f"Unexpected error: {str(e)}"
        )
    


class MetadataUpdate(BaseModel):
    created_at: datetime
    location: str


@router.patch(
    "/api/image/{image_id}/metadata",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="메타데이터 튜플 수정",
    description="지정된 메타데이터의 created_at, location을 업데이트합니다."
)
async def update_metadata(db: db_dependency, update: MetadataUpdate, image_id: int):
    db_metadata = db.query(Metadata).filter(Metadata.image_id == image_id).first()
    if not db_metadata:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail={"error": "Metadata not found"})
    db_metadata.created_at = update.created_at
    db_metadata.location = update.location
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {str(e)}"
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)



class FinalRequest(BaseModel):
    final: str


@router.patch(
    "/api/image/{image_id}/correction",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="여행기 final 필드 수정",
    description="image_id에 해당하는 튜플의 final 값을 저장합니다."
)
async def update_final(db: db_dependency, image_id: int, final: FinalRequest):
    db_image = db.query(Image).filter(Image.id == image_id).first()
    if not db_image:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail={"error": "image not found"})
    db_image.final = final.final
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {str(e)}"
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)



class ImageQuestionRequest(BaseModel):
    how: str
    emotion: List[int]


class EmotionResponse(BaseModel):
    id: int
    question_response_id: int
    emotion_category: int


class EachImageQuestionResponse(BaseModel):
    image_id: int
    how: str
    emotion_list: List[EmotionResponse]


@router.post(
    "/api/image/{image_id}/question",
    response_model=EachImageQuestionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="이미지에 대한 사전 질문 응답 튜플 생성",
    description="개별 이미지에 대한 사전 질문 응답을 emotion, image_question_response 테이블에 저장합니다."
)
async def create_image_question_response(db: db_dependency, image_id: int, request: ImageQuestionRequest):
    if not db.query(Image).filter(Image.id == image_id).first():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail={"error": "Travelogue not found"})
    try:
        db_image_question_response = ImageQuestionResponse(image_id=image_id, how=request.how)
        db.add(db_image_question_response)
        db.flush()

        emotion_list = []
        for e in request.emotion:
            db_emotion = Emotion(question_response_id=db_image_question_response.id, emotion_category=e)
            db.add(db_emotion)
            db.flush()
            emotion_list.append({
                "id": db_emotion.id,
                "question_response_id": db_emotion.question_response_id,
                "emotion_category": db_emotion.emotion_category
            })
        db.commit()

        return {"image_id": image_id, "how": request.how, "emotion_list": emotion_list}
    except Exception as e:
        db.rollback()
        raise HTTPException(  
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,  
            detail=f"Unexpected error: {str(e)}"
        )
    


class DraftItem(BaseModel):
    image_id: int
    draft: str | None = None

class DraftResponse(BaseModel):
    draft_list: List[DraftItem]


@router.get(
    "/api/travelogue/{travelogue_id}/draft",
    status_code=status.HTTP_200_OK,
    response_model=DraftResponse,
    summary="여행기 초안 반환",
    description="travelogue_id에 대한 draft를 시간 순으로 정렬해 반환합니다."
)
async def get_time_ordered_travelogue_draft(db: db_dependency, travelogue_id: int):
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

        image_dict = {image.id: image for image in images}
        sorted_images = [
            image_dict[metadata.image_id]
            for metadata in db.query(Metadata)
                .filter(Metadata.image_id.in_(image_ids))
                .order_by(asc(Metadata.created_at))
            if metadata.image_id in image_dict
        ]

        return {"draft_list": [{"image_id": image.id, "draft": image.draft} for image in sorted_images]}
    except Exception as e:
        raise HTTPException(  
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,  
            detail=f"Unexpected error: {str(e)}"
        )