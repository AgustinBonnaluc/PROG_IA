"""Validación de piezas y parámetros antes de la optimización."""

from __future__ import annotations

import math

from .modelos import Pieza

MAX_CANTIDAD = 500
"""Tope de unidades por pieza: cada unidad se expande en variables del solver."""


def _es_numero_finito(valor: object) -> bool:
    """Indica si ``valor`` es un int o float finito (``bool`` no cuenta)."""
    return (
        isinstance(valor, (int, float))
        and not isinstance(valor, bool)
        and math.isfinite(valor)
    )


def validar_parametros(largo_barra_mm: float, kerf_mm: float) -> None:
    """Valida los parámetros de planta y lanza ``ValueError`` si son inválidos.

    Reglas:
    - ``largo_barra_mm`` debe ser un número finito y positivo.
    - ``kerf_mm`` debe ser un número finito y no negativo. Un kerf negativo
      haría que en una barra "entren" más piezas de las que caben de verdad.
    """
    if not _es_numero_finito(largo_barra_mm) or largo_barra_mm <= 0:
        raise ValueError(
            f"largo_barra_mm debe ser un número positivo, se recibió {largo_barra_mm!r}"
        )
    if not _es_numero_finito(kerf_mm) or kerf_mm < 0:
        raise ValueError(
            f"kerf_mm no puede ser negativo ni infinito, se recibió {kerf_mm!r}"
        )


def validar_piezas(
    piezas: list[Pieza],
    largo_barra_mm: float,
    kerf_mm: float,
) -> None:
    """Valida los parámetros y cada pieza; lanza ``ValueError`` ante el primer error.

    Reglas por pieza:
    - ``largo_mm`` debe ser un número finito y positivo.
    - ``cantidad`` debe ser un entero entre 1 y ``MAX_CANTIDAD``.
    - ``largo_mm + kerf_mm`` no puede superar ``largo_barra_mm``
      (la pieza no entraría en ninguna barra).
    """
    validar_parametros(largo_barra_mm, kerf_mm)

    for p in piezas:
        if not _es_numero_finito(p.largo_mm) or p.largo_mm <= 0:
            raise ValueError(
                f"Pieza '{p.pieza_id}' (OT {p.ot}): largo_mm debe ser positivo, "
                f"se recibió {p.largo_mm!r}"
            )
        if not isinstance(p.cantidad, int) or isinstance(p.cantidad, bool):
            raise ValueError(
                f"Pieza '{p.pieza_id}' (OT {p.ot}): cantidad debe ser un entero, "
                f"se recibió {p.cantidad!r}"
            )
        if p.cantidad <= 0:
            raise ValueError(
                f"Pieza '{p.pieza_id}' (OT {p.ot}): cantidad debe ser positiva, "
                f"se recibió {p.cantidad}"
            )
        if p.cantidad > MAX_CANTIDAD:
            raise ValueError(
                f"Pieza '{p.pieza_id}' (OT {p.ot}): cantidad {p.cantidad} supera el "
                f"máximo permitido ({MAX_CANTIDAD})"
            )
        if p.largo_mm + kerf_mm > largo_barra_mm:
            raise ValueError(
                f"Pieza '{p.pieza_id}' (OT {p.ot}): largo ({p.largo_mm} mm) + kerf "
                f"({kerf_mm} mm) = {p.largo_mm + kerf_mm} mm supera el largo de "
                f"barra ({largo_barra_mm} mm)"
            )
