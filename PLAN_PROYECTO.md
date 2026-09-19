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

**Fuera del alcance (por ahora)**

- Diseño de PCB y firmware (solo se reservan espacios y rutas de cables).
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
| F0.2 | `docker-compose.yml` con `ollama`, `orchestrator` (vacío), `qdrant` | `docker compose up -d` levanta todo sin errores |
| F0.3 | Habilitar GPU en Ollama (CUDA 12.8+, `OLLAMA_MAX_LOADED_MODELS=2`) y descargar `qwen3.8` y `gemma3:12b` | Ambos responden; `nvidia-smi` muestra **~25 GB en uso y actividad en la GPU durante la inferencia**. Prueba negativa explícita: confirmar que NO está cayendo a CPU |
| F0.4 | `scripts/start-host-mcps.ps1`: lanza `mcp-proxy` para FreeCAD (:8101) y PrusaSlicer (:8102) | `curl http://localhost:8101/sse` responde en el host |
| F0.5 | Cliente MCP en `orchestrator/mcp/client.py` (HTTP/SSE) | Desde el contenedor se listan las herramientas de ambos MCP |
| F0.6 | `orchestrator/llm/router.py` con proveedor local y DeepSeek (defaults para `DEEPSEEK_BASE_URL` y `DEEPSEEK_MODEL`) | Test que llama a cada proveedor y devuelve texto; si falta la API key, DeepSeek queda deshabilitado sin romper |
| F0.7 | Traducción de rutas contenedor ↔ host (`WORKSPACE` ↔ `HOST_WORKSPACE`) | Un archivo creado en `/workspace/test.txt` es abierto por FreeCAD vía MCP |
| F0.8 | Logging estructurado (JSONL) de cada llamada a LLM y herramienta | Cada llamada deja una línea en `workspace/<proyecto>/log/` |
| F0.9 | `HumanPort` con el adaptador CLI (§ 8.5 de la arquitectura): `ask()` y `notify()` | Un `ask()` desde el orquestador bloquea, se responde por consola y el estado se persiste |
| F0.10 | Verificar `freecadcmd` headless: ejecutar una macro y exportar STL sin GUI | Un cubo se construye y exporta desde un proceso sin interfaz |
| F0.11 | **Migrar del perfil `dev` al `prod`** (§ 6.1.1 de la arquitectura) y **repasar todo lo desarrollado con DeepSeek** | `INTELLIPRINT_PROFILE=prod` y la suite completa en verde **con modelos locales**. Es donde van a salir los fallos que la nube tapó: `deepseek-chat` sigue esquemas mejor que `qwen3.8` |

**Entregable:** comando `docker compose run orchestrator python -m smoke_test` que crea un cubo en FreeCAD, exporta STL y lo lamina en PrusaSlicer, sin LLM.

**Riesgos:** GPU no disponible en WSL2 → plan B: Ollama nativo en Windows y `OLLAMA_URL=http://host.docker.internal:11434`.

> **Deuda declarada.** Mientras la 5090 no esté disponible se desarrolla con el perfil `dev` (DeepSeek en la nube, § 6.1.1). Incumple *local primero* a propósito y de forma temporal. **F0.11 es la tarea que salda esa deuda**, y no está hecha hasta que la suite pase con modelos locales.

---

### Deuda técnica declarada

Dos decisiones que desbloquean trabajo hoy incumpliendo algo del diseño. Están aquí para que se vean juntas y no se conviertan en el estado permanente.

| Deuda | Qué incumple | La salda | Cuándo |
|---|---|---|---|
| Perfil `dev` con DeepSeek en la nube (ADR-007b) | *Local primero* (§ 1) | **F0.11** | Al tener la 5090 |
| Canal de Telegram **abierto**, sin lista blanca (ADR-012) | Regla 1 de § 8.5 | **F5.10** | Antes de usarlo de verdad |

