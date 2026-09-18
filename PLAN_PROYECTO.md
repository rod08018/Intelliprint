# Intelliprint — Plan del proyecto

Plan de implementación del sistema descrito en [SISTEMA_MULTIAGENTE.md](SISTEMA_MULTIAGENTE.md). Está organizado en fases incrementales: cada fase termina con algo que funciona de extremo a extremo y se puede probar imprimiendo una pieza real.

---

## 1. Objetivo y alcance

**Objetivo:** que a partir de un requerimiento en lenguaje natural el sistema produzca un diseño mecánico multipieza, ensamblado, probado y laminado, listo para imprimir en FDM, usando modelos locales y DeepSeek solo como respaldo.

**Dentro del alcance**

- Orquestador multiagente en Docker (LangGraph).
- Modelos locales vía Ollama; escalamiento a DeepSeek con tope de costo.
- Integración con los MCP existentes de FreeCAD y PrusaSlicer (en el host).
- MCP nuevos: `mech-toolkit` (geometría/tolerancias/DFM) y `sim` (cinemática y colisiones).
- Librería de hardware comercial.
- UI web mínima para aprobaciones y seguimiento.
- Proyectos de referencia: soporte NEMA17, garra con MG996R, brazo de 3 GDL y brazo de 6 GDL.

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
| S2 | GPU NVIDIA visible en Docker | `docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi` |
| S3 | MCP de FreeCAD y PrusaSlicer funcionando en el host | Ya probados por el usuario |
| S4 | `DEEPSEEK_API_KEY` definida en Windows | `echo $env:DEEPSEEK_API_KEY` (no vacío) |
| S5 | Python 3.11+ y `uv` en el host para los puentes MCP | `python --version`, `uv --version` |
| S6 | Impresora y material de referencia definidos | Llenar `config/printers/<impresora>.yaml` |

**Dato a confirmar al inicio:** VRAM disponible. Determina qué modelos caben a la vez:

| VRAM | Configuración recomendada |
|------|---------------------------|
| 8 GB | Solo `qwen3:8b` (Q4) para todos los roles; 1 tarea a la vez |
| 12–16 GB | `qwen3:8b` + `qwen2.5-coder:14b` alternando; QA con `gemma3:12b` cargado bajo demanda |
| 24 GB+ | 2–3 modelos cargados; 2 Part Designers en paralelo |

---

## 3. Resumen de fases

| Fase | Nombre | Resultado | Esfuerzo estimado* |
|------|--------|-----------|--------------------|
| 0 | Infraestructura | Docker + Ollama + puentes MCP + esqueleto del orquestador | 1 semana |
| 1 | Pipeline de una pieza | Requerimiento → pieza FreeCAD → STL → PrusaSlicer | 2 semanas |
| 2 | Herramientas deterministas y QA | `mech-toolkit`, librería de hardware, QA con mediciones | 2 semanas |
| 3 | Descomposición y ensamble | Varias piezas en paralelo, interfaces, ensamble e interferencias | 3 semanas |
| 4 | Ingeniería de sistema y simulación | Cinemática, actuación, electrónica, `sim`, reapertura selectiva | 3 semanas |
| 5 | Escalamiento, UI y feedback | DeepSeek con presupuesto, gates en UI, calibración con impresiones reales | 2 semanas |
| 6 | Endurecimiento | Evaluaciones, métricas, documentación, brazo de 6 GDL | 2 semanas |

\* Estimado para dedicación parcial (~10–15 h/semana). Total aproximado: **15 semanas**.

```
Semana:   1  2  3  4  5  6  7  8  9 10 11 12 13 14 15
Fase 0   ██
Fase 1      ████
Fase 2            ████
Fase 3                  ██████
Fase 4                        ██████
Fase 5                              ████
Fase 6                                    ████
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
| F0.3 | Habilitar GPU en el contenedor de Ollama y descargar `qwen3:8b` | `ollama run qwen3:8b` responde; `nvidia-smi` muestra uso de GPU |
| F0.4 | `scripts/start-host-mcps.ps1`: lanza `mcp-proxy` para FreeCAD (:8101) y PrusaSlicer (:8102) | `curl http://localhost:8101/sse` responde en el host |
| F0.5 | Cliente MCP en `orchestrator/mcp/client.py` (HTTP/SSE) | Desde el contenedor se listan las herramientas de ambos MCP |
| F0.6 | `orchestrator/llm/router.py` con proveedor local y DeepSeek (defaults para `DEEPSEEK_BASE_URL` y `DEEPSEEK_MODEL`) | Test que llama a cada proveedor y devuelve texto; si falta la API key, DeepSeek queda deshabilitado sin romper |
| F0.7 | Traducción de rutas contenedor ↔ host (`WORKSPACE` ↔ `HOST_WORKSPACE`) | Un archivo creado en `/workspace/test.txt` es abierto por FreeCAD vía MCP |
| F0.8 | Logging estructurado (JSONL) de cada llamada a LLM y herramienta | Cada llamada deja una línea en `workspace/<proyecto>/log/` |

