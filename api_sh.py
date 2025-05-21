from fastapi import APIRouter, Depends, HTTPException, Response, status, Query
from pydantic import BaseModel, conlist, conint
from typing import Annotated, List, Optional, Dict, Any
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from models import Purpose, TravelQuestionResponse, Travelogue, Image, TravelogueImage, Metadata
from database import SessionLocal
from starlette import status
from datetime import datetime
from sqlalchemy import or_
from gcs_utils import generate_signed_url, extract_gcs_file_name, extract_datetime_location_from_gcs, extract_created_at_from_gcs, upload_pdf_and_generate_url, bucket, BUCKET_NAME
from google.cloud import storage
import exifread
import io
import requests
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderUnavailable
import os
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from PIL import Image as PILImage
from dotenv import load_dotenv


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



class CaptionResponse(BaseModel):
    image_id: int
    caption: str

class MetadataResponse(BaseModel):
    image_id: int
    created_at: Optional[datetime] = None
    location: Optional[str] = None

class CaptionMetadataResponse(BaseModel):
    caption_list: List[CaptionResponse]
    metadata_list: List[MetadataResponse]


def convert_to_degrees(value):
    d = float(value.values[0].num) / float(value.values[0].den)
    m = float(value.values[1].num) / float(value.values[1].den)
    s = float(value.values[2].num) / float(value.values[2].den)
    return d + (m / 60.0) + (s / 3600.0)

geolocator = Nominatim(user_agent="your_app_name", timeout=600)

def reverse_geocode(lat: float, lon: float) -> str: 
    try:
        location = geolocator.reverse((lat, lon), language='ko')
        if location and location.address:
            return location.address
        else:
            return "주소 정보 없음"
    except GeocoderUnavailable:
        return "주소 정보 없음"
    except Exception:
        return "주소 정보 없음"
    

@router.post(
    "/api/image/{travelogue_id}/selection/second",
    status_code=status.HTTP_201_CREATED,
    response_model=CaptionMetadataResponse,
    summary="이미지 2차 선별/캡셔닝/메타데이터 추출",
    description="여행기 중 사용하지 않을 이미지 비활성화 및 나머지 이미지 대상으로 AI 캡션과 백엔드 메타데이터를 추출합니다."
)
async def select_second_image(
    travelogue_id: int,
    image_ids: Optional[List[int]] = Query(None),
    db: Session = Depends(get_db)
):
    caption_list = []
    metadata_list = []

    try:
        if image_ids:
            images_to_update = db.query(Image).filter(Image.id.in_(image_ids)).all()
            if not images_to_update:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"해당 image_ids에 해당하는 이미지가 없습니다."
                )
            for img in images_to_update:
                img.is_in_travelogue = False
            try:
                db.commit()
            except Exception as e:
                db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"이미지 비활성화 중 오류 발생: {str(e)}"
                )

        mappings = db.query(TravelogueImage).filter(
            TravelogueImage.travelogue_id == travelogue_id
        ).all()
        if not mappings:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Travelogue id : {travelogue_id} not found"
            )

        image_ids_valid = [m.image_id for m in mappings]
        images = db.query(Image).filter(
            Image.id.in_(image_ids_valid),
            Image.is_in_travelogue == True
        ).all()

        # 3. AI 캡셔닝 요청 데이터 생성
        ai_request_data = {"image_list": [
            {"image_id": img.id, "image_url": generate_signed_url(img.uri)} for img in images
        ]
        }

        # 4. AI 서버로 캡셔닝 요청
        try:
            ai_response = requests.get("http://34.64.172.167:8000/generate-caption", json=ai_request_data)
            ai_response.raise_for_status()
            caption_results = ai_response.json()
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"AI server error: {str(e)}"
            )

        # 5. 메타데이터 추출 및 DB 저장
        for img in images:
            try:
                meta = extract_datetime_location_from_gcs(img.uri)
                created_at = meta["created_at"]
                gps_latitude = meta.get("gps_latitude")
                gps_latitude_ref = meta.get("gps_latitude_ref")
                gps_longitude = meta.get("gps_longitude")
                gps_longitude_ref = meta.get("gps_longitude_ref")
                if gps_latitude and gps_latitude_ref and gps_longitude and gps_longitude_ref:
                    lat = convert_to_degrees(gps_latitude)
                    lon = convert_to_degrees(gps_longitude)
                    if gps_latitude_ref.values != 'N':
                        lat = -lat
                    if gps_longitude_ref.values != 'E':
                        lon = -lon
                    location_str = reverse_geocode(lat, lon)
                else:
                    location_str = None
            except Exception:
                created_at = None
                location_str = None


            # 기존 Metadata 조회
            existing_meta = db.query(Metadata).filter(Metadata.image_id == img.id).first()

            # Metadata 업데이트 또는 생성
            if existing_meta:
                existing_meta.created_at = created_at
                existing_meta.location = location_str
            else:
                db.add(Metadata(
                    image_id=img.id,
                    created_at=created_at,
                    location=location_str
                ))

            metadata_list.append({
                "image_id": img.id,
                "created_at": created_at,
                "location": location_str,
            })

        # 6. 캡션 결과 정리 및 image 테이블에 저장
        for cap in caption_results:
            caption_list.append({
                "image_id": cap["image_id"],
                "caption": cap["caption"]
            })
            # image 테이블에 캡션 저장
            img = db.query(Image).filter(Image.id == cap["image_id"]).first()
            if img:
                img.caption = cap["caption"]

        db.commit()
        return {
            "caption_list": caption_list,
            "metadata_list": metadata_list
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {str(e)}"
        )
    

