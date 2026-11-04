"""Normalización y validación de la salida del LLM.

El modelo solo *extrae* datos. Todo lo que tiene que ser exacto se decide acá,
en Python: conversión de unidades, materiales válidos, límites, fecha de
entrega y qué datos faltan. Así un error o una inyección en el mensaje no
llega nunca a la base.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from corte.validacion import MAX_CANTIDAD

A_MM = {"mm": 1, "cm": 10, "m": 1000}
TIPOS = {"pedido", "pedido_incompleto", "no_es_pedido"}
MAX_CLIENTE = 120
MAX_DESCRIPCION = 60

DIAS_SEMANA = {
    "lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3,
    "viernes": 4, "sabado": 5, "domingo": 6,
}
_FECHA_NUMERICA = re.compile(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2}|\d{4}))?\b")


class ErrorRespuestaLLM(ValueError):
    """La salida del modelo no tiene la estructura esperada."""


@dataclass(frozen=True)
class PiezaPedido:
    """Una pieza ya validada y expresada en milímetros."""

    descripcion: str
    material: str
    largo_mm: int
    cantidad: int


@dataclass
class Interpretacion:
    """Resultado de interpretar un mensaje, listo para decidir qué hacer."""

    tipo: str
    cliente: str | None = None
    fecha_entrega: date | None = None
    piezas: list[PiezaPedido] = field(default_factory=list)
    faltantes: list[str] = field(default_factory=list)
    descartadas: list[str] = field(default_factory=list)

    @property
    def completa(self) -> bool:
        """``True`` si el pedido puede registrarse tal como está."""
        return self.tipo == "pedido"


# ── utilidades ───────────────────────────────────────────────────────

def _sin_acentos(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )


def limpiar_texto(valor: Any, max_largo: int) -> str | None:
    """Devuelve el texto sin caracteres de control ni espacios repetidos.

    Devuelve ``None`` si queda vacío o si no es un string. Si supera
    ``max_largo`` se recorta.
    """
    if not isinstance(valor, str):
        return None
    sin_control = "".join(" " if unicodedata.category(c).startswith("C") else c for c in valor)
    limpio = " ".join(sin_control.split())
    if not limpio or limpio.lower() in {"null", "none", "desconocido"}:
        return None
    return limpio[:max_largo]


def resolver_fecha(texto: str | None, hoy: date) -> date | None:
    """Convierte la fecha tal como la escribió el cliente en una ``date``.

    Acepta "hoy", "mañana", un día de la semana (la próxima ocurrencia,
    nunca el mismo día) y fechas ``dd/mm`` o ``dd/mm/aaaa``. Si ``dd/mm`` ya
    pasó este año, se toma el año siguiente. Devuelve ``None`` si no puede
    resolverla: en ese caso se le pregunta al cliente.
    """
    if not texto:
        return None
    normal = _sin_acentos(texto.lower())

    numerica = _FECHA_NUMERICA.search(normal)
    if numerica:
        dia, mes, anio = numerica.groups()
        try:
            if anio:
                anio_int = int(anio) + (2000 if len(anio) == 2 else 0)
                return date(anio_int, int(mes), int(dia))
            candidata = date(hoy.year, int(mes), int(dia))
            return candidata if candidata >= hoy else date(hoy.year + 1, int(mes), int(dia))
        except ValueError:
            return None

    palabras = set(re.findall(r"[a-z]+", normal))
    if "hoy" in palabras:
        return hoy
    if "manana" in palabras:
        return hoy + timedelta(days=1)
    for nombre, numero in DIAS_SEMANA.items():
        if nombre in palabras:
            dias = (numero - hoy.weekday()) % 7 or 7
            return hoy + timedelta(days=dias)
    return None


def _a_entero(valor: Any) -> int | None:
    """Acepta enteros y floats sin parte decimal (4.0); el resto es ``None``."""
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return valor
    if isinstance(valor, float) and math.isfinite(valor) and valor.is_integer():
        return int(valor)
    return None


# ── normalización ────────────────────────────────────────────────────

def _validar_pieza(
    cruda: Any, materiales: dict[str, int], kerf_mm: float
) -> tuple[PiezaPedido | None, str | None]:
    """Devuelve ``(pieza, None)`` si es válida o ``(None, motivo)`` si no."""
    if not isinstance(cruda, dict):
        return None, "pieza con formato inválido"
    descripcion = limpiar_texto(cruda.get("descripcion"), MAX_DESCRIPCION) or "pieza"

    material = cruda.get("material")
    if material not in materiales:
        return None, f"'{descripcion}': material no identificado"

    valor, unidad = cruda.get("largo_valor"), cruda.get("largo_unidad")
    if (
        unidad not in A_MM
        or isinstance(valor, bool)
        or not isinstance(valor, (int, float))
        or not math.isfinite(valor)
        or valor <= 0
    ):
        return None, f"'{descripcion}': falta la medida"
    largo_mm = round(valor * A_MM[unidad])

    cantidad = _a_entero(cruda.get("cantidad"))
    if cantidad is None or cantidad <= 0:
        return None, f"'{descripcion}': falta la cantidad"
    if cantidad > MAX_CANTIDAD:
        return None, f"'{descripcion}': cantidad {cantidad} supera el máximo de {MAX_CANTIDAD}"

    largo_barra = materiales[material]
    if largo_mm + kerf_mm > largo_barra:
        return None, f"'{descripcion}': {largo_mm} mm no entra en una barra de {largo_barra} mm"

    return PiezaPedido(descripcion, material, largo_mm, cantidad), None


def normalizar(
    respuesta: str | dict,
    materiales: dict[str, int],
    kerf_mm: float,
    hoy: date,
) -> Interpretacion:
    """Valida la salida del LLM y calcula qué falta para registrar el pedido.

    Parameters
    ----------
    respuesta:
        JSON devuelto por la skill ``interpretar-pedido`` (texto o dict).
    materiales:
        Catálogo de la base: ``{codigo: largo_barra_mm}``.
    kerf_mm:
        Ancho de corte, para rechazar piezas que no entran en una barra.
    hoy:
        Fecha de referencia para resolver "viernes", "mañana", etc.

    Raises
    ------
    ErrorRespuestaLLM
        Si la respuesta no es un JSON con la estructura mínima esperada.
    """
    if isinstance(respuesta, str):
        try:
            respuesta = json.loads(respuesta)
        except json.JSONDecodeError as e:
            raise ErrorRespuestaLLM(f"El modelo no devolvió JSON válido: {e}") from e
    if not isinstance(respuesta, dict) or respuesta.get("tipo") not in TIPOS:
        raise ErrorRespuestaLLM("La respuesta del modelo no tiene un 'tipo' válido")
    piezas_crudas = respuesta.get("piezas") or []
    if not isinstance(piezas_crudas, list):
        raise ErrorRespuestaLLM("'piezas' debe ser una lista")

    piezas, descartadas = [], []
    for cruda in piezas_crudas:
        pieza, motivo = _validar_pieza(cruda, materiales, kerf_mm)
        if pieza:
            piezas.append(pieza)
        else:
            descartadas.append(motivo)

    # Sin piezas válidas, se respeta que no es un pedido (descarta piezas de relleno).
    if respuesta["tipo"] == "no_es_pedido" and not piezas:
        return Interpretacion(tipo="no_es_pedido")

    cliente = limpiar_texto(respuesta.get("cliente"), MAX_CLIENTE)
    fecha = resolver_fecha(limpiar_texto(respuesta.get("fecha_entrega_texto"), 40), hoy)

    faltantes = []
    if not cliente:
        faltantes.append("nombre del cliente o empresa")
    if not fecha:
        faltantes.append("fecha de entrega")
    if not piezas and not descartadas:
        faltantes.append("piezas con medida, material y cantidad")
    elif respuesta["tipo"] == "pedido_incompleto" and not descartadas:
        # Python puede ser más estricto que el modelo, nunca más permisivo.
        faltantes.append("medida, material o cantidad de alguna pieza")
    faltantes.extend(descartadas)

    return Interpretacion(
        tipo="pedido_incompleto" if faltantes else "pedido",
        cliente=cliente,
        fecha_entrega=fecha,
        piezas=piezas,
        faltantes=faltantes,
        descartadas=descartadas,
    )
