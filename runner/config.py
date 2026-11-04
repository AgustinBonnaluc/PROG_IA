"""Carga declarativa del agente y sus skills.

El agente se define en ``agente/<nombre>.agent.md`` y cada skill en
``agente/skills/<nombre>/SKILL.md``. Ambos son Markdown con un frontmatter YAML
entre líneas ``---``. Este módulo los lee, valida su estructura y los expone
como objetos inmutables: el comportamiento se cambia editando los ``.md``,
no el código.
"""

from __future__ import annotations

import importlib
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any
from urllib.parse import urlparse

import yaml

RAIZ = Path(__file__).resolve().parent.parent
DIR_AGENTE = RAIZ / "agente"
AGENTE_POR_DEFECTO = DIR_AGENTE / "ingreso-ot.agent.md"

PROVEEDORES = {"ollama"}
TIPOS_SKILL = {"llm", "herramienta"}
HOSTS_LOCALES = {"localhost", "127.0.0.1", "::1"}
PREFIJO_ENTRYPOINT = "runner."
"""Las herramientas solo pueden apuntar a funciones de este paquete.

Sin esta restricción, un ``SKILL.md`` modificado podría declarar
``entrypoint: os:system`` y el agente lo importaría y ejecutaría.
"""

_FRONTMATTER = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n?(.*)\Z", re.S)


class ErrorConfiguracion(ValueError):
    """La definición del agente o de una skill es inválida."""


def leer_markdown(ruta: Path) -> tuple[dict[str, Any], str]:
    """Devuelve ``(frontmatter, cuerpo)`` de un archivo Markdown.

    El YAML se interpreta con ``yaml.safe_load``, que no instancia objetos de
    Python: una etiqueta como ``!!python/object/apply:os.system`` produce un
    error en lugar de ejecutar código.
    """
    texto = Path(ruta).read_text(encoding="utf-8")
    coincidencia = _FRONTMATTER.match(texto)
    if not coincidencia:
        raise ErrorConfiguracion(f"{ruta}: falta el frontmatter YAML delimitado por '---'")
    try:
        datos = yaml.safe_load(coincidencia.group(1)) or {}
    except yaml.YAMLError as e:
        raise ErrorConfiguracion(f"{ruta}: YAML inválido ({e})") from e
    if not isinstance(datos, dict):
        raise ErrorConfiguracion(f"{ruta}: el frontmatter debe ser un mapa clave: valor")
    return datos, coincidencia.group(2)


def extraer_seccion(cuerpo: str, titulo: str) -> str | None:
    """Devuelve el texto de la sección ``## <titulo>`` hasta el próximo ``## ``."""
    patron = re.compile(rf"^##[ \t]+{re.escape(titulo)}[ \t]*$(.*?)(?=^##[ \t]|\Z)", re.M | re.S)
    coincidencia = patron.search(cuerpo)
    return coincidencia.group(1).strip() if coincidencia else None


def _requerir(datos: dict, clave: str, ruta: Path) -> Any:
    if clave not in datos or datos[clave] in (None, ""):
        raise ErrorConfiguracion(f"{ruta}: falta el campo obligatorio '{clave}'")
    return datos[clave]


def _congelar(mapa: dict | None) -> MappingProxyType:
    return MappingProxyType(dict(mapa or {}))


# ── modelos de configuración ─────────────────────────────────────────

@dataclass(frozen=True)
class ConfigModelo:
    """Modelo de lenguaje y parámetros de inferencia del agente."""

    proveedor: str
    nombre: str
    host: str
    parametros: MappingProxyType
    keep_alive: str = "5m"
    timeout_s: float = 600.0


@dataclass(frozen=True)
class Skill:
    """Una habilidad del agente, tal como está declarada en su ``SKILL.md``."""

    nombre: str
    descripcion: str
    tipo: str
    ruta: Path
    prompt: str | None = None
    esquema: dict | None = None
    entrypoint: str | None = None
    parametros: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))

    def funcion(self) -> Callable[..., Any]:
        """Importa y devuelve la función de una skill de tipo ``herramienta``."""
        if self.tipo != "herramienta" or not self.entrypoint:
            raise ErrorConfiguracion(f"La skill '{self.nombre}' no es una herramienta")
        modulo, _, nombre = self.entrypoint.partition(":")
        return getattr(importlib.import_module(modulo), nombre)


@dataclass(frozen=True)
class ConfigAgente:
    """Agente completo: modelo, skills habilitadas, límites e instrucciones."""

    nombre: str
    descripcion: str
    modelo: ConfigModelo
    skills: MappingProxyType
    limites: MappingProxyType
    ruta: Path

    def skill(self, nombre: str) -> Skill:
        """Devuelve una skill declarada en el agente o lanza ``ErrorConfiguracion``."""
        if nombre not in self.skills:
            raise ErrorConfiguracion(
                f"La skill '{nombre}' no está habilitada en {self.ruta.name}"
            )
        return self.skills[nombre]


