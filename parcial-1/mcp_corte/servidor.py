"""Servidor MCP para optimización de corte unidimensional.

Expone la herramienta ``optimizar_corte`` vía FastMCP.
**No se conecta a ninguna base de datos.**

Ejecución::

    python -m mcp_corte.servidor
"""

from __future__ import annotations

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))


from mcp.server.fastmcp import FastMCP

from corte.modelos import Pieza
from corte.validacion import validar_piezas
from corte.optimizador import optimizar_corte
from corte.metricas import calcular_metricas

mcp = FastMCP("corte-ot-metalurgica")


@mcp.tool()
def optimizar_corte_tool(
    piezas: list[dict],
    largo_barra_mm: float,
    kerf_mm: float,
) -> dict:
    """Optimiza el corte unidimensional de barras.

    Recibe una lista de piezas con sus dimensiones y devuelve un plan
    de corte óptimo junto con métricas de aprovechamiento.

    Parameters
    ----------
    piezas:
        Lista de diccionarios con claves ``pieza_id``, ``ot``,
        ``largo_mm`` y ``cantidad``.
    largo_barra_mm:
        Largo nominal de la barra en milímetros.
    kerf_mm:
        Ancho de corte de la sierra en milímetros.

    Returns
    -------
    dict
        Diccionario con ``barras`` (lista de barras con sus cortes),
        ``metricas`` y metadatos del solver.
    """
    # Convertir dicts a Pieza
    lista_piezas = [
        Pieza(
            pieza_id=p["pieza_id"],
            ot=p["ot"],
            largo_mm=p["largo_mm"],
            cantidad=p["cantidad"],
        )
        for p in piezas
    ]

    # Validar, optimizar, calcular métricas
    plan = optimizar_corte(lista_piezas, largo_barra_mm, kerf_mm)
    metricas = calcular_metricas(plan)

    # Serializar resultado
    barras_out = []
    for barra in plan.barras:
        cortes_out = [
            {"pieza_id": c.pieza_id, "ot": c.ot, "largo_mm": c.largo_mm}
            for c in barra.cortes
        ]
        barras_out.append({"barra_id": barra.barra_id, "cortes": cortes_out})

    return {
        "barras": barras_out,
        "metricas": metricas,
        "cota_inferior": plan.cota_inferior,
        "estado_solver": plan.estado_solver,
    }


if __name__ == "__main__":
    mcp.run()
