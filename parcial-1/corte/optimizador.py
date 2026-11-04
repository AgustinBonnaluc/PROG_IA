"""Optimizador de corte unidimensional con OR-Tools CP-SAT.

Consolida las piezas de **todas** las OT recibidas en una misma bolsa
(dos OT distintas pueden compartir barra) y minimiza la cantidad de
barras usadas.
"""

from __future__ import annotations

import math
from ortools.sat.python import cp_model

from .modelos import Barra, Corte, Pieza, PlanCorte
from .validacion import validar_piezas


# ── helpers ──────────────────────────────────────────────────────────

def _expandir_piezas(piezas: list[Pieza]) -> list[Corte]:
    """Expande cada Pieza según su cantidad en unidades individuales."""
    unidades: list[Corte] = []
    for p in piezas:
        for _ in range(p.cantidad):
            unidades.append(Corte(pieza_id=p.pieza_id, ot=p.ot, largo_mm=p.largo_mm))
    return unidades


def _cota_inferior(unidades: list[Corte], largo_barra_mm: float, kerf_mm: float) -> int:
    """Cota inferior trivial: ceil(Σ(largo + kerf) / largo_barra)."""
    total = sum(u.largo_mm + kerf_mm for u in unidades)
    return math.ceil(total / largo_barra_mm)


def _first_fit_decreasing(
    unidades: list[Corte], largo_barra_mm: float, kerf_mm: float
) -> int:
    """Heurística FFD para obtener una cota superior razonable."""
    ordenadas = sorted(unidades, key=lambda u: u.largo_mm, reverse=True)
    remanentes: list[float] = []
    for u in ordenadas:
        necesita = u.largo_mm + kerf_mm
        colocada = False
        for i, rem in enumerate(remanentes):
            if rem >= necesita:
                remanentes[i] -= necesita
                colocada = True
                break
        if not colocada:
            remanentes.append(largo_barra_mm - necesita)
    return len(remanentes)


# ── función pública ──────────────────────────────────────────────────

_SOLVER_TIMEOUT_S = 10.0


def optimizar_corte(
    piezas: list[Pieza],
    largo_barra_mm: float,
    kerf_mm: float = 0.0,
) -> PlanCorte:
    """Optimiza el corte unidimensional usando CP-SAT.

    Parameters
    ----------
    piezas:
        Lista de piezas (ya consolidadas por material por el caller).
    largo_barra_mm:
        Largo nominal de la barra en milímetros.
    kerf_mm:
        Ancho de corte de la sierra, sumado al largo de cada pieza.

    Returns
    -------
    PlanCorte
        Plan con barras asignadas, cota inferior y estado del solver.

    Raises
    ------
    ValueError
        Si alguna pieza falla la validación.
    RuntimeError
        Si el solver no encuentra solución factible.
    """
    # 1. Validar
    validar_piezas(piezas, largo_barra_mm, kerf_mm)

    # 2. Expandir
    unidades = _expandir_piezas(piezas)
    n = len(unidades)

    if n == 0:
        return PlanCorte(
            barras=[],
            largo_barra_mm=largo_barra_mm,
            kerf_mm=kerf_mm,
            cota_inferior=0,
            estado_solver="OPTIMAL",
        )

    lb = _cota_inferior(unidades, largo_barra_mm, kerf_mm)
    ub = _first_fit_decreasing(unidades, largo_barra_mm, kerf_mm)
    m = ub  # número máximo de barras a considerar

    # 3. Modelo CP-SAT
    model = cp_model.CpModel()

    # x[i][j] = 1 si la unidad i va en la barra j
    x: list[list[cp_model.IntVar]] = []
    for i in range(n):
        fila = []
        for j in range(m):
            fila.append(model.new_bool_var(f"x_{i}_{j}"))
        x.append(fila)

    # y[j] = 1 si la barra j se usa
    y: list[cp_model.IntVar] = []
    for j in range(m):
        y.append(model.new_bool_var(f"y_{j}"))

    # Cada unidad asignada a exactamente 1 barra
    for i in range(n):
        model.add_exactly_one(x[i][j] for j in range(m))

    # Capacidad de cada barra (largo_pieza + kerf para cada pieza)
    largos = [int(round(u.largo_mm + kerf_mm)) for u in unidades]
    cap = int(round(largo_barra_mm))

    for j in range(m):
        model.add(
            sum(largos[i] * x[i][j] for i in range(n)) <= cap * y[j]
        )

    # Romper simetría: barras usadas en orden
    for j in range(m - 1):
        model.add(y[j] >= y[j + 1])

    # Objetivo: minimizar barras usadas
    model.minimize(sum(y[j] for j in range(m)))

    # 4. Resolver
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = _SOLVER_TIMEOUT_S

    status = solver.solve(model)
    status_name = solver.status_name(status)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError(
            f"El solver no encontró solución factible (estado: {status_name})"
        )

    # 5. Extraer solución
    barras_resultado: list[Barra] = []
    barra_id = 1
    for j in range(m):
        if solver.value(y[j]) == 1:
            cortes_barra: list[Corte] = []
            for i in range(n):
                if solver.value(x[i][j]) == 1:
                    cortes_barra.append(unidades[i])
            barras_resultado.append(Barra(barra_id=barra_id, cortes=cortes_barra))
            barra_id += 1

    return PlanCorte(
        barras=barras_resultado,
        largo_barra_mm=largo_barra_mm,
        kerf_mm=kerf_mm,
        cota_inferior=lb,
        estado_solver=status_name,
    )
