"""Pruebas unitarias de runner.pedido: lo que Python decide sobre la salida del LLM."""

from datetime import date

import pytest

from runner.pedido import ErrorRespuestaLLM, limpiar_texto, normalizar, resolver_fecha

HOY = date(2026, 11, 2)  # lunes
MATERIALES = {"CE-40x40x1.6": 6000, "ANG-1.1/4x1/8": 6000, "PLA-2x3/16": 6000}
KERF = 3.0


def _respuesta(piezas, tipo="pedido", cliente="Taller Ferraro", fecha="viernes"):
    return {"tipo": tipo, "cliente": cliente, "fecha_entrega_texto": fecha, "piezas": piezas}


def _pieza(valor=90, unidad="cm", cantidad=4, material="CE-40x40x1.6", descripcion="pata"):
    return {"descripcion": descripcion, "material": material, "largo_valor": valor,
            "largo_unidad": unidad, "cantidad": cantidad}


# ── normalizar: casos típicos ────────────────────────────────────────

@pytest.mark.parametrize("valor, unidad, esperado", [(900, "mm", 900), (90, "cm", 900),
                                                      (1.2, "m", 1200), (0.25, "m", 250)])
def test_convierte_unidades_a_milimetros(valor, unidad, esperado):
    # Arrange
    respuesta = _respuesta([_pieza(valor=valor, unidad=unidad)])

    # Act
    interp = normalizar(respuesta, MATERIALES, KERF, HOY)

    # Assert
    assert interp.piezas[0].largo_mm == esperado


def test_pedido_completo_queda_listo_para_registrar():
    # Arrange
    respuesta = _respuesta([_pieza(), _pieza(valor=70, cantidad=2, descripcion="cabezal")])

    # Act
    interp = normalizar(respuesta, MATERIALES, KERF, HOY)

    # Assert
    assert interp.completa
    assert interp.cliente == "Taller Ferraro"
    assert interp.fecha_entrega == date(2026, 11, 6)
    assert [(p.largo_mm, p.cantidad) for p in interp.piezas] == [(900, 4), (700, 2)]
    assert interp.faltantes == []


def test_acepta_json_como_texto():
    # Arrange
    texto = '{"tipo": "pedido", "cliente": "X", "fecha_entrega_texto": "15/11", "piezas": []}'

    # Act
    interp = normalizar(texto, MATERIALES, KERF, HOY)

    # Assert
    assert interp.tipo == "pedido_incompleto"


# ── normalizar: Python decide qué falta ──────────────────────────────

def test_sin_cliente_ni_fecha_queda_incompleto():
    # Arrange
    respuesta = _respuesta([_pieza()], cliente=None, fecha=None)

    # Act
    interp = normalizar(respuesta, MATERIALES, KERF, HOY)

    # Assert
    assert not interp.completa
    assert "nombre del cliente o empresa" in interp.faltantes
    assert "fecha de entrega" in interp.faltantes


def test_si_el_modelo_dice_incompleto_python_no_lo_registra():
    # Arrange: el modelo omitió una pieza sin medida y avisó que falta algo
    respuesta = _respuesta([_pieza()], tipo="pedido_incompleto")

    # Act
    interp = normalizar(respuesta, MATERIALES, KERF, HOY)

    # Assert
    assert not interp.completa


def test_si_el_modelo_dice_completo_pero_falta_la_fecha_python_lo_corrige():
    # Arrange
    respuesta = _respuesta([_pieza()], tipo="pedido", fecha="cuando puedan")

    # Act
    interp = normalizar(respuesta, MATERIALES, KERF, HOY)

    # Assert
    assert interp.tipo == "pedido_incompleto"
    assert "fecha de entrega" in interp.faltantes


def test_no_es_pedido_ignora_piezas_de_relleno():
    # Arrange: pieza de relleno con largo 0
    respuesta = _respuesta([_pieza(valor=0, cantidad=0, material="DESCONOCIDO")],
                           tipo="no_es_pedido", cliente=None, fecha=None)

    # Act
    interp = normalizar(respuesta, MATERIALES, KERF, HOY)

    # Assert
    assert interp.tipo == "no_es_pedido"
    assert interp.piezas == []


