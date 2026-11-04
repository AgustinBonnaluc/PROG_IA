"""Modelos de datos para el planificador de corte unidimensional."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Pieza:
    """Una pieza a cortar, tal como viene de la orden de trabajo."""

    pieza_id: str
    ot: str
    largo_mm: float
    cantidad: int


@dataclass
class Corte:
    """Un corte individual asignado a una barra."""

    pieza_id: str
    ot: str
    largo_mm: float


@dataclass
class Barra:
    """Una barra física con la lista de cortes asignados."""

    barra_id: int
    cortes: list[Corte] = field(default_factory=list)


@dataclass
class PlanCorte:
    """Resultado completo del optimizador."""

    barras: list[Barra]
    largo_barra_mm: float
    kerf_mm: float
    cota_inferior: int
    estado_solver: str
