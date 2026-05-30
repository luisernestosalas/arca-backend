"""
Endpoints de certificaciones con generación de PDF y upload a Supabase Storage.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import logging

from app.db.session import get_db
from app.models.models import Certification, Subject, Simulation
from app.schemas.simulation import CertificationOut, CertVerifyOut
from app.core.auth import AuthenticatedUser, get_current_user, get_optional_user
from app.services.supabase_client import get_storage_client
from app.services.pdf_generator import generate_certificate_pdf
from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/verify/{cert_id}", response_model=CertVerifyOut)
async def verify_certification(
    cert_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(get_optional_user),
):
    cert = await db.get(Certification, cert_id)
    if not cert:
        return CertVerifyOut(
            valid=False, cert_id=cert_id, subject_name="",
            level="", score=0, valid_until=None,
            revoked=False, message="Certificado no encontrado",
        )

    subject = await db.get(Subject, cert.subject_id)
    subject_name = subject.name if subject else "Desconocido"

    revoked = cert.revoked_at is not None
    expired = cert.valid_until and cert.valid_until < date.today()
    valid = not revoked and not expired and cert.level != "NO_CERT"

    if revoked:
        message = f"Certificado revocado el {cert.revoked_at.date()}"
    elif expired:
        message = f"Certificado vencido el {cert.valid_until}"
    elif cert.level == "NO_CERT":
        message = "Sujeto no certificado — fragilidad estructural detectada"
    else:
        message = f"Certificado ARCA {cert.level} válido hasta {cert.valid_until}"

    return CertVerifyOut(
        valid=valid, cert_id=cert_id, subject_name=subject_name,
        level=cert.level, score=cert.score, valid_until=cert.valid_until,
        revoked=revoked, message=message,
    )


@router.post("/{cert_id}/generate-pdf", status_code=201)
async def generate_and_upload_pdf(
    cert_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(get_current_user),
):
    cert = await db.get(Certification, cert_id)
    if not cert:
        raise HTTPException(status_code=404, detail="Certificado no encontrado")

    subject = await db.get(Subject, cert.subject_id)
    simulation = await db.get(Simulation, cert.simulation_id)

    dim_scores = {}
    if simulation and simulation.score_by_dimension:
        for d in simulation.score_by_dimension:
            dim_scores[d["id"]] = d["score"]

    verify_url = f"{settings.PUBLIC_BASE_URL}/api/v1/certifications/verify/{cert_id}"

    try:
        pdf_bytes = generate_certificate_pdf(
            cert_id=str(cert_id),
            subject_name=subject.name if subject else "N/A",
            cert_level=cert.level,
            global_score=cert.score,
            p_survival=cert.p_survival,
            ife_score=simulation.ife_score if simulation else 0,
            dim_scores=dim_scores,
            stress_results=simulation.stress_results if simulation else [],
            valid_from=cert.valid_from,
            valid_until=cert.valid_until,
            cert_hash=cert.certificate_hash or "",
            verify_url=verify_url,
        )
    except Exception as e:
        logger.error(f"Error generando PDF: {e}")
        raise HTTPException(status_code=500, detail=f"Error generando PDF: {e}")

    try:
        storage = get_storage_client()
        pdf_url = await storage.upload_pdf(
            cert_id=str(cert_id),
            pdf_bytes=pdf_bytes,
            subject_name=subject.name if subject else "N/A",
        )
    except Exception as e:
        logger.error(f"Error subiendo a Storage: {e}")
        raise HTTPException(status_code=500, detail=f"Error subiendo PDF: {e}")

    cert.public_url = pdf_url
    await db.commit()
    return {"cert_id": str(cert_id), "pdf_url": pdf_url}


@router.get("/{cert_id}/download")
async def download_pdf(cert_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    cert = await db.get(Certification, cert_id)
    if not cert or not cert.public_url:
        raise HTTPException(status_code=404, detail="PDF no disponible")
    return RedirectResponse(url=cert.public_url)


@router.get("/subject/{subject_id}", response_model=list[CertificationOut])
async def list_subject_certifications(
    subject_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(get_current_user),
):
    result = await db.execute(
        select(Certification)
        .where(Certification.subject_id == subject_id)
        .order_by(Certification.issued_at.desc())
    )
    return result.scalars().all()


@router.post("/{cert_id}/revoke")
async def revoke_certification(
    cert_id: uuid.UUID, reason: str,
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(get_current_user),
):
    cert = await db.get(Certification, cert_id)
    if not cert:
        raise HTTPException(status_code=404, detail="Certificado no encontrado")
    cert.revoked_at = datetime.utcnow()
    cert.revoke_reason = reason
    await db.commit()
    if cert.public_url:
        try:
            await get_storage_client().delete_pdf(str(cert_id))
        except Exception:
            pass
    return {"message": "Certificado revocado", "cert_id": str(cert_id)}
