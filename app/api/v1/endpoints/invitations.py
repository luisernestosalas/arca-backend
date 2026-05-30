"""
Flujo de invitaciones: fondo invita startup → startup completa certificación.
"""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr
from typing import Optional

from app.db.session import get_db
from app.models.models import Invitation, Subject, Certification
from app.core.auth import get_optional_user

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────────────────

class InvitationCreate(BaseModel):
    email: Optional[str] = None
    company_name: Optional[str] = None
    message: Optional[str] = None
    expires_days: int = 7

class InvitationOut(BaseModel):
    id: uuid.UUID
    token: str
    email: Optional[str]
    company_name: Optional[str]
    message: Optional[str]
    status: str
    expires_at: datetime
    created_at: datetime
    link: str

    class Config:
        from_attributes = True

class InvitationPublic(BaseModel):
    """Lo que ve la startup al abrir el link."""
    id: uuid.UUID
    company_name: Optional[str]
    message: Optional[str]
    status: str
    expires_at: datetime
    expired: bool


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/", response_model=InvitationOut)
async def create_invitation(
    body: InvitationCreate,
    db: AsyncSession = Depends(get_db),
):
    """El fondo crea una invitación y obtiene un link único."""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=body.expires_days)

    inv = Invitation(
        token=token,
        email=body.email,
        company_name=body.company_name,
        message=body.message,
        expires_at=expires_at,
    )
    db.add(inv)
    await db.commit()
    await db.refresh(inv)

    from app.core.config import settings
    link = f"{settings.PUBLIC_BASE_URL}/invitacion/{token}"

    return InvitationOut(
        id=inv.id,
        token=inv.token,
        email=inv.email,
        company_name=inv.company_name,
        message=inv.message,
        status=inv.status,
        expires_at=inv.expires_at,
        created_at=inv.created_at,
        link=link,
    )


@router.get("/{token}", response_model=InvitationPublic)
async def get_invitation(token: str, db: AsyncSession = Depends(get_db)):
    """La startup abre el link y ve la invitación."""
    result = await db.execute(
        select(Invitation).where(Invitation.token == token)
    )
    inv = result.scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=404, detail="Invitación no encontrada")

    expired = datetime.now(timezone.utc) > inv.expires_at.replace(tzinfo=timezone.utc)

    return InvitationPublic(
        id=inv.id,
        company_name=inv.company_name,
        message=inv.message,
        status=inv.status,
        expires_at=inv.expires_at,
        expired=expired,
    )


@router.patch("/{token}/complete")
async def complete_invitation(
    token: str,
    subject_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Marca la invitación como completada una vez la startup certifica."""
    result = await db.execute(
        select(Invitation).where(Invitation.token == token)
    )
    inv = result.scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=404, detail="Invitación no encontrada")

    inv.status = "completed"
    inv.subject_id = subject_id
    inv.completed_at = datetime.now(timezone.utc)
    await db.commit()
    return {"message": "Invitación completada", "token": token}


@router.get("/", response_model=list[InvitationOut])
async def list_invitations(db: AsyncSession = Depends(get_db)):
    """El fondo ve todas sus invitaciones."""
    result = await db.execute(
        select(Invitation).order_by(Invitation.created_at.desc())
    )
    invitations = result.scalars().all()

    from app.core.config import settings
    return [
        InvitationOut(
            id=inv.id,
            token=inv.token,
            email=inv.email,
            company_name=inv.company_name,
            message=inv.message,
            status=inv.status,
            expires_at=inv.expires_at,
            created_at=inv.created_at,
            link=f"{settings.PUBLIC_BASE_URL}/invitacion/{inv.token}",
        )
        for inv in invitations
    ]