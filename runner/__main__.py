"""Consola del agente.

Uso::

    python -m runner skills
    python -m runner planificar
    python -m runner pedido "Hola, soy de ... necesito ..."
    python -m runner pedido --archivo pedidos/01_normal.txt
    python -m runner repetir --archivo pedidos/01_normal.txt -n 3
    python -m runner pruebas corte/validacion.py --funcion validar_piezas --contexto corte/modelos.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path

from .config import ErrorConfiguracion, cargar_agente
from .llm import ClienteOllama, ErrorLLM
from .pedido import ErrorRespuestaLLM
from .repositorio import ErrorBase, Repositorio

LINEA = "─" * 64


def _titulo(texto: str) -> None:
    print(f"\n{LINEA}\n{texto}\n{LINEA}")


def _leer_mensaje(args: argparse.Namespace) -> str:
    if args.archivo:
        return Path(args.archivo).read_text(encoding="utf-8").strip()
    if args.texto:
        return args.texto
    raise SystemExit("Indicá el mensaje entre comillas o con --archivo")


def _mostrar_planes(planes: list[dict]) -> None:
    print(f"\n{'Material':<16}{'Barras':>16}{'Aprovechamiento':>24}")
    for p in planes:
        antes_b = "—" if p["barras_antes"] is None else p["barras_antes"]
        antes_a = "—" if p["aprovechamiento_antes"] is None else f"{p['aprovechamiento_antes']} %"
        barras = f"{antes_b} → {p['barras_despues']}"
        aprovechamiento = f"{antes_a} → {p['aprovechamiento_despues']} %"
        estado = p["estado_solver"].lower()
        print(f"{p['material']:<16}{barras:>16}{aprovechamiento:>24}   ({estado})")


def cmd_skills(config, _args) -> None:
    _titulo(f"Agente {config.nombre}  ({config.ruta.name})")
    m = config.modelo
    print(f"{config.descripcion}\n")
    print(f"Modelo: {m.proveedor} · {m.nombre} · {m.host}")
    print("Parámetros: " + ", ".join(f"{k}={v}" for k, v in m.parametros.items()))
    print("\nSkills habilitadas:")
    for s in config.skills.values():
        destino = s.entrypoint if s.tipo == "herramienta" else "prompt + " + (
            "esquema JSON" if s.esquema else "texto libre")
        print(f"  • {s.nombre:<20} [{s.tipo}] {destino}")
        print(f"    {s.descripcion}")


def cmd_pedido(agente, args) -> None:
    mensaje = _leer_mensaje(args)
    _titulo("Mensaje del cliente")
    print(mensaje)
    _titulo("Agente")
    respuesta = agente.procesar(mensaje)
    interp = respuesta.interpretacion
    if interp and interp.piezas:
        print("\nPiezas interpretadas:")
        for p in interp.piezas:
            print(f"  {p.cantidad:>3} × {p.largo_mm:>5} mm  {p.material:<14} {p.descripcion}")
        print(f"Cliente: {interp.cliente or '—'} · Entrega: {interp.fecha_entrega or '—'}")
    print(f"\n[{respuesta.tipo.upper()}] {respuesta.mensaje}")
    if respuesta.planes:
        _mostrar_planes(respuesta.planes)
        print("\nVer el panel: http://127.0.0.1:8090")


def cmd_repetir(agente, args) -> None:
    mensaje = _leer_mensaje(args)
    _titulo(f"Repetibilidad: el mismo mensaje {args.n} veces")
    huellas = []
    for i in range(1, args.n + 1):
        interp = agente.interpretar(mensaje)
        datos = json.dumps(asdict(interp), sort_keys=True, default=str, ensure_ascii=False)
        huella = hashlib.sha256(datos.encode()).hexdigest()[:12]
        huellas.append(huella)
        print(f"  corrida {i}: {interp.tipo:<18} huella {huella}")
    iguales = len(set(huellas)) == 1
    print("\nResultado: " + ("idéntico en todas las corridas" if iguales else "HUBO DIFERENCIAS"))


def cmd_planificar(agente, _args) -> None:
    _titulo("Plan de corte de todas las OT pendientes")
    _mostrar_planes(agente.planificar_todo())


def cmd_pruebas(agente, args) -> None:
    _titulo(f"Generando borrador de tests para {args.funcion}")
    ruta = agente.generar_pruebas(args.modulo, args.funcion, args.contexto)
    print(f"\nBorrador guardado en {ruta}")
    print("Revisalo y, si está bien, movelo a tests/unit/ para que pytest lo ejecute.")


def main(argv: list[str] | None = None) -> int:
    # La consola de Windows no usa UTF-8 por defecto
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(prog="python -m runner", description="Agente de ingreso de OT")
    sub = parser.add_subparsers(dest="comando", required=True)
    sub.add_parser("skills", help="muestra el agente y las skills cargadas desde los .md")
    sub.add_parser("planificar", help="calcula el plan inicial de todas las OT pendientes")
    for nombre, ayuda in [("pedido", "procesa un pedido"), ("repetir", "comprueba la repetibilidad")]:
        p = sub.add_parser(nombre, help=ayuda)
        p.add_argument("texto", nargs="?")
        p.add_argument("--archivo")
        if nombre == "repetir":
            p.add_argument("-n", type=int, default=3)
    p = sub.add_parser("pruebas", help="genera un borrador de tests con el LLM")
    p.add_argument("modulo")
    p.add_argument("--funcion", required=True)
    p.add_argument("--contexto", nargs="*", default=[])
    args = parser.parse_args(argv)

    try:
        config = cargar_agente()
        if args.comando == "skills":
            cmd_skills(config, args)
            return 0

        llm = ClienteOllama(config.modelo)
        repo = None if args.comando == "pruebas" else Repositorio.desde_entorno()
        from .agente import Agente

        agente = Agente(config, llm, repo)
        comandos = {"pedido": cmd_pedido, "repetir": cmd_repetir,
                    "planificar": cmd_planificar, "pruebas": cmd_pruebas}
        try:
            comandos[args.comando](agente, args)
        finally:
            if repo:
                repo.cerrar()
    except (ErrorConfiguracion, ErrorLLM, ErrorBase, ErrorRespuestaLLM, ValueError) as e:
        print(f"\nError: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        if not type(e).__module__.startswith("psycopg2"):
            raise
        # Errores de la base: mensaje corto, sin traceback ni datos de conexión.
        print(f"\nError de la base de datos: {str(e).splitlines()[0]}\n"
              "No se guardó nada de esta operación. Volvé a ejecutar el comando.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
