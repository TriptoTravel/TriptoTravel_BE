from fastapi import FastAPI, Depends
import uvicorn
from sqlalchemy.orm import Session
from models import Travelogue
from database import SessionLocal

app = FastAPI()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

from pydantic import BaseModel
from typing import List
from datetime import datetime
class TravelogueResponse(BaseModel):
    id: int
    style_category: int | None = None
    created_at: datetime

@app.get("/", response_model=List[TravelogueResponse])
def get_test_with_db(db: Session = Depends(get_db)):
    return db.query(Travelogue).all()

if __name__ == "__main__":
    uvicorn.run(app, host="localhost", port=8000)