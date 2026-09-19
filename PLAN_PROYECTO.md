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
| S4 | `DEEPSEEK_API_KEY` definida en Windows | `echo $env:DEEPSEEK_API_KEY` (no vacío) |
| S5 | Python 3.11+ y `uv` en el host para los puentes MCP | `python --version`, `uv --version` |
| S6 | Impresora y material de referencia definidos | Llenar `config/printers/<impresora>.yaml` |
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

| Fase | Nombre | Resultado | Esfuerzo estimado* |
|------|--------|-----------|--------------------|
| 0 | Infraestructura | Docker + Ollama + puentes MCP + esqueleto del orquestador | 1 semana |
| 1 | Pipeline de una pieza | Requerimiento → pieza FreeCAD → STL → PrusaSlicer | 2 semanas |
| 2 | Herramientas deterministas y QA | `mech-toolkit`, librería de hardware, QA con mediciones | 2 semanas |
| 3 | Descomposición y ensamble | Varias piezas en paralelo, interfaces, ensamble e interferencias | 3 semanas |
| 4 | Ingeniería de sistema y simulación | Cinemática, actuación, electrónica, `sim`, reapertura selectiva | 3 semanas |
| 5 | Interfaz humana, escalamiento y feedback | `HumanPort` con adaptadores CLI/web/Telegram, DeepSeek con presupuesto, calibración con impresiones reales | 3 semanas |
| 6 | Endurecimiento | Evaluaciones, métricas, documentación, brazo de 6 GDL | 2 semanas |

\* Estimado para dedicación parcial (~10–15 h/semana). Total aproximado: **16 semanas**.

```
Semana:   1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16
Fase 0   ██
Fase 1      ████
Fase 2            ████
Fase 3                  ██████
Fase 4                        ██████
Fase 5                              ██████
Fase 6                                      ████
```

---

## 4. Fases en detalle

Convención de IDs: `F<fase>.<tarea>`. Cada tarea tiene un criterio de aceptación verificable.

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

**Entregable:** comando `docker compose run orchestrator python -m smoke_test` que crea un cubo en FreeCAD, exporta STL y lo lamina en PrusaSlicer, sin LLM.

**Riesgos:** GPU no disponible en WSL2 → plan B: Ollama nativo en Windows y `OLLAMA_URL=http://host.docker.internal:11434`.

---

### Fase 1 — Pipeline de una pieza (semanas 2–3)

**Objetivo:** primer flujo con LLM de extremo a extremo para una pieza simple.

| ID | Tarea | Criterio de aceptación |
|----|-------|------------------------|
| F1.1 | Esquemas Pydantic: `Spec`, `PartTask`, `PartResult`, `SlicingReport`, **`Recipe`** | Validación falla con mensajes claros ante datos incompletos |
| F1.2 | Salida estructurada: JSON mode de Ollama + validación + reintento con el error | ≥ 90 % de respuestas válidas en 20 pruebas con `qwen3.8` |
| F1.3 | **Requirements Agent** en modo **admisión conversacional** (§ 4.1): lee texto, fotos y medidas, pregunta por `HumanPort` hasta completar la spec, y **clasifica el producto** (§ 4.2) | Convierte 10 pedidos de prueba en `spec.yaml` válidos; pregunta cuando falta un dato crítico; clasifica correctamente 10 de 10 (incluidos soportes estáticos) |
| F1.3b | Estado `INTAKE` en el grafo, **sin transición a diseño sin confirmación explícita** | Test: no existe camino de `INTAKE` a `DECOMPOSED` sin la confirmación. Intentarlo lanza error, no avanza |
| F1.4 | Plantillas de macros FreeCAD (sketch + pad + pocket + fillet, export STL/STEP) y `compose_build_script(recipe)` que las ensambla | Una receta de prueba produce un `build.py` que se ejecuta sin error en `freecadcmd` |
| F1.5 | RAG mínimo: indexar en Qdrant la documentación de la API Python de FreeCAD (Part/PartDesign/Sketcher) + ejemplos propios | Una consulta "pocket circular en cara superior" devuelve el ejemplo correcto |
| F1.6 | **Part Designer Agent**: emite `recipe.json` (**no Python**); el orquestador compone `build.py` y lo ejecuta en `freecadcmd` | Soporte NEMA17 generado con dimensiones correctas en ≥ 4 de 5 intentos |
| F1.7 | Bucle de error en dos niveles: receta inválida → error de esquema al agente (barato, sin ejecutar); fallo de ejecución → traceback al agente (máx. 3) | Tasa de éxito final ≥ 4 de 5; los errores de esquema se detectan sin lanzar FreeCAD |
| F1.8 | **Slicing/Cost Agent** mínimo: laminar con perfil fijo y leer estadísticas | Reporte con gramos, tiempo y si requiere soportes |
| F1.9 | Grafo LangGraph lineal: Admisión → Part Designer → Slicing, con estado en `state.sqlite` | Un comando CLI ejecuta todo y deja los artefactos en `workspace/projects/<id>/` |
| F1.10 | Versionado git automático del proyecto tras cada estado | `git log` del proyecto muestra un commit por etapa |
| F1.11 | **Registro de proyectos** `workspace/registry.sqlite` (§ 5.1): id fecha+slug, nombre, clase, estado, fechas, coste, **qué espera del humano** | Tres proyectos de clases distintas coexisten; una consulta devuelve cuál espera qué |
| F1.12 | `submit()` en el `HumanPort` + adaptador CLI (`intelliprint new`), con adjuntos guardados en `intake/` | Un requerimiento con dos fotos crea el proyecto, lo registra y guarda los adjuntos dentro de `workspace/` |
| F1.13 | `MAX_CONCURRENT_PROJECTS` y cola de proyectos (regla 9 de § 4) | Con el límite en 1, el segundo proyecto queda encolado en vez de competir por la GPU |

