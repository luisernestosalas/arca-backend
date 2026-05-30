"""
Endpoints de certificación de políticas públicas.
"""
from __future__ import annotations

import uuid
from datetime import datetime, date, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel
from typing import Optional
import logging

from app.db.session import get_db
from app.models.models import Policy

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────────────────

class PolicyInput(BaseModel):
    title: str
    policy_type: str  # ley, decreto, resolucion, ordenanza, acuerdo
    entity: str
    jurisdiction: str  # nacional, departamental, municipal
    country_code: str = "CO"

    # P1 — Población beneficiada
    population_target: int  # personas beneficiadas directamente
    population_vulnerable_pct: float  # % de población vulnerable
    coverage_geographic: str  # nacional, regional, local

    # P2 — Impacto en empleo
    jobs_created: int
    jobs_at_risk: int
    employment_quality: str  # formal, informal, mixto

    # P3 — Equidad distributiva
    income_quintile_focus: str  # q1_q2, q3, q4_q5, todos
    gender_equity_included: bool
    ethnic_minority_included: bool

    # P4 — Sostenibilidad fiscal
    annual_budget_cop: float  # costo anual en COP
    funding_source: str  # presupuesto_nacional, credito, mixto, privado
    fiscal_years: int  # duración en años

    # P5 — Viabilidad operacional
    implementing_entity_exists: bool
    implementation_months: int
    has_monitoring_plan: bool

    # P6 — Riesgo de captura
    benefits_specific_sector: bool
    lobbying_evidence: bool
    conflict_of_interest: bool


class PolicyOut(BaseModel):
    id: uuid.UUID
    title: str
    policy_type: str
    entity: str
    jurisdiction: str
    global_score: Optional[float]
    cert_level: Optional[str]
    p1_score: Optional[float]
    p2_score: Optional[float]
    p3_score: Optional[float]
    p4_score: Optional[float]
    p5_score: Optional[float]
    p6_score: Optional[float]
    status: str
    created_at: datetime
    certified_at: Optional[datetime]
    valid_until: Optional[date]

    class Config:
        from_attributes = True


# ── Motor de scoring ──────────────────────────────────────────────────────────

def calculate_policy_scores(data: PolicyInput) -> dict:
    # P1 — Población beneficiada (peso 25%)
    p1 = 0.0
    if data.population_target >= 1_000_000: p1 += 40
    elif data.population_target >= 100_000: p1 += 25
    elif data.population_target >= 10_000: p1 += 15
    else: p1 += 5
    if data.population_vulnerable_pct >= 60: p1 += 35
    elif data.population_vulnerable_pct >= 30: p1 += 20
    else: p1 += 5
    if data.coverage_geographic == "nacional": p1 += 25
    elif data.coverage_geographic == "regional": p1 += 15
    else: p1 += 8
    p1 = min(p1, 100)

    # P2 — Impacto en empleo (peso 15%)
    net_jobs = data.jobs_created - data.jobs_at_risk
    p2 = 0.0
    if net_jobs >= 10000: p2 += 50
    elif net_jobs >= 1000: p2 += 35
    elif net_jobs >= 0: p2 += 20
    else: p2 += 0
    if data.employment_quality == "formal": p2 += 50
    elif data.employment_quality == "mixto": p2 += 30
    else: p2 += 10
    p2 = min(p2, 100)

    # P3 — Equidad distributiva (peso 20%)
    p3 = 0.0
    if data.income_quintile_focus == "q1_q2": p3 += 60
    elif data.income_quintile_focus == "todos": p3 += 40
    elif data.income_quintile_focus == "q3": p3 += 25
    else: p3 += 5
    if data.gender_equity_included: p3 += 20
    if data.ethnic_minority_included: p3 += 20
    p3 = min(p3, 100)

    # P4 — Sostenibilidad fiscal (peso 25%)
    p4 = 0.0
    budget_bn = data.annual_budget_cop / 1_000_000_000
    if budget_bn <= 10: p4 += 40
    elif budget_bn <= 100: p4 += 25
    elif budget_bn <= 1000: p4 += 10
    else: p4 += 0
    if data.funding_source == "presupuesto_nacional": p4 += 35
    elif data.funding_source == "mixto": p4 += 25
    elif data.funding_source == "privado": p4 += 20
    else: p4 += 5
    if data.fiscal_years <= 4: p4 += 25
    elif data.fiscal_years <= 8: p4 += 15
    else: p4 += 5
    p4 = min(p4, 100)

    # P5 — Viabilidad operacional (peso 10%)
    p5 = 0.0
    if data.implementing_entity_exists: p5 += 40
    if data.implementation_months <= 6: p5 += 35
    elif data.implementation_months <= 12: p5 += 20
    else: p5 += 5
    if data.has_monitoring_plan: p5 += 25
    p5 = min(p5, 100)

    # P6 — Riesgo de captura (peso 5%) — scoring inverso
    p6 = 100.0
    if data.benefits_specific_sector: p6 -= 40
    if data.lobbying_evidence: p6 -= 35
    if data.conflict_of_interest: p6 -= 25
    p6 = max(p6, 0)

    # Score global ponderado
    global_score = (
        p1 * 0.25 +
        p2 * 0.15 +
        p3 * 0.20 +
        p4 * 0.25 +
        p5 * 0.10 +
        p6 * 0.05
    )

    # Nivel de certificación
    if global_score >= 70:
        cert_level = "VIABLE"
    elif global_score >= 50:
        cert_level = "VIABLE_CON_OBSERVACIONES"
    elif global_score >= 30:
        cert_level = "REQUIERE_REFORMULACION"
    else:
        cert_level = "NO_VIABLE"

    return {
        "p1": round(p1, 1),
        "p2": round(p2, 1),
        "p3": round(p3, 1),
        "p4": round(p4, 1),
        "p5": round(p5, 1),
        "p6": round(p6, 1),
        "global": round(global_score, 1),
        "cert_level": cert_level,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/", response_model=PolicyOut)
async def create_policy(body: PolicyInput, db: AsyncSession = Depends(get_db)):
    scores = calculate_policy_scores(body)

    policy = Policy(
        title=body.title,
        policy_type=body.policy_type,
        entity=body.entity,
        jurisdiction=body.jurisdiction,
        country_code=body.country_code,
        p1_score=scores["p1"],
        p2_score=scores["p2"],
        p3_score=scores["p3"],
        p4_score=scores["p4"],
        p5_score=scores["p5"],
        p6_score=scores["p6"],
        global_score=scores["global"],
        cert_level=scores["cert_level"],
        input_data=body.model_dump(),
        status="certified",
        certified_at=datetime.now(timezone.utc),
        valid_until=date.today() + timedelta(days=365),
    )
    db.add(policy)
    await db.commit()
    await db.refresh(policy)
    return policy


@router.get("/", response_model=list[PolicyOut])
async def list_policies(limit: int = 50, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Policy).order_by(desc(Policy.created_at)).limit(limit)
    )
    return result.scalars().all()


@router.get("/{policy_id}", response_model=PolicyOut)
async def get_policy(policy_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    policy = await db.get(Policy, policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Política no encontrada")
    return policy