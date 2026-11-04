"""Métricas del plan de corte."""

from __future__ import annotations

from .modelos import PlanCorte


def calcular_metricas(plan: PlanCorte) -> dict:
    """Calcula métricas de uso de material a partir de un ``PlanCorte``.

    Devuelve un ``dict`` con:
    - ``barras_usadas``: cantidad de barras físicas usadas.
    - ``desperdicio_mm``: milímetros de material desperdiciado.
    - ``aprovechamiento_pct``: porcentaje de aprovechamiento, redondeado a 1 decimal.
    """
    barras_usadas = len(plan.barras)
    if barras_usadas == 0:
        return {
            "barras_usadas": 0,
            "desperdicio_mm": 0.0,
            "aprovechamiento_pct": 0.0,
        }

    total_disponible = barras_usadas * plan.largo_barra_mm

    total_usado = 0.0
    for barra in plan.barras:
        for corte in barra.cortes:
            total_usado += corte.largo_mm + plan.kerf_mm

    desperdicio = total_disponible - total_usado
    aprovechamiento = round(total_usado / total_disponible * 100, 1) if total_disponible > 0 else 0.0

    return {
        "barras_usadas": barras_usadas,
        "desperdicio_mm": desperdicio,
        "aprovechamiento_pct": aprovechamiento,
    }