**Entregable:** `intelliprint new "soporte para motor NEMA17 atornillable a perfil 2020"` abre la admisión, pregunta lo que falte, y tras confirmar produce `.FCStd`, `.stl`, `.3mf` y reporte, con el proyecto dado de alta en el registro.

**Prueba real:** imprimir el soporte y comprobar que el motor y el perfil encajan. Anotar las holguras reales medidas (entrada para la Fase 2).

---

### Fase 2 — Herramientas deterministas y QA (semanas 4–5)

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
| F2.9 | **Tolerances/DFM Agent** | Aplica holguras según interfaz y deja la pieza orientada para imprimir |
| F2.10 | `derive_assertions(interface)`: aserciones medibles por tipo de interfaz (**capa 1 del QA**) | Una interfaz `bearing_seat` 608zz `press` produce la aserción Ø22.10 ±0.05 sin intervención de ningún LLM |
| F2.11 | **QA Agent de tres capas** (§ 7.1 de la arquitectura): aserciones + DFM + pase libre con visión, y `qa_report.json` | Detecta ≥ 8 de 10 defectos sembrados |
| F2.12 | **Regla dura del veredicto**: `PASS ⟺ capa1 ∧ capa2 ∧ sin_defectos_LLM`. El LLM escribe en una lista, no en el veredicto | Test adversarial: con un QA Agent forzado a responder siempre "aprobado", una pieza con cota fuera de tolerancia **sigue dando FAIL** |
| F2.13 | Capa de visión: pasar los renders de `views/` al modelo y pedir defectos | Detecta ≥ 3 de 5 catástrofes sembradas invisibles a las cotas (pocket en cara equivocada, sólido partido, booleana que borra media pieza) |
| F2.14 | Bucle Part Designer ↔ DFM ↔ QA con máximo 3 iteraciones | Una pieza con defecto sembrado se corrige y pasa |
| F2.15 | **Pieza de calibración de holguras** generada por el sistema (peine de agujeros y ejes 0.0–0.5 mm) | Tras imprimirla, el usuario introduce los resultados y el perfil se actualiza |

**Entregable:** soporte NEMA17 regenerado usando generadores de librería, con QA y DFM aprobados; pieza de calibración impresa y perfil ajustado.

---

### Fase 3 — Descomposición y ensamble (semanas 6–8)

**Objetivo:** diseñar productos de varias piezas que encajen entre sí.

