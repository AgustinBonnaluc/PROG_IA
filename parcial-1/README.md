# Planificación de cortes para órdenes de trabajo

**Parcial 1 · Programación con IA Generativa**
Autor: Agustín Bonnaluc

## Descripción

Caso hipotético inspirado en un proyecto real de optimización para una empresa metalúrgica. Se toma un único problema del dominio, la planificación del corte de perfiles de acero para cumplir las órdenes de trabajo (OT), y se lo resuelve de punta a punta con un flujo asistido por IA en Google Antigravity, integrando dos servidores MCP.


## Supuestos del modelo

| Supuesto | Valor |
|---|---|
| Largo de barra comercial | 6000 mm (por material, tabla `materiales`) |
| Kerf de la sierra | 3 mm (tabla `parametros_planta`) |
| Consumo por pieza | largo de la pieza + kerf (modelo conservador) |
| Alcance | Solo OT en estado `pendiente` |

Todos los datos (clientes, OT, piezas) son ficticios.

## Arquitectura

```
Agente de Antigravity (cliente MCP)
 ├── MCP Supabase (remoto)  →  Postgres: materiales, OT, piezas, parámetros, planes de corte
 └── MCP local mcp_corte    →  Optimizador OR-Tools (servicio de cómputo sin estado)
```

El servidor local no se conecta a la base: recibe las piezas como parámetro y devuelve el plan. De esta forma no necesita credenciales y la persistencia queda centralizada en el MCP de Supabase.

## Código inicial y código final

Ambos estados conviven en esta entrega, en carpetas separadas:

| | Carpeta | Qué contiene |
|---|---|---|
| **Inicial** | `legacy/` | `corte_manual.py`, el planificador tal como estaba antes de la asistencia de IA: un único script con los datos embebidos, llenado secuencial por OT, sin considerar el kerf y sin pruebas. Se conserva sin modificar. |
| **Final** | `corte/`, `mcp_corte/`, `tests/` | El resultado del flujo asistido: lógica separada en módulos, optimizador con OR-Tools, servidor MCP y pruebas automatizadas. |

La comparación se puede reproducir ejecutando ambos (ver Puesta en marcha): el script inicial informa 19 barras y 72,3 % de aprovechamiento, con tres barras que en la práctica no cierran por el kerf; el optimizado usa 15 barras y alcanza 91,5 %.

## Estructura

```
corte-ot-metalurgica/
├── README.md
├── requirements.txt
├── .env.example                # plantilla de la cadena de conexión
├── mcp_config.example.json     # configuración MCP sin credenciales
├── db/
│   └── seed.sql                # esquema y datos (idempotente)
├── legacy/
│   └── corte_manual.py         # código inicial
├── web/                        # panel web de solo lectura
│   ├── app.py
│   └── templates/index.html
├── corte/                      # código final: dominio, validación, optimizador, métricas
├── mcp_corte/
│   └── servidor.py             # código final: servidor MCP local con FastMCP
└── tests/                      # código final: pruebas con pytest
```

## Panel web

`web/app.py` es un servicio Flask de **solo lectura** sobre la misma base. No calcula nada: muestra las órdenes de trabajo con sus piezas y dibuja cada barra del plan de corte como una franja con sus piezas a escala, coloreadas según la OT de origen. Sirve para ver el efecto de la optimización sin leer tablas SQL: antes de correr el agente no hay planes, después aparecen las barras llenas.


## Requisitos previos

- Python 3.11 o 3.12
- Google Antigravity
- Cuenta de Supabase con un proyecto dedicado a esta demo
- Dependencias de Python: `ortools`, `mcp` (serie 1.x), `flask`, `psycopg2-binary`, `python-dotenv` y `pytest` (ver `requirements.txt`)

## Puesta en marcha

**1. Base de datos.** Crear un proyecto en Supabase, abrir el SQL Editor y ejecutar `db/seed.sql` completo. El script crea las tablas y carga los datos; no hace falta preparar nada antes. La consulta final debe devolver tres filas, una por material. Puede volver a ejecutarse en cualquier momento para resetear la demo.

**2. Entorno de Python** (PowerShell, ejecutar los comandos de a uno):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Si la activación falla por las directivas de ejecución, habilitarlas solo para esta sesión con `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`.

**3. Servidores MCP.** En Antigravity: *Settings → Customizations → Open MCP Config*. Copiar el contenido de `mcp_config.example.json`, reemplazar `TU_PROJECT_REF` por el Project ID de Supabase y ajustar las rutas absolutas del servidor local. Guardar, pulsar *Refresh* y autenticar Supabase con el flujo OAuth que se abre en el navegador.

**4. Panel web.** Copiar `.env.example` a `.env` y pegar la cadena de conexión de Supabase (botón *Connect* del dashboard, pestaña *Session pooler*). Reemplazar `[YOUR-PASSWORD]`, **corchetes incluidos**, por la contraseña de la base. Luego:

```powershell
python web/app.py
```

Abrir http://127.0.0.1:8080.

**5. Código inicial.**

```powershell
python legacy/corte_manual.py
```

**6. Código final.**

```powershell
pytest -v
```

## Seguridad

- La configuración MCP no contiene credenciales: Supabase se autentica por OAuth.
- El servidor de Supabase está acotado a un único proyecto (`project_ref`) y a los grupos de herramientas `database` y `docs`.
- Se usa un proyecto de Supabase exclusivo para la demo, dado que el flujo requiere operaciones de escritura.
- La cadena de conexión del panel vive en `.env`, que está excluido de la entrega; solo se incluye `.env.example`.
