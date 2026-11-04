"""Acceso a la base de Supabase (Postgres).

Todas las consultas usan parámetros (``%s``): los valores viajan separados del
texto SQL y el driver los escapa. Ningún dato que venga del cliente o del LLM
se concatena en una consulta.
"""

from __future__ import annotations

import os
from datetime import date
from typing import Any

from corte.modelos import PlanCorte

from .pedido import PiezaPedido


class ErrorBase(RuntimeError):
    """No se pudo acceder a la base de datos."""


class Repositorio:
    """Operaciones del agente sobre la base. Recibe una conexión DB-API abierta."""

    def __init__(self, conexion: Any) -> None:
        self._conn = conexion

    @classmethod
    def desde_entorno(cls) -> "Repositorio":
        """Conecta usando ``DATABASE_URL`` del archivo ``.env``."""
        import psycopg2
        import psycopg2.extras
        from dotenv import load_dotenv

        load_dotenv()
        url = os.environ.get("DATABASE_URL")
        if not url:
            raise ErrorBase(
                "Falta DATABASE_URL. Copiá .env.example a .env y pegá la cadena de "
                "conexión de Supabase."
            )
        try:
            conexion = psycopg2.connect(
                url,
                cursor_factory=psycopg2.extras.RealDictCursor,
                connect_timeout=10,
                keepalives=1,
                keepalives_idle=30,
            )
            # Cancela transacciones que queden abiertas si se corta la conexión.
            with conexion.cursor() as cur:
                cur.execute("SET idle_in_transaction_session_timeout = '30s'")
            conexion.commit()
        except psycopg2.OperationalError as e:
            # El mensaje del driver puede incluir el host; nunca la contraseña.
            raise ErrorBase(f"No se pudo conectar a Supabase: {str(e).splitlines()[0]}") from e
        return cls(conexion)

    def cerrar(self) -> None:
        if not self._conn.closed:
            self._conn.close()

    def _deshacer(self) -> None:
        """Rollback que no tapa el error original si la conexión ya se cortó."""
        if not self._conn.closed:
            self._conn.rollback()

    # ── lectura ──────────────────────────────────────────────────────

    def _consultar(self, sql: str, params: tuple = ()) -> list[dict]:
        with self._conn.cursor() as cur:
            cur.execute(sql, params)
            filas = [dict(f) for f in cur.fetchall()]
        self._conn.commit()  # cierra la transacción de solo lectura
        return filas

    def materiales(self) -> dict[str, dict]:
        """Catálogo: ``{codigo: {"id", "largo_barra_mm"}}``."""
        filas = self._consultar("SELECT id, codigo, largo_barra_mm FROM materiales")
        return {f["codigo"]: {"id": f["id"], "largo_barra_mm": f["largo_barra_mm"]} for f in filas}

    def kerf_mm(self) -> float:
        filas = self._consultar(
            "SELECT valor FROM parametros_planta WHERE clave = %s", ("kerf_mm",)
        )
        if not filas:
            raise ErrorBase("Falta el parámetro 'kerf_mm' en parametros_planta")
        return float(filas[0]["valor"])

    def siguiente_codigo_ot(self) -> str:
        filas = self._consultar(
            "SELECT COALESCE(MAX(CAST(SUBSTRING(codigo FROM %s) AS INTEGER)), 99) + 1 AS n "
            "FROM ordenes_trabajo",
            (r"^OT-(\d+)$",),
        )
        return f"OT-{filas[0]['n']}"

    def piezas_pendientes(self, material_id: int) -> list[dict]:
        """Piezas de OT pendientes para un material."""
        return self._consultar(
            """
            SELECT p.id, o.codigo AS ot, p.largo_mm, p.cantidad
            FROM piezas p
            JOIN ordenes_trabajo o ON o.id = p.orden_id
            WHERE p.material_id = %s AND o.estado = %s
            ORDER BY p.id
            """,
            (material_id, "pendiente"),
        )

    def plan_vigente(self, material_id: int) -> dict | None:
        filas = self._consultar(
            "SELECT barras_usadas, aprovechamiento_pct FROM planes_corte WHERE material_id = %s",
            (material_id,),
        )
        return filas[0] if filas else None

    # ── escritura ────────────────────────────────────────────────────

    def insertar_ot(
        self,
        codigo: str,
        cliente: str,
        descripcion: str,
        fecha_entrega: date,
        mensaje_original: str,
        piezas: list[PiezaPedido],
        materiales: dict[str, dict],
    ) -> int:
        """Inserta la OT y sus piezas en una sola transacción y devuelve su id."""
        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ordenes_trabajo
                        (codigo, cliente, descripcion, fecha_entrega, estado, origen, mensaje_original)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (codigo, cliente, descripcion, fecha_entrega, "pendiente", "agente",
                     mensaje_original),
                )
                orden_id = cur.fetchone()["id"]
                cur.executemany(
                    """
                    INSERT INTO piezas (orden_id, material_id, descripcion, largo_mm, cantidad)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    [
                        (orden_id, materiales[p.material]["id"], p.descripcion, p.largo_mm,
                         p.cantidad)
                        for p in piezas
                    ],
                )
            self._conn.commit()
        except Exception:
            self._deshacer()
            raise
        return orden_id

    def guardar_plan(
        self,
        material_id: int,
        motivo: str,
        plan: PlanCorte,
        metricas: dict,
        antes: dict | None,
    ) -> None:
        """Reemplaza el plan vigente del material en una sola transacción."""
        try:
            with self._conn.cursor() as cur:
                cur.execute("DELETE FROM planes_corte WHERE material_id = %s", (material_id,))
                cur.execute(
                    """
                    INSERT INTO planes_corte
                        (material_id, motivo, barras_usadas, desperdicio_mm, aprovechamiento_pct,
                         cota_inferior, barras_antes, aprovechamiento_antes)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        material_id,
                        motivo,
                        metricas["barras_usadas"],
                        metricas["desperdicio_mm"],
                        metricas["aprovechamiento_pct"],
                        plan.cota_inferior,
                        antes["barras_usadas"] if antes else None,
                        antes["aprovechamiento_pct"] if antes else None,
                    ),
                )
                plan_id = cur.fetchone()["id"]
                cur.executemany(
                    """
                    INSERT INTO cortes (plan_id, nro_barra, posicion, largo_mm, pieza_id)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    [
                        (plan_id, barra.barra_id, posicion, round(corte.largo_mm),
                         int(corte.pieza_id))
                        for barra in plan.barras
                        for posicion, corte in enumerate(barra.cortes, start=1)
                    ],
                )
            self._conn.commit()
        except Exception:
            self._deshacer()
            raise
