# Intelliprint — Plan del proyecto

Plan de implementación del sistema descrito en [SISTEMA_MULTIAGENTE.md](SISTEMA_MULTIAGENTE.md). Está organizado en fases incrementales: cada fase termina con algo que funciona de extremo a extremo y se puede probar imprimiendo una pieza real.

---

## 1. Objetivo y alcance

**Objetivo:** que a partir de un requerimiento en lenguaje natural el sistema produzca un diseño mecánico multipieza, ensamblado, probado y laminado, listo para imprimir en FDM, usando modelos locales y DeepSeek solo como respaldo — y que pueda consultarte y recibir cambios tuyos por Telegram mientras trabaja.

**Dentro del alcance**

- Orquestador multiagente en Docker (LangGraph).
- Modelos locales vía Ollama; escalamiento a DeepSeek con tope de costo.
- Integración con los MCP existentes de FreeCAD y PrusaSlicer (en el host).
- MCP nuevos: `mech-toolkit` (geometría/tolerancias/DFM) y `sim` (cinemática y colisiones).
- Librería de hardware comercial.
- `HumanPort` con tres adaptadores: CLI, UI web mínima y **Telegram vía OpenClaw**, para **crear proyectos** (`submit`), aprobar gates, recibir consultas con imágenes y pedir cambios a distancia.
- **Fase de admisión conversacional**: el sistema pregunta lo que falte antes de empezar a diseñar, aceptando fotos, croquis y medidas.
- **Multiproyecto**: registro global, proyectos de clases distintas (`static_part`, `mechanism`, `robot`) conviviendo, con fases condicionales según la clase.
- Proyectos de referencia: soporte NEMA17 y soporte de vaso (`static_part`), garra con MG996R (`mechanism`), brazo de 3 GDL y brazo de 6 GDL (`robot`).
- **Probar el control ROS 2 del robot en Gazebo antes de imprimir** (ADR-017): el código lo escribe la persona; el sistema le da el robot simulado con el par real de sus servos, un informe y un vídeo.

**Fuera del alcance (por ahora)**

- Diseño de PCB y firmware (solo se reservan espacios y rutas de cables). El **control en ROS 2 sí entra** (ADR-017); el firmware del microcontrolador que hace de puente a los servos, no.
- Análisis FEM completo (se usan reglas y cálculos estáticos simples).
- Impresoras distintas de las configuradas en `config/printers/`.
- Envío automático a la impresora: la impresión la lanza siempre el humano.

---

## 2. Supuestos y prerrequisitos

| # | Supuesto | Cómo verificarlo |
|---|----------|------------------|
| S1 | Windows 11 con Docker Desktop (backend WSL2) | `docker version` |
| S2 | GPU NVIDIA visible en Docker | `docker run --rm --gpus all nvidia/cuda:12.8.0-base-ubuntu22.04 nvidia-smi` |
| S3 | MCP de FreeCAD y PrusaSlicer funcionando en el host | Ya probados por el usuario |
| S4 | `DEEPSEEK_API_KEY` definida en `.env` (no versionado) | Obligatoria con el perfil `dev`; opcional con `prod`, solo para escalamiento |
| S5 | Python 3.11+ y `uv` en el host para los puentes MCP | `python --version`, `uv --version` |
| S6 | Impresora y material de referencia: **AnkerMake M5 + PETG** | `config/printers/ankermake_m5_petg.yaml`. Cama 235×235×250, boquilla 0.4, extrusor directo |
| S7 | `freecadcmd` disponible para construcción headless | `freecadcmd -c "print(1)"` responde |
| S8 | Bot de Telegram creado y chat ID propio conocido | `TELEGRAM_BOT_TOKEN` y `TELEGRAM_ALLOWED_USERS` definidas |

### 2.1 Hardware confirmado

| Recurso | Valor |
|---------|-------|
| GPU | RTX 5090 — **32 GB VRAM** (Blackwell, `sm_120`) |
| RAM del sistema | 92 GB |

Con 32 GB caben **los dos modelos residentes a la vez** (§ 6.1 de la arquitectura):

| Modelo | Rol | VRAM |
|--------|-----|------|
| `qwen3.8` (27B, con visión) | Diseño, todos los roles salvo QA | 16.5 GB |
| `gemma3:12b` | QA (revisor distinto, con visión) | ~8 GB |
| `nomic-embed-text` | Embeddings para RAG | ~0.3 GB |
| **Total** | | **~25 GB de 32 GB** |

Requiere `OLLAMA_MAX_LOADED_MODELS=2`.

> ⚠️ **Blackwell necesita CUDA 12.8+ y una versión reciente de Ollama.** Una versión antigua no da error: **cae a CPU en silencio**. Verificarlo explícitamente en F0.3 — si no, vas a pasar horas creyendo que el modelo es lento.

Los 92 GB de RAM hacen que el consumo de los contenedores (`mech-toolkit`, `sim`, `qdrant`, `openclaw`) sea irrelevante en la planificación.

---

## 3. Resumen de fases

| Fase | Nombre | Resultado | Semanas |
|------|--------|-----------|---------|
| 0 | Infraestructura | Docker + Ollama + puentes MCP + esqueleto del orquestador | 1 |
| 1 | Pipeline de una pieza | Contratos, admisión mínima, receta → `build.py` → STL → laminado | 4 |
| 2 | Herramientas deterministas y QA | `mech-toolkit`, librería de hardware, QA de tres capas, escotilla | 4 |
| 3 | Descomposición y ensamble | Varias piezas en paralelo, interfaces, ensamble e interferencias | 3 |
| 4 | Ingeniería de sistema y simulación | Cinemática, actuación, electrónica, `sim`, fases condicionales | 3 |
| 5 | Multiproyecto y canal humano | Registro, admisión conversacional, web y Telegram, escalamiento | 4 |
| 6 | Endurecimiento | Evaluaciones, métricas, documentación, brazo de 6 GDL | 2 |
| 7 | Proyectos por partes | Obras: árbol de piezas, cada una diseñada contra la ficha de las anteriores | — |
| 8 | Kits para montar | El usuario imprime el kit; sale con compras, instrucciones, coste por kit y avisos para niños (ADR-019) | — |

| Semana | 1 | 2–5 | 6–9 | 10–12 | 13–15 | 16–19 | 20–21 |
|---|---|---|---|---|---|---|---|
| **Fase** | 0 | 1 | 2 | 3 | 4 | 5 | 6 |

Estimado para dedicación parcial (~10–15 h/semana). Total: **21 semanas**.

> **De 15 a 21 semanas, en dos saltos y por motivos distintos.**
>
> De 15 a 19 fue **alcance nuevo**: admisión conversacional, registro multiproyecto, clases de producto, `HumanPort` con tres adaptadores y Telegram.
>
> De 19 a 21 fue **trabajo que faltaba en el plan** y salió al construir las primeras tareas: el puente entre aserciones y mediciones, el perfil de laminado de PrusaSlicer, la escotilla de Python, la conversión de spec a tarea de pieza, la procedencia de los datos, la validez del sólido y el entorno de desarrollo. No es alcance añadido: son pasos que siempre hicieron falta y no estaban escritos.

**Las fases 3 y 4 no son estrictamente secuenciales para la clase `robot`.** La resolución de interfaces necesita la cinemática (§ 5), así que la Fase 3 se cierra con `static_part` y `mechanism` —el entregable es la garra— y el `robot` completo no cierra hasta la Fase 4. Por eso los hitos H3 y H4 son de clases distintas.

---

## 4. Fases en detalle

Convención de IDs: `F<fase>.<tarea>`. Cada tarea tiene un criterio de aceptación verificable.

**Los IDs son estables.** Una vez que el código, los tests y los commits los citan, renumerar deja referencias apuntando a la tarea equivocada. Una tarea que se mueve de fase recibe el siguiente ID libre de su fase nueva, y su ID antiguo se queda en la tabla como nota de adónde fue. Por eso una tabla puede no estar en orden numérico.

### Fase 0 — Infraestructura (semana 1)

**Objetivo:** que el contenedor del orquestador pueda llamar a un modelo local y a las herramientas de FreeCAD y PrusaSlicer.

| ID | Tarea | Criterio de aceptación |
|----|-------|------------------------|
| F0.1 | Crear estructura del repositorio (sección 12 de la arquitectura), `.gitignore` (excluir `workspace/`, `*.gcode`, logs) | `git status` limpio tras el primer commit |
| F0.2 | `docker-compose.yml` con `ollama`, `orchestrator` (vacío), `qdrant` | `docker compose up -d` levanta todo sin errores **Hecho (2026-09-20):** `docker-compose.yml` con orchestrator, suite, web, intelliprint-mcp, crafty-config, crafty y ollama (opcional). Sin `qdrant`: F2.19 no existe y un servicio que no usa nadie es ruido. |
| F0.3 | Habilitar GPU en Ollama (CUDA 12.8+, `OLLAMA_MAX_LOADED_MODELS=2`) y descargar `qwen3.8` y `gemma3:12b` | Ambos responden; `nvidia-smi` muestra **~25 GB en uso y actividad en la GPU durante la inferencia**. Prueba negativa explícita: confirmar que NO está cayendo a CPU |
| F0.4 | `scripts/start-host-mcps.ps1`: lanza `mcp-proxy` para FreeCAD (:8101) y PrusaSlicer (:8102) | `curl http://localhost:8101/sse` responde en el host **Hecho (2026-09-20), pero NO como estaba escrito:** el script existe y levanta un puente, aunque solo para **PrusaSlicer** (:8102). FreeCAD no lo necesita: va dentro del contenedor (ADR-014). Y no usa `mcp-proxy`: es un MCP propio, `scripts/host_bridge.py`, que comprueba rutas y resuelve el perfil por nombre. |
| F0.5 | Cliente MCP en `orchestrator/mcp/client.py` (HTTP/SSE) | Desde el contenedor se listan las herramientas de ambos MCP **Hecho (2026-09-20):** `orchestrator/mcp/client.py`, síncrono (el orquestador no es async) y con transporte streamable-http. «Ambos MCP» se quedó en uno: el de FreeCAD no llegó a hacer falta. |
| F0.6 | `orchestrator/llm/router.py` con proveedor local y DeepSeek (defaults para `DEEPSEEK_BASE_URL` y `DEEPSEEK_MODEL`) | Test que llama a cada proveedor y devuelve texto; si falta la API key, DeepSeek queda deshabilitado sin romper |
| F0.7 | Traducción de rutas contenedor ↔ host (`WORKSPACE` ↔ `HOST_WORKSPACE`) | Un archivo creado en `/workspace/test.txt` es abierto por FreeCAD vía MCP **Hecho (2026-09-20):** `orchestrator/hostpaths.py`. Solo traduce lo que está DENTRO del workspace; lo de fuera es error, no un caso a resolver. |
| F0.8 | Logging estructurado (JSONL) de cada llamada a LLM y herramienta | Cada llamada deja una línea en `workspace/<proyecto>/log/` |
| F0.9 | `HumanPort` con el adaptador CLI (§ 8.5 de la arquitectura): `ask()` y `notify()` | Un `ask()` desde el orquestador bloquea, se responde por consola y el estado se persiste |
| F0.10 | Verificar `freecadcmd` headless: ejecutar una macro y exportar STL sin GUI | Un cubo se construye y exporta desde un proceso sin interfaz |
| F0.11 | **Migrar del perfil `dev` al `prod`** (§ 6.1.1 de la arquitectura) y **repasar todo lo desarrollado con DeepSeek** | `INTELLIPRINT_PROFILE=prod` y la suite completa en verde **con modelos locales**. Es donde van a salir los fallos que la nube tapó: `deepseek-chat` sigue esquemas mejor que `qwen3.8` |

