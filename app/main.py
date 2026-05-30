from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from app.api.v1.endpoints import simulations, certifications, subjects, health, invitations, policies
from app.core.config import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY:
        try:
            from app.services.supabase_client import get_storage_client
            await get_storage_client().ensure_bucket_exists()
            logger.info("Supabase Storage inicializado")
        except Exception as e:
            logger.warning(f"No se pudo inicializar Supabase Storage: {e}")
    yield


app = FastAPI(
    title="ARCA API",
    description="Arquitectura de Riesgo y Certificación Anticipatoria",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(subjects.router, prefix="/api/v1/subjects", tags=["subjects"])
app.include_router(simulations.router, prefix="/api/v1/simulations", tags=["simulations"])
app.include_router(certifications.router, prefix="/api/v1/certifications", tags=["certifications"])
app.include_router(invitations.router, prefix="/api/v1/invitations", tags=["invitations"])
app.include_router(policies.router, prefix="/api/v1/policies", tags=["policies"])

