---
name: planificar-corte
description: Recalcula el plan de corte de los materiales indicados con OR-Tools y lo guarda con el antes y el después.
tipo: herramienta
entrypoint: runner.herramientas:planificar_corte

entradas:
  materiales: Códigos de material a replanificar (vacío = todos).
  motivo: Texto corto que queda registrado en el plan, por ejemplo "Ingreso OT-108".

salidas:
  formato: lista
  campos: [material, barras_antes, barras_despues, aprovechamiento_antes, aprovechamiento_despues, estado_solver]
---

# Skill: planificar-corte

## Rol

Planificador de corte de la planta.

## Objetivo

Dado el conjunto de OT pendientes, minimizar la cantidad de barras de 6 m que
hay que cortar, consolidando piezas de distintas OT en una misma barra.

## Entradas y salidas

- **Entradas:** códigos de material y motivo del recálculo.
- **Salida:** por material, barras y aprovechamiento antes y después.

## Restricciones

- Es una herramienta determinista: no usa el LLM. Reutiliza el optimizador
  CP-SAT del Parcial 1 (`corte/`).
- Solo considera OT en estado `pendiente`.
- Cada pieza consume su largo más el kerf de la sierra (`parametros_planta`).
- El solver tiene un tope de 30 s por material (en la práctica resuelve en
  pocos segundos); si no demuestra el óptimo, devuelve la mejor solución
  encontrada y lo informa en `estado_solver`.
- El plan anterior del material se reemplaza dentro de una transacción: o se
  guarda el plan nuevo completo, o queda el anterior.