# ── carga ────────────────────────────────────────────────────────────

def _cargar_modelo(datos: dict, ruta: Path) -> ConfigModelo:
    if not isinstance(datos, dict):
        raise ErrorConfiguracion(f"{ruta}: 'modelo' debe ser un mapa")
    proveedor = _requerir(datos, "proveedor", ruta)
    if proveedor not in PROVEEDORES:
        raise ErrorConfiguracion(f"{ruta}: proveedor '{proveedor}' no soportado")

    host = str(_requerir(datos, "host", ruta))
    url = urlparse(host)
    if url.scheme not in {"http", "https"} or url.hostname not in HOSTS_LOCALES:
        raise ErrorConfiguracion(
            f"{ruta}: el host del modelo debe ser local (se recibió '{host}'); "
            "los pedidos de clientes no pueden salir de la PC"
        )

    parametros = datos.get("parametros") or {}
    temperatura = parametros.get("temperature")
    if not isinstance(temperatura, (int, float)) or not 0 <= temperatura <= 2:
        raise ErrorConfiguracion(f"{ruta}: 'parametros.temperature' debe estar entre 0 y 2")

    return ConfigModelo(
        proveedor=proveedor,
        nombre=str(_requerir(datos, "nombre", ruta)),
        host=host.rstrip("/"),
        parametros=_congelar(parametros),
        keep_alive=str(datos.get("keep_alive", "5m")),
        timeout_s=float(datos.get("timeout_s", 600)),
    )


def cargar_skill(ruta: Path) -> Skill:
    """Lee y valida un ``SKILL.md``."""
    datos, cuerpo = leer_markdown(ruta)
    nombre = _requerir(datos, "name", ruta)
    if nombre != ruta.parent.name:
        raise ErrorConfiguracion(
            f"{ruta}: name '{nombre}' no coincide con la carpeta '{ruta.parent.name}'"
        )
    tipo = _requerir(datos, "tipo", ruta)
    if tipo not in TIPOS_SKILL:
        raise ErrorConfiguracion(f"{ruta}: tipo '{tipo}' inválido (usar {sorted(TIPOS_SKILL)})")

    prompt = esquema = entrypoint = None
    if tipo == "llm":
        prompt = extraer_seccion(cuerpo, "Prompt")
        if not prompt:
            raise ErrorConfiguracion(f"{ruta}: una skill 'llm' necesita una sección '## Prompt'")
        salidas = datos.get("salidas") or {}
        if salidas.get("formato") == "json":
            esquema = salidas.get("esquema")
            if not isinstance(esquema, dict):
                raise ErrorConfiguracion(f"{ruta}: salida json sin 'esquema'")
    else:
        entrypoint = str(_requerir(datos, "entrypoint", ruta))
        if not entrypoint.startswith(PREFIJO_ENTRYPOINT) or ":" not in entrypoint:
            raise ErrorConfiguracion(
                f"{ruta}: entrypoint '{entrypoint}' no permitido; debe ser "
                f"'{PREFIJO_ENTRYPOINT}<modulo>:<funcion>'"
            )

    return Skill(
        nombre=nombre,
        descripcion=str(_requerir(datos, "description", ruta)),
        tipo=tipo,
        ruta=ruta,
        prompt=prompt,
        esquema=esquema,
        entrypoint=entrypoint,
        parametros=_congelar(datos.get("parametros")),
    )


def cargar_agente(ruta: Path = AGENTE_POR_DEFECTO) -> ConfigAgente:
    """Lee el ``.agent.md`` y todas las skills que declara."""
    ruta = Path(ruta)
    datos, _ = leer_markdown(ruta)
    nombres = _requerir(datos, "skills", ruta)
    if not isinstance(nombres, list):
        raise ErrorConfiguracion(f"{ruta}: 'skills' debe ser una lista")

    skills = {}
    for nombre in nombres:
        archivo = ruta.parent / "skills" / str(nombre) / "SKILL.md"
        if not archivo.is_file():
            raise ErrorConfiguracion(f"{ruta}: la skill '{nombre}' no existe ({archivo})")
        skills[nombre] = cargar_skill(archivo)

    return ConfigAgente(
        nombre=str(_requerir(datos, "name", ruta)),
        descripcion=str(_requerir(datos, "description", ruta)).strip(),
        modelo=_cargar_modelo(_requerir(datos, "modelo", ruta), ruta),
        skills=_congelar(skills),
        limites=_congelar(datos.get("limites")),
        ruta=ruta,
    )