**Entregable:** comando `docker compose run orchestrator python -m smoke_test` que crea un cubo en FreeCAD, exporta STL y lo lamina en PrusaSlicer, sin LLM.

**Riesgos:** GPU no disponible en WSL2 → plan B: Ollama nativo en Windows y `OLLAMA_URL=http://host.docker.internal:11434`.

---

### Fase 1 — Pipeline de una pieza (semanas 2–3)

**Objetivo:** primer flujo con LLM de extremo a extremo para una pieza simple.

| ID | Tarea | Criterio de aceptación |
|----|-------|------------------------|
| F1.1 | Esquemas Pydantic: `Spec`, `PartTask`, `PartResult`, `SlicingReport` | Validación falla con mensajes claros ante datos incompletos |
| F1.2 | Salida estructurada: JSON mode de Ollama + validación + reintento con el error | ≥ 90 % de respuestas válidas en 20 pruebas con `qwen3:8b` |
| F1.3 | **Requirements Agent** (prompt en `config/agents/requirements.md`) | Convierte 10 pedidos de prueba en `spec.yaml` válidos; pregunta cuando falta un dato crítico |
| F1.4 | Plantillas de macros FreeCAD (sketch + pad + pocket + fillet, export STL/STEP) | Las plantillas se ejecutan sin error en FreeCAD |
| F1.5 | RAG mínimo: indexar en Qdrant la documentación de la API Python de FreeCAD (Part/PartDesign/Sketcher) + ejemplos propios | Una consulta "pocket circular en cara superior" devuelve el ejemplo correcto |
| F1.6 | **Part Designer Agent**: genera `build.py` parametrizado desde `params.json` y lo ejecuta vía MCP | Soporte NEMA17 generado con dimensiones correctas en ≥ 3 de 5 intentos |
| F1.7 | Bucle de error: si la macro falla, reenviar traceback al agente (máx. 3) | Tasa de éxito final ≥ 4 de 5 |
| F1.8 | **Slicing/Cost Agent** mínimo: laminar con perfil fijo y leer estadísticas | Reporte con gramos, tiempo y si requiere soportes |
| F1.9 | Grafo LangGraph lineal: Requirements → Part Designer → Slicing, con estado en `state.sqlite` | Un comando CLI ejecuta todo y deja los artefactos en `workspace/<proyecto>/` |
| F1.10 | Versionado git automático del proyecto tras cada estado | `git log` del proyecto muestra un commit por etapa |

**Entregable:** `intelliprint new "soporte para motor NEMA17 atornillable a perfil 2020"` produce `.FCStd`, `.stl`, `.3mf` y reporte.

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
| F2.7 | Macros de medición vía FreeCAD MCP: `measure`, `section_view` | Miden diámetros de agujeros con error < 0.01 mm |
| F2.8 | `validate_macro`: análisis estático (AST) que bloquea `os`, `shutil`, `subprocess`, `open` fuera de `workspace/`, etc. | 100 % de las macros maliciosas de prueba bloqueadas; 0 falsos positivos en las plantillas |
| F2.9 | **Tolerances/DFM Agent** | Aplica holguras según interfaz y deja la pieza orientada para imprimir |
| F2.10 | **QA Agent** con modelo distinto (`gemma3:12b`); checklist obligatorio + `qa_report.json` con PASS/FAIL y defectos | Detecta ≥ 8 de 10 defectos sembrados; no aprueba piezas con fallas numéricas |
| F2.11 | Bucle Part Designer ↔ DFM ↔ QA con máximo 3 iteraciones | Una pieza con defecto sembrado se corrige y pasa |
| F2.12 | **Pieza de calibración de holguras** generada por el sistema (peine de agujeros y ejes 0.0–0.5 mm) | Tras imprimirla, el usuario introduce los resultados y el perfil se actualiza |

