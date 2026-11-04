"""Orquestación del agente de ingreso de OT."""

from __future__ import annotations

import ast
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .config import RAIZ, ConfigAgente
from .llm import ClienteOllama
from .pedido import Interpretacion, normalizar
from .repositorio import Repositorio

DIR_BORRADORES = RAIZ / "borradores"
_BLOQUE_CODIGO = re.compile(r"```(?:python)?\s*\n(.*?)```", re.S)


@dataclass
class Respuesta:
    """Lo que el agente informa después de procesar un mensaje."""

    tipo: str
    mensaje: str
    interpretacion: Interpretacion | None = None
    codigo_ot: str | None = None
    planes: list[dict] = field(default_factory=list)


class Agente:
    """Ejecuta las skills declaradas en el ``.agent.md``.

    Las dependencias (cliente del LLM, repositorio, fecha y salida de log) se
    inyectan para que las pruebas puedan reemplazarlas.
    """

    def __init__(
        self,
        config: ConfigAgente,
        llm: ClienteOllama,
        repo: Repositorio,
        hoy: date | None = None,
        log: Callable[[str], None] = print,
    ) -> None:
        self.config = config
        self.llm = llm
        self.repo = repo
        self.hoy = hoy or date.today()
        self.log = log

    # ── skills ───────────────────────────────────────────────────────

    def _invocar_llm(self, nombre_skill: str, mensaje: str) -> str:
        skill = self.config.skill(nombre_skill)
        opciones = {**self.config.modelo.parametros, **skill.parametros}
        self.log(
            f"→ skill {skill.nombre} · {self.config.modelo.nombre} · "
            f"temperature={opciones.get('temperature')} seed={opciones.get('seed')}"
        )
        inicio = time.perf_counter()
        salida = self.llm.completar(skill.prompt, mensaje, skill.esquema, skill.parametros)
        self.log(f"  respuesta en {time.perf_counter() - inicio:.1f} s")
        return salida

    def _invocar_herramienta(self, nombre_skill: str, **kwargs):
        skill = self.config.skill(nombre_skill)
        self.log(f"→ skill {skill.nombre} · herramienta {skill.entrypoint}")
        return skill.funcion()(self.repo, **kwargs)

    # ── casos de uso ─────────────────────────────────────────────────

    def interpretar(self, mensaje: str) -> Interpretacion:
        """Skill ``interpretar-pedido`` más la validación en Python."""
        maximo = self.config.limites.get("max_caracteres_mensaje", 2000)
        if not mensaje or not mensaje.strip():
            raise ValueError("El mensaje está vacío")
        if len(mensaje) > maximo:
            raise ValueError(f"El mensaje supera el máximo de {maximo} caracteres")

        crudo = self._invocar_llm("interpretar-pedido", mensaje)
        catalogo = self.repo.materiales()
        return normalizar(
            crudo,
            {codigo: m["largo_barra_mm"] for codigo, m in catalogo.items()},
            self.repo.kerf_mm(),
            self.hoy,
        )

    def procesar(self, mensaje: str) -> Respuesta:
        """Interpreta un pedido y, si está completo, lo registra y replanifica."""
        interp = self.interpretar(mensaje)

        if interp.tipo == "no_es_pedido":
            return Respuesta(
                "no_es_pedido",
                "El mensaje no contiene un pedido de piezas. No se registró nada.",
                interp,
            )

        if not interp.completa:
            consulta = "\n".join(f"  - {f}" for f in interp.faltantes)
            return Respuesta(
                "pedido_incompleto",
                "No se registró la OT. Para cargarla hay que pedirle al cliente:\n" + consulta,
                interp,
            )

        codigo = self.repo.siguiente_codigo_ot()
        descripcion = "Pedido por mensaje: " + ", ".join(p.descripcion for p in interp.piezas)
        self.repo.insertar_ot(
            codigo=codigo,
            cliente=interp.cliente,
            descripcion=descripcion[:120],
            fecha_entrega=interp.fecha_entrega,
            mensaje_original=mensaje,
            piezas=interp.piezas,
            materiales=self.repo.materiales(),
        )
        self.log(f"  OT {codigo} registrada")

        materiales = sorted({p.material for p in interp.piezas})
        planes = self._invocar_herramienta(
            "planificar-corte", materiales=materiales, motivo=f"Ingreso {codigo}"
        )
        return Respuesta("pedido", f"OT {codigo} registrada y plan de corte actualizado.",
                         interp, codigo, planes)

    def planificar_todo(self, motivo: str = "Plan inicial") -> list[dict]:
        """Invoca ``planificar-corte`` sobre todos los materiales."""
        return self._invocar_herramienta("planificar-corte", materiales=None, motivo=motivo)

    def generar_pruebas(
        self,
        modulo: str | Path,
        funcion: str,
        contexto: list[str | Path] | None = None,
        destino: Path = DIR_BORRADORES,
    ) -> Path:
        """Skill ``generar-pruebas``: guarda un borrador de tests y devuelve su ruta.

        Raises
        ------
        ValueError
            Si un archivo está fuera del proyecto, no es ``.py``, la función no
            existe o el modelo no devolvió código Python válido.
        """
        principal = _archivo_del_proyecto(modulo)
        fuente = principal.read_text(encoding="utf-8")
        if funcion not in {
            n.name for n in ast.walk(ast.parse(fuente)) if isinstance(n, ast.FunctionDef)
        }:
            raise ValueError(f"La función '{funcion}' no existe en {principal.name}")

        import_path = ".".join(principal.relative_to(RAIZ).with_suffix("").parts)
        partes = [
            f"Escribí tests para la función `{funcion}`. Importala así:\n"
            f"from {import_path} import {funcion}\n",
            f"# Archivo {principal.relative_to(RAIZ).as_posix()}\n{fuente}",
        ]
        for extra in contexto or []:
            archivo = _archivo_del_proyecto(extra)
            partes.append(
                f"# Archivo {archivo.relative_to(RAIZ).as_posix()}\n"
                f"{archivo.read_text(encoding='utf-8')}"
            )

        salida = self._invocar_llm("generar-pruebas", "\n\n".join(partes))
        bloque = _BLOQUE_CODIGO.search(salida)
        codigo = (bloque.group(1) if bloque else salida).strip() + "\n"
        try:
            ast.parse(codigo)  # solo se analiza la sintaxis: el código no se ejecuta
        except SyntaxError as e:
            raise ValueError(f"El modelo no devolvió Python válido (línea {e.lineno})") from e

        destino.mkdir(parents=True, exist_ok=True)
        archivo_salida = destino / f"test_{funcion}_borrador.py"
        archivo_salida.write_text(codigo, encoding="utf-8")
        return archivo_salida


def _archivo_del_proyecto(ruta: str | Path) -> Path:
    """Resuelve ``ruta`` y verifica que sea un ``.py`` dentro del proyecto.

    Evita que la skill lea archivos arbitrarios (por ejemplo ``../../.env``)
    y los envíe al modelo.
    """
    candidata = (RAIZ / ruta).resolve()
    if not candidata.is_relative_to(RAIZ) or candidata.suffix != ".py" or not candidata.is_file():
        raise ValueError(f"'{ruta}' no es un archivo .py del proyecto")
    return candidata
