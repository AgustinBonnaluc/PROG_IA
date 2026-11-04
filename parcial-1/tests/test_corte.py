"""Tests para el paquete de corte unidimensional."""

from __future__ import annotations

import math
from collections import Counter

import pytest

from corte.modelos import Pieza
from corte.validacion import validar_piezas
from corte.optimizador import optimizar_corte
from corte.metricas import calcular_metricas


# ── fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def piezas_multi_ot() -> list[Pieza]:
    """Piezas de varias OT que comparten material (caso realista)."""
    return [
        Pieza(pieza_id="pata", ot="OT-101", largo_mm=2000, cantidad=4),
        Pieza(pieza_id="travesano", ot="OT-101", largo_mm=1450, cantidad=6),
        Pieza(pieza_id="larguero", ot="OT-102", largo_mm=1500, cantidad=4),
        Pieza(pieza_id="pata_mesa", ot="OT-102", largo_mm=900, cantidad=4),
        Pieza(pieza_id="cabezal", ot="OT-102", largo_mm=700, cantidad=2),
    ]


LARGO_BARRA = 6000.0
KERF = 3.0


# ── test: cada unidad aparece exactamente una vez ────────────────────

def test_cada_unidad_aparece_una_vez(piezas_multi_ot: list[Pieza]) -> None:
    """Cada unidad individual de pieza debe estar en exactamente 1 barra."""
    plan = optimizar_corte(piezas_multi_ot, LARGO_BARRA, KERF)

    # Contar apariciones por pieza_id en el plan
    conteo_plan: Counter[str] = Counter()
    for barra in plan.barras:
        for corte in barra.cortes:
            conteo_plan[corte.pieza_id] += 1

    # Contar unidades esperadas
    conteo_esperado: Counter[str] = Counter()
    for p in piezas_multi_ot:
        conteo_esperado[p.pieza_id] += p.cantidad

    assert conteo_plan == conteo_esperado


# ── test: ninguna barra excede su capacidad ──────────────────────────

def test_capacidad_barra(piezas_multi_ot: list[Pieza]) -> None:
    """Ninguna barra debe superar largo_barra_mm considerando kerf."""
    plan = optimizar_corte(piezas_multi_ot, LARGO_BARRA, KERF)

    for barra in plan.barras:
        largo_total = sum(c.largo_mm + KERF for c in barra.cortes)
        assert largo_total <= LARGO_BARRA, (
            f"Barra {barra.barra_id} excede capacidad: {largo_total} > {LARGO_BARRA}"
        )


# ── test: resultado >= cota inferior ─────────────────────────────────

def test_cota_inferior(piezas_multi_ot: list[Pieza]) -> None:
    """El número de barras usadas nunca puede ser menor que la cota inferior."""
    plan = optimizar_corte(piezas_multi_ot, LARGO_BARRA, KERF)

    total_largo = sum(
        (p.largo_mm + KERF) * p.cantidad for p in piezas_multi_ot
    )
    lb_esperada = math.ceil(total_largo / LARGO_BARRA)

    assert plan.cota_inferior == lb_esperada
    assert len(plan.barras) >= plan.cota_inferior


# ── test: pieza más larga que la barra se rechaza ────────────────────

def test_pieza_mas_larga_rechazada() -> None:
    """Una pieza cuyo largo + kerf supera la barra debe lanzar ValueError."""
    piezas = [
        Pieza(pieza_id="gigante", ot="OT-999", largo_mm=6500, cantidad=1),
    ]

    with pytest.raises(ValueError, match="supera el largo de barra"):
        optimizar_corte(piezas, LARGO_BARRA, KERF)


# ── test: pieza con largo no positivo se rechaza ─────────────────────

def test_pieza_largo_no_positivo_rechazada() -> None:
    """Una pieza con largo <= 0 debe lanzar ValueError."""
    piezas = [
        Pieza(pieza_id="nula", ot="OT-999", largo_mm=0, cantidad=1),
    ]

    with pytest.raises(ValueError, match="largo_mm debe ser positivo"):
        validar_piezas(piezas, LARGO_BARRA, KERF)


# ── test: pieza con cantidad no positiva se rechaza ──────────────────

def test_pieza_cantidad_no_positiva_rechazada() -> None:
    """Una pieza con cantidad <= 0 debe lanzar ValueError."""
    piezas = [
        Pieza(pieza_id="cero", ot="OT-999", largo_mm=500, cantidad=0),
    ]

    with pytest.raises(ValueError, match="cantidad debe ser positiva"):
        validar_piezas(piezas, LARGO_BARRA, KERF)


# ── test: métricas coherentes ────────────────────────────────────────

def test_metricas_coherentes(piezas_multi_ot: list[Pieza]) -> None:
    """Las métricas deben ser consistentes con el plan."""
    plan = optimizar_corte(piezas_multi_ot, LARGO_BARRA, KERF)
    metricas = calcular_metricas(plan)

    assert metricas["barras_usadas"] == len(plan.barras)
    assert metricas["desperdicio_mm"] >= 0
    assert 0 < metricas["aprovechamiento_pct"] <= 100


# ── test: OTs distintas comparten barra ──────────────────────────────

def test_ots_comparten_barra() -> None:
    """Dos OT distintas deben poder compartir una misma barra."""
    piezas = [
        Pieza(pieza_id="a", ot="OT-1", largo_mm=2000, cantidad=1),
        Pieza(pieza_id="b", ot="OT-2", largo_mm=2000, cantidad=1),
    ]

    plan = optimizar_corte(piezas, LARGO_BARRA, KERF)

    # Ambas caben en 1 sola barra (2000+3 + 2000+3 = 4006 <= 6000)
    assert len(plan.barras) == 1
    ots_en_barra = {c.ot for c in plan.barras[0].cortes}
    assert ots_en_barra == {"OT-1", "OT-2"}
