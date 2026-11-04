"""Pruebas integradas del cliente de Ollama con la red simulada (mock de urlopen)."""

import io
import json
import urllib.error
from unittest.mock import MagicMock

import pytest

from runner.llm import ClienteOllama, ErrorLLM


def _respuesta_http(cuerpo):
    respuesta = MagicMock()
    respuesta.__enter__.return_value = io.BytesIO(json.dumps(cuerpo).encode())
    return respuesta


def _cliente(config, cuerpo):
    abrir_url = MagicMock(return_value=_respuesta_http(cuerpo))
    return ClienteOllama(config.modelo, abrir_url=abrir_url), abrir_url


def _cuerpo_enviado(abrir_url):
    pedido = abrir_url.call_args.args[0]
    return pedido, json.loads(pedido.data)


def test_envia_los_parametros_declarados_en_el_agent_md(config):
    # Arrange
    cliente, abrir_url = _cliente(config, {"message": {"content": "{}"}})
    skill = config.skill("interpretar-pedido")

    # Act
    cliente.completar(skill.prompt, "hola", esquema=skill.esquema)

    # Assert
    pedido, cuerpo = _cuerpo_enviado(abrir_url)
    assert pedido.full_url == "http://localhost:11434/api/chat"
    assert cuerpo["model"] == "qwen2.5:7b"
    assert cuerpo["options"]["temperature"] == 0
    assert cuerpo["options"]["seed"] == 42
    assert cuerpo["format"] == skill.esquema
    assert cuerpo["stream"] is False
    assert [m["role"] for m in cuerpo["messages"]] == ["system", "user"]


def test_los_parametros_de_la_skill_tienen_prioridad(config):
    # Arrange
    cliente, abrir_url = _cliente(config, {"message": {"content": "x = 1"}})
    skill = config.skill("generar-pruebas")

    # Act
    cliente.completar(skill.prompt, "código", parametros_extra=skill.parametros)

    # Assert
    _, cuerpo = _cuerpo_enviado(abrir_url)
    assert cuerpo["options"]["num_ctx"] == 8192        # de la skill
    assert cuerpo["options"]["temperature"] == 0       # del agente
    assert "format" not in cuerpo                      # salida de texto libre


def test_devuelve_el_contenido_del_mensaje(config):
    # Arrange
    cliente, _ = _cliente(config, {"message": {"content": '{"tipo": "pedido"}'}})

    # Act
    texto = cliente.completar("sistema", "hola")

    # Assert
    assert texto == '{"tipo": "pedido"}'


def test_ollama_apagado_da_un_error_claro(config):
    # Arrange
    abrir_url = MagicMock(side_effect=urllib.error.URLError("Connection refused"))
    cliente = ClienteOllama(config.modelo, abrir_url=abrir_url)

    # Act / Assert
    with pytest.raises(ErrorLLM, match="¿Está abierto"):
        cliente.completar("sistema", "hola")


@pytest.mark.parametrize("cuerpo", [{"error": "model not found"}, {"otra": "cosa"}])
def test_respuesta_de_error_o_sin_mensaje_lanza_error_llm(config, cuerpo):
    # Arrange
    cliente, _ = _cliente(config, cuerpo)

    # Act / Assert
    with pytest.raises(ErrorLLM):
        cliente.completar("sistema", "hola")
