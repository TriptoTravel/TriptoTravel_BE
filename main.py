from fastapi import FastAPI
from sqlalchemy import text
from database import engine
import uvicorn
import models

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

@app.get("/")
def read_root():
    with engine.connect() as conn:
        result = conn.execute(text("SELECT * FROM trip_to_travel.travelogue"))
        data = [dict(row._mapping) for row in result]
    return data

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)