load_dotenv()

@router.get(
    "/api/travelogue/{travelogue_id}/export",
    status_code=status.HTTP_200_OK,
    summary="여행기 PDF 저장",
    description="완성된 여행기의 PDF 바이너리를 반환합니다."
)
async def export_travelogue(travelogue_id: int, db: Session = Depends(get_db)):
    try:
        travelogue = db.query(Travelogue).filter(Travelogue.id == travelogue_id).first()
        if not travelogue:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": f"Travelogue ID {travelogue_id} not found"}
            )

        image_ids = db.query(TravelogueImage.image_id).filter(
            TravelogueImage.travelogue_id == travelogue_id
        ).all()
        image_ids = [i[0] for i in image_ids]
        images = db.query(Image).filter(
            Image.id.in_(image_ids),
            Image.is_in_travelogue == True
        ).order_by(Image.id).all()

        if not images:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "No images found for this travelogue."}
            )

        font_path = os.getenv("FONT_PATH", "fonts/malgun.ttf")
        font_name = "MalgunGothic"
        base_dir = os.path.dirname(os.path.abspath(__file__))
        font_path_full = os.path.join(base_dir, font_path)
        
        try:
            pdfmetrics.registerFont(TTFont(font_name, font_path_full))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"폰트 등록 실패: {e}")

        images_with_dates = []
        for img in images:
            file_name = extract_gcs_file_name(img.uri)
            blob = bucket.blob(file_name)
            if not blob.exists():
                continue
            created_at = extract_created_at_from_gcs(img.uri)
            images_with_dates.append({
                "img": img,
                "created_at": created_at
            })
        images_with_dates.sort(key=lambda x: (x["created_at"] is None, x["created_at"]))

        if not images_with_dates:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "GCS에 존재하는 이미지가 없습니다."}
            )

        buffer = io.BytesIO()
        p = canvas.Canvas(buffer, pagesize=letter)
        width, height = letter

        for item in images_with_dates:
            img = item["img"]
            file_name = extract_gcs_file_name(img.uri)
            blob = bucket.blob(file_name)
            image_bytes = blob.download_as_bytes()
            image_stream = io.BytesIO(image_bytes)
            image_reader = ImageReader(image_stream)

            image_stream.seek(0)
            pil_img = PILImage.open(image_stream)
            orig_width, orig_height = pil_img.size
            max_img_width = width * 0.8
            if orig_width > max_img_width:
                ratio = max_img_width / orig_width
                orig_width = int(orig_width * ratio)
                orig_height = int(orig_height * ratio)

            final_text = img.final if img.final is not None else ""
            font_size = 12
            line_spacing = 4
            max_text_width = width * 0.8

            wrapped_lines = []
            for raw_line in final_text.splitlines():
                line = ""
                for char in raw_line:
                    test_line = line + char
                    if p.stringWidth(test_line, font_name, font_size) > max_text_width:
                        wrapped_lines.append(line)
                        line = char
                    else:
                        line = test_line
                wrapped_lines.append(line)

            text_block_height = len(wrapped_lines) * (font_size + line_spacing) if wrapped_lines else 0
            block_height = orig_height + (30 if wrapped_lines else 0) + text_block_height
            y_block = (height - block_height) / 2
            x = (width - orig_width) / 2
            y = y_block + text_block_height + (30 if wrapped_lines else 0)

            p.drawImage(image_reader, x, y, width=orig_width, height=orig_height)

            if wrapped_lines:
                max_line_width = max(p.stringWidth(line, font_name, font_size) for line in wrapped_lines)
                text_x = (width - max_line_width) / 2
                text_y = y - 30

                p.setFont(font_name, font_size)
                text_object = p.beginText(text_x, text_y)
                for line in wrapped_lines:
                    text_object.textLine(line)
                p.drawText(text_object)

            p.showPage()

        p.save()
        buffer.seek(0)
        pdf_bytes = buffer.getvalue()

        file_name = f"exports/travelogue_{travelogue_id}.pdf"
        blob = bucket.blob(file_name)
        blob.upload_from_string(pdf_bytes, content_type="application/pdf")

        return Response(content=pdf_bytes, media_type="application/pdf")

    except HTTPException as e:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="서버 내부 오류가 발생했습니다."
        )
    


class ShareResponse(BaseModel):
    share_url: str

@router.get(
    "/api/travelogue/{travelogue_id}/share",
    status_code=status.HTTP_200_OK,
    response_model=ShareResponse,
    summary="여행기 PDF 공유 링크 발급",
    description="GCS에 저장된 여행기 PDF의 다운로드 링크를 반환합니다."
)
async def share_travelogue_pdf(travelogue_id: int):
    file_name = f"exports/travelogue_{travelogue_id}.pdf"
    blob = bucket.blob(file_name)

    if not blob.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"PDF 파일이 존재하지 않습니다: {file_name}"
        )

    share_url = blob.generate_signed_url(
        version="v4",
        expiration=3600,
        method="GET"
    )

    return {"share_url": share_url}
