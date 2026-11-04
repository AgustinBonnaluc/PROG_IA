# Agente de ingreso de órdenes de trabajo

**Parcial 2 · Programación con IA Generativa**
Autor: Agustín Bonnaluc

> El Parcial 1 (optimizador de cortes con servidores MCP) está en
> [`parcial-1/`](parcial-1/), con su propio README, tal como se entregó.

## Descripción

Continuación del Parcial 1, donde se optimizó el corte de perfiles de acero de
una metalúrgica. Ese flujo partía de órdenes de trabajo (OT) ya cargadas en la base. 
En la práctica, los pedidos llegan por WhatsApp o por mail, escritos como habla cada cliente:

> *"Hola, soy de Taller Mecánico Ferraro. Necesito 4 patas de 90 cm en caño de
> 40 y 2 cabezales de 70 cm del mismo caño. Lo necesito para el viernes."*

Este proyecto agrega un **agente local** que lee esos mensajes, los convierte
en OT validadas, las registra en Supabase y recalcula el plan de corte
mostrando cuántas barras extra implica cada pedido.

## Arquitectura

```
Mensaje del cliente
   │
   ▼
Agente ingreso-ot  (agente/ingreso-ot.agent.md)
   │
   ├─ skill interpretar-pedido  [LLM]   qwen2.5:7b en Ollama, temperature 0, seed 42
   │      salida: JSON con esquema fijo (cliente, fecha, piezas)
   │
   ├─ validación en Python      [sin LLM]
   │      unidades → mm · materiales del catálogo · límites · fecha · faltantes
   │
   ├─ ¿completo? ── no ──► no se guarda nada; se informa qué preguntarle al cliente
   │      │
   │      sí
   │      ▼
   ├─ Supabase (Postgres): INSERT parametrizado de la OT y sus piezas
   │
   └─ skill planificar-corte    [herramienta]  OR-Tools CP-SAT (código del Parcial 1)
          guarda el plan nuevo con el antes y el después
                │
                ▼
          Panel web (Flask) se actualiza solo
```

La skill **generar-pruebas** se invoca aparte: el agente redacta borradores de
tests pytest que una persona revisa antes de incorporarlos.

### Decisiones de diseño

| Decisión | Motivo |
|---|---|
| Modelo local (Ollama) | Los pedidos de clientes no salen de la PC. |
| `temperature: 0` y `seed: 42` | Mismo mensaje, misma respuesta: se comprueba con `python -m runner repetir`. |
| Salida con esquema JSON | Ollama restringe la generación al esquema; el modelo no puede responder otra cosa. |
| El LLM no convierte unidades ni decide si el pedido está completo | Las cuentas y las reglas se hacen en Python, que no se equivoca. Python puede ser más estricto que el modelo, nunca más permisivo. |
| El LLM no tiene acceso a la base | En el Parcial 1 el agente escribía en Supabase vía MCP con permisos amplios. Acá el modelo solo devuelve datos; las escrituras las hace el código con consultas parametrizadas (mínimo privilegio). |
| Una sola llamada al LLM por pedido | En CPU cada llamada tarda entre 30 y 80 s; el campo `tipo` del JSON cumple el rol de enrutador. |

## Agente y skills

Toda la configuración es declarativa, en Markdown con frontmatter YAML. Para
cambiar el modelo, sus parámetros o el prompt se edita el `.md`, no el código.

| Archivo | Contenido |
|---|---|
| `agente/ingreso-ot.agent.md` | Rol, objetivo, flujo y restricciones. Frontmatter: modelo, host, parámetros de inferencia, skills habilitadas y límites. |
| `agente/skills/interpretar-pedido/SKILL.md` | Skill LLM. Frontmatter: entradas y esquema JSON de salida. Cuerpo: rol, objetivo, restricciones y la sección `## Prompt` que se envía al modelo. |
| `agente/skills/planificar-corte/SKILL.md` | Skill herramienta. Frontmatter: `entrypoint` a la función Python, entradas y salidas. |
| `agente/skills/generar-pruebas/SKILL.md` | Skill LLM con parámetros propios (`num_ctx`, `num_predict`) que se combinan con los del agente. |

`runner/config.py` lee y valida estos archivos: campos obligatorios, que el
nombre coincida con la carpeta, rango de temperatura, que el host del modelo
sea local y que el `entrypoint` apunte al paquete `runner`.