| ID | Tarea | Criterio de aceptación |
|----|-------|------------------------|
| F3.1 | Esquemas `ProductTree` e `Interface` con **estados `symbolic` / `resolved`** (§ 3 de la arquitectura) + validador: toda interfaz referencia piezas existentes, sin ciclos, y **ninguna interfaz `symbolic` puede llegar a la Fase 3** | Árboles inválidos rechazados con mensaje claro; una interfaz sin resolver bloquea el avance |
| F3.2 | **Decomposition Agent**: árbol + interfaces **simbólicas** (sin cotas ni `frame`) + tareas con dependencias | Para 5 productos de prueba genera árboles razonables revisados a mano; **ninguna salida contiene números inventados** |
| F3.3 | `resolve_interfaces()`: convierte simbólicas en resueltas usando la hardware library y la salida de la ingeniería de sistema | Toda interfaz de la garra queda resuelta con cotas trazables a `library/`, no a un LLM |
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

### Fase 4 — Ingeniería de sistema y simulación (semanas 9–11)

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

### Fase 5 — Interfaz humana, escalamiento y feedback (semanas 12–14)

| ID | Tarea | Criterio de aceptación |
|----|-------|------------------------|
| F5.1 | Política de escalamiento en `router.py` (fallos, complejidad, contexto, petición manual) | Cada escalamiento registra motivo, tokens y costo |
| F5.2 | Tope `max_usd_per_project` y contador persistente | Al alcanzar el tope se detiene y pide autorización |
| F5.3 | Filtro de datos salientes: solo texto, sin rutas del host ni archivos | Test que verifica que ninguna ruta `C:\` sale hacia DeepSeek |
| F5.4 | **Adaptador web** del `HumanPort` (FastAPI + HTMX): lista de proyectos, estado por pieza, reportes, capturas, botones de gate | Ambos gates se aprueban desde el navegador **sin duplicar la lógica de gate** |
| F5.5 | **Adaptador Telegram** vía OpenClaw: contenedor, lista blanca obligatoria, `ask`/`notify`/**`submit`** con texto e imágenes | Creas un proyecto desde el móvil mandando texto y dos fotos; recibes las preguntas de admisión y un render; respondes y continúa |
| F5.5b | Consultas de registro por Telegram: qué proyectos hay, estado de uno, qué espera de ti | *"¿qué tengo pendiente?"* devuelve la lista con estados desde `registry.sqlite` |
| F5.6 | Peticiones de cambio entrantes → `ChangeRequest` → defecto con autor humano, por la maquinaria de reapertura existente | "haz los dedos más largos" reabre solo las piezas afectadas, sin ruta paralela |
| F5.7 | Seguridad del canal: texto **y contenido de imágenes** como dato, lista blanca de tipos y tamaño de adjuntos, filtro de salida compartido con DeepSeek, escotilla de Python cerrada sin gate | Test de inyección por texto **y por imagen** (una foto con "ignora las instrucciones anteriores" escrito): ninguna ejecuta nada. Ninguna ruta `C:\` sale por Telegram. Un adjunto no permitido se rechaza |
| F5.8 | **Gate humano #2** con resumen: BOM, placas, gramos, horas, advertencias de QA | Aprobación deja los archivos en `fabrication/` |
| F5.9 | Instrucciones de ensamble generadas (orden, hardware por paso, capturas) | Documento legible para montar la garra sin ayuda |
| F5.10 | Registro de feedback de impresión ("flojo", "apretado", "se rompió en X"), también por Telegram | El feedback ajusta el perfil de holguras o crea defectos en la pieza |

**Entregable:** flujo completo operable desde el navegador **y desde el móvil**. El sistema te consulta por Telegram enviándote renders, tú apruebas gates y pides cambios sin estar delante del PC, y los costos de DeepSeek son visibles.

---

### Fase 6 — Endurecimiento (semanas 15–16)

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
F0.5 cliente MCP ─┬─► F1.6 Part Designer ─► F2.14 bucle QA ─► F3.7 piezas ─► F3.8 Assembly
F0.6 router LLM ──┘         ▲                      ▲                              │
F1.4 compose_build_script ──┘                      │                              ▼
F2.2 librería ─► F2.5 generadores ─► F1.6          │            F4.6 URDF ─► F4.9 Test/Sim
F2.4 perfil ─► F2.9 Tolerances                     │
F3.1 esquemas ─► F3.2 Decomposition (simbólicas) ──┼─► F3.3 resolve_interfaces ─► F3.4 gate 1
                                                   │              ▲
F2.10 derive_assertions ───────────────────────────┘              │
F4.1 sim ─► F4.2 Kinematics ─► F4.4 Actuation ────────────────────┘
F0.9 HumanPort ─► F3.4 gate 1 ─► F5.4 web ─► F5.5 Telegram
```