**Entregable:** comando `docker compose run orchestrator python -m smoke_test` que crea un cubo en FreeCAD, exporta STL y lo lamina en PrusaSlicer, sin LLM.

**Riesgos:** GPU no disponible en WSL2 → plan B: Ollama nativo en Windows y `OLLAMA_URL=http://host.docker.internal:11434`.

> **Deuda declarada.** Mientras la 5090 no esté disponible se desarrolla con el perfil `dev` (DeepSeek en la nube, § 6.1.1). Incumple *local primero* a propósito y de forma temporal. **F0.11 es la tarea que salda esa deuda**, y no está hecha hasta que la suite pase con modelos locales.

---

### Deuda técnica declarada

Decisiones que desbloquean trabajo hoy incumpliendo algo del diseño, o que no se pueden cerrar sin un recurso que ahora no está disponible. Están aquí para que se vean juntas y no se conviertan en el estado permanente.

| Deuda | Qué incumple | La salda | Cuándo |
|---|---|---|---|
| Perfil `dev` con DeepSeek en la nube (ADR-007b) | *Local primero* (§ 1) | **F0.11** | **La 5090 ya está.** Ollama corre con la tarjeta y `qwen3.8` descargado; falta el cliente de Ollama y revalidar la suite con modelos locales. Es la deuda mayor que queda |
| Canal de Telegram **abierto**, sin lista blanca (ADR-012) | Regla 1 de § 8.5 | **F5.10** (hecha, opcional) | **Abierto por decisión del usuario (2026-09-21).** La lista existe pero es opcional; el 2026-09-20 se había hecho obligatoria sin su aprobación. Antes: `TELEGRAM_ALLOWED_USERS` es obligatoria y cierra los dos caminos: el bot propio y Crafty |
| Agujero M3 pasante de **3.3** en el perfil de la M5, sin validar | Es casi un ajuste *justo* de la ISO 273 (3.26), y contradice el `clearance_mm: 0.35` del mismo perfil (3.3 implica 0.3). La ISO 273 *normal* es 3.4 | **F2.18** (pieza de calibración) | Al tener la impresora. **2026-11-09:** el usuario lo apunta desde la web (F2.21 (impresora)); lo medido manda sobre el perfil sin tocar `config/` |
| ~~**El orquestador no habla MCP con FreeCAD**~~ | Era F0.4 y F0.5 | — | ✅ **RESUELTA de otra forma el 2026-09-20 (ADR-014).** FreeCAD va DENTRO del contenedor: no hace falta puente, porque el orquestador y `freecadcmd` están en el mismo sitio. El puente (`scripts/start-host-mcps.ps1` + `orchestrator/mcp/client.py`) SÍ se construyó, pero para **PrusaSlicer**, que se queda fuera a propósito |
| ~~**Todo corre nativo en macOS, no en contenedores**~~ | La fase 0 entera: F0.2 (`docker-compose.yml`), F0.4 (puentes MCP), F0.5 (cliente MCP desde el contenedor), F0.7 (traducción de rutas contenedor ↔ host) y § 8.4 de la arquitectura | **F0.2** y **F0.7** | ✅ **SALDADA el 2026-09-20** en la PC de la 5090 (Windows 11). Orquestador, suite, interfaz web, MCP y Crafty en contenedores; el puente a PrusaSlicer, en el host (ADR-014) |
| G-code de inicio de la M5 **no verificado** | Viene del perfil comunitario, no de una impresión real. La instantánea `tests/snapshots/m5_start_gcode.txt` lo marca `NO VERIFICADO` | Primera impresión real | Al tener la impresora |

> Sobre la de los contenedores, ahora saldada, conviene guardar por qué importaba: mientras el sistema solo existió como instalación hecha a mano en un ordenador, **mudarlo era trabajo manual y silencioso** —rutas absolutas, un LaunchAgent que solo existe en macOS, secretos copiados a mano—, y nada de eso lo verificaba un test. Era la deuda que más se parecía a volverse permanente, porque no duele hasta el día que cambias de máquina. Ese día llegó, y mudarla costó encontrar tres fallos que solo se ven al cambiar de sistema operativo: el corpus de referencia entregado con CRLF, un `.ps1` ilegible para PowerShell 5.1 y 19 tests rojos por el encoding por defecto de Windows.

> **Las dos últimas dependen de la impresora**, que no está disponible ahora. No se corrigen a ciegas: cambiar 3.3 por 3.4 sin imprimir sería sustituir un valor sin validar por otro igual de sin validar. El orden al tener la impresora: (1) revisar las cinco primeras líneas del G-code de inicio e imprimir algo pequeño; (2) imprimir la pieza de calibración (F2.18) y medir; (3) fijar `M3_through_mm` y las holguras con esas medidas, poner `calibrated: true` y marcar la instantánea como verificada.

> Sobre la de Telegram, ya saldada, la precisión que la justificaba: **un bot de Telegram no es local aunque corra en tu PC**. Hace *polling* contra los servidores de Telegram, que le entregan los mensajes de cualquiera desde cualquier sitio. Apagar la máquina protege; que sea "local" no. Mientras la deuda viva, quien encuentre el bot puede crear proyectos, gastar saldo de DeepSeek y **contestar las tres barreras** — incluida la que guarda la escotilla de Python.

---

### Fase 1 — Pipeline de una pieza (semanas 2–5)

**Objetivo:** primer flujo con LLM de extremo a extremo para una pieza simple, con los contratos que sostienen toda la arquitectura.

Un solo proyecto cada vez y una sola vía de entrada (consola). El multiproyecto y los canales llegan en la Fase 5; lo que **sí** está aquí desde el principio es la **barrera de admisión**, porque es estructural y retrofitarla después sería rehacer el grafo.

| ID | Tarea | Criterio de aceptación |
|----|-------|------------------------|
| F1.0 | Entorno de desarrollo: `pyproject.toml`, venv, dependencias, `pytest` configurado | `pytest` corre desde el repo limpio tras un solo comando de instalación |
| F1.1 | Esquemas Pydantic: `Spec` (**con `class`** y **procedencia por campo**, ver F1.2), `Interface` (`symbolic`/`resolved`), `Recipe`, `PartTask`, `PartResult`, `QaReport`, `SlicingReport` | Validación falla con mensajes claros; una interfaz simbólica con geometría y una resuelta sin ella se rechazan |
| F1.2 | **Procedencia de los datos**: cada campo de `spec.yaml` marca si lo dijo el usuario o lo estimó el modelo | Una spec con `payload_g` estimado queda distinguible de una con `payload_g` dicho por el usuario |
| F1.3 | Salida estructurada: JSON mode + validación + reintento con el error exacto | ≥ 90 % de respuestas válidas en 20 pruebas con `qwen3.8` |
| F1.4 | **Requirements Agent**: produce `spec.yaml`, **clasifica el producto** y **marca qué estimó** | 10 pedidos → specs válidas; clase correcta 10 de 10, incluidos soportes estáticos; los campos inventados quedan marcados como estimados |
| F1.5 | Estado `INTAKE` con **confirmación obligatoria**, vía `HumanPort` (adaptador CLI de F0.9) | Test estructural: **no existe camino de `INTAKE` a `DECOMPOSED` sin confirmación**. Intentarlo lanza error, no avanza |
| F1.6 | Plantillas de macros FreeCAD (sketch + pad + pocket + fillet, export STL/STEP) y `compose_build_script(recipe)` que las ensambla | Una receta produce un `build.py` que corre en `freecadcmd` y devuelve el volumen esperado del sólido |
| F1.7 | **Validez del sólido** en el epílogo de `build.py`: `Shape.isValid()` y número de sólidos esperado | Una booleana que deja una forma degenerada **falla al construir**, no tres fases después. Test con un caso de cara coincidente |
| F1.8 | *Movida a **F2.19**.* Era el RAG sobre la API de FreeCAD. Con ADR-002 el Part Designer ya no escribe Python de FreeCAD, así que el RAG solo sirve a la escotilla, y se fue con ella a la Fase 2 | — |
| F1.9 | **`Spec` → `PartTask`**: convertir la spec de una pieza en la tarea que recibe el Part Designer | El soporte NEMA17 se diseña desde `spec.yaml` **sin que nadie escriba el enunciado a mano** |
| F1.10 | **Part Designer Agent**: emite `recipe.json` (**no Python**); el orquestador compone `build.py` y lo ejecuta en `freecadcmd` | Soporte NEMA17 con dimensiones correctas en ≥ 4 de 5 intentos |
| F1.11 | Bucle de error en dos niveles: receta inválida → error de esquema al agente (barato, sin ejecutar); fallo de ejecución → traceback (máx. 3) | Tasa de éxito final ≥ 4 de 5; los errores de esquema se detectan **sin lanzar FreeCAD** |
| F1.12 | **Perfil de laminado de PrusaSlicer** (`config/slicing/*.ini`) para la **AnkerMake M5**: PrusaSlicer **no trae perfil de esta impresora**, así que hay que definirla a mano — cama 235×235×250, boquilla 0.4, velocidades, y G-code de inicio y fin. Incluye **densidad de filamento** | Laminar el soporte devuelve **gramos > 0** y un tiempo realista para la M5. Es distinto de `config/printers/*.yaml` (F2.4), que son holguras **2026-10-24:** el perfil activo (`config/impresion.yaml`) es el importado de la calibración del usuario en eufyMake Studio con eSun PLA+ (`orchestrator/perfiles_laminado.py`), con lo que PrusaSlicer no entiende anotado en su cabecera. Sigue **sin verificar** con un G-code de PrusaSlicer impreso de verdad. |
| F1.13 | **Slicing/Cost Agent** mínimo: laminar con el perfil de F1.12 y leer estadísticas | Reporte con gramos, tiempo y si requiere soportes |
| F1.14 | Grafo LangGraph lineal: `INTAKE` → Part Designer → Slicing, con estado en `state.sqlite` | Un comando de consola ejecuta todo y deja los artefactos en `workspace/projects/<id>/` |
| F1.15 | Versionado git automático del proyecto tras cada estado | `git log` del proyecto muestra un commit por etapa |
| F1.16 | **Trazabilidad petición → receta** (`orchestrator/traceability.py`): las cotas con unidad de la petición literal tienen que aparecer en la receta | Una receta con Ø3.2 para una petición de "3.3 mm" se rechaza y se reintenta; "NEMA17", "M3" o "perfil 2020" no dan falsos positivos. Lo que no cuadre tras los reintentos se lista en el resumen del gate. **No se aplica al flujo de mecanismos**: allí el enunciado trae cotas DERIVADAS («la punta queda a 45 mm» de un enlace de 39) y la guardia obligaba a meterlas como parámetro; manda la caja envolvente, que es más fuerte |
| F1.17 | **Suite de verificación en el punto de uso** (marcadores `gui` y `llm`, fuera de la suite rápida): abrir el `.FCStd` en la interfaz real de FreeCAD, `intelliprint new` de extremo a extremo e instantánea del G-code de inicio | `pytest -m "gui or llm"` en verde antes de cerrar cualquier tarea que toque FreeCAD, el laminado o un agente |

**Entregable:** `intelliprint new "soporte para motor NEMA17 atornillable a perfil 2020"` abre la admisión, pregunta lo que falte por consola, y tras confirmar produce `.FCStd`, `.stl`, `.3mf` y reporte.

**Prueba real:** imprimir el soporte y comprobar que el motor y el perfil encajan. Anotar las holguras reales medidas (entrada para la Fase 2).

---

### Fase 2 — Herramientas deterministas y QA (semanas 6–9)

