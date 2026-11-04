"""Cliente mínimo para la API de chat de Ollama."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any

from .config import ConfigModelo


class ErrorLLM(RuntimeError):
    """No se pudo obtener una respuesta del modelo."""


class ClienteOllama:
    """Envía un prompt de sistema y un mensaje al modelo configurado.

    ``abrir_url`` se inyecta para poder reemplazar la red en las pruebas.
    """

    def __init__(
        self,
        modelo: ConfigModelo,
        abrir_url: Callable[..., Any] = urllib.request.urlopen,
    ) -> None:
        self.modelo = modelo
        self._abrir_url = abrir_url

    def completar(
        self,
        sistema: str,
        mensaje: str,
        esquema: dict | None = None,
        parametros_extra: Mapping[str, Any] | None = None,
    ) -> str:
        """Devuelve el texto generado por el modelo.

        Los parámetros del agente (temperatura, semilla, contexto) se combinan
        con los propios de la skill, que tienen prioridad. Si se pasa
        ``esquema``, Ollama restringe la salida a un JSON con esa forma.
        """
        cuerpo: dict[str, Any] = {
            "model": self.modelo.nombre,
            "messages": [
                {"role": "system", "content": sistema},
                {"role": "user", "content": mensaje},
            ],
            "options": {**self.modelo.parametros, **(parametros_extra or {})},
            "keep_alive": self.modelo.keep_alive,
            "stream": False,
        }
        if esquema is not None:
            cuerpo["format"] = esquema

        pedido = urllib.request.Request(
            f"{self.modelo.host}/api/chat",
            data=json.dumps(cuerpo).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self._abrir_url(pedido, timeout=self.modelo.timeout_s) as respuesta:
                datos = json.load(respuesta)
        except urllib.error.URLError as e:
            raise ErrorLLM(
                f"No se pudo conectar con Ollama en {self.modelo.host}. "
                f"¿Está abierto y el modelo '{self.modelo.nombre}' descargado? ({e.reason})"
            ) from e
        except (TimeoutError, json.JSONDecodeError) as e:
            raise ErrorLLM(f"Respuesta inválida o demorada de Ollama: {e}") from e

        if "error" in datos:
            raise ErrorLLM(f"Ollama devolvió un error: {datos['error']}")
        try:
            return datos["message"]["content"]
        except (KeyError, TypeError) as e:
            raise ErrorLLM("La respuesta de Ollama no tiene el formato esperado") from e
