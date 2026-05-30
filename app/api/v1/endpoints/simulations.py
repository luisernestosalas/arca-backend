from __future__ import annotations

import uuid
from datetime import datetime, date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.session import get_db
from app.models.models import Simulation, Submission, Certification, Subject
from app.schemas.simulation import SimulationRequest, SimulationOut, CertificationOut
from app.services.simulation_engine import ARCASimulationEngine
from app.services.anti_manipulation import ARCAAntiManipulationSystem

router = APIRouter()


@router.post("/", response_model=SimulationOut, status_code=status.HTTP_201_CREATED)
async def run_simulation(
    payload: SimulationRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Ejecuta una simulación Monte Carlo completa para un sujeto.
    Crea automáticamente una certificación si el sujeto pasa la validación.
    """
    # Verificar que el sujeto existe
    subject = await db.get(Subject, payload.subject_id)
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")

    # Construir datos para antimanipulación
    submission_data: dict = {"dim_scores": payload.dim_scores.to_dict()}
    if payload.metrics:
        submission_data.update(payload.metrics.model_dump(exclude_none=True))

    # Sistema antimanipulación
    anti_manip_result = None
    effective_scores = payload.dim_scores.to_dict()

    if payload.run_anti_manipulation:
        validator = ARCAAntiManipulationSystem()
        anti_manip_result = validator.validate(submission_data)
        if not anti_manip_result.passed:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "Submission failed anti-manipulation validation",
                    "penalty_total": anti_manip_result.penalty_total,
                    "issues": [
                        {"type": i.type, "severity": i.severity, "description": i.description}
                        for i in anti_manip_result.issues
                    ],
                },
            )
        # Usar scores ajustados si hay penalizaciones
        if anti_manip_result.adjusted_scores:
            effective_scores = anti_manip_result.adjusted_scores

    # Guardar submission
    submission = Submission(
        subject_id=payload.subject_id,
        data=submission_data,
        status="simulating",
        anti_manipulation_score=anti_manip_result.penalty_total if anti_manip_result else 0,
        anti_manipulation_flags={
            "issues": [
                {"type": i.type, "severity": i.severity, "description": i.description}
                for i in anti_manip_result.issues
            ]
        } if anti_manip_result else None,
    )
    db.add(submission)
    await db.flush()

    # Ejecutar motor de simulación
    engine = ARCASimulationEngine(
        dim_scores=effective_scores,
        industry=subject.industry,
        n_simulations=payload.n_simulations,
        seed=payload.seed,
    )
    result = engine.run()

    # Serializar resultados de dimensiones
    dim_results_json = [
        {
            "id": d.id, "name": d.name, "score": d.score,
            "weight": d.weight, "critical_threshold": d.critical_threshold,
            "breach_rate": d.breach_rate, "marginal_impact": d.marginal_impact,
            "criticality_rank": d.criticality_rank,
        }
        for d in result.dimension_results
    ]

    stress_json = [
        {
            "id": s.id, "name": s.name,
            "score_under_stress": s.score_under_stress,
            "survived": s.survived,
            "dimension_scores": s.dimension_scores,
        }
        for s in result.stress_results
    ]

    anti_manip_json = None
    if anti_manip_result:
        anti_manip_json = {
            "passed": anti_manip_result.passed,
            "penalty_total": anti_manip_result.penalty_total,
            "requires_human_review": anti_manip_result.requires_human_review,
            "issues": [
                {"type": i.type, "severity": i.severity,
                 "description": i.description, "penalty": i.penalty}
                for i in anti_manip_result.issues
            ],
            "adjusted_scores": anti_manip_result.adjusted_scores,
        }

    # Guardar simulación
    simulation = Simulation(
        subject_id=payload.subject_id,
        submission_id=submission.id,
        n_simulations=result.n_simulations,
        seed=result.seed,
        p_survival=result.p_survival,
        ife_score=result.ife_score,
        global_score=result.global_score,
        cert_level=result.cert_level,
        score_by_dimension=dim_results_json,
        stress_results=stress_json,
        score_distribution=result.score_distribution,
        percentiles=result.percentiles,
        anti_manipulation=anti_manip_json,
        cert_hash=result.cert_hash,
        duration_ms=result.duration_ms,
    )
    db.add(simulation)
    await db.flush()

    # Crear certificación automáticamente
    today = date.today()
    valid_until = None
    if result.valid_months > 0:
        valid_until = today + timedelta(days=result.valid_months * 30)

    cert_id = uuid.uuid4()
    certification = Certification(
        id=cert_id,
        simulation_id=simulation.id,
        subject_id=payload.subject_id,
        level=result.cert_level,
        score=result.global_score,
        p_survival=result.p_survival,
        valid_from=today,
        valid_until=valid_until,
        certificate_hash=result.cert_hash,
        public_url=f"/api/v1/certifications/verify/{cert_id}",
    )
    db.add(certification)

    # Actualizar submission
    submission.status = "certified"
    await db.commit()
    await db.refresh(simulation)

    # Construir respuesta
    return SimulationOut(
        id=simulation.id,
        subject_id=payload.subject_id,
        p_survival=result.p_survival,
        ife_score=result.ife_score,
        global_score=result.global_score,
        cert_level=result.cert_level,
        valid_months=result.valid_months,
        dimension_results=dim_results_json,
        stress_results=stress_json,
        percentiles=result.percentiles,
        score_distribution=result.score_distribution,
        anti_manipulation=anti_manip_json,
        engine_version=result.engine_version,
        n_simulations=result.n_simulations,
        seed=result.seed,
        duration_ms=result.duration_ms,
        cert_hash=result.cert_hash,
        created_at=simulation.created_at,
    )


@router.get("/{simulation_id}", response_model=SimulationOut)
async def get_simulation(
    simulation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    sim = await db.get(Simulation, simulation_id)
    if not sim:
        raise HTTPException(status_code=404, detail="Simulation not found")
    return sim


@router.get("/subject/{subject_id}", response_model=list[SimulationOut])
async def list_subject_simulations(
    subject_id: uuid.UUID,
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
):
    """Historial de simulaciones de un sujeto — muestra trayectoria de resiliencia."""
    result = await db.execute(
        select(Simulation)
        .where(Simulation.subject_id == subject_id)
        .order_by(Simulation.created_at.desc())
        .limit(limit)
    )
    return result.scalars().all()