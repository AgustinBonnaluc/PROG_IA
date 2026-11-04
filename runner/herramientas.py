"""Herramientas deterministas que el agente invoca como skills."""

from __future__ import annotations

from corte import Pieza, calcular_metricas, optimizar_corte

from .repositorio import Repositorio


def planificar_corte(
    repo: Repositorio,
    materiales: list[str] | None = None,
    motivo: str = "Recálculo",
) -> list[dict]:
    """Skill ``planificar-corte``: reoptimiza y guarda el plan de cada material.

    Parameters
    ----------
    repo:
        Acceso a la base.
    materiales:
        Códigos de material a replanificar. ``None`` o vacío replanifica todos.
    motivo:
        Texto que queda registrado en el plan (por ejemplo "Ingreso OT-108").

    Returns
    -------
    list[dict]
        Por material: barras y aprovechamiento antes y después, y el estado
        del solver.
    """
    catalogo = repo.materiales()
    kerf = repo.kerf_mm()
    codigos = sorted(materiales) if materiales else sorted(catalogo)

    resumen = []
    for codigo in codigos:
        material = catalogo[codigo]
        piezas = [
            Pieza(pieza_id=str(f["id"]), ot=f["ot"], largo_mm=f["largo_mm"], cantidad=f["cantidad"])
            for f in repo.piezas_pendientes(material["id"])
        ]
        antes = repo.plan_vigente(material["id"])
        plan = optimizar_corte(piezas, material["largo_barra_mm"], kerf)
        metricas = calcular_metricas(plan)
        repo.guardar_plan(material["id"], motivo, plan, metricas, antes)

        resumen.append(
            {
                "material": codigo,
                "barras_antes": antes["barras_usadas"] if antes else None,
                "barras_despues": metricas["barras_usadas"],
                "aprovechamiento_antes": float(antes["aprovechamiento_pct"]) if antes else None,
                "aprovechamiento_despues": metricas["aprovechamiento_pct"],
                "estado_solver": plan.estado_solver,
            }
        )
    return resumen