## Estructura

```
corte-ot-agente/
├── README.md
├── requirements.txt
├── pyproject.toml              # configuración de pytest y bandit
├── .env.example                # plantilla de la cadena de conexión
├── agente/                     # definición declarativa del agente y sus skills
├── runner/                     # ejecuta el agente
│   ├── __main__.py             # consola: python -m runner ...
│   ├── config.py               # lectura y validación de los .md
│   ├── llm.py                  # cliente de Ollama
│   ├── pedido.py               # validación de la salida del LLM
│   ├── repositorio.py          # SQL parametrizado sobre Supabase
│   ├── herramientas.py         # skill planificar-corte
│   └── agente.py               # orquestación
├── corte/                      # optimizador del Parcial 1, con dos errores corregidos
├── db/seed.sql                 # esquema y datos (idempotente)
├── web/                        # panel de solo lectura
├── pedidos/                    # mensajes de ejemplo para la demo
└── tests/
    ├── conftest.py             # LLM falso y repositorio en memoria
    ├── unit/                   # validación, optimizador, pedido, configuración
    └── integration/            # flujo completo, cliente Ollama, SQL, generar-pruebas
├── borradores/                 # tests redactados por la skill generar-pruebas
└── parcial-1/                  # entrega del Parcial 1
```

## Requisitos previos

