from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import Optional
import uuid

from app.db.session import get_db
from app.models.models import Subject, Certification, Simulation
from app.schemas.simulation import SubjectCreate, SubjectOut
from pydantic import BaseModel
from datetime import datetime

router = APIRouter()


class SubjectWithCert(BaseModel):
    id: uuid.UUID
    name: str
    industry: str
    stage: Optional[str] = None
    country_code: Optional[str] = None
    created_at: datetime
    # Última certificación
    cert_id: Optional[uuid.UUID] = None
    cert_level: Optional[str] = None
    cert_score: Optional[float] = None
    cert_p_survival: Optional[float] = None
    cert_valid_until: Optional[str] = None
    cert_issued_at: Optional[datetime] = None
    # Scores por dimensión
    score_by_dimension: Optional[list] = None
    # Certificación anterior para tendencia
    prev_score: Optional[float] = None

    model_config = {"from_attributes": True}


@router.post("/", response_model=SubjectOut, status_code=201)
async def create_subject(payload: SubjectCreate, db: AsyncSession = Depends(get_db)):
    subject = Subject(**payload.model_dump())
    db.add(subject)
    await db.commit()
    await db.refresh(subject)
    return subject


@router.get("/portfolio", response_model=list[SubjectWithCert])
async def get_portfolio(limit: int = 50, db: AsyncSession = Depends(get_db)):
    """
    Retorna todos los sujetos con su última certificación.
    Endpoint principal para el panel del fondo.
    """
    subjects_result = await db.execute(
        select(Subject).order_by(desc(Subject.created_at)).limit(limit)
    )
    subjects = subjects_result.scalars().all()

    portfolio = []
    for subject in subjects:
        # Obtener última certificación
        cert_result = await db.execute(
            select(Certification)
            .where(Certification.subject_id == subject.id)
            .where(Certification.revoked_at == None)
            .order_by(desc(Certification.issued_at))
            .limit(1)
        )
        latest_cert = cert_result.scalar_one_or_none()

        # Obtener certificación anterior para tendencia
        prev_score = None
        score_by_dimension = None

        if latest_cert:
            prev_result = await db.execute(
                select(Certification)
                .where(Certification.subject_id == subject.id)
                .where(Certification.id != latest_cert.id)
                .where(Certification.revoked_at == None)
                .order_by(desc(Certification.issued_at))
                .limit(1)
            )
            prev_cert = prev_result.scalar_one_or_none()
            if prev_cert:
                prev_score = float(prev_cert.score)

            # Obtener scores por dimensión de la simulación
            sim_result = await db.execute(
                select(Simulation)
                .where(Simulation.id == latest_cert.simulation_id)
            )
            sim = sim_result.scalar_one_or_none()
            if sim and sim.score_by_dimension:
                score_by_dimension = sim.score_by_dimension

        portfolio.append(SubjectWithCert(
            id=subject.id,
            name=subject.name,
            industry=subject.industry,
            stage=subject.stage,
            country_code=subject.country_code,
            created_at=subject.created_at,
            cert_id=latest_cert.id if latest_cert else None,
            cert_level=latest_cert.level if latest_cert else None,
            cert_score=float(latest_cert.score) if latest_cert else None,
            cert_p_survival=float(latest_cert.p_survival) if latest_cert else None,
            cert_valid_until=str(latest_cert.valid_until) if latest_cert and latest_cert.valid_until else None,
            cert_issued_at=latest_cert.issued_at if latest_cert else None,
            score_by_dimension=score_by_dimension,
            prev_score=prev_score,
        ))

    return portfolio


@router.get("/{subject_id}", response_model=SubjectOut)
async def get_subject(subject_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    subject = await db.get(Subject, subject_id)
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    return subject


@router.get("/", response_model=list[SubjectOut])
async def list_subjects(limit: int = 20, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Subject).order_by(Subject.created_at.desc()).limit(limit))
    return result.scalars().all()