> Sobre la segunda, una precisión que conviene tener delante: **un bot de Telegram no es local aunque corra en tu PC**. Hace *polling* contra los servidores de Telegram, que le entregan los mensajes de cualquiera desde cualquier sitio. Apagar la máquina protege; que sea "local" no. Mientras la deuda viva, quien encuentre el bot puede crear proyectos, gastar saldo de DeepSeek y **contestar las tres barreras** — incluida la que guarda la escotilla de Python.

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
| F1.12 | **Perfil de laminado de PrusaSlicer** (`config/slicing/*.ini`) para la **AnkerMake M5**: PrusaSlicer **no trae perfil de esta impresora**, así que hay que definirla a mano — cama 235×235×250, boquilla 0.4, velocidades, y G-code de inicio y fin. Incluye **densidad de filamento** | Laminar el soporte devuelve **gramos > 0** y un tiempo realista para la M5. Es distinto de `config/printers/*.yaml` (F2.4), que son holguras |
| F1.13 | **Slicing/Cost Agent** mínimo: laminar con el perfil de F1.12 y leer estadísticas | Reporte con gramos, tiempo y si requiere soportes |
| F1.14 | Grafo LangGraph lineal: `INTAKE` → Part Designer → Slicing, con estado en `state.sqlite` | Un comando de consola ejecuta todo y deja los artefactos en `workspace/projects/<id>/` |
| F1.15 | Versionado git automático del proyecto tras cada estado | `git log` del proyecto muestra un commit por etapa |

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
| F2.11 | **Tolerances/DFM Agent** | Aplica holguras según interfaz y deja la pieza orientada para imprimir |
| F2.12 | `derive_assertions(interface)`: aserciones medibles por tipo de interfaz (**capa 1 del QA**) | Una interfaz `bearing_seat` 608zz `press` produce la aserción Ø22.10 ±0.05 sin intervención de ningún LLM |
| F2.13 | **Puente aserción ↔ medición** (ADR-011): transformar el `frame` a coordenadas de la pieza con su `placement`, **buscar la geometría que el contrato exige** según el `query` derivado del tipo, y medirla | Las aserciones de F2.12 se resuelven a valores medidos reales. Un agujero desplazado da **"no encontrado" → FAIL**, no una medida correcta en la cara equivocada. **Sin esto la capa 1 no tiene datos y ADR-003 no funciona** |
| F2.14 | **QA Agent de tres capas** (§ 7.1 de la arquitectura): aserciones + DFM + pase libre con visión, y `qa_report.json` | Detecta ≥ 8 de 10 defectos sembrados |
| F2.15 | **Regla dura del veredicto**: `PASS ⟺ capa1 ∧ capa2 ∧ sin_defectos_LLM`. El LLM escribe en una lista, no en el veredicto | Test adversarial: con un QA Agent forzado a responder siempre "aprobado", una pieza con cota fuera de tolerancia **sigue dando FAIL** |
| F2.16 | Capa de visión: pasar los renders de `views/` al modelo y pedir defectos | Detecta ≥ 3 de 5 catástrofes sembradas invisibles a las cotas (pocket en cara equivocada, sólido partido, booleana que borra media pieza) |
| F2.17 | Bucle Part Designer ↔ DFM ↔ QA con máximo 3 iteraciones | Una pieza con defecto sembrado se corrige y pasa |
| F2.18 | **Pieza de calibración de holguras** generada por el sistema (peine de agujeros y ejes 0.0–0.5 mm) | Tras imprimirla, el usuario introduce los resultados y el perfil se actualiza |

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
| F3.11 | QA de ensamble: interfaces coherentes a ambos lados (mismo patrón, misma holgura) | Detecta patrones de tornillos desalineados |
| F3.12 | Reapertura selectiva: un defecto de ensamble reabre solo las piezas/interfaces implicadas | Tras modificar una interfaz, solo se regeneran las piezas que la usan |
| F3.13 | Slicing por placas: agrupar piezas en la cama y laminar cada placa | Reporte con número de placas, gramos y horas totales |

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
| F4.10 | Integrar al grafo con **fases condicionales por clase** (§ 4.2): `static_part` salta la Fase 2 entera, `mechanism` solo corre Actuation, `robot` las tres | Un `static_part` no invoca Kinematics ni Electronics (verificado en el log); el brazo de 3 GDL corre el flujo completo sin intervención salvo gates |

**Entregable:** brazo de 3 GDL con torque validado, sin colisiones en su rango, impreso y movido con servos.

---

### Fase 5 — Multiproyecto y canal humano (semanas 16–19)

**Objetivo:** dejar de ser una herramienta de consola de un proyecto y pasar a ser algo que usas desde el móvil, con varios encargos abiertos a la vez.