- Python 3.11 o superior
- [Ollama](https://ollama.com/download) con el modelo `qwen2.5:7b` (unos 4,7 GB)
- Un proyecto de Supabase dedicado a la demo

## Puesta en marcha

**1. Modelo local.**

```powershell
ollama pull qwen2.5:7b
```

**2. Entorno de Python** (PowerShell, de a un comando):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Si la activación falla por las directivas de ejecución:
`Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`.

**3. Base de datos.** En el SQL Editor de Supabase ejecutar `db/seed.sql`
completo. Crea las tablas y carga los datos; la consulta final devuelve tres
filas, una por material. Se puede volver a ejecutar para resetear la demo.

**4. Conexión.** Copiar `.env.example` a `.env` y pegar la cadena de conexión
(botón *Connect* del dashboard, pestaña *Session pooler*), reemplazando
`[YOUR-PASSWORD]` por la contraseña de la base.

**5. Plan inicial y panel.**

```powershell
python -m runner planificar
python web/app.py
```

Abrir http://127.0.0.1:8090. El panel se actualiza solo cada 4 segundos. Si el
puerto está ocupado, se puede cambiar con la variable `PUERTO_PANEL`.

## Uso

```powershell
# Configuración cargada desde los .md
python -m runner skills

# Procesar un pedido
python -m runner pedido --archivo pedidos/01_normal.txt
python -m runner pedido "Hola, soy de ... necesito ..."

# Repetibilidad: el mismo mensaje varias veces debe dar la misma huella
python -m runner repetir --archivo pedidos/01_normal.txt -n 3

# Borrador de tests generado por el agente (queda en borradores/)
python -m runner pruebas corte/validacion.py --funcion validar_piezas --contexto corte/modelos.py
```

| Pedido de ejemplo | Resultado esperado |
|---|---|
| `01_normal.txt` | OT registrada; el plan de caño se recalcula. |
| `02_unidades_mixtas.txt` | Metros y milímetros convertidos; se replanifican ángulo y planchuela. |
| `03_ambiguo.txt` | No se registra; el agente indica que faltan cliente y medidas. |
| `04_malicioso.txt` | Se ignora la orden inyectada; el texto con SQL no afecta la base. |
| `05_no_es_pedido.txt` | No se registra nada. |

## Pruebas

```powershell
python -m pytest -v
```

Las pruebas no necesitan Ollama ni Supabase: usan un LLM falso y un
repositorio en memoria (`tests/conftest.py`), así que corren en segundos y
siempre dan el mismo resultado. Todas siguen el patrón AAA.

| Tipo | Archivo | Qué cubre |
|---|---|---|
| Unitarias | `unit/test_validacion.py` | Límites exactos, kerf negativo o infinito, cantidades no enteras o enormes. |
| Unitarias | `unit/test_optimizador.py` | Pruebas del Parcial 1 y regresiones de los errores corregidos. |
| Unitarias | `unit/test_pedido.py` | Conversión de unidades, fechas ("viernes", "15/11"), piezas descartadas, faltantes. |
| Unitarias | `unit/test_config.py` | Lectura de los `.md` y rechazo de configuraciones inválidas o inseguras. |
| Integradas | `integration/test_flujo_agente.py` | Mensaje → OT → plan, con config real y optimizador real. |
| Integradas | `integration/test_cliente_ollama.py` | Petición HTTP armada con los parámetros del `.agent.md` (red simulada). |
| Integradas | `integration/test_repositorio_sql.py` | Valores como parámetros, nunca dentro del SQL; rollback ante fallas. |
| Integradas | `integration/test_generar_pruebas.py` | Borradores sin texto extra, sintaxis válida, sin lectura fuera del proyecto. |

## Seguridad

Análisis estático:

```powershell
python -m bandit -c pyproject.toml -r runner corte web
```

Resultado: sin hallazgos. El mismo análisis sobre el panel del Parcial 1 marcaba
un problema de severidad alta (`B201`: Flask con `debug=True`, que expone el
depurador de Werkzeug y permite ejecutar código), corregido en esta versión.
Para reproducir la comparación:

```powershell
python -m bandit -r parcial-1/web parcial-1/corte
```

| Riesgo | Mitigación | Prueba |
|---|---|---|
| Inyección SQL desde el mensaje del cliente | Consultas parametrizadas (`%s`); el texto nunca se concatena. | `test_repositorio_sql.py` |
| Inyección de instrucciones al LLM ("ignorá tus instrucciones...") | El prompt trata el mensaje como dato; si el modelo igual obedece, la validación en Python rechaza valores fuera de rango y no se guarda nada. | `test_inyeccion_que_engana_al_modelo_igual_se_bloquea` |
| XSS en el panel (un nombre como `<img onerror=...>`) | Todo texto de la base se escapa antes de insertarse en el HTML; cabecera `Content-Security-Policy`. | Revisión del panel |
| Cantidades enormes que agotan la memoria del solver | Tope `MAX_CANTIDAD` en Python y `CHECK` en la base. | `test_rechaza_cantidad_mayor_al_maximo` |
| YAML malicioso en un `.md` | `yaml.safe_load`, que no instancia objetos de Python. | `test_yaml_con_etiqueta_de_python_no_ejecuta_codigo` |
| Skill que apunta a una función peligrosa (`os:system`) | Solo se aceptan `entrypoint` del paquete `runner`. | `test_rechaza_entrypoint_fuera_del_paquete` |
| Fuga de datos de clientes a terceros | El host del modelo debe ser local. | `test_rechaza_host_del_modelo_que_no_es_local` |
| La skill generar-pruebas lee secretos (`.env`) | Solo lee archivos `.py` dentro del proyecto; el código generado no se ejecuta. | `test_no_lee_archivos_fuera_del_proyecto_o_que_no_son_py` |
| Credenciales en el repositorio | La cadena de conexión vive en `.env`, excluido por `.gitignore`. | — |
| Depurador de Flask expuesto | Desactivado salvo `FLASK_DEBUG=1`; el panel escucha solo en `127.0.0.1`. | — |

### Errores corregidos del Parcial 1

Al escribir casos borde aparecieron dos errores en el optimizador:

1. **Redondeo del kerf.** CP-SAT trabaja con enteros y el código usaba
   `round()`. Con un kerf de 0,5 mm, dos piezas de 3000 mm (6001 mm reales)
   "entraban" en una barra de 6000 mm. Ahora las piezas se redondean hacia
   arriba y la barra hacia abajo.
2. **Kerf negativo sin validar.** Con `kerf_mm = -1000`, el optimizador ubicaba
   7500 mm de piezas en una barra de 6000 mm. Ahora se rechaza.

## Panel web

Mejoras respecto del Parcial 1:

- Las OT ingresadas por el agente se marcan y muestran el mensaje original del cliente.
- Cada plan muestra el impacto del último recálculo ("Ingreso OT-108: +1 barra").
- Las piezas de OT del agente se resaltan dentro de las barras.
- Se actualiza solo y destaca las OT nuevas, sin recargar la página.
- Escapa todos los textos (XSS) y cierra las conexiones a la base, que antes quedaban abiertas.
