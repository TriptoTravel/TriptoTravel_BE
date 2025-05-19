from google.cloud import storage
from typing import Optional
from google.oauth2 import service_account
from datetime import timedelta, datetime
import os
import io
import exifread
import asyncio

BUCKET_NAME = "trip_to_travel_bucket"

credentials_info = {
    "type": "service_account",
    "project_id": os.environ["GOOGLE_PROJECT_ID"],
    "private_key_id": os.environ["GOOGLE_PRIVATE_KEY_ID"],
    "private_key": os.environ["GOOGLE_PRIVATE_KEY"].replace('\\n', '\n'),
    "client_email": os.environ["GOOGLE_CLIENT_EMAIL"],
    "client_id": os.environ["GOOGLE_CLIENT_ID"],
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": os.environ["GOOGLE_CLIENT_X509_CERT_URL"]
}

credentials = service_account.Credentials.from_service_account_info(credentials_info)
storage_client = storage.Client(credentials=credentials, project=credentials_info["project_id"])
bucket = storage_client.bucket(BUCKET_NAME)

# 동시 업로드 수 제한 (5개)
UPLOAD_CONCURRENCY_LIMIT = 5
upload_semaphore = asyncio.Semaphore(UPLOAD_CONCURRENCY_LIMIT)

async def upload_image_to_gcs(file_bytes, file_name: str, content_type: Optional[str] = "image/jpeg") -> str:
    async with upload_semaphore:
        def _upload():
            blob = bucket.blob(file_name)
            blob.upload_from_string(file_bytes, content_type=content_type)
            return f"gs://{BUCKET_NAME}/{file_name}"
        
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _upload)

def delete_image_from_gcs(file_name: str) -> bool:
    blob = bucket.blob(file_name)
    if blob.exists():
        blob.delete()
        return True
    else:
        return False
    
def generate_signed_url(image_uri: str, expiration: int = 300) -> str:
    file_name = image_uri.split(f"gs://{BUCKET_NAME}/")[-1]
    print(file_name)
    blob = bucket.blob(file_name)
    return blob.generate_signed_url(
        version="v4",
        expiration=timedelta(seconds=expiration),
        method="GET"
    )

def extract_gcs_file_name(image_uri: str) -> str:
    prefix = f"gs://{BUCKET_NAME}/"
    if image_uri.startswith(prefix):
        return image_uri[len(prefix):]
    return image_uri

def extract_created_at_from_gcs(image_path: str) -> datetime:
    file_name = extract_gcs_file_name(image_path)
    blob = bucket.blob(file_name)
    if not blob.exists():
        return None
    image_bytes = blob.download_as_bytes()
    stream = io.BytesIO(image_bytes)
    tags = exifread.process_file(stream, details=False)
    for tag in ("EXIF DateTimeOriginal", "Image DateTime"):
        if tag in tags:
            try:
                return datetime.strptime(str(tags[tag]), "%Y:%m:%d %H:%M:%S")
            except Exception:
                continue
    return None

def upload_pdf_and_generate_url(file_path: str, travelogue_id: int) -> str:
    file_name = f"exports/travelogue_{travelogue_id}.pdf"
    with open(file_path, "rb") as f:
        file_bytes = f.read()
    blob = bucket.blob(file_name)
    blob.upload_from_string(file_bytes, content_type="application/pdf")

    url = blob.generate_signed_url(
        version="v4",
        expiration=timedelta(hours=1),
        method="GET"
    )
    return url