Ruta crítica: F0.5 → F1.4 → F1.6 → F2.5 → F2.14 → F3.2 → F3.3 → F3.8 → F4.6 → F4.9.

> **Dependencia invertida respecto al plan original.** `F3.3 resolve_interfaces` **depende de `F4.2 Kinematics` y `F4.4 Actuation`**: los `frame` salen de la cinemática y el hardware definitivo de la selección de actuadores. Para productos sin cadena cinemática (soporte NEMA17, garra) el resolvedor usa la hardware library y los frames del árbol, y la Fase 3 puede completarse antes de la Fase 4. Para el brazo de 3 y 6 GDL, **la resolución completa no es posible hasta tener la Fase 4**. Es la razón de ser de los dos estados de interfaz: permiten que la Fase 3 avance con lo que sí se puede resolver, en lugar de inventar y corregir después.

---

## 6. Estrategia de pruebas

| Nivel | Qué se prueba | Herramienta |
|-------|---------------|-------------|
| Unitario | Esquemas, `apply_fit`, generadores (dimensiones), `validate_macro`, router | `pytest` dentro de los contenedores |
| Herramientas | Chequeos DFM sobre STL con defectos conocidos | `pytest` + set `tests/fixtures/stl/` |
| Integración | Orquestador ↔ MCP de FreeCAD/PrusaSlicer | `smoke_test` (requiere host con FreeCAD abierto) |
| Agentes | Salida válida y correcta de cada agente sobre casos fijos | Suite de evaluación (F6.1), con semilla y temperatura bajas |
| Adversarial | Que el QA no pueda aprobar una pieza defectuosa (F2.12) y que un mensaje de Telegram no pueda ejecutar código (F5.7) | `pytest` con agentes simulados que responden siempre "aprobado" y con mensajes de inyección |
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

Todas se calculan desde `state.sqlite` y los logs.

---

## 8. Riesgos del plan

| Riesgo | Prob. | Impacto | Mitigación | Plan B |
|--------|-------|---------|------------|--------|
| Geometría generada por el LLM poco fiable | Baja | Alto | **El LLM no genera geometría**: emite una receta validada contra esquema y `build.py` lo compone el orquestador | Ampliar el catálogo de generadores; escotilla con DeepSeek |
| Catálogo de generadores insuficiente | **Alta** | Medio | Es el riesgo que sustituye al anterior: se mide con la métrica de escotilla y se ataca escribiendo generadores | Escotilla con DeepSeek mientras tanto |
| VRAM insuficiente | Baja | Medio | 25 GB de 32 GB con ambos modelos residentes | Descargar `gemma3:12b` y usar `qwen3.8` también para QA |
| Ollama cae a CPU en silencio (Blackwell) | Media | Alto | Verificación explícita de GPU en F0.3; CUDA 12.8+ | Ollama nativo en Windows en vez de contenedor |
| Inyección de prompt por Telegram | Baja | Alto | Lista blanca obligatoria; texto entrante como dato; escotilla cerrada sin gate (F5.7) | Desactivar peticiones de cambio y dejar Telegram solo para notificaciones |
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
| H1 | 3 | Soporte NEMA17 desde texto, impreso |
| H2 | 5 | QA detecta defectos; perfil de holguras calibrado |
| H3 | 8 | Garra MG996R impresa y montada |
| H4 | 11 | Brazo 3 GDL impreso y moviéndose |
| H5 | 14 | Flujo completo desde la UI y desde Telegram, con costos visibles |
| H6 | 16 | Brazo 6 GDL diseñado; suite de evaluación en verde |

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
3. Crear el bot de Telegram y anotar el chat ID propio (S8), necesario para F5.5.
4. Ejecutar F0.1–F0.3 (repositorio, compose, Ollama con GPU) **verificando explícitamente que no cae a CPU**.
5. F0.10: comprobar `freecadcmd` headless en el PC, que es la base del paralelismo de la Fase 3.
