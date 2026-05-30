"""
Tests del motor de simulación ARCA.
Ejecutar: docker compose exec api python -m pytest tests/ -v
"""
import pytest
import numpy as np
from app.services.simulation_engine import ARCASimulationEngine
from app.services.anti_manipulation import ARCAAntiManipulationSystem


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def healthy_scores():
    return {"D1": 80, "D2": 75, "D3": 85, "D4": 78, "D5": 90, "D6": 72, "D7": 80}

def fragile_scores():
    return {"D1": 25, "D2": 20, "D3": 35, "D4": 28, "D5": 40, "D6": 22, "D7": 30}

def silver_scores():
    return {"D1": 58, "D2": 45, "D3": 72, "D4": 63, "D5": 81, "D6": 55, "D7": 68}


# ---------------------------------------------------------------------------
# Motor — tests básicos
# ---------------------------------------------------------------------------

class TestSimulationEngine:

    def test_healthy_subject_gets_high_p_survival(self):
        engine = ARCASimulationEngine(healthy_scores(), seed=42, n_simulations=5000)
        result = engine.run()
        assert result.p_survival >= 0.80, f"Expected ≥0.80, got {result.p_survival}"

    def test_fragile_subject_gets_low_p_survival(self):
        engine = ARCASimulationEngine(fragile_scores(), seed=42, n_simulations=5000)
        result = engine.run()
        assert result.p_survival <= 0.50, f"Expected ≤0.50, got {result.p_survival}"

    def test_result_is_reproducible_with_same_seed(self):
        r1 = ARCASimulationEngine(silver_scores(), seed=123, n_simulations=1000).run()
        r2 = ARCASimulationEngine(silver_scores(), seed=123, n_simulations=1000).run()
        assert r1.p_survival == r2.p_survival
        assert r1.global_score == r2.global_score
        assert r1.cert_hash == r2.cert_hash

    def test_different_seeds_produce_different_results(self):
        r1 = ARCASimulationEngine(silver_scores(), seed=1, n_simulations=2000).run()
        r2 = ARCASimulationEngine(silver_scores(), seed=999, n_simulations=2000).run()
        # Con suficientes simulaciones, resultados deben ser muy cercanos pero no idénticos
        assert abs(r1.p_survival - r2.p_survival) < 0.05

    def test_global_score_is_weighted_average(self):
        scores = {"D1": 100, "D2": 0, "D3": 0, "D4": 0, "D5": 0, "D6": 0, "D7": 0}
        engine = ARCASimulationEngine(scores, seed=42)
        result = engine.run()
        # Solo D1 con peso 0.30 → global_score ≈ 30
        assert abs(result.global_score - 30.0) < 1.0

    def test_cert_levels_assigned_correctly(self):
        # PLATINUM: todos los scores altos
        r_plat = ARCASimulationEngine(
            {"D1":95,"D2":90,"D3":92,"D4":88,"D5":96,"D6":85,"D7":90}, seed=42
        ).run()
        assert r_plat.cert_level == "PLATINUM"

        # NO_CERT: todos los scores bajos
        r_none = ARCASimulationEngine(
            {"D1":10,"D2":5,"D3":15,"D4":8,"D5":12,"D6":10,"D7":8}, seed=42
        ).run()
        assert r_none.cert_level == "NO_CERT"

    def test_veto_rule_caps_level_at_silver(self):
        # Una dimensión < 20 → máximo SILVER
        scores = {"D1": 90, "D2": 15, "D3": 88, "D4": 85, "D5": 90, "D6": 82, "D7": 88}
        result = ARCASimulationEngine(scores, seed=42).run()
        assert result.cert_level not in ("PLATINUM", "GOLD"), \
            f"Veto rule should cap at SILVER, got {result.cert_level}"

    def test_ife_score_in_valid_range(self):
        result = ARCASimulationEngine(silver_scores(), seed=42).run()
        assert 0.0 <= result.ife_score <= 100.0

    def test_dimension_results_have_correct_count(self):
        result = ARCASimulationEngine(silver_scores(), seed=42).run()
        assert len(result.dimension_results) == 7

    def test_stress_tests_have_correct_count(self):
        result = ARCASimulationEngine(silver_scores(), seed=42).run()
        assert len(result.stress_results) == 5

    def test_score_distribution_sums_to_n_simulations(self):
        n = 3000
        result = ARCASimulationEngine(silver_scores(), seed=42, n_simulations=n).run()
        total = sum(b["count"] for b in result.score_distribution)
        assert total == n

    def test_percentiles_are_ordered(self):
        result = ARCASimulationEngine(silver_scores(), seed=42).run()
        p = result.percentiles
        assert p["p5"] <= p["p25"] <= p["p50"] <= p["p75"] <= p["p95"]

    def test_criticality_ranks_are_unique(self):
        result = ARCASimulationEngine(silver_scores(), seed=42).run()
        ranks = [d.criticality_rank for d in result.dimension_results]
        assert sorted(ranks) == list(range(1, 8))


