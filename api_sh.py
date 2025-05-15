from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, conlist, conint
from typing import Annotated, List
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from models import Purpose, TravelQuestionResponse, Travelogue, Travelogue, Image, TravelogueImage
from database import SessionLocal
from starlette import status
from datetime import datetime
from gcs_utils import extract_gcs_file_name, extract_created_at_from_gcs, upload_pdf_and_generate_url, bucket, BUCKET_NAME
import exifread
import io
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
    

load_dotenv()

class ExportResponse(BaseModel):
    file_path: str
    export_url: str

@router.get(
    "/api/travelogue/{travelogue_id}/export",
    status_code=status.HTTP_200_OK,
    response_model=ExportResponse,
    summary="여행기 PDF 저장 및 공유",
    description="완성된 여행기를 PDF로 저장하고 공유 링크를 생성합니다."
)
async def export_travelogue(travelogue_id: int, db: db_dependency):
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

        desktop_dir = os.path.join(os.path.expanduser("~"), "Desktop")
        os.makedirs(desktop_dir, exist_ok=True)
        file_path = os.path.join(desktop_dir, f"travelogue_{travelogue_id}.pdf")
        with open(file_path, "wb") as f:
            f.write(buffer.getvalue())

        try:
            export_url = upload_pdf_and_generate_url(file_path, travelogue_id)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"PDF 업로드 실패: {str(e)}"
            )

        return {
            "file_path": file_path,
            "export_url": export_url
        }

    except HTTPException as e:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="서버 내부 오류가 발생했습니다."
        )