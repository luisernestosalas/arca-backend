from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Subjects
# ---------------------------------------------------------------------------

class SubjectCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=500)
    industry: str = Field(..., pattern="^(startup|fintech|saas|ecommerce|real_estate|fund|public_policy)$")
    stage: Optional[str] = Field(None, pattern="^(pre_seed|seed|series_a|series_b|growth|mature)?$")
    country_code: str = Field("CO", min_length=2, max_length=2)
    currency: str = Field("USD", min_length=3, max_length=3)


class SubjectOut(SubjectCreate):
    id: UUID
    tenant_id: Optional[UUID] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Simulation input
# ---------------------------------------------------------------------------

class DimScores(BaseModel):
    D1: float = Field(..., ge=0, le=100, description="Liquidez estructural")
    D2: float = Field(..., ge=0, le=100, description="Concentración de ingresos")
    D3: float = Field(..., ge=0, le=100, description="Dependencia operacional")
    D4: float = Field(..., ge=0, le=100, description="Exposición macro")
    D5: float = Field(..., ge=0, le=100, description="Resiliencia legal/regulatoria")
    D6: float = Field(..., ge=0, le=100, description="Capacidad adaptativa")
    D7: float = Field(..., ge=0, le=100, description="Gobernanza")

    def to_dict(self) -> dict[str, float]:
        return self.model_dump()


class OperationalMetrics(BaseModel):
    """Métricas operacionales para el sistema antimanipulación."""
    revenue_usd: Optional[float] = Field(None, ge=0)
    expenses_usd: Optional[float] = Field(None, ge=0)
    cash_usd: Optional[float] = Field(None, ge=0)
    monthly_burn_usd: Optional[float] = Field(None, ge=0)
    runway_months: Optional[float] = Field(None, ge=0, le=120)
    headcount: Optional[int] = Field(None, ge=1)
    customer_count: Optional[int] = Field(None, ge=1)
    customer_revenues: Optional[list[float]] = Field(None, description="Revenue por cliente para cálculo HHI")
    gross_margin: Optional[float] = Field(None, ge=0, le=1)
    revenue_growth_yoy: Optional[float] = None
    burn_multiple: Optional[float] = Field(None, ge=0)
    profitability_reported: Optional[str] = Field(None, pattern="^(positive|negative|breakeven)?$")


class SimulationRequest(BaseModel):
    subject_id: UUID
    dim_scores: DimScores
    metrics: Optional[OperationalMetrics] = None
    n_simulations: int = Field(10_000, ge=1_000, le=50_000)
    seed: Optional[int] = Field(None, ge=0)
    run_anti_manipulation: bool = True


# ---------------------------------------------------------------------------
# Simulation output
# ---------------------------------------------------------------------------

class DimensionResultOut(BaseModel):
    id: str
    name: str
    score: float
    weight: float
    critical_threshold: float
    breach_rate: float
    marginal_impact: float
    criticality_rank: int


class StressResultOut(BaseModel):
    id: str
    name: str
    score_under_stress: float
    survived: bool
    dimension_scores: list[float]


class AntiManipulationOut(BaseModel):
    passed: bool
    penalty_total: float
    requires_human_review: bool
    issues: list[dict[str, Any]]
    adjusted_scores: dict[str, float]


class SimulationOut(BaseModel):
    id: UUID
    subject_id: UUID
    p_survival: float
    ife_score: float
    global_score: float
    cert_level: str
    valid_months: int
    dimension_results: list[DimensionResultOut]
    stress_results: list[StressResultOut]
    percentiles: dict[str, float]
    score_distribution: list[dict]
    anti_manipulation: Optional[AntiManipulationOut] = None
    engine_version: str
    n_simulations: int
    seed: int
    duration_ms: int
    cert_hash: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Certifications
# ---------------------------------------------------------------------------

class CertificationOut(BaseModel):
    id: UUID
    simulation_id: UUID
    subject_id: UUID
    level: str
    score: float
    p_survival: float
    valid_from: date
    valid_until: Optional[date]
    certificate_hash: str
    public_url: str
    issued_at: datetime
    revoked_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class CertVerifyOut(BaseModel):
    valid: bool
    cert_id: UUID
    subject_name: str
    level: str
    score: float
    valid_until: Optional[date]
    revoked: bool
    message: str