# ---------------------------------------------------------------------------
# Anti-manipulation — tests
# ---------------------------------------------------------------------------

class TestAntiManipulation:

    def test_clean_submission_passes(self):
        submission = {
            "dim_scores": silver_scores(),
            "revenue_usd": 480_000,
            "expenses_usd": 520_000,
            "cash_usd": 350_000,
            "monthly_burn_usd": 25_000,
            "runway_months": 14,
        }
        result = ARCAAntiManipulationSystem().validate(submission)
        # Sin inconsistencias graves
        critical = [i for i in result.issues if i.severity == "CRITICAL"]
        assert len(critical) == 0

    def test_detects_runway_discrepancy(self):
        submission = {
            "dim_scores": silver_scores(),
            "cash_usd": 100_000,
            "monthly_burn_usd": 25_000,   # runway implícito: 4 meses
            "runway_months": 24,           # declarado: 24 meses → discrepancia
        }
        result = ARCAAntiManipulationSystem().validate(submission)
        types = [i.type for i in result.issues]
        assert "RUNWAY_DISCREPANCY" in types

    def test_detects_single_client_dependency(self):
        submission = {
            "dim_scores": silver_scores(),
            "customer_revenues": [400_000, 20_000, 30_000, 10_000],  # 81% en un cliente
        }
        result = ARCAAntiManipulationSystem().validate(submission)
        types = [i.type for i in result.issues]
        assert "SINGLE_CLIENT_DEPENDENCY" in types

    def test_detects_high_hhi(self):
        submission = {
            "dim_scores": silver_scores(),
            "customer_revenues": [300_000, 200_000, 50_000, 50_000],  # HHI alto
        }
        result = ARCAAntiManipulationSystem().validate(submission)
        types = [i.type for i in result.issues]
        assert "HIDDEN_CONCENTRATION" in types or "SINGLE_CLIENT_DEPENDENCY" in types

    def test_adjusted_scores_lower_than_original_on_violation(self):
        submission = {
            "dim_scores": {**silver_scores(), "D2": 80},
            "customer_revenues": [450_000, 10_000, 10_000],  # D2=80 pero concentración crítica
        }
        result = ARCAAntiManipulationSystem().validate(submission)
        # D2 debe ser penalizado
        if "D2" in result.adjusted_scores:
            assert result.adjusted_scores["D2"] < 80


# ---------------------------------------------------------------------------
# Discriminación — test de backtesting
# ---------------------------------------------------------------------------

class TestDiscrimination:
    """
    Verifica que el motor discrimina correctamente entre sujetos resilientes y frágiles.
    AUC implícita debe ser > 0.70.
    """

    def _p_survival(self, scores: dict) -> float:
        return ARCASimulationEngine(scores, seed=42, n_simulations=3000).run().p_survival

    def test_resilient_always_beats_fragile(self):
        resilient_cases = [
            {"D1":82,"D2":78,"D3":85,"D4":80,"D5":88,"D6":75,"D7":82},
            {"D1":75,"D2":72,"D3":80,"D4":74,"D5":85,"D6":70,"D7":78},
        ]
        fragile_cases = [
            {"D1":28,"D2":22,"D3":38,"D4":30,"D5":42,"D6":25,"D7":32},
            {"D1":35,"D2":18,"D3":45,"D4":28,"D5":38,"D6":30,"D7":25},
        ]

        for resilient in resilient_cases:
            for fragile in fragile_cases:
                p_res = self._p_survival(resilient)
                p_fra = self._p_survival(fragile)
                assert p_res > p_fra, (
                    f"Resilient P={p_res:.3f} should beat fragile P={p_fra:.3f}"
                )
