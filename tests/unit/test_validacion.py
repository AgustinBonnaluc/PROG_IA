"""Pruebas unitarias de corte.validacion (patrón AAA)."""

import math

import pytest

from corte.modelos import Pieza
from corte.validacion import MAX_CANTIDAD, validar_parametros, validar_piezas

LARGO_BARRA = 6000.0
KERF = 3.0


def _pieza(largo=1000, cantidad=1):
    return Pieza(pieza_id="p", ot="OT-1", largo_mm=largo, cantidad=cantidad)


# ── casos típicos y límites ──────────────────────────────────────────

def test_acepta_pieza_valida():
    # Arrange
    piezas = [_pieza(1500, 4)]

    # Act
    resultado = validar_piezas(piezas, LARGO_BARRA, KERF)

    # Assert
    assert resultado is None


def test_acepta_pieza_que_ocupa_la_barra_exacta():
    # Arrange: 5997 + 3 de kerf = 6000, justo el largo de la barra
    piezas = [_pieza(5997)]

    # Act
    resultado = validar_piezas(piezas, LARGO_BARRA, KERF)

    # Assert
    assert resultado is None


def test_acepta_cantidad_igual_al_maximo():
    # Arrange
    piezas = [_pieza(cantidad=MAX_CANTIDAD)]

    # Act
    resultado = validar_piezas(piezas, LARGO_BARRA, KERF)

    # Assert
    assert resultado is None


def test_acepta_kerf_cero():
    # Arrange
    kerf = 0.0

    # Act
    resultado = validar_parametros(LARGO_BARRA, kerf)

    # Assert
    assert resultado is None


# ── excepciones: parámetros de planta ────────────────────────────────

@pytest.mark.parametrize("kerf", [-1, -1000, math.nan, math.inf])
def test_rechaza_kerf_negativo_o_no_finito(kerf):
    # Arrange
    piezas = [_pieza()]

    # Act / Assert
    with pytest.raises(ValueError, match="kerf_mm"):
        validar_piezas(piezas, LARGO_BARRA, kerf)


@pytest.mark.parametrize("largo_barra", [0, -6000, math.nan])
def test_rechaza_largo_de_barra_invalido(largo_barra):
    # Arrange
    piezas = [_pieza()]

    # Act / Assert
    with pytest.raises(ValueError, match="largo_barra_mm"):
        validar_piezas(piezas, largo_barra, KERF)


# ── excepciones: piezas ──────────────────────────────────────────────

@pytest.mark.parametrize("largo", [0, -5, math.nan, math.inf, "1000"])
def test_rechaza_largo_no_positivo_o_no_numerico(largo):
    # Arrange
    piezas = [_pieza(largo=largo)]

    # Act / Assert
    with pytest.raises(ValueError, match="largo_mm debe ser positivo"):
        validar_piezas(piezas, LARGO_BARRA, KERF)


def test_rechaza_cantidad_cero():
    # Arrange
    piezas = [_pieza(cantidad=0)]

    # Act / Assert
    with pytest.raises(ValueError, match="cantidad debe ser positiva"):
        validar_piezas(piezas, LARGO_BARRA, KERF)


@pytest.mark.parametrize("cantidad", [1.5, True, "4"])
def test_rechaza_cantidad_no_entera(cantidad):
    # Arrange
    piezas = [_pieza(cantidad=cantidad)]

    # Act / Assert
    with pytest.raises(ValueError, match="cantidad debe ser un entero"):
        validar_piezas(piezas, LARGO_BARRA, KERF)


def test_rechaza_cantidad_mayor_al_maximo():
    # Arrange
    piezas = [_pieza(cantidad=10**9)]

    # Act / Assert
    with pytest.raises(ValueError, match="supera el máximo permitido"):
        validar_piezas(piezas, LARGO_BARRA, KERF)


def test_rechaza_pieza_que_no_entra_por_el_kerf():
    # Arrange: 5998 + 3 = 6001 > 6000
    piezas = [_pieza(5998)]

    # Act / Assert
    with pytest.raises(ValueError, match="supera el largo de barra"):
        validar_piezas(piezas, LARGO_BARRA, KERF)
