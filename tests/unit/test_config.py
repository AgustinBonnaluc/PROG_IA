"""Pruebas unitarias de la carga declarativa del agente y sus skills."""

import textwrap

import pytest

from runner.config import ErrorConfiguracion, cargar_agente, cargar_skill, extraer_seccion


def _escribir(ruta, texto):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(textwrap.dedent(texto).lstrip(), encoding="utf-8")
    return ruta


def _agente_md(tmp_path, host="http://localhost:11434", temperatura=0, skills="[eco]"):
    return _escribir(tmp_path / "prueba.agent.md", f"""
        ---
        name: prueba
        description: agente de prueba
        modelo:
          proveedor: ollama
          nombre: modelo-x
          host: {host}
          parametros:
            temperature: {temperatura}
        skills: {skills}
        ---
        cuerpo
        """)


def _skill_llm(tmp_path, nombre="eco"):
    return _escribir(tmp_path / "skills" / nombre / "SKILL.md", f"""
        ---
        name: {nombre}
        description: repite
        tipo: llm
        ---
        ## Prompt
        Repetí el mensaje.
        """)


# ── el agente real del repositorio ───────────────────────────────────

def test_carga_el_agente_real_con_sus_parametros(config):
    # Arrange: la fixture lee agente/ingreso-ot.agent.md

    # Act
    modelo = config.modelo

    # Assert
    assert modelo.nombre == "qwen2.5:7b"
    assert modelo.parametros["temperature"] == 0
    assert modelo.parametros["seed"] == 42
    assert set(config.skills) == {"interpretar-pedido", "planificar-corte", "generar-pruebas"}


def test_skill_llm_real_tiene_prompt_y_esquema(config):
    # Arrange / Act
    skill = config.skill("interpretar-pedido")

    # Assert
    assert skill.tipo == "llm"
    assert "Catálogo de materiales" in skill.prompt
    assert "## Rol" not in skill.prompt  # solo se envía la sección Prompt
    assert skill.esquema["required"] == ["tipo", "cliente", "fecha_entrega_texto", "piezas"]


def test_skill_herramienta_real_resuelve_su_funcion(config):
    # Arrange
    skill = config.skill("planificar-corte")

    # Act
    funcion = skill.funcion()

    # Assert
    assert funcion.__name__ == "planificar_corte"


def test_pedir_una_skill_no_habilitada_lanza_error(config):
    # Arrange / Act / Assert
    with pytest.raises(ErrorConfiguracion, match="no está habilitada"):
        config.skill("borrar-base")


def test_la_configuracion_es_inmutable(config):
    # Arrange / Act / Assert
    with pytest.raises(TypeError):
        config.modelo.parametros["temperature"] = 1


# ── validaciones de estructura ───────────────────────────────────────

def test_extrae_solo_la_seccion_pedida():
    # Arrange
    cuerpo = "## Rol\nanalista\n\n## Prompt\nhacé esto\n\n## Notas\notra cosa"

    # Act
    seccion = extraer_seccion(cuerpo, "Prompt")

    # Assert
    assert seccion == "hacé esto"


def test_rechaza_archivo_sin_frontmatter(tmp_path):
    # Arrange
    ruta = _escribir(tmp_path / "skills" / "eco" / "SKILL.md", "# Sin frontmatter\n")

    # Act / Assert
    with pytest.raises(ErrorConfiguracion, match="frontmatter"):
        cargar_skill(ruta)


def test_rechaza_skill_llm_sin_prompt(tmp_path):
    # Arrange
    ruta = _escribir(tmp_path / "skills" / "eco" / "SKILL.md", """
        ---
        name: eco
        description: x
        tipo: llm
        ---
        ## Rol
        nada
        """)

    # Act / Assert
    with pytest.raises(ErrorConfiguracion, match="## Prompt"):
        cargar_skill(ruta)


def test_rechaza_nombre_que_no_coincide_con_la_carpeta(tmp_path):
    # Arrange
    ruta = _skill_llm(tmp_path, nombre="eco")
    destino = tmp_path / "skills" / "otra" / "SKILL.md"
    destino.parent.mkdir(parents=True)
    ruta.rename(destino)

    # Act / Assert
    with pytest.raises(ErrorConfiguracion, match="no coincide"):
        cargar_skill(destino)


def test_rechaza_skill_declarada_que_no_existe(tmp_path):
    # Arrange
    ruta = _agente_md(tmp_path, skills="[inexistente]")

    # Act / Assert
    with pytest.raises(ErrorConfiguracion, match="no existe"):
        cargar_agente(ruta)


@pytest.mark.parametrize("temperatura", [-1, 3, "'alta'"])
def test_rechaza_temperatura_fuera_de_rango(tmp_path, temperatura):
    # Arrange
    _skill_llm(tmp_path)
    ruta = _agente_md(tmp_path, temperatura=temperatura)

    # Act / Assert
    with pytest.raises(ErrorConfiguracion, match="temperature"):
        cargar_agente(ruta)


# ── seguridad de la configuración ────────────────────────────────────

@pytest.mark.parametrize("host", ["https://api.ejemplo.com", "http://192.168.0.10:11434",
                                  "ftp://localhost"])
def test_rechaza_host_del_modelo_que_no_es_local(tmp_path, host):
    # Arrange
    _skill_llm(tmp_path)
    ruta = _agente_md(tmp_path, host=host)

    # Act / Assert
    with pytest.raises(ErrorConfiguracion, match="debe ser local"):
        cargar_agente(ruta)


@pytest.mark.parametrize("entrypoint", ["os:system", "subprocess:run", "runner.herramientas"])
def test_rechaza_entrypoint_fuera_del_paquete(tmp_path, entrypoint):
    # Arrange
    ruta = _escribir(tmp_path / "skills" / "peligrosa" / "SKILL.md", f"""
        ---
        name: peligrosa
        description: x
        tipo: herramienta
        entrypoint: {entrypoint}
        ---
        """)

    # Act / Assert
    with pytest.raises(ErrorConfiguracion, match="no permitido"):
        cargar_skill(ruta)


def test_yaml_con_etiqueta_de_python_no_ejecuta_codigo(tmp_path):
    # Arrange: con yaml.load() inseguro esto ejecutaría un comando del sistema
    ruta = _escribir(tmp_path / "skills" / "eco" / "SKILL.md", """
        ---
        name: !!python/object/apply:os.system ["echo hackeado"]
        description: x
        tipo: llm
        ---
        """)

    # Act / Assert
    with pytest.raises(ErrorConfiguracion, match="YAML inválido"):
        cargar_skill(ruta)
