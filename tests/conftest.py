"""Dobles de prueba compartidos: un LLM falso y un repositorio en memoria.

Permiten probar el agente completo sin Ollama ni Supabase, de forma rápida y
siempre con el mismo resultado.
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from runner.config import cargar_agente

HOY = date(2026, 11, 2)  # lunes


class LLMFalso:
    """Devuelve respuestas preparadas y registra cada llamada."""

    def __init__(self, *respuestas):
        self.respuestas = [r if isinstance(r, str) else json.dumps(r) for r in respuestas]
        self.llamadas = []

    def completar(self, sistema, mensaje, esquema=None, parametros_extra=None):
        self.llamadas.append(
            {"sistema": sistema, "mensaje": mensaje, "esquema": esquema,
             "parametros_extra": dict(parametros_extra or {})}
        )
        return self.respuestas.pop(0)


class RepositorioEnMemoria:
    """Implementa la misma interfaz que ``runner.repositorio.Repositorio``."""

    def __init__(self):
        self._materiales = {
            "CE-40x40x1.6": {"id": 1, "largo_barra_mm": 6000},
            "ANG-1.1/4x1/8": {"id": 2, "largo_barra_mm": 6000},
            "PLA-2x3/16": {"id": 3, "largo_barra_mm": 6000},
        }
        self.ordenes = [{"id": 1, "codigo": "OT-101", "estado": "pendiente", "origen": "planilla"}]
        self.piezas = [
            {"id": 1, "orden_id": 1, "material_id": 1, "largo_mm": 2000, "cantidad": 4},
            {"id": 2, "orden_id": 1, "material_id": 1, "largo_mm": 1450, "cantidad": 6},
        ]
        self.planes = {}

    def materiales(self):
        return {k: dict(v) for k, v in self._materiales.items()}

    def kerf_mm(self):
        return 3.0

    def siguiente_codigo_ot(self):
        return f"OT-{max(int(o['codigo'][3:]) for o in self.ordenes) + 1}"

    def piezas_pendientes(self, material_id):
        pendientes = {o["id"]: o["codigo"] for o in self.ordenes if o["estado"] == "pendiente"}
        return [
            {"id": p["id"], "ot": pendientes[p["orden_id"]], "largo_mm": p["largo_mm"],
             "cantidad": p["cantidad"]}
            for p in self.piezas
            if p["material_id"] == material_id and p["orden_id"] in pendientes
        ]

    def plan_vigente(self, material_id):
        plan = self.planes.get(material_id)
        return {k: plan[k] for k in ("barras_usadas", "aprovechamiento_pct")} if plan else None

    def insertar_ot(self, codigo, cliente, descripcion, fecha_entrega, mensaje_original,
                    piezas, materiales):
        orden_id = len(self.ordenes) + 1
        self.ordenes.append({
            "id": orden_id, "codigo": codigo, "cliente": cliente, "descripcion": descripcion,
            "fecha_entrega": fecha_entrega, "estado": "pendiente", "origen": "agente",
            "mensaje_original": mensaje_original,
        })
        for p in piezas:
            self.piezas.append({
                "id": len(self.piezas) + 1, "orden_id": orden_id,
                "material_id": materiales[p.material]["id"], "largo_mm": p.largo_mm,
                "cantidad": p.cantidad,
            })
        return orden_id

    def guardar_plan(self, material_id, motivo, plan, metricas, antes):
        self.planes[material_id] = {**metricas, "aprovechamiento_pct": metricas["aprovechamiento_pct"],
                                    "motivo": motivo, "plan": plan, "antes": antes}


@pytest.fixture
def config():
    """Configuración real, leída de los .md del repositorio."""
    return cargar_agente()


@pytest.fixture
def repo():
    return RepositorioEnMemoria()
