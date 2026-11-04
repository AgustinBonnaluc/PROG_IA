"""Panel de planificación de cortes.

Servicio de solo lectura sobre la base de la metalúrgica alojada en Supabase.
No calcula nada: muestra las OT (marcando las que ingresó el agente, con el
mensaje original del cliente) y el plan de corte vigente con el impacto del
último recálculo. Se actualiza solo cada pocos segundos.

Uso:
    python web/app.py
    http://127.0.0.1:8090   (otro puerto: variable PUERTO_PANEL)
"""

import os
from contextlib import closing

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template

load_dotenv()

app = Flask(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")


def get_db():
    """Abre una conexión a Postgres usando la cadena del archivo .env."""
    if not DATABASE_URL:
        raise RuntimeError(
            "Falta la variable DATABASE_URL. Copiá .env.example a .env y "
            "pegá la cadena de conexión de Supabase."
        )
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)


def consultar(sql, params=None):
    # closing(): el "with" de psycopg2 cierra la transacción, no la conexión.
    with closing(get_db()) as conn, conn, conn.cursor() as cur:
        cur.execute(sql, params or ())
        return [dict(fila) for fila in cur.fetchall()]


@app.after_request
def cabeceras_seguridad(respuesta):
    """Cabeceras básicas: sin scripts de terceros ni inserción en iframes."""
    respuesta.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; frame-ancestors 'none'"
    )
    respuesta.headers["X-Content-Type-Options"] = "nosniff"
    return respuesta


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/api/ordenes")
def api_ordenes():
    """Órdenes de trabajo con sus piezas y el total de milímetros requeridos."""
    ordenes = consultar(
        """
        SELECT o.id, o.codigo, o.cliente, o.descripcion, o.fecha_entrega, o.estado,
               o.origen, o.mensaje_original,
               o.fecha_entrega - CURRENT_DATE AS dias_restantes,
               COALESCE(SUM(p.cantidad), 0)                AS piezas,
               COALESCE(SUM(p.cantidad * p.largo_mm), 0)   AS mm_requeridos
        FROM ordenes_trabajo o
        LEFT JOIN piezas p ON p.orden_id = o.id
        GROUP BY o.id
        ORDER BY o.creada_en DESC, o.fecha_entrega
        """
    )
    piezas = consultar(
        """
        SELECT p.id, p.orden_id, p.descripcion, p.largo_mm, p.cantidad, m.codigo AS material
        FROM piezas p
        JOIN materiales m ON m.id = p.material_id
        ORDER BY p.id
        """
    )
    for orden in ordenes:
        orden["piezas_detalle"] = [p for p in piezas if p["orden_id"] == orden["id"]]
    return jsonify(ordenes)


@app.route("/api/planes")
def api_planes():
    """Plan de corte vigente por material, con el detalle de cada barra."""
    planes = consultar(
        """
        SELECT pc.id, pc.fecha, pc.motivo, pc.barras_usadas, pc.desperdicio_mm,
               pc.aprovechamiento_pct, pc.cota_inferior,
               pc.barras_antes, pc.aprovechamiento_antes,
               m.codigo AS material, m.largo_barra_mm, m.kg_por_metro
        FROM planes_corte pc
        JOIN materiales m ON m.id = pc.material_id
        ORDER BY m.codigo
        """
    )
    cortes = consultar(
        """
        SELECT c.plan_id, c.nro_barra, c.posicion, c.largo_mm,
               p.descripcion, o.codigo AS ot, o.origen
        FROM cortes c
        JOIN piezas p ON p.id = c.pieza_id
        JOIN ordenes_trabajo o ON o.id = p.orden_id
        ORDER BY c.plan_id, c.nro_barra, c.posicion
        """
    )

    for plan in planes:
        barras = {}
        for corte in [c for c in cortes if c["plan_id"] == plan["id"]]:
            barras.setdefault(corte["nro_barra"], []).append(corte)
        plan["barras"] = [
            {"nro": nro, "cortes": barras[nro], "ocupado_mm": sum(c["largo_mm"] for c in barras[nro])}
            for nro in sorted(barras)
        ]
    return jsonify({"disponible": True, "planes": planes})


if __name__ == "__main__":
    # Debug solo con FLASK_DEBUG=1: el depurador de Werkzeug permite ejecutar código.
    puerto = int(os.environ.get("PUERTO_PANEL", "8090"))
    app.run(host="127.0.0.1", port=puerto, debug=os.environ.get("FLASK_DEBUG") == "1")