**Entregable:** soporte NEMA17 regenerado usando generadores de librería, con QA y DFM aprobados; pieza de calibración impresa y perfil ajustado.

---

### Fase 3 — Descomposición y ensamble (semanas 6–8)

**Objetivo:** diseñar productos de varias piezas que encajen entre sí.

| ID | Tarea | Criterio de aceptación |
|----|-------|------------------------|
| F3.1 | Esquemas `ProductTree`, `Interface` (ver sección 3 de la arquitectura) y validador de consistencia (toda interfaz referencia piezas existentes, sin ciclos de dependencia) | Árboles inválidos rechazados con mensaje claro |
| F3.2 | **Decomposition Agent**: árbol + interfaces + tareas con dependencias | Para 5 productos de prueba genera árboles razonables revisados a mano |
| F3.3 | **Gate humano #1** vía CLI (aprobar / editar / rechazar spec y árbol) | El flujo se pausa y se reanuda desde el estado guardado |
| F3.4 | Planificador de tareas: orden topológico y ejecución paralela limitada por `MAX_PARALLEL_PARTS` | Piezas independientes se diseñan en paralelo sin saturar VRAM |
| F3.5 | Part Designer recibe interfaces y usa los `frame` para ubicar features | Las features de interfaz quedan en las coordenadas definidas |
| F3.6 | **Assembly Agent**: importa piezas y hardware, posiciona según interfaces, genera `assembly.FCStd` | Ensamble de la garra cargado correctamente en FreeCAD |
| F3.7 | `interference_check` (booleana de intersección entre pares) con reporte de volumen y ubicación | Detecta interferencias sembradas ≥ 0.05 mm³ |
| F3.8 | Generación de BOM (`bom.csv`) de piezas impresas + hardware | BOM coincide con el ensamble |
| F3.9 | QA de ensamble: interfaces coherentes a ambos lados (mismo patrón, misma holgura) | Detecta patrones de tornillos desalineados |
| F3.10 | Reapertura selectiva: un defecto de ensamble reabre solo las piezas/interfaces implicadas | Tras modificar una interfaz, solo se regeneran las piezas que la usan |
| F3.11 | Slicing por placas: agrupar piezas en la cama y laminar cada placa | Reporte con número de placas, gramos y horas totales |

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
| F4.10 | Integrar al grafo: Fase 2 del sistema antes del diseño de piezas; Test después del ensamble | Flujo completo para brazo de 3 GDL sin intervención salvo gates |

**Entregable:** brazo de 3 GDL con torque validado, sin colisiones en su rango, impreso y movido con servos.

---

### Fase 5 — Escalamiento, UI y feedback (semanas 12–13)