| ID | Tarea | Criterio de aceptación |
|----|-------|------------------------|
| F5.1 | **Registro de proyectos** `workspace/registry.sqlite` (§ 5.1): id fecha+slug, nombre, clase, estado, fechas, coste, **qué espera del humano** | Tres proyectos de clases distintas coexisten; una consulta devuelve cuál espera qué |
| F5.2 | `submit()` en el `HumanPort` con **adjuntos** guardados en `intake/` (lista blanca de tipos y tamaño) | Un requerimiento con dos fotos crea el proyecto, lo registra y guarda los adjuntos dentro de `workspace/` |
| F5.3 | **Admisión conversacional** multivuelta: el Requirements Agent usa las fotos y las medidas y pregunta hasta completar la spec | Un requerimiento vago con dos fotos acaba en una spec completa tras ≤ 4 preguntas |
| F5.4 | `MAX_CONCURRENT_PROJECTS` y cola de proyectos (regla 9 de § 4) | Con el límite en 1, el segundo proyecto queda encolado en vez de competir por la GPU |
| F5.5 | **Adaptador web** del `HumanPort` (FastAPI + HTMX): lista de proyectos, estado por pieza, reportes, capturas, botones de gate | Ambos gates se aprueban desde el navegador **sin duplicar la lógica de gate** |
| F5.6 | **Adaptador Telegram** vía OpenClaw: contenedor, lista blanca obligatoria, `ask`/`notify`/`submit` con texto e imágenes | Creas un proyecto desde el móvil mandando texto y dos fotos; recibes las preguntas de admisión y un render; respondes y continúa |
| F5.7 | Consultas de registro por Telegram: qué proyectos hay, estado de uno, qué espera de ti | *"¿qué tengo pendiente?"* devuelve la lista con estados desde `registry.sqlite` |
| F5.8 | Peticiones de cambio entrantes → `ChangeRequest` → defecto con autor humano, por la maquinaria de reapertura existente | "haz los dedos más largos" reabre solo las piezas afectadas, sin ruta paralela |
| F5.9 | **Seguridad del canal**: texto **y contenido de imágenes** como dato, adjuntos no ejecutables ni fuera de `workspace/`, escotilla de Python cerrada sin gate | Test de inyección por texto **y por imagen** (una foto con "ignora las instrucciones anteriores" escrito): ninguna ejecuta nada. Un adjunto no permitido se rechaza |
| F5.10 | **Cerrar el canal: lista blanca `TELEGRAM_ALLOWED_USERS`** (salda ADR-012) | El bot responde a los chat IDs de la lista e **ignora al resto**. Sin lista definida, el canal no arranca. Test: un mensaje de un ID ajeno no crea proyecto ni contesta gates |
| F5.11 | Política de escalamiento en `router.py` (fallos, complejidad, contexto, petición manual) | Cada escalamiento registra motivo, tokens y costo |
| F5.12 | Tope `max_usd_per_project` y contador persistente | Al alcanzar el tope se detiene y pide autorización |
| F5.13 | Filtro de datos salientes, compartido por DeepSeek y Telegram | Test: ninguna ruta `C:\` ni credencial sale por ninguno de los dos destinos |
| F5.14 | **Gate humano #2** con resumen: BOM, placas, gramos, horas, advertencias de QA | Aprobación deja los archivos en `fabrication/` |
| F5.15 | Instrucciones de ensamble generadas (orden, hardware por paso, capturas) | Documento legible para montar la garra sin ayuda |
| F5.16 | Registro de feedback de impresión ("flojo", "apretado", "se rompió en X"), también por Telegram | El feedback ajusta el perfil de holguras o crea defectos en la pieza |

**Entregable:** le mandas al bot *"una pieza que sujete un vaso en el carruaje de mi hijo"* con dos fotos, te pregunta lo que falta, apruebas los dos gates desde el móvil y recibes el G-code — con otros dos proyectos abiertos a la vez y los costos de DeepSeek visibles.

---

### Fase 6 — Endurecimiento (semanas 20–21)

| ID | Tarea | Criterio de aceptación |
|----|-------|------------------------|
| F6.1 | Suite de evaluación: 10 requerimientos de referencia con resultados esperados | Se ejecuta con un comando y produce tabla de métricas |
| F6.2 | Comparar modelos locales por rol (`qwen3.8`, `qwen3:32b`, `gemma3:27b`, `mistral-small`) usando el perfil `prod` | Tabla de tasa de éxito, iteraciones y tiempo por rol; actualizar `models.yaml` |
| F6.3 | Afinar prompts con los fallos más frecuentes de los logs | Mejora medible en la suite |
| F6.4 | Reanudación tras caída (reiniciar contenedor a mitad de proyecto) | El proyecto continúa desde el último estado |
| F6.5 | Documentación: README de uso, cómo añadir hardware, impresoras y agentes | Un tercero puede levantar el sistema siguiendo el README |
| F6.6 | Proyecto final: brazo de 6 GDL | Diseño completo con < 20 % de pasos escalados a DeepSeek |

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

---

## 11. Próximos pasos inmediatos

1. ~~Confirmar VRAM~~ — **hecho**: RTX 5090, 32 GB (§ 2.1). Falta definir impresora y material de referencia.
2. Confirmar cómo se lanzan hoy los MCP de FreeCAD y PrusaSlicer (comando exacto y si son stdio o HTTP).
3. Crear el bot de Telegram y anotar el chat ID propio (S8), necesario para F5.6. No corre prisa: es de la semana 14.
4. Ejecutar F0.1–F0.3 (repositorio, compose, Ollama con GPU) **verificando explícitamente que no cae a CPU**.
5. F0.10: comprobar `freecadcmd` headless en el PC, que es la base del paralelismo de la Fase 3.
