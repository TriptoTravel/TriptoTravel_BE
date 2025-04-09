from fastapi import FastAPI
from supabase import create_client
import os
from dotenv import load_dotenv

load_dotenv()

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")

supabase = create_client(url, key)

app = FastAPI()

@app.get("/")
def read_root():
    # Supabase에서 "travelogue" 라는 테이블의 모든 데이터 조회
    data = supabase.table("travelogue").select("*").execute()
    return data.data