**Objetivo:** que la geometría crítica la haga código y que exista una revisión independiente basada en mediciones.

| ID | Tarea | Criterio de aceptación |
|----|-------|------------------------|
| F2.1 | Servicio `mcp/mech-toolkit` (FastMCP, Docker) | El orquestador lista sus herramientas |
| F2.2 | Librería de hardware inicial en `library/` (tornillería M2–M5, tuercas, insertos, 608zz/623zz/625zz, NEMA14/17, SG90/MG90S/MG996R/DS3218, ESP32, Nano, TMC2209) con esquema validado | `list_hardware` y `get_hardware` devuelven datos correctos; test de esquema para todos los YAML |
| F2.3 | Descargar/crear STEP para cada ítem de la librería | Cada ítem tiene STEP que carga en FreeCAD |
| F2.4 | Perfil de impresora/material `config/printers/*.yaml` con holguras (usar mediciones de la Fase 1) | `apply_fit` devuelve valores del perfil |
| F2.5 | Generadores: `generate_bearing_housing`, `generate_bolt_pattern`, `generate_servo_mount`, `place_commercial_part` | Cada generador produce una macro que FreeCAD ejecuta; tests con dimensiones esperadas |
| F2.6 | Chequeos DFM: `check_wall_thickness`, `check_overhangs`, `check_fits_bed`, `suggest_print_orientation` (trimesh) | Detectan los defectos de un set de 10 STL de prueba con fallas conocidas |
| F2.7 | Macros de medición vía FreeCAD MCP: `measure`, `section_view`, `get_view` | Miden diámetros de agujeros con error < 0.01 mm; las vistas se guardan en `parts/<pieza>/views/` |
| F2.8 | `validate_macro`: análisis estático (AST). **Solo para la escotilla** | Bloquea las macros destructivas del set de prueba; 0 falsos positivos en las plantillas. **Documentado como red de seguridad, no como sandbox** |
| F2.9 | **La escotilla de Python libre** (§ 6.3): marcar una pieza como atípica, generar macro con DeepSeek, pasar `validate_macro`, ejecutar y registrar el motivo | Una pieza que ningún generador cubre se construye por la escotilla; el motivo queda en `log/`. Con el modelo local **no** se abre |
| F2.10 | **Métrica de escotilla**: contador persistente de piezas atípicas por proyecto y en global, con el generador que habría hecho falta | La métrica de § 7 se puede consultar y **nombra qué generador escribir** |
| F2.19 | **RAG para la escotilla** (era F1.8): indexar en Qdrant la API Python de FreeCAD (Part/PartDesign/Sketcher) + ejemplos propios, y usarlo **solo** al generar macros de la escotilla (F2.9) | Una consulta "pocket circular en cara superior" devuelve el ejemplo correcto; una pieza atípica construida por la escotilla usa ese contexto. Requiere Ollama (`nomic-embed-text`) y Qdrant |
| F2.20 | **Encaje físico con holgura mínima** (`mech_toolkit/fit.py`): holgura radial entre el agujero de la pieza y el saliente del hardware ≥ la que pide el perfil. Sustituye a "intersección = 0", que contaba tocarse como encajar | El soporte de Ø22 contra el NEMA17 de referencia da **FAIL** con el motivo *"el agujero tiene que ser de al menos Ø22.35"*; con Ø22.4 da PASS. El motivo es accionable: dice qué valor poner |
| F2.21 | **Los datos de la impresora desde la web** (impresora): una página «Impresora» donde el usuario apunta lo que midió en sus pruebas impresas, con las fotos como evidencia. Dos pruebas de Intelliprint cambian el perfil: la pieza de F2.18 (calibración) da las holguras y los agujeros M3, y una **barra de flexión** nueva, impresa tumbada y de pie, da la resistencia a lo largo del filamento y entre capas (σ = 6·F·L / (b·h²) con el peso con el que rompió). Las pruebas propias del usuario (Printables u otras) se guardan como **referencia**, con foto y nota, sin cambiar números. Los números los escribe el usuario: una foto no enseña si un eje entra justo o con juego. Lo medido vive en `workspace/impresoras/<perfil>/` con su historial (no se borra nada) y **manda sobre** `config/printers/`, que sigue siendo el valor por defecto; `config/` sigue en solo lectura dentro del contenedor | Una medida de holguras apuntada en la web cambia el agujero M3 con el que se diseña y deja el perfil calibrado, con la fecha y la foto; unos valores que la pieza no puede dar no cambian nada. La barra rota con 2 kg a 50 mm da 36.8 MPa (cálculo a mano). El perfil de `config/` no se toca |
| F2.11 | **Tolerances/DFM Agent** | Aplica holguras según interfaz y deja la pieza orientada para imprimir |
| F2.12 | `derive_assertions(interface)`: aserciones medibles por tipo de interfaz (**capa 1 del QA**) | Una interfaz `bearing_seat` 608zz `press` produce la aserción Ø22.10 ±0.05 sin intervención de ningún LLM |
| F2.13 | **Puente aserción ↔ medición** (ADR-011): transformar el `frame` a coordenadas de la pieza con su `placement`, **buscar la geometría que el contrato exige** según el `query` derivado del tipo, y medirla | Las aserciones de F2.12 se resuelven a valores medidos reales. Un agujero desplazado da **"no encontrado" → FAIL**, no una medida correcta en la cara equivocada. **Sin esto la capa 1 no tiene datos y ADR-003 no funciona** |
| F2.14 | **QA Agent de tres capas** (§ 7.1 de la arquitectura): aserciones + DFM + pase libre con visión, y `qa_report.json` | Detecta ≥ 8 de 10 defectos sembrados |
| F2.15 | **Regla dura del veredicto**: `PASS ⟺ capa1 ∧ capa2 ∧ sin_defectos_LLM`. El LLM escribe en una lista, no en el veredicto | Test adversarial: con un QA Agent forzado a responder siempre "aprobado", una pieza con cota fuera de tolerancia **sigue dando FAIL** |
| F2.16 | Capa de visión: pasar los renders de `views/` al modelo y pedir defectos | Detecta ≥ 3 de 5 catástrofes sembradas invisibles a las cotas (pocket en cara equivocada, sólido partido, booleana que borra media pieza) |
| F2.17 | Bucle Part Designer ↔ DFM ↔ QA con máximo 3 iteraciones | Una pieza con defecto sembrado se corrige y pasa |
| F2.18 | **Pieza de calibración de holguras** generada por el sistema (peine de agujeros y ejes 0.0–0.5 mm) | Tras imprimirla, el usuario introduce los resultados y el perfil se actualiza **2026-10-24:** `intelliprint calibrar pieza` construye el peine (5.0 a 5.5 mm), el eje de 5 mm y la placa M3 (2.6 a 3.6 y 3.8 a 4.4), sin números grabados porque no hay generador de texto: se orientan por una muesca. `intelliprint calibrar resultados` es el único camino que cambia `fits` y `holes` del perfil activo, y rechaza valores que la pieza no pudo dar. **Falta imprimirla y medir.** |

**Entregable:** soporte NEMA17 regenerado usando generadores de librería, con QA y DFM aprobados; pieza de calibración impresa y perfil ajustado.

---

### Fase 3 — Descomposición y ensamble (semanas 10–12)

**Objetivo:** diseñar productos de varias piezas que encajen entre sí.

**Alcance por clase:** esta fase se cierra con `static_part` y `mechanism`. El `robot` no puede completarse aquí porque `F3.3` necesita la cinemática de la Fase 4 (§ 5).

