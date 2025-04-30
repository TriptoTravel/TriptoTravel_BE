from google.cloud import storage
from typing import Optional
from google.oauth2 import service_account
import os

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

def upload_image_to_gcs(file_bytes, file_name: str, content_type: Optional[str] = "image/jpeg") -> str:
    blob = bucket.blob(file_name)
    blob.upload_from_string(file_bytes, content_type=content_type)
    return f"gs://{BUCKET_NAME}/{file_name}"

def delete_image_from_gcs(file_name: str) -> bool:
    blob = bucket.blob(file_name)
    if blob.exists():
        blob.delete()
        return True
    else:
        return False