"""Pruebas integradas del repositorio con una conexión Postgres simulada.

Verifican el contrato de seguridad: los datos viajan como parámetros y nunca
dentro del texto SQL, y una falla deja la base como estaba (rollback).
"""

import re
from datetime import date
from unittest.mock import MagicMock

import pytest

from corte import Pieza, calcular_metricas, optimizar_corte
from runner.pedido import PiezaPedido
from runner.repositorio import Repositorio

MATERIALES = {"CE-40x40x1.6": {"id": 1, "largo_barra_mm": 6000}}
CLIENTE_MALICIOSO = "Ferraro'); DROP TABLE piezas;--"


@pytest.fixture
def conexion():
    conn = MagicMock()
    conn.closed = 0  # psycopg2 usa 0 para una conexión abierta
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = {"id": 7}
    cursor.fetchall.return_value = []
    return conn, cursor


def _insertar(repo, cliente=CLIENTE_MALICIOSO):
    return repo.insertar_ot(
        codigo="OT-108",
        cliente=cliente,
        descripcion="Pedido por mensaje: pata",
        fecha_entrega=date(2026, 11, 6),
        mensaje_original=f"Cliente: {cliente}",
        piezas=[PiezaPedido("pata", "CE-40x40x1.6", 900, 4)],
        materiales=MATERIALES,
    )


def test_el_texto_del_cliente_viaja_como_parametro_y_no_en_el_sql(conexion):
    # Arrange
    conn, cursor = conexion
    repo = Repositorio(conn)

    # Act
    _insertar(repo)

    # Assert
    sql, params = cursor.execute.call_args.args
    assert CLIENTE_MALICIOSO not in sql
    assert "DROP" not in sql.upper()
    assert CLIENTE_MALICIOSO in params


def test_cantidad_de_marcadores_coincide_con_los_parametros(conexion):
    # Arrange
    conn, cursor = conexion
    repo = Repositorio(conn)

    # Act
    _insertar(repo, cliente="Taller Ferraro")

    # Assert
    sql, params = cursor.execute.call_args.args
    assert sql.count("%s") == len(params)
    filas_piezas = cursor.executemany.call_args.args[1]
    assert filas_piezas == [(7, 1, "pata", 900, 4)]
    conn.commit.assert_called_once()


def test_si_falla_la_insercion_de_piezas_se_hace_rollback(conexion):
    # Arrange
    conn, cursor = conexion
    cursor.executemany.side_effect = RuntimeError("violación de check")
    repo = Repositorio(conn)

    # Act / Assert
    with pytest.raises(RuntimeError):
        _insertar(repo)
    conn.rollback.assert_called_once()
    conn.commit.assert_not_called()


def test_si_se_corta_la_conexion_se_informa_el_error_original(conexion):
    # Arrange: el servidor cierra la conexión a mitad de la inserción
    conn, cursor = conexion

    def cortar(*_):
        conn.closed = 2
        raise ConnectionError("server closed the connection unexpectedly")

    cursor.executemany.side_effect = cortar
    repo = Repositorio(conn)

    # Act / Assert: no se intenta un rollback que taparía el error real
    with pytest.raises(ConnectionError, match="server closed"):
        _insertar(repo)
    conn.rollback.assert_not_called()


def test_guardar_plan_reemplaza_el_anterior_en_una_transaccion(conexion):
    # Arrange
    conn, cursor = conexion
    repo = Repositorio(conn)
    plan = optimizar_corte([Pieza("15", "OT-108", 900, 4)], 6000, 3)
    metricas = calcular_metricas(plan)

    # Act
    repo.guardar_plan(1, "Ingreso OT-108", plan, metricas, {"barras_usadas": 5,
                                                            "aprovechamiento_pct": 90.1})

    # Assert
    sentencias = [c.args[0].strip().split()[0].upper() for c in cursor.execute.call_args_list]
    assert sentencias == ["DELETE", "INSERT"]
    cortes = cursor.executemany.call_args.args[1]
    assert [(c[1], c[2], c[4]) for c in cortes] == [(1, 1, 15), (1, 2, 15), (1, 3, 15), (1, 4, 15)]
    conn.commit.assert_called_once()


def test_ninguna_consulta_del_modulo_formatea_valores_en_el_sql():
    # Arrange: análisis estático simple del código fuente
    import runner.repositorio as modulo
    fuente = open(modulo.__file__, encoding="utf-8").read()

    # Act
    sql_formateado = re.findall(r"execute\w*\(\s*f[\"']|\.format\(|%\s*\(", fuente)

    # Assert
    assert sql_formateado == []