| ID | Tarea | Criterio de aceptación |
|----|-------|------------------------|
| F3.1 | Esquema `ProductTree` con **`placement` por pieza** + validador de consistencia: toda interfaz referencia piezas existentes, sin ciclos, y **ninguna interfaz `symbolic` llega al diseño de piezas** (el esquema `Interface` es de F1.1) | Árboles inválidos rechazados con mensaje claro; una interfaz sin resolver bloquea el avance; una pieza sin placement también |
| F3.2 | **Decomposition Agent**: árbol + interfaces **simbólicas** (sin cotas ni `frame`) + tareas con dependencias | Para 5 productos de prueba genera árboles razonables revisados a mano; **ninguna salida contiene números inventados** |
| F3.3 | `resolve_interfaces()`: convierte simbólicas en resueltas usando la hardware library y la salida de la ingeniería de sistema, **y asigna la `placement` de cada pieza** (§ 3.2, ADR-011) | Toda interfaz de la garra queda resuelta con cotas trazables a `library/`, no a un LLM; cada pieza tiene placement y el QA puede llevar los frames a coordenadas de pieza |
| F3.4 | **Gate humano #1** vía `HumanPort` (adaptador CLI), **después de resolver interfaces** | El flujo se pausa y se reanuda desde el estado guardado; lo aprobado es lo que se construye |
| F3.5 | Planificador de tareas: orden topológico y ejecución paralela limitada por `MAX_PARALLEL_PARTS`, con un proceso `freecadcmd` por pieza | Piezas independientes se construyen en paralelo; el límite es CPU, no VRAM |
| F3.6 | Estado `BLOCKED_ON_HUMAN`: el planificador salta piezas bloqueadas y sigue con las demás | Una pieza esperando respuesta no impide que las otras avancen; el proyecto sobrevive a un reinicio mientras espera |
| F3.7 | Part Designer recibe interfaces **resueltas** y usa los `frame` para ubicar features | Las features de interfaz quedan en las coordenadas definidas |
| F3.8 | **Assembly Agent**: importa piezas y hardware, posiciona según interfaces, genera `assembly.FCStd` (instancia GUI) | Ensamble de la garra cargado correctamente en FreeCAD |
| F3.9 | `interference_check` (booleana de intersección entre pares) con reporte de volumen y ubicación | Detecta interferencias sembradas ≥ 0.05 mm³ |
| F3.10 | Generación de BOM (`bom.csv`) de piezas impresas + hardware | BOM coincide con el ensamble |
| F3.11 | QA de ensamble: interfaces coherentes a ambos lados (mismo patrón, misma holgura) Usa `check_fit` (F2.20) en cada interfaz pieza-pieza y pieza-hardware. | Detecta patrones de tornillos desalineados |
| F3.12 | Reapertura selectiva: un defecto de ensamble reabre solo las piezas/interfaces implicadas. El motivo de F2.20 (*"el agujero tiene que ser de al menos Ø…"*) vuelve al Part Designer como defecto, por el mismo bucle que F1.11: el ensamblaje manda a cambiar con el valor concreto, no con un "no encaja". | Tras modificar una interfaz, solo se regeneran las piezas que la usan |
| F3.13 | Slicing por placas: agrupar piezas en la cama y laminar cada placa | Reporte con número de placas, gramos y horas totales |
| F3.14 | Pipeline de **mecanismo** de 1 GDL, empezando por la biela-manivela-corredera (`intelliprint mecanismo`). La disposición la calcula el código a partir de la carrera y de las holguras del perfil (ADR-010, enmienda). El Part Designer diseña cada pieza con enunciados que salen de esa disposición. Siempre se guardan `assembly.FCStd`, con todo visible, y `animation.gif` de una vuelta. El barrido de choques cubre la vuelta completa con holgura mínima física. **Avance:** hecho con DeepSeek (perfil dev). Cada pieza construida se compara con la caja envolvente que espera la disposición; si no cuadra, el motivo vuelve al modelo con los números. En la primera prueba real, el modelo centró la bancada en el origen y la retroalimentación lo corrigió. Pendiente: que el Requirements Agent saque la carrera de una petición en lenguaje natural, y otros mecanismos de 1 GDL. | Carrera de 60 mm sin choques en 36 posiciones; un eje demasiado alto se detecta solo a 165–195°; el ensamble se ve completo al abrirlo en la interfaz de FreeCAD |
| F3.15 | **Mechanism Designer**: convierte la petición en texto en un `MechanismSpec`. El esquema lleva piezas con su enunciado y su caja envolvente, pasadores, un árbol cinemático con fórmulas, pares en contacto o fijos, y requisitos medibles. Las fórmulas las evalúa un intérprete con lista blanca (`orchestrator/mechanisms/expr.py`), nunca `eval`. La cinemática y los requisitos los comprueba el código. El Part Designer dibuja las piezas. Las piezas que se mueven por contacto (`rest_on`) encuentran su posición en la geometría real, no con una fórmula, y los bloqueos (`blocks`) se comprueban forzando la articulación. Los choques, contactos, topes, bloqueos y posiciones vuelven al agente como motivo, hasta que funciona: el bucle no se rinde por número de rondas, se detiene por el tope de gasto (F5.12) o por atascarse repitiendo el mismo fallo, y entonces pregunta. Un Design Reviewer cierra con un informe requisito por requisito (`cumple` / `no_cumple` / `no_verificable`). | Los retos de mecanismos (bisagra, trinquete, gato de tijera, prensa, leva) salen de su texto sin que nadie escriba la disposición; cada uno con `assembly.FCStd` y GIF, y el informe de lo que cumple y lo que no |
| F3.16 | **Laminado por pieza según su uso** (usos): el diseñador declara el `uso` de cada pieza (`general`, `estructural`, `estetica`, `prototipo`) y los ajustes de PrusaSlicer de cada uso salen de `config/slicing/usos.yaml`, que revisa una persona; el modelo no escribe ajustes. La web abre un proyecto `.3mf` con los ajustes de cada pieza, y el puente recibe el nombre del uso, nunca ajustes sueltos | Laminar el `.3mf` da los gramos de laminar cada pieza por separado con sus ajustes (±3 %), comprobado en el host con PrusaSlicer 2.9.6. **Hecho (2026-10-24).** Los valores de la tabla son propuestos: falta ajustarlos imprimiendo |
| F3.17 | **Requisitos estructurados** (requisitos): la spec lleva `requisitos`, cada uno con `id`, tipo (cota, agujero, encaje, fijación, carga…), valor y origen. Lo que dice venir del usuario tiene que ser una cita literal de la petición, y ninguna cota en mm de la petición puede quedarse sin requisito: el código lo comprueba y el error vuelve al modelo. El tamaño de un tornillo («tornillos de 4 mm») ya no se exige como cota de la pieza | El Part Designer recibe cada requisito con su id; una cita inventada o una cota olvidada se corrige en el reintento. **Hecho (2026-11-04).** Falta que las modificaciones reemplacen requisitos por id |
| F3.18 | **Ingeniero** (ingeniero): antes de dibujar, un agente con el rol `reason` propone el concepto —idea, camino de carga, orientación de impresión, fijaciones con la tabla del perfil, casos de carga, alternativas y como mucho tres preguntas—. Recibe el perfil activo entero. Ver ADR-015 | El concepto llega al Part Designer como «dibuja ESTA idea» con las secciones mínimas. **Hecho (2026-11-04)** para piezas; los mecanismos aún no pasan por él |
| F3.19 | **Resistencia en código** (resistencia): el ingeniero plantea el caso de carga y `orchestrator/ingenieria.py` calcula la flexión del voladizo con la resistencia del material del perfil, entre capas si la orientación las pone a tracción. Si no llega al factor de seguridad, el concepto vuelve con el canto que haría falta | Tests con valores hechos a mano. **Hecho (2026-11-04).** Resistencias sin ensayar (como F2.18); FEM con CalculiX como seguimiento |
| F3.20 | **Visto bueno al concepto** (concepto): una pieza no se modela sin aprobar el concepto. Por consola va en la confirmación de la admisión; por la web y Telegram la pieza para «por aprobar» con `concepto.md`, y se aprueba con un botón o con `aprobar_concepto`. Contestar a las preguntas no aprueba: el ingeniero rehace el concepto y vuelve a esperar | Desde la web y Telegram se ve la idea, se contesta y se aprueba, y lo que se modela es el concepto aprobado con la spec aprobada, sin redactarla otra vez. **Hecho (2026-11-04)** |
| F3.21 | **Buscar lo que falta en internet** (investigar): antes de los requisitos, un agente dice qué componentes nombra la petición sin dar sus medidas; el código busca (DuckDuckGo, sin clave) y lee las páginas, y el agente saca cada dato con su URL y una cita literal que el código comprueba en la página. Lo encontrado entra en los requisitos como `catalogo` y sale en el concepto con su fuente, para revisarlo antes de aprobar. Va dentro de Intelliprint para que sirva igual desde la web que desde Telegram. Motivo: el soporte de la Raspberry Pi 4 salió con el patrón de agujeros centrado, sacado de memoria (2026-11-04) | Una petición con un componente sin medidas sale con sus medidas citadas y con fuente, y un dato cuya cita no está en la página no entra |

**Entregable:** garra con MG996R (5–8 piezas) ensamblada sin interferencias, laminada y **impresa y montada físicamente**.

---

### Fase 4 — Ingeniería de sistema y simulación (semanas 13–15)

**Objetivo:** validar que el mecanismo se mueve y que los actuadores alcanzan.

| ID | Tarea | Criterio de aceptación |
|----|-------|------------------------|
| F4.1 | Servicio `mcp/sim` (ikpy, PyBullet, trimesh) en Docker | El orquestador lista sus herramientas |
| F4.2 | **Kinematics Agent**: eslabones, GDL, rangos, espacio de trabajo | Brazo de 3 GDL con alcance calculado dentro de ±5 % del objetivo |
| F4.3 | `joint_torques` en poses críticas con carga útil y masas estimadas (`mass_properties`) | Coincide con un cálculo manual de referencia ±10 % |
| F4.4 | **Actuation Agent**: selecciona actuadores de la librería con margen ≥ 1.5× | Rechaza actuadores insuficientes y justifica la elección |
| F4.5 | **Electronics Agent**: MCU, drivers, fuente, canales de cable, soportes de PCB como requisitos de pieza | Genera features de paso de cable en las piezas afectadas |
| F4.6 | `export_urdf` desde el ensamble (mallas simplificadas + masas) | El URDF carga en PyBullet |
| F4.7 | `sweep_collisions` sobre rangos articulares | Detecta autocolisiones sembradas |
| F4.8 | `stability_test` con carga máxima | Detecta vuelco de una base demasiado pequeña |
| F4.9 | **Test/Sim Agent**: ejecuta la batería y traduce fallos a defectos por pieza/interfaz | Un fallo de torque reabre Actuation; una colisión reabre las piezas implicadas |
| F4.10 | Integrar al grafo con **fases condicionales por clase** (§ 4.2): `static_part` salta la Fase 2 entera, `mechanism` corre la cinemática determinista y Actuation (ADR-010, enmienda), `robot` las tres | Un `static_part` no invoca Kinematics ni Electronics (verificado en el log); el brazo de 3 GDL corre el flujo completo sin intervención salvo gates |
| F4.11 | **Contenedor `sim-ros`** (gazebo): ROS 2 con Gazebo sin ventana, `gz_ros2_control` y `joint_trajectory_controller`, servicio propio en el compose. Versión fijada al construir la imagen con la fuente citada (ADR-017: Jazzy + Harmonic es la pareja confirmada; Lyrical + Jetty, sin confirmar por Gazebo el 2026-11-08) | `docker compose run --rm sim-ros` carga un URDF de dos eslabones escrito a mano, mueve la articulación a un ángulo y `/joint_states` lo devuelve dentro de ±1° |
| F4.12 | **Par de los servos en sus fichas** (par): `par_Nm` a cada tensión, con la hoja de datos citada como el resto de la ficha (ADR-016), en SG90, MG90S, MG996R y DS3218. El `export_urdf` lo pone como límite de esfuerzo de la articulación que mueve ese servo | Test de esquema: ninguna ficha de servo sin par ni sin fuente; el URDF de un brazo con MG996R lleva en `<limit effort>` el valor de la ficha |
| F4.13 | **Probar el código del usuario** (código): el paquete ROS 2 que la persona deja en `control/` del proyecto se lanza contra el URDF de F4.6 en `sim-ros`, con una lista de objetivos (poses y trayectorias). Se graban `/joint_states` y los contactos, y sale `simulacion.md`: pose pedida y alcanzada, choques entre eslabones, par saturado y vuelco | Tres casos sembrados, cada uno con su oráculo hecho a mano: un control correcto llega a todas las poses; uno que manda una articulación fuera de rango sale con el choque nombrado; con un servo demasiado débil para la carga la pose **no se alcanza** y el informe dice qué articulación saturó |
| F4.14 | **Vídeo de la simulación** (vídeo): la grabación de F4.13 se dibuja con la ruta de `orchestrator/animation.py`, sin GPU, y queda junto al informe | El vídeo de un caso sembrado muestra en cada fotograma el ángulo grabado (test con dos fotogramas comparados contra la pose calculada a mano) |
| F4.15 | **Pestaña «Simulación» en la web** (pestaña): en la página de cada proyecto `robot`, el vídeo, el informe y la fecha y versión del código probado. Sin simulación, la pestaña lo dice en vez de esconderse | La pestaña de un proyecto simulado muestra el vídeo y el informe; la de uno sin simular dice que falta y por qué |
| F4.16 | **Botón «Abrir en Gazebo»** (botón): en la pestaña Simulación. Va por el puente del host (`scripts/host_bridge.py`, nueva herramienta junto a `abrir_en_prusaslicer`), que recibe el **nombre** del proyecto, comprueba que está dentro de `workspace/` y lanza el contenedor con interfaz (`--gpus all`, WSLg). El contenedor web nunca monta el socket de Docker (ADR-017) | Test del puente: un nombre con `..` o fuera de `workspace/` se rechaza; uno válido produce la orden con la carpeta del proyecto. Prueba en el host: la ventana de Gazebo se abre con el robot del proyecto |
| F4.17 | **El mismo código en el robot real** (real): interfaz de hardware de `ros2_control` para los servos (PCA9685 en una Pi, o ESP32 con micro-ROS como puente). Lo único que cambia entre simulación y robot es esa interfaz | El paquete que pasó F4.13, sin tocar una línea, mueve el brazo impreso a las mismas poses |

**Entregable:** brazo de 3 GDL con torque validado, sin colisiones en su rango, **con su control ROS 2 probado en Gazebo antes de imprimir** y visible en la pestaña Simulación, impreso y movido con servos por ese mismo código.

---

### Fase 5 — Multiproyecto y canal humano (semanas 16–19)

**Objetivo:** dejar de ser una herramienta de consola de un proyecto y pasar a ser algo que usas desde el móvil, con varios encargos abiertos a la vez.

