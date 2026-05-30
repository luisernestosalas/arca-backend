"""
ARCA Anti-Manipulation System
Valida consistencia interna, anomalías estadísticas y concentración oculta.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ValidationIssue:
    type: str
    severity: str       # LOW, MEDIUM, HIGH, CRITICAL
    description: str
    penalty: float


@dataclass
class ValidationResult:
    passed: bool
    issues: list[ValidationIssue]
    penalty_total: float
    requires_human_review: bool
    adjusted_scores: dict[str, float]   # scores penalizados post-validación


PENALTY_THRESHOLD = 30.0        # penalización máxima antes de bloquear
HIGH_RISK_THRESHOLD = 20.0      # requiere revisión humana


class ARCAAntiManipulationSystem:

    def validate(self, submission: dict[str, Any]) -> ValidationResult:
        issues: list[ValidationIssue] = []

        issues += self._check_internal_consistency(submission)
        issues += self._check_statistical_anomalies(submission)
        issues += self._detect_hidden_concentration(submission)
        issues += self._check_dimension_coherence(submission)

        penalty_total = sum(i.penalty for i in issues)
        passed = penalty_total < PENALTY_THRESHOLD
        requires_human_review = penalty_total >= HIGH_RISK_THRESHOLD

        # Ajustar scores según penalizaciones
        adjusted_scores = self._apply_penalties(
            submission.get("dim_scores", {}), issues, penalty_total
        )

        return ValidationResult(
            passed=passed,
            issues=issues,
            penalty_total=round(penalty_total, 2),
            requires_human_review=requires_human_review,
            adjusted_scores=adjusted_scores,
        )

    # ------------------------------------------------------------------

    def _check_internal_consistency(self, data: dict) -> list[ValidationIssue]:
        issues = []

        revenue = data.get("revenue_usd", 0)
        expenses = data.get("expenses_usd", 0)
        profitability = data.get("profitability_reported")

        if profitability == "positive" and expenses > revenue > 0:
            issues.append(ValidationIssue(
                type="INTERNAL_INCONSISTENCY",
                severity="HIGH",
                description="Rentabilidad declarada positiva pero gastos superan ingresos",
                penalty=15.0,
            ))

        # Runway implícito vs declarado
        cash = data.get("cash_usd", 0)
        burn_rate = data.get("monthly_burn_usd", 1)
        declared_runway = data.get("runway_months", 0)

        if burn_rate > 0 and declared_runway > 0:
            implicit_runway = cash / burn_rate
            discrepancy = abs(implicit_runway - declared_runway) / max(declared_runway, 1)
            if discrepancy > 0.25:
                issues.append(ValidationIssue(
                    type="RUNWAY_DISCREPANCY",
                    severity="MEDIUM",
                    description=(
                        f"Runway declarado {declared_runway:.1f}m vs "
                        f"calculado {implicit_runway:.1f}m "
                        f"(discrepancia {discrepancy:.0%})"
                    ),
                    penalty=10.0,
                ))

        return issues

    def _detect_hidden_concentration(self, data: dict) -> list[ValidationIssue]:
        issues = []
        customer_revenues = data.get("customer_revenues", [])

        if not customer_revenues:
            return issues

        total = sum(customer_revenues)
        if total <= 0:
            return issues

        # HHI: estándar DOJ/FTC — >2500 = alta concentración
        hhi = sum((r / total) ** 2 for r in customer_revenues) * 10_000
        if hhi > 2500:
            issues.append(ValidationIssue(
                type="HIDDEN_CONCENTRATION",
                severity="HIGH",
                description=f"HHI={hhi:.0f} — concentración crítica de ingresos (umbral: 2500)",
                penalty=20.0,
            ))
        elif hhi > 1800:
            issues.append(ValidationIssue(
                type="MODERATE_CONCENTRATION",
                severity="MEDIUM",
                description=f"HHI={hhi:.0f} — concentración moderada de ingresos",
                penalty=8.0,
            ))

        # Cliente principal > 40%
        max_concentration = max(customer_revenues) / total
        if max_concentration > 0.40:
            issues.append(ValidationIssue(
                type="SINGLE_CLIENT_DEPENDENCY",
                severity="CRITICAL",
                description=(
                    f"Cliente principal representa {max_concentration:.0%} del revenue"
                ),
                penalty=25.0,
            ))

        return issues

    def _check_statistical_anomalies(self, data: dict) -> list[ValidationIssue]:
        """
        Compara métricas clave contra benchmarks sectoriales simplificados.
        En Fase 2 se reemplaza por benchmarks dinámicos desde la DB.
        """
        issues = []

        # Benchmarks estáticos para startup Series A (mu, sigma)
        benchmarks = {
            "gross_margin": (0.65, 0.15),
            "revenue_growth_yoy": (1.2, 0.6),
            "burn_multiple": (1.5, 0.8),
        }

        for variable, (mu, sigma) in benchmarks.items():
            value = data.get(variable)
            if value is None or sigma == 0:
                continue
            z_score = (value - mu) / sigma
            if abs(z_score) > 3.0:
                issues.append(ValidationIssue(
                    type="STATISTICAL_OUTLIER",
                    severity="MEDIUM",
                    description=(
                        f"{variable} está a {z_score:.1f}σ del benchmark sectorial"
                    ),
                    penalty=8.0,
                ))

        return issues

    def _check_dimension_coherence(self, data: dict) -> list[ValidationIssue]:
        """
        Verifica coherencia entre scores declarados y métricas operacionales.
        Ejemplo: D1 alto con runway < 6 meses es incoherente.
        """
        issues = []
        dim_scores = data.get("dim_scores", {})

        d1 = dim_scores.get("D1", 50)
        runway = data.get("runway_months", 12)
        if d1 > 75 and runway < 6:
            issues.append(ValidationIssue(
                type="SCORE_METRIC_INCOHERENCE",
                severity="HIGH",
                description=(
                    f"D1={d1} (alto) pero runway={runway}m (<6 meses) — incoherente"
                ),
                penalty=18.0,
            ))

        d2 = dim_scores.get("D2", 50)
        customer_revenues = data.get("customer_revenues", [])
        if customer_revenues and d2 > 70:
            total = sum(customer_revenues)
            if total > 0:
                hhi = sum((r / total) ** 2 for r in customer_revenues) * 10_000
                if hhi > 2500:
                    issues.append(ValidationIssue(
                        type="SCORE_METRIC_INCOHERENCE",
                        severity="HIGH",
                        description=(
                            f"D2={d2} (alto) pero HHI={hhi:.0f} indica alta concentración"
                        ),
                        penalty=15.0,
                    ))

        return issues

    def _apply_penalties(
        self,
        dim_scores: dict[str, float],
        issues: list[ValidationIssue],
        penalty_total: float,
    ) -> dict[str, float]:
        """
        Reduce los scores ajustados proporcionalmente a la penalización.
        Penalización máxima aplicable: 20 puntos sobre cualquier dimensión.
        """
        if not dim_scores or penalty_total <= 0:
            return dict(dim_scores)

        adjusted = dict(dim_scores)

        # Penalizaciones específicas por tipo
        for issue in issues:
            if issue.type in ("SINGLE_CLIENT_DEPENDENCY", "HIDDEN_CONCENTRATION"):
                adjusted["D2"] = max(0, adjusted.get("D2", 50) - issue.penalty * 0.8)
            elif issue.type == "RUNWAY_DISCREPANCY":
                adjusted["D1"] = max(0, adjusted.get("D1", 50) - issue.penalty)
            elif issue.type == "SCORE_METRIC_INCOHERENCE":
                # Penalizar la dimensión relevante
                for dim_id in ["D1", "D2", "D3", "D4", "D5", "D6", "D7"]:
                    if dim_id in issue.description:
                        adjusted[dim_id] = max(0, adjusted.get(dim_id, 50) - issue.penalty * 0.5)

        return {k: round(v, 2) for k, v in adjusted.items()}
