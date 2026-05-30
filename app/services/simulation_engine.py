"""
ARCA Simulation Engine v1.0
Motor Monte Carlo con correlaciones via descomposición de Cholesky.
Cópula Gaussiana en v1, Clayton en v2 para mayor tail dependence.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from scipy.stats import norm


# ---------------------------------------------------------------------------
# Configuración de dimensiones e industrias
# ---------------------------------------------------------------------------

DIMENSIONS = [
    {"id": "D1", "name": "Liquidez estructural",      "weight_startup": 0.30, "critical_threshold": 25},
    {"id": "D2", "name": "Concentración de ingresos", "weight_startup": 0.20, "critical_threshold": 20},
    {"id": "D3", "name": "Dependencia operacional",   "weight_startup": 0.15, "critical_threshold": 20},
    {"id": "D4", "name": "Exposición macro",           "weight_startup": 0.10, "critical_threshold": 15},
    {"id": "D5", "name": "Resiliencia legal",          "weight_startup": 0.10, "critical_threshold": 15},
    {"id": "D6", "name": "Capacidad adaptativa",       "weight_startup": 0.10, "critical_threshold": 20},
    {"id": "D7", "name": "Gobernanza",                 "weight_startup": 0.05, "critical_threshold": 15},
]

# Correlaciones empíricas entre dimensiones (7x7)
# D1 y D2 están altamente correlacionadas: crisis de liquidez suele ir con
# pérdida de clientes concentrados. D3 y D6 comparten vulnerabilidad operacional.
CORRELATION_MATRIX = np.array([
    [1.00, 0.55, 0.30, 0.45, 0.20, 0.25, 0.15],
    [0.55, 1.00, 0.25, 0.35, 0.15, 0.20, 0.10],
    [0.30, 0.25, 1.00, 0.20, 0.15, 0.35, 0.30],
    [0.45, 0.35, 0.20, 1.00, 0.25, 0.20, 0.10],
    [0.20, 0.15, 0.15, 0.25, 1.00, 0.15, 0.25],
    [0.25, 0.20, 0.35, 0.20, 0.15, 1.00, 0.20],
    [0.15, 0.10, 0.30, 0.10, 0.25, 0.20, 1.00],
])

# Escenarios de stress determinístico (shocks absolutos en puntos)
STRESS_SCENARIOS = [
    {"id": "S1", "name": "Credit crunch",          "shocks": [-30, -5,  0, -10,  0,  0,  0]},
    {"id": "S2", "name": "Revenue shock",           "shocks": [ -5,-35, -5,  -5,  0,-10,  0]},
    {"id": "S3", "name": "Key person loss",         "shocks": [  0, -5,-40,  -5,  0,-15,-10]},
    {"id": "S4", "name": "Regulatory disruption",  "shocks": [  0, -5, -5,  -5,-30, -5,-10]},
    {"id": "S5", "name": "Black swan (S1+S2+S4)",  "shocks": [-25,-30, -5, -15,-20,-10, -5]},
]

CERT_LEVELS = [
    {"level": "PLATINUM", "min_score": 85, "min_p_survival": 0.90, "valid_months": 18},
    {"level": "GOLD",     "min_score": 70, "min_p_survival": 0.75, "valid_months": 12},
    {"level": "SILVER",   "min_score": 55, "min_p_survival": 0.60, "valid_months":  6},
    {"level": "BRONZE",   "min_score": 40, "min_p_survival": 0.45, "valid_months":  3},
    {"level": "NO_CERT",  "min_score":  0, "min_p_survival": 0.00, "valid_months":  0},
]


# ---------------------------------------------------------------------------
# Data classes de resultado
# ---------------------------------------------------------------------------

@dataclass
class DimensionResult:
    id: str
    name: str
    score: float
    weight: float
    critical_threshold: float
    breach_rate: float
    marginal_impact: float
    criticality_rank: int = 0


@dataclass
class StressResult:
    id: str
    name: str
    score_under_stress: float
    survived: bool
    dimension_scores: list[float]


@dataclass
class SimulationResult:
    p_survival: float
    ife_score: float
    global_score: float
    cert_level: str
    valid_months: int
    dimension_results: list[DimensionResult]
    stress_results: list[StressResult]
    percentiles: dict[str, float]
    score_distribution: list[dict]
    engine_version: str = "1.0.0"
    n_simulations: int = 10_000
    seed: int = 0
    duration_ms: int = 0
    cert_hash: str = ""


# ---------------------------------------------------------------------------
# Motor principal
# ---------------------------------------------------------------------------

class ARCASimulationEngine:
    """
    Motor de simulación de resiliencia estructural ARCA.

    Uso:
        engine = ARCASimulationEngine(dim_scores, industry="startup", seed=42)
        result = engine.run()
    """

    def __init__(
        self,
        dim_scores: dict[str, float],
        industry: str = "startup",
        n_simulations: int = 10_000,
        seed: Optional[int] = None,
    ):
        self.industry = industry
        self.N = n_simulations
        self.seed = seed if seed is not None else int(time.time()) % 1_000_000
        self.rng = np.random.default_rng(self.seed)

        # Extraer scores en el orden canónico de DIMENSIONS
        self.dim_scores = np.array([
            float(dim_scores.get(d["id"], 50.0))
            for d in DIMENSIONS
        ], dtype=np.float64)

        self.weights = np.array([d["weight_startup"] for d in DIMENSIONS])
        self.thresholds = np.array([d["critical_threshold"] for d in DIMENSIONS])

        # Descomposición de Cholesky (precalculada una sola vez)
        self._L = np.linalg.cholesky(CORRELATION_MATRIX)

    # ------------------------------------------------------------------
    # Punto de entrada principal
    # ------------------------------------------------------------------

    def run(self) -> SimulationResult:
        t0 = time.perf_counter()

        # 1. Score global base (sin Monte Carlo)
        global_score = float(np.dot(self.weights, self.dim_scores))

        # 2. Simulación Monte Carlo
        scenarios = self._generate_scenarios()          # (N, 7)
        survival_mask = self._evaluate_survival(scenarios)  # (N,) bool

        p_survival = float(survival_mask.mean())
        ife = self._compute_ife(scenarios, survival_mask)

        # 3. Métricas por dimensión
        dim_results = self._dimension_analysis(scenarios, survival_mask)

        # 4. Stress tests determinísticos
        stress_results = self._run_stress_tests()

        # 5. Distribución de scores
        scenario_scores = scenarios @ self.weights
        percentiles = {
            "p5":  float(np.percentile(scenario_scores, 5)),
            "p25": float(np.percentile(scenario_scores, 25)),
            "p50": float(np.percentile(scenario_scores, 50)),
            "p75": float(np.percentile(scenario_scores, 75)),
            "p95": float(np.percentile(scenario_scores, 95)),
        }
        distribution = self._build_distribution(scenario_scores)

        # 6. Nivel de certificación
        cert_level, valid_months = self._assign_cert_level(global_score, p_survival)

        # 7. Hash de certificación (reproducibilidad)
        cert_hash = self._compute_cert_hash(global_score, p_survival, ife)

        duration_ms = int((time.perf_counter() - t0) * 1000)

        return SimulationResult(
            p_survival=round(p_survival, 4),
            ife_score=round(ife, 2),
            global_score=round(global_score, 2),
            cert_level=cert_level,
            valid_months=valid_months,
            dimension_results=dim_results,
            stress_results=stress_results,
            percentiles=percentiles,
            score_distribution=distribution,
            n_simulations=self.N,
            seed=self.seed,
            duration_ms=duration_ms,
            cert_hash=cert_hash,
        )

    # ------------------------------------------------------------------
    # Generación de escenarios correlacionados
    # ------------------------------------------------------------------

    def _generate_scenarios(self) -> np.ndarray:
        """
        Genera N escenarios aplicando shocks correlacionados a los scores base.
        Usa Cópula Gaussiana via Cholesky. Clayton en v2.

        Returns: array (N, 7) con scores bajo escenario ∈ [0, 100]
        """
        n_dims = len(DIMENSIONS)

        # Shocks independientes estándar normales
        Z = self.rng.standard_normal((self.N, n_dims))

        # Introducir correlación via Cholesky: cada fila es un escenario
        correlated = Z @ self._L.T

        # Transformar a percentiles uniformes (cópula gaussiana)
        uniform_shocks = norm.cdf(correlated)  # (N, 7) ∈ [0, 1]

        # Convertir a shocks en escala de score: media 0, std ~20
        # Centrado en 0 para que el score base sea el caso esperado
        score_shocks = (uniform_shocks - 0.5) * 40  # rango aprox [-20, +20]

        # Aplicar shocks al score base y clip a [0, 100]
        scenarios = np.clip(self.dim_scores + score_shocks, 0.0, 100.0)

        return scenarios

    # ------------------------------------------------------------------
    # Evaluación de supervivencia
    # ------------------------------------------------------------------

    def _evaluate_survival(self, scenarios: np.ndarray) -> np.ndarray:
        """
        Supervivencia = no más de 1 dimensión por debajo de su umbral crítico.
        Regla ARCA: 2+ violaciones simultáneas = fallo estructural.

        Returns: bool array (N,)
        """
        # Cuántas dimensiones violan su umbral en cada escenario
        violations = (scenarios < self.thresholds).sum(axis=1)  # (N,)
        return violations <= 1

    # ------------------------------------------------------------------
    # Índice de Fragilidad Estructural (IFE)
    # ------------------------------------------------------------------

    def _compute_ife(self, scenarios: np.ndarray, survival_mask: np.ndarray) -> float:
        """
        IFE ∈ [0, 100]. 100 = máxima resiliencia.
        Penaliza tanto la frecuencia de fallo como la profundidad.
        """
        p_failure = 1.0 - survival_mask.mean()

        failure_scenarios = scenarios[~survival_mask]
        if len(failure_scenarios) == 0:
            avg_depth = 0.0
        else:
            # Profundidad = cuánto se violan los umbrales en escenarios de fallo
            violations = np.maximum(0, self.thresholds - failure_scenarios)
            normalized = violations / np.maximum(self.thresholds, 1e-9)
            avg_depth = float(normalized.sum(axis=1).mean())

        ife_raw = p_failure * 0.6 + avg_depth * 0.4
        return max(0.0, 100.0 * (1.0 - ife_raw))

    # ------------------------------------------------------------------
    # Análisis por dimensión
    # ------------------------------------------------------------------

    def _dimension_analysis(
        self, scenarios: np.ndarray, survival_mask: np.ndarray
    ) -> list[DimensionResult]:
        """
        Para cada dimensión: breach_rate y marginal_impact (sensibilidad).
        """
        results = []
        base_p_survival = survival_mask.mean()

        for i, dim in enumerate(DIMENSIONS):
            breach_rate = float((scenarios[:, i] < self.thresholds[i]).mean())

            # Impacto marginal: sensibilidad de P(supervivencia) al deterioro de dim i
            delta = 5.0
            perturbed = scenarios.copy()
            perturbed[:, i] = np.clip(perturbed[:, i] - delta, 0, 100)
            p_perturbed = self._evaluate_survival(perturbed).mean()
            marginal_impact = float((base_p_survival - p_perturbed) / delta)

            results.append(DimensionResult(
                id=dim["id"],
                name=dim["name"],
                score=round(float(self.dim_scores[i]), 1),
                weight=dim["weight_startup"],
                critical_threshold=float(self.thresholds[i]),
                breach_rate=round(breach_rate, 4),
                marginal_impact=round(marginal_impact, 6),
            ))

        # Rankear por impacto marginal (1 = más crítico)
        ranked = sorted(results, key=lambda r: r.marginal_impact, reverse=True)
        for rank, r in enumerate(ranked):
            r.criticality_rank = rank + 1

        return results

    # ------------------------------------------------------------------
    # Stress tests determinísticos
    # ------------------------------------------------------------------

    def _run_stress_tests(self) -> list[StressResult]:
        results = []
        for scenario in STRESS_SCENARIOS:
            shocks = np.array(scenario["shocks"], dtype=np.float64)
            stressed_scores = np.clip(self.dim_scores + shocks, 0.0, 100.0)
            violations = int((stressed_scores < self.thresholds).sum())
            survived = violations <= 1
            score_under_stress = float(np.dot(self.weights, stressed_scores))

            results.append(StressResult(
                id=scenario["id"],
                name=scenario["name"],
                score_under_stress=round(score_under_stress, 2),
                survived=survived,
                dimension_scores=[round(float(s), 1) for s in stressed_scores],
            ))
        return results

    # ------------------------------------------------------------------
    # Distribución de scores
    # ------------------------------------------------------------------

    def _build_distribution(self, scenario_scores: np.ndarray) -> list[dict]:
        buckets = 20
        bucket_size = 100.0 / buckets
        distribution = []
        for b in range(buckets):
            lo = b * bucket_size
            hi = (b + 1) * bucket_size
            count = int(((scenario_scores >= lo) & (scenario_scores < hi)).sum())
            distribution.append({"lo": round(lo, 1), "hi": round(hi, 1), "count": count})
        return distribution

    # ------------------------------------------------------------------
    # Nivel de certificación
    # ------------------------------------------------------------------

    def _assign_cert_level(self, score: float, p_survival: float) -> tuple[str, int]:
        # Regla de veto: si alguna dimensión < 20, máximo SILVER
        veto_active = any(s < 20.0 for s in self.dim_scores)

        for lvl in CERT_LEVELS:
            if score >= lvl["min_score"] and p_survival >= lvl["min_p_survival"]:
                level = lvl["level"]
                if veto_active and level in ("PLATINUM", "GOLD"):
                    level = "SILVER"
                    months = next(l["valid_months"] for l in CERT_LEVELS if l["level"] == "SILVER")
                    return level, months
                return level, lvl["valid_months"]

        return "NO_CERT", 0

    # ------------------------------------------------------------------
    # Hash de certificación
    # ------------------------------------------------------------------

    def _compute_cert_hash(self, score: float, p_survival: float, ife: float) -> str:
        payload = f"{score:.4f}:{p_survival:.4f}:{ife:.4f}:{self.seed}:v1.0.0"
        return hashlib.sha256(payload.encode()).hexdigest()