| ID | Tarea | Criterio de aceptación |
|----|-------|------------------------|
| F5.1 | **Registro de proyectos** `workspace/registry.sqlite` (§ 5.1): id fecha+slug, nombre, clase, estado, fechas, coste, **qué espera del humano** | Tres proyectos de clases distintas coexisten; una consulta devuelve cuál espera qué |
| F5.2 | `submit()` en el `HumanPort` con **adjuntos** guardados en `intake/` (lista blanca de tipos y tamaño) | Un requerimiento con dos fotos crea el proyecto, lo registra y guarda los adjuntos dentro de `workspace/` |
| F5.3 | **Admisión conversacional** multivuelta: el Requirements Agent usa las fotos y las medidas y pregunta hasta completar la spec | Un requerimiento vago con dos fotos acaba en una spec completa tras ≤ 4 preguntas |
| F5.4 | `MAX_CONCURRENT_PROJECTS` y cola de proyectos (regla 9 de § 4) | Con el límite en 1, el segundo proyecto queda encolado en vez de competir por la GPU |
| F5.5 | **Adaptador web** del `HumanPort` (FastAPI + HTMX): lista de proyectos, estado por pieza, reportes, capturas, botones de gate | Ambos gates se aprueban desde el navegador **sin duplicar la lógica de gate** **Hecho en parte (2026-09-20):** lista de proyectos (incluido `archivo/`), descarga en zip y botón «Slice in PrusaSlicer», que abre el PrusaSlicer del escritorio con las piezas y el perfil. **2026-10-23:** también se pide un diseño desde la página (texto libre y, opcional, un proyecto del que partir), con el mismo `JobStore` que usa Crafty y uno cada vez aunque el otro lo haya lanzado Crafty. **2026-10-23 (2):** la lista es de **proyectos** (una solicitud) y no de ejecuciones: cada ejecución es una versión, se enseña la mejor, un selector deja ver las demás y desde el panel se pide una **modificación**, que sale como versión nueva del mismo proyecto (`web/versiones.py`). **Faltan los botones de gate**, que es lo que cierra la tarea. |
| F5.6 | **Adaptador Telegram** vía OpenClaw: contenedor, lista blanca obligatoria, `ask`/`notify`/`submit` con texto e imágenes | Creas un proyecto desde el móvil mandando texto y dos fotos; recibes las preguntas de admisión y un render; respondes y continúa |
| F5.7 | Consultas de registro por Telegram: qué proyectos hay, estado de uno, qué espera de ti | *"¿qué tengo pendiente?"* devuelve la lista con estados desde `registry.sqlite` |
| F5.8 | Peticiones de cambio entrantes → `ChangeRequest` → defecto con autor humano, por la maquinaria de reapertura existente | "haz los dedos más largos" reabre solo las piezas afectadas, sin ruta paralela |
| F5.9 | **Seguridad del canal**: texto **y contenido de imágenes** como dato, adjuntos no ejecutables ni fuera de `workspace/`, escotilla de Python cerrada sin gate | Test de inyección por texto **y por imagen** (una foto con "ignora las instrucciones anteriores" escrito): ninguna ejecuta nada. Un adjunto no permitido se rechaza |
| F5.10 | **Cerrar el canal: lista blanca `TELEGRAM_ALLOWED_USERS`** (salda ADR-012) | El bot responde a los chat IDs de la lista e **ignora al resto**. Sin lista definida, el canal no arranca. Test: un mensaje de un ID ajeno no crea proyecto ni contesta gates **Hecho (2026-09-20):** cierra el bot propio y a Crafty con la misma lista. Al ajeno no se le contesta nada, y en un grupo cuenta quién escribe, no el grupo. |
| F5.11 | Política de escalamiento en `router.py` (fallos, complejidad, contexto, petición manual) | Cada escalamiento registra motivo, tokens y costo |
| F5.12 | Tope `max_usd_per_project` y contador persistente | Al alcanzar el tope se detiene y pide autorización |
| F5.13 | Filtro de datos salientes, compartido por DeepSeek y Telegram | Test: ninguna ruta `C:\` ni credencial sale por ninguno de los dos destinos |
| F5.14 | **Gate humano #2** con resumen: BOM, placas, gramos, horas, advertencias de QA | Aprobación deja los archivos en `fabrication/` |
| F5.15 | Instrucciones de ensamble generadas (orden, hardware por paso, capturas) | Documento legible para montar la garra sin ayuda. **Movida a F8.6 (montaje) el 2026-11-09:** las instrucciones van en la caja del kit |
| F5.16 | Registro de feedback de impresión ("flojo", "apretado", "se rompió en X"), también por Telegram | El feedback ajusta el perfil de holguras o crea defectos en la pieza |
| F5.17 | **Pieza suelta por todos los canales** (pieza): `intelliprint pieza` diseña, construye y lamina una pieza que no se mueve sin confirmación por consola, en la carpeta que le dan; la web (selector «pieza / mecanismo») y Crafty (`disenar_pieza`) la lanzan por `JobStore`, que guarda la orden en `job.json` para reanudar con la misma. Antes solo se podían pedir mecanismos, que exigen dos piezas: un soporte o un gancho no tenían por dónde entrar | Desde la web y desde Telegram se pide un gancho y sale un proyecto de una pieza que el registro ve como cualquier otro, con `blocked.md` si no sale. **Hecho (2026-11-03).** El visto bueno al concepto llegó con F3.20 (concepto) |
| F5.18 | **Kit de geometría** (kit): las piezas sueltas se dibujan con un programa `construir(kit)` contra `mech_toolkit/kit/` —perfiles extruidos y revolución, booleanas, redondeo y chaflán por selector, agujeros en lágrima y avellanados, tornillos y tuercas con la tabla del perfil, colisas— en una lista blanca que se comprueba en el orquestador y otra vez dentro de FreeCAD. Cada agujero o hueco lleva nombre y sale como rasgo en el resultado. Sustituye a la escotilla de F2.9 para piezas sueltas; los mecanismos siguen con recetas (ADR-002, enmienda) | Una escuadra con cartela, un agujero en lágrima y un redondeo dan el volumen calculado a mano; un programa con `import` o `__class__` no llega a FreeCAD. **Hecho (2026-11-04).** Banco con el kit en tres corridas: 33 %, 43 % y 38 % (línea base: 45 %, una corrida; varía ±10 % entre corridas). Lo que se construye sale mejor —acople 83 %, soporte MG996R sin fallos medidos, escuadra hueca con nervio—; lo que falla ya no es el kit sino la geometría del diseñador (perfiles con lados cruzados, rasgos fuera de la pieza), con motivo exacto, que `deepseek-chat` no corrige en tres intentos |

**Entregable:** le mandas al bot *"una pieza que sujete un vaso en el carruaje de mi hijo"* con dos fotos, te pregunta lo que falta, apruebas los dos gates desde el móvil y recibes el G-code — con otros dos proyectos abiertos a la vez y los costos de DeepSeek visibles.

---

### Fase 6 — Endurecimiento (semanas 20–21)

| ID | Tarea | Criterio de aceptación |
|----|-------|------------------------|
| F6.1 | Suite de evaluación: 10 requerimientos de referencia con resultados esperados | Se ejecuta con un comando y produce tabla de métricas **2026-11-03, adelantada:** `intelliprint banco` (`orchestrator/banco.py`) corre 8 encargos reales de robots y casa (`tests/banco/encargos/`) y mide la pieza construida —agujeros por patrón, alojamientos, envolvente, laminado sin soportes— contra un oráculo escrito desde la petición literal. Lo que aún no sabe medir cuenta como «sin medir», no como aprobado. **Nota de partida: 45 % (19 de 42)** con `deepseek-chat`; 13 exigencias sin medir hasta F2.6 (dfm), F2.12 (aserciones) y la revisión de estética |
| F6.2 | Comparar modelos locales por rol (`qwen3.8`, `qwen3:32b`, `gemma3:27b`, `mistral-small`) usando el perfil `prod` | Tabla de tasa de éxito, iteraciones y tiempo por rol; actualizar `models.yaml` |
| F6.3 | Afinar prompts con los fallos más frecuentes de los logs | Mejora medible en la suite |
| F6.4 | Reanudación tras caída (reiniciar contenedor a mitad de proyecto) | El proyecto continúa desde el último estado |
| F6.5 | Documentación: README de uso, cómo añadir hardware, impresoras y agentes | Un tercero puede levantar el sistema siguiendo el README |
| F6.6 | Proyecto final: brazo de 6 GDL | Diseño completo con < 20 % de pasos escalados a DeepSeek |
| F6.7 | **Requisitos medidos dentro del bucle** (lazo): tras construir, el código compara los rasgos con nombre del kit con los requisitos —diámetro y número de agujeros, patrón por distancias entre centros, alojamientos, envolvente— y lo que no cuadra vuelve al diseñador como un fallo de construcción, con los números. Hoy esa medida solo la hace el banco, después, cuando ya no hay arreglo | En el banco ninguna pieza sale con un agujero pedido que falte o con el patrón desviado sin que el diseñador lo haya recibido como motivo. **Hecho (2026-11-04)** para requisitos de tipo agujero (`orchestrator/medida.py`): diámetro, cantidad y separaciones, medidos perpendicularmente al eje; el requisito lleva `cantidad` y `separaciones_mm` |
| F6.8 | **Entregar el mejor intento** (mejor): si ninguna construcción cumple todo, se entrega la que más requisitos cumple, marcada «con defectos» y con la lista, en vez de nada. Hoy una pieza que se construyó en el intento 2 y falló en el 5 sale sin pieza | Ningún encargo del banco queda sin pieza si al menos una construcción salió. **Hecho (2026-11-04)** para el caso de F6.7 (lazo): la que menos defectos tiene se reconstruye y sale con `defectos`. Una pieza que nunca llegó a construirse sigue sin pieza |
| F6.9 | **El diseñador ve su pieza** (vistas): en cada reintento recibe las vistas renderizadas de lo que construyó (DeepSeek Flash acepta imágenes) además del motivo. Dibuja a ciegas: no ve que el gancho mide 21 mm o que la ventana del servo está fuera | Las vistas viajan en cada reintento; un test comprueba que el cliente las manda |
| F6.10 | **Ejemplos resueltos por familia** (ejemplos): escuadra con cartela, soporte de servo, gancho, clip elástico y pieza de revolución, cada uno construido por un test como el del prompt. **No** con las medidas del banco: sería aprenderse el examen | Los cinco ejemplos se construyen en la suite; la nota no se compara con encargos que copien un ejemplo |
| F6.11 | **Biblioteca de componentes, adelantada** (biblioteca): la fase 4 entra aquí. `kit.componente("SG90")` da el hueco y los puntos de fijación con cotas de hoja de datos citada, para que el diseñador no saque de memoria un servo, un NEMA17 o un perfil 2020 | Los soportes de servo y motor del banco usan el componente; sus cotas coinciden con la hoja citada. **En marcha (2026-11-05), ADR-016:** siete fichas citadas (HC-SR04, Raspberry Pi 4, SG90, MG996R, NEMA 17, perfil 2020, 608ZZ), `kit.componente` con su `hueco()`, y las sondas `componente_cabe` y `componente_entra` dentro del bucle y en el banco, que ahora pide por el flujo de pieza. Los encargos 01–03 y 09–10 se juzgan metiendo el componente real. Falta el borrador de ficha para lo que no está en la biblioteca |
| F6.12 | **Subir el techo de la nota** (techo): 13 de las 42 exigencias son «sin medir» y cuentan como no aprobadas, así que la nota máxima posible hoy es 69 %. Medir la resistencia de la sección real construida, la coaxialidad y la holgura de una ventana con su componente | Ninguna exigencia del banco queda «sin medir» salvo las de estética, que llegan con la revisión visual. **Hecho (2026-11-04), y también la estética medible:** ocho sondas de FreeCAD sobre el STEP (`mech_toolkit/sondas.py`): aristas vivas, resistencia de la sección real cortada a lo largo del brazo, ventana pasante, coaxialidad, paso libre, pared mínima, boca entre caras y retención. Ninguna exigencia queda sin medir. Con `intelliprint banco --rejuzgar` se vuelve a juzgar una corrida sin pedir las piezas: la del 62 % sale **81 % (35 de 43)**. Lo que falla ahora es de diseño: aristas vivas en 5 piezas, las ventanas de los dos servos (un rebaje ciego de 4 mm, no una abertura) y la envolvente del acople |
| F6.13 | **Banco con repeticiones** (ruido): cada encargo tres veces, con nota media, dispersión, coste y tiempo por encargo, y ampliarlo a 15 encargos. Con una sola corrida de 8 piezas la nota varía ±10 % sin tocar nada: 33, 43 y 38 % con el mismo código | Un cambio se da por bueno solo si su mejora supera la dispersión medida |

### Plan para la nota global del banco (2026-11-04)

La nota está mal y es la medida de «usable»: **45 % de partida, y 33, 43 y 38 % con el kit**. Lo que dicen las tres corridas, 24 piezas en total:

- **9 de 24 no se construyeron** y cada una pierde todas sus exigencias: es más de la mitad de los puntos perdidos. Ya no es el kit, sino geometría del diseñador —perfiles con lados que se cruzan, rasgos fuera de la pieza— que no corrige aunque reciba el motivo exacto. En curso: el diseñador con razonador y cinco construcciones (F5.18 (kit)).
- **Las que se construyen fallan en lo que pide el usuario**: el patrón de Ø2 del SG90 desviado 4.1 mm, 2 de los 4 agujeros Ø3.3 del NEMA17, el clip sin su alojamiento Ø6. Lo mide el banco, pero el diseñador nunca se entera: F6.7 (lazo).
- **13 de 42 exigencias no se pueden medir**, así que el techo es 69 %: F6.12 (techo).
- **El ruido tapa las mejoras**: F6.13 (ruido).

Orden, de más a menos puntos por esfuerzo: F6.7 (lazo) → F6.8 (mejor) → F6.13 (ruido) → F6.9 (vistas) → F6.10 (ejemplos) → F6.11 (biblioteca) → F6.12 (techo). Después de cada uno, banco.

**Primera corrida con el razonador, cinco construcciones y F6.7 (lazo) + F6.8 (mejor), 2026-11-04: 62 % (26 de 42).** Las 8 piezas se construyen, y de las 27 exigencias que se pueden medir cumplen 26 (falla solo la envolvente del acople, que sobresale 1.8 mm). Lo que queda son las 15 «sin medir»: con este banco la nota máxima es 64 %, así que el siguiente punto sale de F6.12 (techo), no del diseño. Es una sola corrida: falta confirmarla con F6.13 (ruido), y no separa cuánto es del razonador y cuánto del lazo (la corrida solo con el razonador se paró a medias para no esperar).

**Techo subido (F6.12 (techo)):** la misma corrida, rejuzgada con las sondas, da 81 %. Lo que queda por ganar es diseño, y el diseñador no se entera: las aristas vivas y la ventana pasante no están en el bucle de F6.7 (lazo), que solo mide agujeros.

**Con las sondas en el bucle y `acabar()` (corrida `1104-1420`, 2026-11-04): 95 % (41 de 43)**, rejuzgada con el juez de hoy (la corrida del 62 %, rejuzgada igual, da 84 %). 86 minutos. Siete de las ocho piezas cumplen todo. Al mirar los dos fallos que quedaban salieron tres errores del juez, no del diseño, y se arreglaron con su test:

- la ranura en U abierta por arriba del MG996R, por la que el servo entra y atornilla las orejetas, no contaba: la sonda de ventana solo miraba agujeros cerrados;
- la sonda de aristas vivas contaba también los rincones (n1 + n2 cae fuera del sólido en los dos casos);
- en el SG90, `common` y `cut` devolvían vacío para una caja que atravesaba la base maciza, y la sonda la daba por pasante. Ahora hace falta además holgura medida con `distToShape`.

Y uno del kit: `acabar()` redondeaba también los rincones, que **añade** material: la ventana de 23.2 × 12.6 del SG90 ya no dejaba pasar el cuerpo de 22.8 × 12.2. Ahora redondea solo las esquinas. Lo que falla, los dos en el SG90, es real: esa ventana estrechada y un 38 % de aristas vivas. Es una sola corrida (F6.13 (ruido)), y el aviso de F6.10 (ejemplos) sigue: el ejemplo del prompt se parece a la escuadra de repisa del banco, así que el banco necesita piezas que el diseñador no haya visto.

**El banco por el flujo de pieza, con los componentes en el oráculo (corrida `1105-1958`, 2026-11-05): 63 % (33 de 52).** Es la línea base de F6.11 (biblioteca), con el código anterior a las fichas. El 95 % de arriba no veía lo que importa: ningún encargo llevaba un PCB ni una dirección de montaje, y el banco pedía por `new`, sin investigador ni ingeniero. Los encargos 01–03 ahora se juzgan metiendo el servo o el motor real en la pieza, y entran el 09 (HC-SR04) y el 10 (Raspberry Pi 4). El 10 no llegó a correr en esa tanda, así que sobre nueve encargos es 33 de 49 (67 %). Las «sin medir» son los soportes: el laminado falló por una ruta mal traducida en el puente del host, y la corrida salió primero con 0 % porque esa excepción tumbaba el proceso con la pieza ya construida. Las dos cosas están arregladas.

**Con las fichas, `kit.componente` y las sondas en el bucle (corrida `1105-2120`, 2026-11-05): 88 % (46 de 52)**, frente al 63 % de la línea base, con los diez encargos laminados y nada sin medir. Los cinco encargos con componente lo colocan con `kit.componente`, y en los cinco el componente real cabe y entra: el HC-SR04 y la Pi 4 pasan de 0 a 2 de 3. Lo que falla ya no es el componente:

- **aristas vivas** en cinco piezas (18–43 %): `acabar()` no consigue redondear las de los canales y rebajes que deja `hueco()`;
- **una pared de 0.15 mm** en el soporte del MG996R: la pared mínima se mide en el banco, pero no dentro del bucle, así que el diseñador no se entera.

Es una sola corrida (F6.13 (ruido)); la subida, 25 puntos, supera los ±10 de dispersión medidos.

**Sin rebajes de holgura en los apoyos, con chaflán de respaldo y la pared mínima en el bucle (corrida `1106-1630`, 2026-11-06): 100 % (52 de 52).** Las diez piezas se construyen, se laminan sin soportes, y en los cinco encargos con componente el componente real cabe y entra. Hicieron falta dos arreglos del banco por el camino: un encargo que pasaba de 30 minutos tumbaba la corrida entera (ahora cuenta como no construido y el límite es de una hora, porque el concepto y cinco vueltas del razonador ya no caben en 30). Y uno del bucle: el adaptador de tubo salió «no resuelto» porque la pared de una pieza sin caras planas no se puede medir, y la sonda lo daba por fallo; ahora es «sin medir».

Que el banco esté al 100 % no quiere decir que el sistema esté terminado: quiere decir que este banco ya no distingue. Sigue siendo una sola corrida, los diez encargos son conocidos, y el siguiente paso es F6.13 (ruido): repeticiones y encargos nuevos que el diseñador no haya visto, como el soporte del 608ZZ.

**Objetivo:** 60 % de media en tres corridas con el techo de hoy, y 75 % cuando F6.12 (techo) lo suba. La revisión visual y la estética, sin fase asignada todavía, van después: con piezas que no se construyen no hay nada que mirar.

**Visión.** DeepSeek Flash acepta imágenes (`image_url` en base64; ver api-docs.deepseek.com/guides/vision). El cliente de este repo ya las manda desde F5.2 (adjuntos) —comprobado el 2026-09-21: una imagen roja, «Rojo»—, así que F6.9 (vistas), la revisión visual y la estética **no esperan** a los modelos locales de F0.11 (migrar).

### Fase 7 — Proyectos por partes («obras»)

Un proyecto grande se diseña **pieza a pieza**, con el visto bueno de la persona en cada paso. Las piezas sueltas ya salen (el banco al 100 %, el soporte del 608ZZ útil al tercer intento, 2026-11-09), pero los mecanismos se piensan de una sola vez: `MechanismDesignerAgent.design` saca en una llamada todo el `MechanismSpec`, y la Ginebra murió ahí. El principio: **una pieza terminada es una ficha**, y la siguiente se diseña contra ella con la maquinaria de F6.11 (biblioteca). Fuera de los mecanismos no hay simulación: una pieza sola solo se mide.

| ID | Tarea | Criterio de aceptación |
|----|-------|------------------------|
| F7.1 | **Una pieza terminada es una ficha** (fichar): `fichar()` guarda su STEP construido y sus agujeros con nombre; el `Cuerpo` de una ficha puede ser un `step`; `componente_cabe` lo mide con la forma real y `componente_entra` paso a paso; su `hueco()` es la envolvente con holgura | Una tapa diseñada contra un soporte fichado casa sus agujeros y cabe; desplazada 1 mm, falla nombrando el soporte; un pasador impreso entra por donde hay camino y no por el otro lado. **Hecho (2026-11-09).** El barrido exacto de una forma cualquiera no sale barato (extruir caras falló en 2 de 3 ejes; unir copias, 4 min por eje), por eso el hueco era la envolvente. **Enmienda (2026-11-09):** el hueco de una pieza impresa es su forma real crecida la holgura, sin barrer: la envolvente barrida le cortó a la plataforma del pan-tilt el cuello a 17 mm del cuerno. Si entra lo sigue midiendo `componente_entra` |
| F7.2 | **El desglose** (desglose): un agente propone el árbol del proyecto (nodos pieza o conjunto, con lo que cada uno ofrece y necesita); la persona lo aprueba; cada nodo corre el flujo de pieza con las fichas de los nodos de los que depende | Una petición pequeña da un solo nodo y se comporta como hoy; una grande da hojas del tamaño de un encargo del banco. **Hecho en código (2026-11-09)**: `intelliprint obra`, `orchestrator/obra.py` y el desglosador; probado con modelos de guion, falta verlo con DeepSeek (el pan-tilt de F7.3 (arbol)). Rehacer un nodo **archiva también los que se diseñaron contra él** en vez de marcarlos «a revisar»: su ficha ya no existe, y dejarlos daría un árbol que no casa. La petición de cada nodo lleva solo lo suyo, no la de toda la obra: con ella, el ingeniero exigiría en cada pieza los componentes de todas |
| F7.3 | **El árbol en la web y en Crafty** (arbol): estado por nodo, «Siguiente», «Está bien, la siguiente» (congela y ficha), «impresa y probada», rehacer con aviso a los dependientes, imprimir un nodo suelto | El pan-tilt de dos SG90 se hace de punta a punta desde la web. **Hecho en código (2026-11-09)**: la página del proyecto pinta el desglose y el árbol, y Crafty tiene `disenar_backlog` (antes `disenar_obra`: el usuario lo llama backlog), `pieza_lista`, `marcar_impresa` y `rehacer_pieza`; probado en una web de muestra con piezas construidas en FreeCAD. **Falta el criterio**: el pan-tilt con DeepSeek de verdad |
| F7.4 | **Los mecanismos como conjuntos** (conjunto): el nodo lleva solo la cinemática; se verifica con los STEP congelados de sus hijos (barrido, apoyos, bloqueos) y el defecto vuelve al nodo que lo causa | El trinquete rehecho como obra sigue saliendo; la Ginebra se relanza. **Hecho en código para conjuntos de servos (2026-11-09)**: `orchestrator/conjunto.py`. La cinemática sale de la geometría, sin modelo: cada pieza gira con la `salida` (el eje del SG90, ±90° de su hoja de datos) de lo que monta la pieza sobre la que se colocó, si llega a ella; y se barre todo el recorrido con las piezas construidas y los cuerpos de lo comprado. El conjunto queda «verificado» o «con choques», con el tramo de ángulos de cada choque en su tarjeta. **Falta**: el pan-tilt de verdad, y los mecanismos con fórmula (el trinquete, la Ginebra), que siguen por `MechanismSpec` |
| F7.5 | **Obras en el banco** (obras): encargos de varias piezas con oráculo por nodo y aserciones de encaje entre nodos | El pan-tilt y el soporte del 608ZZ con su polea, en el banco; los diez encargos de pieza no bajan. **Hecho en código (2026-11-09)**: encargos `11_pan_tilt_sg90` y `12_soporte_608zz_polea` con `obra: true`; el banco los pide con `obra --banco`, que da él mismo cada visto bueno, y `juzgar_obra` mide lo de pieza en **cada** pieza, cuenta los componentes en la que los aloja (`cuantos`), sondea cada pieza dentro de la que se diseñó contra ella (`encaje`), y lee la verificación del conjunto (`conjunto_libre`, `articulaciones` con el eje en el mundo). La polea queda `pendiente`: el 608ZZ aún no tiene salida y su conjunto solo se comprueba en reposo. **Corridos (2026-11-09/10)**: los diez de pieza, 100 %; los backlogs, ninguno terminado en cuatro corridas (1109-1949: pan-tilt 60 %, 608ZZ 0 %; 1110-0128: 0 % y 40 %), cada una parada por una trampa distinta del sistema. Desde ahí cada intento descartado queda guardado (`intentos/`) y `banco --reanudar <corrida>` sigue desde la pieza que falló. **Regla para parar, decidida por el usuario (2026-11-10)**: una sola ronda de arreglos hecha así; si el pan-tilt no sale entero, los backlogs se aparcan y se sigue con las piezas sueltas, que funcionan. **Resultado de esa ronda (1110-0313 reanudada)**: 80 % los dos. El 608ZZ con su polea sale entero (lo que falta es su giro, que aún no se simula); el pan-tilt construye sus tres piezas y sus dos servos caben, pero choca al moverse (la plataforma, de 132 mm, contra la base al inclinar; el soporte de giro queda a 0.00 mm del SG90 de la base en todo el giro, sin diagnosticar si es roce o el propio acople al cuerno). Según la regla, **los backlogs quedan aparcados** (2026-11-10). **La ronda del choque a la pieza culpable (F7.7 (culpable), 2026-11-10, la única)**: el soporte de giro se corrigió y dejó de rozar; la plataforma, rehecha con su corrección, bajó su radio de giro de 68.4 a 37.7 mm pero sigue chocando con el SG90 de la base y con el soporte, y su pieza se bloqueó en la brida de la cámara (cinco intentos). El pan-tilt sigue en 80 % y **queda aparcado**. El 608ZZ, rejuzgado sin modelo, sube a **100 %**: su polea apoya en la cara de arriba del aro y ahora se ve girar la vuelta entera sin chocar (la salida del rodamiento tiene `largo`). Nota de la corrida: **90 %** (`banco_rejuzgado-2.md`) |
| F7.6 | **Ver moverse los conjuntos** (animacion): la verificación de un conjunto deja su GIF, con lo que choca en rojo en los cuadros en que choca; el de la obra entera va a la raíz del proyecto (web, Crafty, Telegram); `animar` lo rehace sin modelo; la web enseña el banco (`/banco`, solo para mirar) | Hecho (2026-11-10): «de esas no veo ninguna animación», dijo el usuario, y la web no enseñaba nada del banco. El 608ZZ gira: su ficha tiene salida (el aro interior, vuelta entera) |
| F7.7 | **El choque va a la pieza que lo causa** (culpable): de dos piezas que chocan, la que se diseñó contra la otra; su corrección lleva cifras (radio de giro, dónde empieza lo que choca); la web la ofrece escrita y el banco la aplica al reanudar | Hecho en código (2026-11-10); falta verlo en una ronda real (el pan-tilt 1110-0313) |

### Fase 8 — Kits para montar (ADR-019)

**Objetivo:** que una obra terminada salga como un **kit**. El usuario lo imprime en **sus** impresoras, lo mete en una caja con lo comprado, y el cliente lo **monta solo con las instrucciones**. Es el producto de su empresa de robótica infantil (2026-11-09). El cliente no imprime nada. La programación de los robots se mira después, fuera de esta fase.

**Corregida el mismo día.** La primera versión de esta fase suponía que los clientes imprimían en su casa, y el usuario lo corrigió: «son mías, yo las voy a imprimir para armar kits». F8.2 (ajena) y F8.3 (otras) quedan descartadas por eso, con su ID para que no se reutilice.

**Requisitos previos:**
- **F7.3 (arbol) cerrado de verdad**, con el pan-tilt de dos SG90 hecho con DeepSeek. Es el primer kit: no se empaqueta nada que no haya salido entero como obra.
- **La impresora la configura y calibra el usuario.** Él decide cuándo imprimir la pieza de F2.18 (calibración) y los valores que salen. Hasta entonces los kits se diseñan con el perfil activo tal como está, y el asistente no toca holguras.

| ID | Tarea | Criterio de aceptación |
|----|-------|------------------------|
| F8.1 | **Decidir el kit con el usuario** (cliente): las preguntas abiertas de ADR-019 sobre quién monta el kit y qué lleva la caja (edad del cliente, herramientas que se permiten, si lo comprado va dentro, formato de las instrucciones, precios de material y componentes para el coste). Las decide el usuario; el asistente propone y no rellena por defecto | `config/kit.yaml` con cada decisión, su fecha y «decidido por el usuario». Ninguna otra tarea de la fase empieza sin él |
| F8.2 | ~~Perfil de diseño para una impresora ajena~~ (ajena) | **Descartada (2026-11-09):** los kits los imprime el usuario en sus impresoras. Se diseñan con su perfil activo (`config/impresion.yaml`), que calibra él con F2.18 (calibración) |
| F8.3 | ~~Laminar en otras impresoras~~ (otras) | **Descartada (2026-11-09)**, por lo mismo que F8.2 (ajena). Si el usuario tiene más de una impresora, cada una lleva su perfil en `config/printers/` y se elige en `config/impresion.yaml`, como ya se hace hoy |
| F8.4 | **La lista de compras** (compras): lo comprado sale de la `compra` de cada nodo de la obra (F7.2 (desglose)) y la tornillería, de los agujeros con nombre de las fichas (`tornillo("M3")` con su largo). `compras.csv`: id, nombre, cantidad, fuente de la ficha | El pan-tilt da 2 SG90 y la tornillería contada a mano sobre sus agujeros, sin una pieza de más ni de menos |
| F8.5 | **El paquete de producción** (paquete): `intelliprint kit <obra>` deja `kit/` con las piezas en STL y 3MF, el G-code de la impresora del usuario, `compras.csv`, las instrucciones de F8.6 (montaje) y la versión del kit. En una carpeta aparte va **lo que entra en la caja**: las instrucciones y la lista de piezas y compras, sin nada interno (rondas, registros, especificación, `.git`) | Test de contenido: están todas las piezas de la obra, y la parte de la caja no lleva nada interno ni G-code |
| F8.6 | **Instrucciones de montaje** (montaje): antes F5.15. El orden sale de las dependencias del árbol de la obra. Cada paso lleva las piezas, numeradas igual que en la lista, lo comprado que usa y una imagen renderizada de cómo queda. Imágenes antes que texto, porque quien monta puede ser un niño | Una persona que no ha visto el diseño monta el pan-tilt solo con ellas. Test: el orden respeta las dependencias del árbol, y cada pieza y cada compra aparece en algún paso |
| F8.7 | **Reglas para montaje infantil** (infantil): el kit se revisa antes de empaquetarse y avisa de: piezas que caben en el cilindro de piezas pequeñas (16 CFR 1501, con la norma descargada y citada) si la edad de F8.1 (cliente) lo pide; más tipos de tornillo de los decididos; aristas vivas (la sonda de F6.12 (techo)); y cualquier paso que necesite pegamento. **Es una ayuda, no una certificación** de seguridad de juguetes (EN 71, ASTM F963) | Tests con piezas sembradas: una de 20 mm se avisa como pieza pequeña y una de 60 mm no; un kit con tres largos de tornillo, si F8.1 (cliente) decidió dos, sale con el aviso |
| F8.8 | **El kit en la web y en Crafty** (descarga): en la página de una obra terminada, un botón «Kit» con lo que trae (piezas, compras, gramos, horas y coste de F8.11 (coste), avisos de F8.7 (infantil)), la descarga y «Abrir en PrusaSlicer» con todas las placas. En Crafty, `empaquetar_kit` | Desde la web se descarga el kit del pan-tilt; mientras la obra no está terminada, el botón no aparece |
| F8.9 | **Lo que cuentan al montar e imprimir** (reportes): un kit tiene versión. Se registra contra esa versión lo que sale de las impresiones del usuario («flojo», «apretado», «se rompió en X», que es F5.16) y lo que cuentan quienes montan («no entra», «no entendí el paso 3»). Con varios reportes iguales se propone el cambio en la pieza o en las instrucciones; las holguras de la impresora las sigue cambiando solo el usuario | Tres reportes de «no entra» en la misma unión proponen un cambio con los reportes citados; uno solo no propone nada |
| F8.10 | **La prueba de verdad** (prueba): el usuario imprime el kit del pan-tilt y lo monta alguien que no ha visto el diseño, de la edad decidida en F8.1 (cliente), solo con lo que hay en la caja | Montado y moviéndose. Lo que falle entra como reporte de F8.9 (reportes) |
| F8.11 | **Coste y producción por kit** (coste): gramos y horas por kit, las placas que hacen falta en la cama del usuario, y el coste: filamento por los gramos, al precio por kilo de F8.1 (cliente), más lo comprado a sus precios. Para un lote de N kits, cuántas placas y cuántas horas de impresora | Test con el pan-tilt: el coste por kit coincide con la cuenta hecha a mano con los gramos del laminado y los precios de `config/kit.yaml` |

**Orden:** F8.1 (cliente) → F8.4 (compras) → F8.5 (paquete) → F8.11 (coste) → F8.6 (montaje) → F8.7 (infantil) → F8.8 (descarga) → F8.10 (prueba) → F8.9 (reportes).

**Entregable:** el pan-tilt de dos SG90 como kit, con su coste por unidad, impreso por el usuario y montado sin ayuda por alguien que no lo ha visto.

---

## 5. Dependencias entre tareas críticas

```
F0.5 cliente MCP ─┬─► F1.10 Part Designer ─► F2.17 bucle QA ─► F3.7 piezas ─► F3.8 Assembly
F0.6 router LLM ──┘         ▲                      ▲                              │
F1.6 compose_build_script ──┘                      │                              ▼
F1.1 esquemas ─► F3.1 ProductTree                  │            F4.6 URDF ─► F4.9 Test/Sim
F2.2 librería ─► F2.5 generadores ─► F1.10         │
F1.9 spec→tarea ──────────────────► F1.10         │
F2.4 perfil ─► F2.11 Tolerances                    │
F3.1 ─► F3.2 Decomposition (simbólicas) ───────────┼─► F3.3 resolve_interfaces ─► F3.4 gate 1
                                                   │              ▲
