from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app.routers import cities, weather

app = FastAPI(title="Weather API")
app.add_middleware(SessionMiddleware, secret_key="rH1Icchj4TWVmrqLGSNbYmbkJ2BjmDk")
app.include_router(cities.router)
app.include_router(weather.router)


@app.get("/")
def read_root():
    return {"status": "ok"}
