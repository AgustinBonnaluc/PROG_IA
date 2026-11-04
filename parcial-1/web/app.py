"""Panel de planificación de cortes.

Servicio de solo lectura sobre la base de la metalúrgica alojada en Supabase.
No calcula nada: muestra lo que hay en la base antes y después de que el
agente ejecute la optimización a través de los servidores MCP.

Uso:
    python web/app.py
    http://127.0.0.1:8080
"""

import os

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
    with get_db() as conn, conn.cursor() as cur:
        cur.execute(sql, params or ())
        return [dict(fila) for fila in cur.fetchall()]


def existe_tabla(nombre):
    resultado = consultar("SELECT to_regclass(%s) IS NOT NULL AS existe", (nombre,))
    return resultado[0]["existe"]


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/api/parametros")
def api_parametros():
    """Parámetros de planta y catálogo de materiales."""
    return jsonify(
        {
            "parametros": consultar("SELECT clave, valor, descripcion FROM parametros_planta"),
            "materiales": consultar(
                "SELECT id, codigo, descripcion, largo_barra_mm, kg_por_metro "
                "FROM materiales ORDER BY codigo"
            ),
        }
    )


@app.route("/api/ordenes")
def api_ordenes():
    """Órdenes de trabajo con sus piezas y el total de milímetros requeridos."""
    ordenes = consultar(
        """
        SELECT o.id, o.codigo, o.cliente, o.descripcion, o.fecha_entrega, o.estado,
               o.fecha_entrega - CURRENT_DATE AS dias_restantes,
               COALESCE(SUM(p.cantidad), 0)                AS piezas,
               COALESCE(SUM(p.cantidad * p.largo_mm), 0)   AS mm_requeridos
        FROM ordenes_trabajo o
        LEFT JOIN piezas p ON p.orden_id = o.id
        GROUP BY o.id
        ORDER BY o.fecha_entrega
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
    """Planes de corte guardados por el agente, con el detalle de cada barra.

    Las tablas planes_corte y cortes las crea el agente durante la demostración,
    así que antes de eso este endpoint devuelve una lista vacía en lugar de fallar.
    """
    if not (existe_tabla("planes_corte") and existe_tabla("cortes")):
        return jsonify({"disponible": False, "planes": []})

    planes = consultar(
        """
        SELECT pc.id, pc.fecha, pc.barras_usadas, pc.desperdicio_mm,
               pc.aprovechamiento_pct, pc.cota_inferior,
               m.codigo AS material, m.largo_barra_mm, m.kg_por_metro
        FROM planes_corte pc
        JOIN materiales m ON m.id = pc.material_id
        ORDER BY pc.id
        """
    )
    cortes = consultar(
        """
        SELECT c.plan_id, c.nro_barra, c.posicion, c.largo_mm,
               p.descripcion, o.codigo AS ot
        FROM cortes c
        LEFT JOIN piezas p ON p.id = c.pieza_id
        LEFT JOIN ordenes_trabajo o ON o.id = p.orden_id
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
    app.run(port=8080, debug=True)