# ── normalizar: piezas inválidas (casos borde) ───────────────────────

@pytest.mark.parametrize("pieza, motivo", [
    (_pieza(material="DESCONOCIDO"), "material no identificado"),
    (_pieza(material="TITANIO"), "material no identificado"),
    (_pieza(valor=0), "falta la medida"),
    (_pieza(valor=-90), "falta la medida"),
    (_pieza(unidad="pulgadas"), "falta la medida"),
    (_pieza(cantidad=0), "falta la cantidad"),
    (_pieza(cantidad=2.5), "falta la cantidad"),
    (_pieza(cantidad=999999), "supera el máximo"),
    (_pieza(valor=7, unidad="m"), "no entra en una barra"),
])
def test_descarta_piezas_invalidas_y_lo_informa(pieza, motivo):
    # Arrange
    respuesta = _respuesta([pieza])

    # Act
    interp = normalizar(respuesta, MATERIALES, KERF, HOY)

    # Assert
    assert interp.piezas == []
    assert not interp.completa
    assert any(motivo in f for f in interp.faltantes)


def test_cantidad_float_entera_se_acepta():
    # Arrange
    respuesta = _respuesta([_pieza(cantidad=4.0)])

    # Act
    interp = normalizar(respuesta, MATERIALES, KERF, HOY)

    # Assert
    assert interp.piezas[0].cantidad == 4


# ── normalizar: excepciones ──────────────────────────────────────────

@pytest.mark.parametrize("respuesta", ["no es json", "[]", '{"tipo": "otro"}', {"piezas": []},
                                       {"tipo": "pedido", "piezas": "muchas"}])
def test_rechaza_respuesta_con_estructura_invalida(respuesta):
    # Arrange: la respuesta viene del parámetro

    # Act / Assert
    with pytest.raises(ErrorRespuestaLLM):
        normalizar(respuesta, MATERIALES, KERF, HOY)


# ── resolver_fecha ───────────────────────────────────────────────────

@pytest.mark.parametrize("texto, esperado", [
    ("viernes", date(2026, 11, 6)),
    ("para el Miércoles", date(2026, 11, 4)),
    ("el lunes", date(2026, 11, 9)),          # hoy es lunes: el próximo
    ("hoy", HOY),
    ("mañana", date(2026, 11, 3)),
    ("15/11", date(2026, 11, 15)),
    ("10/01", date(2027, 1, 10)),             # ya pasó este año
    ("20-12-2026", date(2026, 12, 20)),
    ("1/2/27", date(2027, 2, 1)),
])
def test_resuelve_fechas_habituales(texto, esperado):
    # Arrange: el texto y la fecha esperada vienen del parámetro

    # Act
    fecha = resolver_fecha(texto, HOY)

    # Assert
    assert fecha == esperado


@pytest.mark.parametrize("texto", [None, "", "cuando puedan", "31/02", "pronto"])
def test_devuelve_none_si_la_fecha_no_se_puede_resolver(texto):
    # Arrange: el texto viene del parámetro

    # Act
    fecha = resolver_fecha(texto, HOY)

    # Assert
    assert fecha is None


# ── limpiar_texto ────────────────────────────────────────────────────

def test_limpia_caracteres_de_control_y_espacios():
    # Arrange
    valor = "  Taller\x00 Ferraro\n\t SRL  "

    # Act
    limpio = limpiar_texto(valor, 120)

    # Assert
    assert limpio == "Taller Ferraro SRL"


@pytest.mark.parametrize("valor", [None, 42, "", "   ", "null", "Desconocido"])
def test_valores_vacios_o_no_texto_devuelven_none(valor):
    # Arrange: el valor viene del parámetro

    # Act
    limpio = limpiar_texto(valor, 120)

    # Assert
    assert limpio is None


def test_recorta_textos_demasiado_largos():
    # Arrange
    valor = "A" * 500

    # Act
    limpio = limpiar_texto(valor, 120)

    # Assert
    assert len(limpio) == 120
