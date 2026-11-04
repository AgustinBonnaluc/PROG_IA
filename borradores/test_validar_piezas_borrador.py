import pytest
from corte.validacion import validar_piezas
from corte.modelos import Pieza

# Arrange
def test_rechaza_largo_negativo():
    piezas = [Pieza("P1", "OT1", -10.0, 1)]
    largo_barra_mm = 3000.0
    kerf_mm = 0.5

    # Act & Assert
    with pytest.raises(ValueError) as e:
        validar_piezas(piezas, largo_barra_mm, kerf_mm)
    assert str(e.value) == "Pieza 'P1' (OT OT1): largo_mm debe ser positivo, se recibió -10.0"

# Arrange
def test_rechaza_cantidad_negativa():
    piezas = [Pieza("P1", "OT1", 10.0, -1)]
    largo_barra_mm = 3000.0
    kerf_mm = 0.5

    # Act & Assert
    with pytest.raises(ValueError) as e:
        validar_piezas(piezas, largo_barra_mm, kerf_mm)
    assert str(e.value) == "Pieza 'P1' (OT OT1): cantidad debe ser positiva, se recibió -1"

# Arrange
def test_rechaza_cantidad_maxima():
    piezas = [Pieza("P1", "OT1", 10.0, 501)]
    largo_barra_mm = 3000.0
    kerf_mm = 0.5

    # Act & Assert
    with pytest.raises(ValueError) as e:
        validar_piezas(piezas, largo_barra_mm, kerf_mm)
    assert str(e.value) == "Pieza 'P1' (OT OT1): cantidad 501 supera el máximo permitido (500)"

# Arrange
def test_rechaza_largo_mas_kerf():
    piezas = [Pieza("P1", "OT1", 3001.5, 1)]
    largo_barra_mm = 3000.0
    kerf_mm = 0.5

    # Act & Assert
    with pytest.raises(ValueError) as e:
        validar_piezas(piezas, largo_barra_mm, kerf_mm)
    assert str(e.value) == "Pieza 'P1' (OT OT1): largo (3001.5 mm) + kerf (0.5 mm) = 3002.0 mm supera el largo de barra (3000.0 mm)"

# Arrange
def test_valida_pieza():
    piezas = [Pieza("P1", "OT1", 10.0, 1)]
    largo_barra_mm = 3000.0
    kerf_mm = 0.5

    # Act
    try:
        validar_piezas(piezas, largo_barra_mm, kerf_mm)
    except ValueError as e:
        pytest.fail(f"validar_piezas() raised an unexpected ValueError: {e}")

# Arrange
def test_valida_vacio():
    piezas = []
    largo_barra_mm = 3000.0
    kerf_mm = 0.5

    # Act
    try:
        validar_piezas(piezas, largo_barra_mm, kerf_mm)
    except ValueError as e:
        pytest.fail(f"validar_piezas() raised an unexpected ValueError: {e}")