| ID | Tarea | Criterio de aceptación |
|----|-------|------------------------|
| F5.1 | Política de escalamiento en `router.py` (fallos, complejidad, contexto, petición manual) | Cada escalamiento registra motivo, tokens y costo |
| F5.2 | Tope `max_usd_per_project` y contador persistente | Al alcanzar el tope se detiene y pide autorización |
| F5.3 | Filtro de datos salientes: solo texto, sin rutas del host ni archivos | Test que verifica que ninguna ruta `C:\` sale hacia DeepSeek |
| F5.4 | UI web (FastAPI + HTMX o similar): lista de proyectos, estado por pieza, vista de reportes y capturas, botones de gate | Ambos gates se aprueban desde el navegador |
| F5.5 | **Gate humano #2** con resumen: BOM, placas, gramos, horas, advertencias de QA | Aprobación deja los archivos en `fabrication/` |
| F5.6 | Instrucciones de ensamble generadas (orden, hardware por paso, capturas) | Documento legible para montar la garra sin ayuda |
| F5.7 | Registro de feedback de impresión ("flojo", "apretado", "se rompió en X") | El feedback ajusta el perfil de holguras o crea defectos en la pieza |

**Entregable:** flujo completo operado desde la UI, con costos de DeepSeek visibles.

---

### Fase 6 — Endurecimiento (semanas 14–15)

| ID | Tarea | Criterio de aceptación |
|----|-------|------------------------|
| F6.1 | Suite de evaluación: 10 requerimientos de referencia con resultados esperados | Se ejecuta con un comando y produce tabla de métricas |
| F6.2 | Comparar modelos locales por rol (qwen3, qwen2.5-coder, gemma3, mistral-small) | Tabla de tasa de éxito, iteraciones y tiempo por rol; actualizar `models.yaml` |
| F6.3 | Afinar prompts con los fallos más frecuentes de los logs | Mejora medible en la suite |
| F6.4 | Reanudación tras caída (reiniciar contenedor a mitad de proyecto) | El proyecto continúa desde el último estado |
| F6.5 | Documentación: README de uso, cómo añadir hardware, impresoras y agentes | Un tercero puede levantar el sistema siguiendo el README |
| F6.6 | Proyecto final: brazo de 6 GDL | Diseño completo con < 20 % de pasos escalados a DeepSeek |

---

## 5. Dependencias entre tareas críticas

```
F0.5 cliente MCP ─┬─► F1.6 Part Designer ─► F2.11 bucle QA ─► F3.5 piezas con interfaces ─► F3.6 Assembly
F0.6 router LLM ──┘                                                                             │
F2.2 librería ──► F2.5 generadores ──► F3.5                                                     ▼
F2.4 perfil ──► F2.9 Tolerances                                               F4.6 URDF ─► F4.9 Test/Sim
F3.1 esquemas ─► F3.2 Decomposition ─► F3.4 planificador ─► F3.5
F4.1 sim ─► F4.2 Kinematics ─► F4.4 Actuation
```

Ruta crítica: F0.5 → F1.6 → F2.5 → F2.11 → F3.2 → F3.6 → F4.6 → F4.9.

---

## 6. Estrategia de pruebas

| Nivel | Qué se prueba | Herramienta |
|-------|---------------|-------------|
| Unitario | Esquemas, `apply_fit`, generadores (dimensiones), `validate_macro`, router | `pytest` dentro de los contenedores |
| Herramientas | Chequeos DFM sobre STL con defectos conocidos | `pytest` + set `tests/fixtures/stl/` |
| Integración | Orquestador ↔ MCP de FreeCAD/PrusaSlicer | `smoke_test` (requiere host con FreeCAD abierto) |
| Agentes | Salida válida y correcta de cada agente sobre casos fijos | Suite de evaluación (F6.1), con semilla y temperatura bajas |
| Extremo a extremo | Proyectos de referencia completos | CLI `intelliprint eval` |
| Físico | Impresión y montaje real | Checklist manual por hito |

Regla: las herramientas deterministas deben tener tests antes de que un agente las use.

---

## 7. Métricas de éxito

| Métrica | Meta final |
|---------|-----------|
| Piezas que pasan QA en ≤ 3 iteraciones | ≥ 85 % |
| Ensambles sin interferencias en el primer ensamble | ≥ 70 % |
| Pasos escalados a DeepSeek | < 20 % |
| Costo DeepSeek por proyecto | < 2 USD |
| Encajes correctos en impresión real (sin lijar) | ≥ 90 % de las interfaces |
| Tiempo de diseño de la garra (sin impresión) | < 45 min |

Todas se calculan desde `state.sqlite` y los logs.

---

## 8. Riesgos del plan

| Riesgo | Prob. | Impacto | Mitigación | Plan B |
|--------|-------|---------|------------|--------|
| Macros FreeCAD generadas por 8B poco fiables | Alta | Alto | Generadores de `mech-toolkit` + plantillas + RAG | Part Designer solo rellena parámetros de plantillas; DeepSeek para piezas atípicas |
| VRAM insuficiente | Media | Medio | Cuantización Q4, un modelo por rol cargado a la vez | Usar `qwen3:8b` para todos los roles |
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
| H5 | 13 | Flujo completo desde la UI con costos visibles |
| H6 | 15 | Brazo 6 GDL diseñado; suite de evaluación en verde |

---

## 10. Mejoras futuras

- Análisis FEM simple con CalculiX (FreeCAD FEM) para piezas críticas.
- Generación de firmware base (ESP32) a partir de la spec de electrónica.
- Soporte para Cura/OrcaSlicer y múltiples impresoras.
- Visión: comparar foto de la pieza impresa contra el modelo para feedback automático.
- Biblioteca de diseños aprobados reutilizables como punto de partida.
- Integración de OpenClaw como interfaz de chat sobre el orquestador.

---

## 11. Próximos pasos inmediatos

1. Confirmar VRAM de la GPU y la impresora/material de referencia.
2. Confirmar cómo se lanzan hoy los MCP de FreeCAD y PrusaSlicer (comando exacto y si son stdio o HTTP).
3. Ejecutar F0.1–F0.3 (repositorio, compose, Ollama con GPU).
