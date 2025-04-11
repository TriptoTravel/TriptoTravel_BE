from fastapi import FastAPI
from database import supabase
import uvicorn

app = FastAPI()

@app.get("/")
def read_root():
    # Supabase에서 "travelogue" 라는 테이블의 모든 데이터 조회
    data = supabase.table("travelogue").select("*").execute()
    return data.data

if __name__ == "__main__":
     uvicorn.run(app, host="0.0.0.0", port=8000)