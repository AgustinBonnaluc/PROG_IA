"""Validación de piezas antes de la optimización."""

from __future__ import annotations

from .modelos import Pieza


def validar_piezas(
    piezas: list[Pieza],
    largo_barra_mm: float,
    kerf_mm: float,
) -> None:
    """Valida cada pieza y lanza ``ValueError`` si alguna es inválida.

    Reglas:
    - ``largo_mm`` debe ser positivo.
    - ``cantidad`` debe ser positivo.
    - ``largo_mm + kerf_mm`` no puede superar ``largo_barra_mm``
      (la pieza no entraría en ninguna barra).
    """
    for p in piezas:
        if p.largo_mm <= 0:
            raise ValueError(
                f"Pieza '{p.pieza_id}' (OT {p.ot}): largo_mm debe ser positivo, "
                f"se recibió {p.largo_mm}"
            )
        if p.cantidad <= 0:
            raise ValueError(
                f"Pieza '{p.pieza_id}' (OT {p.ot}): cantidad debe ser positiva, "
                f"se recibió {p.cantidad}"
            )
        if p.largo_mm + kerf_mm > largo_barra_mm:
            raise ValueError(
                f"Pieza '{p.pieza_id}' (OT {p.ot}): largo ({p.largo_mm} mm) + kerf "
                f"({kerf_mm} mm) = {p.largo_mm + kerf_mm} mm supera el largo de "
                f"barra ({largo_barra_mm} mm)"
            )