F2.12 derive_assertions ─► F2.13 puente medición ──┘              │
F2.7 measure ──────────────┘                                      │
F4.1 sim ─► F4.2 Kinematics ─► F4.4 Actuation ────────────────────┘   (solo clase `robot`)

F0.9 HumanPort ─► F1.5 INTAKE ─► F3.4 gate 1 ─► F5.5 web ─► F5.6 Telegram
F1.4 clasificación ─────────────────────────────► F4.10 fases condicionales
F1.12 perfil laminado ──────────────────────────► F1.13 Slicing Agent
F2.19 RAG ─────────────────────────────────────► F2.9 escotilla
```

Ruta crítica: F0.5 → F1.6 → F1.10 → F2.5 → F2.13 → F2.17 → F3.2 → F3.3 → F3.8 → F4.6 → F4.9.

> **La única dependencia que va hacia atrás.** `F3.3 resolve_interfaces` **necesita `F4.2 Kinematics` y `F4.4 Actuation`** cuando el producto es un `robot`: los `frame` salen de la cinemática y el hardware definitivo de la selección de actuadores. Para `static_part` y `mechanism` el resolvedor se apaña con la hardware library y los frames del árbol, así que la Fase 3 **se cierra con la garra** y el brazo espera a la Fase 4.
>
> Esto no es un defecto del plan: es la consecuencia de ADR-001 hecha visible. Los dos estados de interfaz existen precisamente para que la Fase 3 avance con lo que se puede resolver de verdad, en lugar de inventar cotas y corregirlas después.

**Dos decisiones de orden que conviene no revertir sin pensarlo:**

- **La barrera de admisión (`F1.5`) va en la Fase 1, no en la 5**, aunque el canal de Telegram sea de la 5. Es una transición del grafo: añadirla después obligaría a rehacer la máquina de estados con el pipeline ya montado encima.
- **La clasificación (`F1.4`) también va en la Fase 1**, aunque las fases condicionales (`F4.10`) sean de la 4. Es un campo de `Spec` y una instrucción de prompt: si llegara tarde, las fases 3 y 4 se construirían asumiendo `robot` siempre y habría que retrofitarlas.

---

## 6. Estrategia de pruebas

| Nivel | Qué se prueba | Herramienta |
|-------|---------------|-------------|
| Unitario | Esquemas, `apply_fit`, generadores (dimensiones), `validate_macro`, router | `pytest` dentro de los contenedores |
| Herramientas | Chequeos DFM sobre STL con defectos conocidos | `pytest` + set `tests/fixtures/stl/` |
| Integración | Orquestador ↔ MCP de FreeCAD/PrusaSlicer | `smoke_test` (requiere host con FreeCAD abierto) |
| Agentes | Salida válida y correcta de cada agente sobre casos fijos | Suite de evaluación (F6.1), con semilla y temperatura bajas |
| Adversarial | Que el QA no pueda aprobar una pieza defectuosa (F2.15), que no se pueda diseñar sin confirmar la admisión (F1.5) y que un mensaje o una imagen de Telegram no puedan ejecutar código (F5.9) | `pytest` con agentes simulados que responden siempre "aprobado", transiciones prohibidas del grafo, y mensajes e imágenes de inyección |
| Extremo a extremo | Proyectos de referencia completos | CLI `intelliprint eval` |
| Físico | Impresión y montaje real | Checklist manual por hito |

Regla: las herramientas deterministas deben tener tests antes de que un agente las use.

### 6.1 Definición de "hecho"

Una tarea **solo está hecha** si cumple las tres condiciones. Salieron de cinco fallos que llegaron al usuario con la suite en verde: una cota perdida entre la petición y la pieza, un `.FCStd` que se abría vacío, una referencia de encaje dibujada por el propio sistema, un QA que confundía agujero con saliente, y una holgura cero dada por buena.

1. **El test falla sin el cambio.** Visto fallar antes de implementar y, para las garantías estructurales, verificado además por mutación: se rompe a propósito el código y se comprueba que el test cae. Un test que nunca ha fallado no ha demostrado nada.
2. **Hay una verificación en el punto de uso**, donde lo experimenta el usuario: la pieza abierta en FreeCAD, el G-code laminado, la petición que escribió. No la representación intermedia. Es `pytest -m "gui or llm"` (F1.17 (verificación)).
3. **El valor esperado viene de un oráculo independiente**: un modelo de referencia descargado (`library/models/reference/`, protegido por SHA-256), un cálculo a mano o la petición literal del usuario. **Nunca** de la salida del propio sistema, ni de los mismos números con los que se diseñó la pieza.

Y un criterio físico, no geométrico: **encajar es tener holgura ≥ la del perfil**, no "intersección cero". Tocarse no es encajar (F2.20 (encaje)).

---

## 7. Métricas de éxito

| Métrica | Meta final |
|---------|-----------|
| Piezas que pasan QA en ≤ 3 iteraciones | ≥ 85 % |
| **Recetas válidas contra esquema al primer intento** | ≥ 90 % |
| **Piezas que necesitan la escotilla de Python** | < 15 % *(si sube, faltan generadores — ver § 6.3)* |
| Ensambles sin interferencias en el primer ensamble | ≥ 70 % |
| Pasos escalados a DeepSeek | < 20 % |
| Costo DeepSeek por proyecto | < 2 USD |
| Encajes correctos en impresión real (sin lijar) | ≥ 90 % de las interfaces |
| Tiempo de diseño de la garra (sin impresión) | < 45 min |

La métrica de la escotilla es la más accionable del conjunto: no mide calidad del modelo, mide **qué te falta construir**. Cada pieza atípica nombra el generador que hay que escribir.

Todas se calculan desde `workspace/state.sqlite`, el registro de proyectos y los logs.

---

## 8. Riesgos del plan

| Riesgo | Prob. | Impacto | Mitigación | Plan B |
|--------|-------|---------|------------|--------|
| Geometría generada por el LLM poco fiable | Baja | Alto | **El LLM no genera geometría**: emite una receta validada contra esquema y `build.py` lo compone el orquestador | Ampliar el catálogo de generadores; escotilla con DeepSeek |
| Catálogo de generadores insuficiente | **Alta** | Medio | Es el riesgo que sustituye al anterior: se mide con la métrica de escotilla y se ataca escribiendo generadores | Escotilla con DeepSeek mientras tanto |
| VRAM insuficiente | Baja | Medio | 25 GB de 32 GB con ambos modelos residentes | Descargar `gemma3:12b` y usar `qwen3.8` también para QA |
| Ollama cae a CPU en silencio (Blackwell) | Media | Alto | Verificación explícita de GPU en F0.3; CUDA 12.8+ | Ollama nativo en Windows en vez de contenedor |
| Inyección de prompt por Telegram (texto o imagen) | Baja | Alto | Lista blanca obligatoria; texto y contenido de imágenes como dato; escotilla cerrada sin gate (F5.9) | Desactivar peticiones de cambio y dejar Telegram solo para notificaciones |
| El alcance sigue creciendo y las 19 semanas se quedan cortas | **Alta** | Medio | Fases con entregable propio: puedes parar en cualquiera y tener algo que funciona | Recortar la Fase 5 a solo notificaciones por Telegram y operar los gates desde la web |
| **El perfil `dev` se queda** y el sistema acaba dependiendo de la nube | Media | Alto | Deuda escrita en tres sitios (ADR-007b, § 6.1.1 y `models.yaml`) y tarea propia (F0.11) | Asumirlo explícitamente y reescribir la restricción "local primero" en vez de dejarla incumplida en silencio |
| Lo desarrollado con DeepSeek no funciona con `qwen3.8` | **Alta** | Medio | `deepseek-chat` es un suelo optimista: lo que falla aquí falla más en local. F0.11 repasa todo con modelos locales | Bajar el listón de los agentes: menos campos por esquema, más pasos pequeños |
| Puente stdio→HTTP inestable | Media | Alto | Reintentos y health checks en el cliente | Correr los MCP dentro de Docker apuntando al RPC de FreeCAD |
| Decomposition produce árboles incoherentes | Media | Alto | Validador de consistencia + gate humano #1 | Escalar siempre la descomposición a DeepSeek |
| Simulación lenta o inexacta con mallas complejas | Media | Medio | Mallas simplificadas / primitivas para colisión | Solo chequeo de interferencias estático por pasos |
| El robot pasa en Gazebo y falla impreso (servo ideal, masas estimadas, plástico rígido; ADR-017) | Media | Medio | El par sale de la ficha citada y un servo débil sembrado tiene que quedarse corto (F4.13); el informe dice lo que no simula | Margen de par ≥ 1.5× (F4.4) y primera prueba real sin carga |
| La ventana de Gazebo no abre por WSLg o no hay GPU libre (la 5090 va casi llena) | Media | Bajo | La comprobación corre sin ventana y sin GPU; la ventana es solo para mirar (F4.16) | Ver el vídeo de la pestaña Simulación |
| Holguras no transferibles entre materiales | Alta | Medio | Perfil por impresora + material, pieza de calibración | Ajuste manual del perfil tras cada impresión |
| Alcance crece (FEM, PCB, firmware) | Media | Medio | Fuera de alcance explícito (sección 1) | Registrar como mejoras futuras |

---

## 9. Hitos y demostraciones

| Hito | Fin de semana | Demostración |
|------|---------------|--------------|
| H0 | 1 | Cubo creado en FreeCAD y laminado desde el contenedor |
| H1 | 5 | Soporte NEMA17 desde texto, impreso *(`static_part`)* |
| H2 | 9 | QA detecta defectos y no puede aprobarlos; perfil de holguras calibrado |
| H3 | 12 | Garra MG996R impresa y montada *(`mechanism`)* |
| H4 | 15 | Brazo 3 GDL impreso y moviéndose *(`robot`)* |
| H5 | 19 | Proyecto creado, consultado y aprobado enteramente desde el móvil, con otros dos abiertos a la vez |
| H6 | 21 | Brazo 6 GDL diseñado; suite de evaluación en verde |
| H8 | — | Kit del pan-tilt impreso por el usuario y montado solo con las instrucciones por alguien que no lo ha visto |

Los hitos H1, H3 y H4 son de **clases distintas a propósito**: cada uno valida que el grafo hace lo correcto con su clase, incluido saltarse las fases que no aplican.

---

## 10. Mejoras futuras

- Análisis FEM simple con CalculiX (FreeCAD FEM) para piezas críticas.
- Generación de firmware base (ESP32) a partir de la spec de electrónica.
- Soporte para Cura/OrcaSlicer y múltiples impresoras.
- Visión: comparar foto de la pieza impresa contra el modelo para feedback automático.
- Biblioteca de diseños aprobados reutilizables como punto de partida.
- **Sandbox real para la escotilla**: ejecutar `freecadcmd` en un contenedor desechable sin red, con solo la carpeta de la pieza montada. Sustituiría a `validate_macro`, que es una red de seguridad y no un límite (§ 8.3 de la arquitectura).
- Más canales del `HumanPort` (WhatsApp, Signal): son adaptadores adicionales, no cambios de arquitectura.
- **Costo de Crafty: bajar su nivel de pensamiento.** Crafty conversa con `deepseek-flash` (decisión del usuario, 2026-09-21), pero con el pensamiento en **alto**, el valor por defecto de OpenClaw. Para charlar y pasar encargos probablemente sobra, y el pensamiento se paga como salida en cada mensaje. Se dejó así a propósito; es la siguiente palanca de costo si hace falta. Iría en `orchestrator/crafty.py`, como el modelo (averiguar antes qué ruta de `openclaw.json` lo controla).

---

## 11. Próximos pasos inmediatos

1. ~~Confirmar VRAM~~ — **hecho**: RTX 5090, 32 GB (§ 2.1). Falta definir impresora y material de referencia.
2. Confirmar cómo se lanzan hoy los MCP de FreeCAD y PrusaSlicer (comando exacto y si son stdio o HTTP).
3. Crear el bot de Telegram y anotar el chat ID propio (S8), necesario para F5.6. No corre prisa: es de la semana 14.
4. Ejecutar F0.1–F0.3 (repositorio, compose, Ollama con GPU) **verificando explícitamente que no cae a CPU**.
5. F0.10: comprobar `freecadcmd` headless en el PC, que es la base del paralelismo de la Fase 3.
