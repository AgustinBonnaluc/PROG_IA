"""Pruebas integradas de la skill generar-pruebas (LLM falso + archivos reales)."""

import pytest

from conftest import HOY, LLMFalso
from runner.agente import Agente

CODIGO_GENERADO = '''Acá tenés los tests:

```python
from corte.validacion import validar_piezas


def test_algo():
    # Arrange
    x = 1
    # Act
    y = x + 1
    # Assert
    assert y == 2
```
'''


def _agente(config, *respuestas):
    llm = LLMFalso(*respuestas)
    return Agente(config, llm, repo=None, hoy=HOY, log=lambda _: None), llm


def test_guarda_el_borrador_sin_el_texto_alrededor_del_codigo(config, tmp_path):
    # Arrange
    agente, _ = _agente(config, CODIGO_GENERADO)

    # Act
    ruta = agente.generar_pruebas("corte/validacion.py", "validar_piezas", destino=tmp_path)

    # Assert
    contenido = ruta.read_text(encoding="utf-8")
    assert ruta.name == "test_validar_piezas_borrador.py"
    assert contenido.startswith("from corte.validacion import validar_piezas")
    assert "Acá tenés" not in contenido and "```" not in contenido


def test_envia_al_modelo_el_codigo_fuente_y_el_import(config, tmp_path):
    # Arrange
    agente, llm = _agente(config, CODIGO_GENERADO)

    # Act
    agente.generar_pruebas("corte/validacion.py", "validar_piezas",
                           contexto=["corte/modelos.py"], destino=tmp_path)

    # Assert
    mensaje = llm.llamadas[0]["mensaje"]
    assert "from corte.validacion import validar_piezas" in mensaje
    assert "def validar_piezas(" in mensaje
    assert "class Pieza" in mensaje
    assert llm.llamadas[0]["parametros_extra"]["num_predict"] == 1500


def test_rechaza_codigo_con_errores_de_sintaxis(config, tmp_path):
    # Arrange
    agente, _ = _agente(config, "def test_roto(:\n    pass")

    # Act / Assert
    with pytest.raises(ValueError, match="Python válido"):
        agente.generar_pruebas("corte/validacion.py", "validar_piezas", destino=tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_rechaza_funcion_inexistente_sin_llamar_al_modelo(config, tmp_path):
    # Arrange
    agente, llm = _agente(config)

    # Act / Assert
    with pytest.raises(ValueError, match="no existe"):
        agente.generar_pruebas("corte/validacion.py", "funcion_fantasma", destino=tmp_path)
    assert llm.llamadas == []


@pytest.mark.parametrize("ruta", ["../corte-ot-metalurgica/corte/optimizador.py", ".env",
                                  "agente/ingreso-ot.agent.md", "C:/Windows/win.ini"])
def test_no_lee_archivos_fuera_del_proyecto_o_que_no_son_py(config, tmp_path, ruta):
    # Arrange
    agente, llm = _agente(config)

    # Act / Assert
    with pytest.raises(ValueError, match="no es un archivo .py del proyecto"):
        agente.generar_pruebas(ruta, "algo", destino=tmp_path)
    assert llm.llamadas == []
