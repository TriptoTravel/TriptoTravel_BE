from fastapi import FastAPI
import uvicorn
from api_sm import router as router_sm
from api_sh import router as router_sh

app = FastAPI()

app.include_router(router_sm)
app.include_router(router_sh)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)