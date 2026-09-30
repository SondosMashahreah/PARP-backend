from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from sqlalchemy import text

from app.core.config import settings
from app.core.database import Base, engine
from app.models.user import User  # noqa: F401 - registers the table metadata
from app.routers.assistant import router as assistant_router
from app.routers.auth import router as auth_router
from app.routers.profile import router as profile_router
from app.routers.education import router as education_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Development convenience. Replace with Alembic migrations before production rollout.
    # Keep the existing user-table startup behavior. Education tables use the explicit import command.
    Base.metadata.create_all(bind=engine, tables=[User.__table__])
    yield


app = FastAPI(
    title="PARP API",
    description="Palestinian Action Research Platform API",
    version="1.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(GZipMiddleware, minimum_size=1000)

app.include_router(education_router)
app.include_router(assistant_router)
app.include_router(auth_router)
app.include_router(profile_router)


@app.get("/")
def root():
    return {"message": "PARP API is running"}


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/database-health")
def database_health():
    with engine.connect() as connection:
        result = connection.execute(text("SELECT 1"))
        return {"database": "connected", "result": result.scalar()}
