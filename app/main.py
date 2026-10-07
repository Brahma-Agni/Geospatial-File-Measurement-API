import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.files import router as files_router
from app.config import get_settings
from app.database import create_tables
from app.exceptions.handlers import register_exception_handlers


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    create_tables()
    yield


app = FastAPI(
    title="Geospatial File Measurement API",
    version="1.0.0",
    description="Upload KML or zipped ESRI Shapefiles and calculate CRS-safe measurements.",
    lifespan=lifespan,
)
register_exception_handlers(app)
app.include_router(files_router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
