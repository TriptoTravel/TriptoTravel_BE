from fastapi import FastAPI
from database import supabase, Base
from sqlalchemy import create_engine, MetaData, text
import os
from dotenv import load_dotenv
import uvicorn

load_dotenv()
db_url = os.getenv("DATABASE_URL")

#스키마 이름 지정
metadata = MetaData(schema="trip_to_travel")
engine = create_engine(db_url)

# 테이블 생성
Base.metadata = metadata
Base.metadata.create_all(bind=engine)

app = FastAPI()

@app.get("/")
def read_root():
    with engine.connect() as conn:
        result = conn.execute(text("SELECT * FROM trip_to_travel.travelogue"))
        data = [dict(row._mapping) for row in result]
    return data

if __name__ == "__main__":
     uvicorn.run(app, host="0.0.0.0", port=8000)