"""Pruebas unitarias del optimizador y las métricas (patrón AAA).

Incluye las pruebas del Parcial 1 y las de regresión de los dos errores
encontrados en esta etapa: el redondeo del kerf y el kerf negativo.
"""

import math
from collections import Counter

import pytest

from corte.metricas import calcular_metricas
from corte.modelos import Pieza
from corte.optimizador import optimizar_corte

LARGO_BARRA = 6000.0
KERF = 3.0


@pytest.fixture
def piezas_multi_ot():
    """Piezas de varias OT que comparten material (caso realista)."""
    return [
        Pieza(pieza_id="pata", ot="OT-101", largo_mm=2000, cantidad=4),
        Pieza(pieza_id="travesano", ot="OT-101", largo_mm=1450, cantidad=6),
        Pieza(pieza_id="larguero", ot="OT-102", largo_mm=1500, cantidad=4),
        Pieza(pieza_id="pata_mesa", ot="OT-102", largo_mm=900, cantidad=4),
        Pieza(pieza_id="cabezal", ot="OT-102", largo_mm=700, cantidad=2),
    ]


def _consumo(barra, kerf):
    return sum(c.largo_mm + kerf for c in barra.cortes)


# ── comportamiento general ───────────────────────────────────────────

def test_cada_unidad_aparece_una_sola_vez(piezas_multi_ot):
    # Arrange
    esperado = Counter()
    for p in piezas_multi_ot:
        esperado[p.pieza_id] += p.cantidad

    # Act
    plan = optimizar_corte(piezas_multi_ot, LARGO_BARRA, KERF)

    # Assert
    obtenido = Counter(c.pieza_id for b in plan.barras for c in b.cortes)
    assert obtenido == esperado


def test_ninguna_barra_supera_su_largo(piezas_multi_ot):
    # Arrange / Act
    plan = optimizar_corte(piezas_multi_ot, LARGO_BARRA, KERF)

    # Assert
    assert all(_consumo(b, KERF) <= LARGO_BARRA for b in plan.barras)


def test_barras_usadas_respetan_la_cota_inferior(piezas_multi_ot):
    # Arrange
    total = sum((p.largo_mm + KERF) * p.cantidad for p in piezas_multi_ot)

    # Act
    plan = optimizar_corte(piezas_multi_ot, LARGO_BARRA, KERF)

    # Assert
    assert plan.cota_inferior == math.ceil(total / LARGO_BARRA)
    assert len(plan.barras) >= plan.cota_inferior


def test_ots_distintas_comparten_barra():
    # Arrange
    piezas = [
        Pieza(pieza_id="a", ot="OT-1", largo_mm=2000, cantidad=1),
        Pieza(pieza_id="b", ot="OT-2", largo_mm=2000, cantidad=1),
    ]

    # Act
    plan = optimizar_corte(piezas, LARGO_BARRA, KERF)

    # Assert
    assert len(plan.barras) == 1
    assert {c.ot for c in plan.barras[0].cortes} == {"OT-1", "OT-2"}


def test_lista_vacia_devuelve_plan_vacio():
    # Arrange
    piezas = []

    # Act
    plan = optimizar_corte(piezas, LARGO_BARRA, KERF)

    # Assert
    assert plan.barras == []
    assert calcular_metricas(plan)["barras_usadas"] == 0


def test_dos_piezas_que_llenan_la_barra_exacta_van_juntas():
    # Arrange: (2997 + 3) * 2 = 6000
    piezas = [Pieza(pieza_id="a", ot="OT-1", largo_mm=2997, cantidad=2)]

    # Act
    plan = optimizar_corte(piezas, LARGO_BARRA, KERF)

    # Assert
    assert len(plan.barras) == 1


def test_metricas_coherentes_con_el_plan(piezas_multi_ot):
    # Arrange
    plan = optimizar_corte(piezas_multi_ot, LARGO_BARRA, KERF)

    # Act
    metricas = calcular_metricas(plan)

    # Assert
    assert metricas["barras_usadas"] == len(plan.barras)
    assert metricas["desperdicio_mm"] >= 0
    assert 0 < metricas["aprovechamiento_pct"] <= 100


# ── regresiones ──────────────────────────────────────────────────────

def test_kerf_fraccionario_no_promete_material_inexistente():
    # Arrange: 2 × (3000 + 0,5) = 6001 mm, no entran en una barra
    kerf = 0.5
    piezas = [Pieza(pieza_id="a", ot="OT-1", largo_mm=3000, cantidad=2)]

    # Act
    plan = optimizar_corte(piezas, LARGO_BARRA, kerf)

    # Assert
    assert len(plan.barras) == 2
    assert all(_consumo(b, kerf) <= LARGO_BARRA for b in plan.barras)


def test_caso_real_de_planta_alcanza_el_optimo_demostrado():
    # Arrange: el caño con las OT del seed más dos pedidos del agente
    datos = [("OT-101", 2000, 4), ("OT-101", 1450, 6), ("OT-102", 1500, 4),
             ("OT-102", 900, 4), ("OT-102", 700, 2), ("OT-103", 3100, 2),
             ("OT-103", 2800, 3), ("OT-106", 800, 2), ("OT-108", 900, 4),
             ("OT-108", 700, 2), ("OT-109", 1500, 3)]
    piezas = [Pieza(str(i), ot, largo, cant) for i, (ot, largo, cant) in enumerate(datos)]

    # Act
    plan = optimizar_corte(piezas, LARGO_BARRA, KERF)

    # Assert
    assert plan.estado_solver == "OPTIMAL"
    assert len(plan.barras) == plan.cota_inferior == 9


def test_kerf_negativo_se_rechaza_antes_de_optimizar():
    # Arrange
    piezas = [Pieza(pieza_id="a", ot="OT-1", largo_mm=2500, cantidad=3)]

    # Act / Assert
    with pytest.raises(ValueError, match="kerf_mm"):
        optimizar_corte(piezas, LARGO_BARRA, -1000)
