# Intelliprint — Registro de decisiones de arquitectura

Cada entrada explica **por qué** el sistema es como es. [SISTEMA_MULTIAGENTE.md](SISTEMA_MULTIAGENTE.md) describe el *qué*; esto describe el *por qué* y qué se descartó.

Fecha de la sesión: **2026-09-18**.

---

## ADR-001 · Las interfaces tienen dos estados: simbólica y resuelta

**Estado:** aceptada · **Afecta a:** § 3, § 4 de la arquitectura; F3.1–F3.4

**Problema.** El diseño original ponía `Decomposition` en la Fase 1 y `Kinematics`/`Actuation` en la Fase 2, pero pedía a `Decomposition` que emitiera interfaces con geometría concreta (`frame: {origin: [0, 0, 45]}`). Eso es imposible de hacer bien: el `45` depende de longitudes de eslabón que aún no se han calculado, y el patrón de tornillos depende de un motor que aún no se ha elegido. El modelo no tenía más opción que inventar. Peor: el **gate humano #1** hacía aprobar precisamente esos números inventados, que la Fase 2 iba a cambiar después.

**Decisión.** Una interfaz nace **simbólica** (tipo, piezas, clase de hardware, `fit`, rol — sin una sola cota) y la Fase 2 la **resuelve** a números por código. El gate #1 se mueve detrás de la resolución.

**Alternativas descartadas.**
- *Reordenar el grafo* (cinemática antes que descomposición): circular. La cinemática necesita saber qué eslabones existen, y eso sale de la descomposición. Además no aplica a productos sin cadena cinemática, como la garra o el soporte NEMA17.
- *Dejarlo y confiar en la reapertura selectiva*: pagas iteraciones de LLM para corregir números que nunca debieron inventarse, y apruebas en el gate algo que sabes que va a cambiar.

**Consecuencias.** El esquema `Interface` gana un estado y el validador impide que una interfaz `symbolic` llegue a la Fase 3. Aparece una dependencia invertida respecto al plan original: `F3.3 resolve_interfaces` depende de `F4.2` y `F4.4` para productos con cinemática.

---

## ADR-002 · El Part Designer emite recetas, no Python

**Estado:** aceptada · **Afecta a:** § 2, § 5, § 6.3, § 8.3; F1.6, F1.10, F1.11, F2.9

**Problema.** El documento original estaba a medio camino entre dos arquitecturas incompatibles: la tarea del Part Designer decía que el agente genera `build.py`, y § 9.2 decía que `mech-toolkit` tiene generadores. La tabla de riesgos calificaba "macros generadas por un modelo pequeño" como probabilidad **alta** e impacto **alto** — el mayor riesgo del proyecto.

**Decisión.** El Part Designer emite una **receta**: una lista validada contra esquema de llamadas a generadores con sus parámetros. `build.py` lo compone el orquestador. Existe una **escotilla** para piezas atípicas donde sí se permite Python libre, con DeepSeek y `validate_macro`.

**Por qué.** Un error del modelo pasa de ser un traceback tras ejecutar FreeCAD a un campo rechazado por el esquema antes de lanzar nada. Y rellenar un JSON de seis campos es una tarea mucho más fácil que escribir Python de la API de FreeCAD, que es justo donde los modelos se caen.

**Consecuencias.**
- Desaparece la necesidad de un modelo especializado en código (`qwen2.5-coder:14b` sale del stack).
- **El porcentaje de piezas que usan la escotilla se convierte en métrica de producto**, no en tasa de fallo: cada pieza atípica nombra el generador que falta escribir. El sistema se vuelve más determinista con el uso.
- El riesgo principal se desplaza de "el modelo escribe mal" a "me faltan generadores", que es un problema de trabajo acotado en vez de uno de fiabilidad estadística.

**Enmienda (2026-11-04): las piezas sueltas se escriben con un kit, en una lista blanca (F5.18 (kit)).**

**Qué falló.** «Me faltan generadores» resultó no ser un problema acotado: cada pieza real necesitaba uno nuevo.
- Las V del sargento salieron con 63 cajas en escalera.
- Los hexágonos salieron cuadrados.
- La escuadra de repisa, con un concepto bueno (una L con nervio, tumbada), salió maciza: 121 g. No había manera de decir «este perfil, extruido».

La escotilla de F2.9 nunca se construyó.

**Decisión.** Para las piezas sueltas, el diseñador escribe una función `construir(kit)` contra un **kit** propio (`mech_toolkit/kit/`). El kit tiene:
- perfiles extruidos en cualquier plano y revolución;
- booleanas, giros y espejo;
- redondeo y chaflán por selector de aristas;
- agujeros (lágrima, avellanado), tornillos y tuercas **con la tabla del perfil**, y colisas.

Cada agujero, tuerca o hueco lleva **nombre** y queda registrado como rasgo (ADR-011). Es lo que se medirá contra los requisitos.

**Lo que cambia de la seguridad.** Ya no viene de que el código lo escriba una persona. Viene de dos cosas:
- **La lista blanca** (`kit/sandbox.py`), que se comprueba dos veces: en el orquestador y otra vez dentro de FreeCAD antes de ejecutar.
  - Solo se admite una función `construir`, aritmética, `for`, `if` y colecciones.
  - Solo se pueden usar **los atributos de la API del kit**: ningún `_algo`, ni `__class__`, ni `gi_frame`.
  - Nada de `import`, `open`, `eval`, clases ni `try`.
- **Medir lo que sale.** El epílogo sigue exigiendo un sólido válido y uno solo. La medida contra los requisitos es F2.6 y F2.12.

**Lo que se conserva.** Un error del modelo sigue volviendo como un error con línea y motivo, dentro del bucle de reintento, antes de lanzar FreeCAD. Los mecanismos siguen con recetas hasta que el kit los cubra: el flujo de mecanismos depende de las cajas envolventes de cada generador.

---

## ADR-003 · El veredicto del QA es aritmético; el LLM solo puede añadir defectos

**Estado:** aceptada · **Afecta a:** § 3.3, § 7.1; F2.12–F2.16

**Problema.** El riesgo "QA aprueba todo" estaba mitigado únicamente con "usa otro modelo". Es una defensa débil: un `gemma3:12b` tampoco sabe qué debería medir en una pieza que no diseñó, y sigue siendo un LLM emitiendo un juicio.

**Decisión.** Tres capas —aserciones derivadas del contrato, chequeos DFM, y un pase libre con visión— y una regla dura:

```
PASS  ⟺  capa1.todas_ok  ∧  capa2.todas_ok  ∧  capa3.defectos == []
```

El LLM escribe en una **lista de defectos**, nunca en el veredicto. No existe ninguna ruta por la que pueda convertir un `FAIL` determinista en `PASS`.

**Por qué funciona.** El peor comportamiento posible de un modelo complaciente pasa a ser *ser inútil* (no aportar defectos) en vez de *aprobar una pieza rota*. Un fallo silencioso se convierte en un fallo barato.

**Habilitado por ADR-001.** Solo es posible porque una interfaz resuelta contiene lo necesario para generar sus propias pruebas: de `IF-003 = bearing_seat, 608zz, press` se deriva mecánicamente "agujero Ø22.10 ±0.05 en el frame de IF-003". Las interfaces dejan de ser documentación y pasan a ser la especificación ejecutable del QA.

**Consecuencia lateral.** Usar un modelo distinto para QA deja de ser un requisito de correctitud y pasa a ser una segunda red opcional. Eso libera presión de VRAM y desacopla el diseño de la elección de modelos.

---

## ADR-004 · Construcción headless, inspección con GUI

**Estado:** aceptada · **Afecta a:** § 9.3, regla 6 de § 4; F0.10, F3.5

**Problema.** La Fase 3 exige diseñar piezas en paralelo, pero el MCP de FreeCAD habla por RPC con **una** instancia en un puerto fijo. Con una GPU rápida, el cuello de botella deja de ser el modelo y pasa a ser FreeCAD.

**Decisión.** Cada pieza se construye en su propio proceso `freecadcmd` efímero. Una única instancia con GUI queda para renderizar vistas y ensamblar.

**Alternativas descartadas.**
- *Pool de instancias GUI en puertos distintos*: obliga a parchear el addon y consume varios GB y una ventana por pieza.
- *Serializar el acceso a una sola FreeCAD*: serializa justo la parte lenta.

**Por qué encaja.** Si `build.py` regenera siempre la pieza desde parámetros, un proceso limpio por pieza es lo natural: sin documento global, sin estado compartido. Un cuelgue de FreeCAD mata una pieza, no el proyecto.

**Tensión conocida.** `freecadcmd` no renderiza. Por eso la inspección se separa: la instancia GUI carga los `.FCStd` ya construidos solo para capturar las imágenes que consume la capa de visión del QA (ADR-003).

*Verificado en macOS el 2026-09-18: `freecadcmd` construye y exporta STL sin GUI.*

---

## ADR-005 · `validate_macro` es una red de seguridad, no un límite de seguridad

**Estado:** aceptada · **Afecta a:** § 8.3; F2.8

**Problema.** El documento presentaba `validate_macro` (lista negra sobre AST) como la razón por la que es seguro no restringir más el acceso al PC. Una lista negra de AST se esquiva sin dificultad con `getattr`, `__import__`, `__builtins__` o `__class__.__bases__`.

**Decisión.** No se endurece la lista negra: se **declara explícitamente su alcance real** en la documentación. Su amenaza es un modelo confundido que borra algo por error, no un atacante.

**Por qué es aceptable.** ADR-002 elimina casi toda la superficie: en el camino normal no hay Python arbitrario que validar. `validate_macro` solo actúa en la escotilla.

**Si algún día hace falta una garantía real**, la respuesta no es una lista negra mejor, sino ejecutar `freecadcmd` en un contenedor desechable sin red y con solo la carpeta de la pieza montada. Anotado en mejoras futuras.

---

## ADR-006 · Telegram es un adaptador de un `HumanPort`, no un agente

**Estado:** aceptada · **Afecta a:** § 8.5, reglas 7 y 8 de § 4; F0.9, F5.4–F5.7

**Problema.** Se pidió "un agente OpenClaw con Telegram" para que el sistema pueda consultar cosas del diseño y recibir peticiones de cambio.

**Decisión.** OpenClaw **no entra en el grafo**. Se define un `HumanPort` con `ask(pregunta, adjuntos)` y `notify(evento)`, y CLI, web y Telegram son tres **adaptadores** del mismo puerto.

**Por qué no es un agente.** Los agentes son trabajadores: leen el blackboard y producen artefactos. OpenClaw mueve mensajes. Además un nodo del grafo se planifica, y los mensajes llegan de forma asíncrona, incluso cuando no hay ningún nodo ejecutándose. Y ya existían dos gates y una UI planeada que son la misma operación —preguntar y esperar—: meter Telegram como agente habría triplicado esa lógica.

**Beneficio colateral.** Unifica el gate por consola (F0.9) y el gate por navegador (F5.4), que en el plan original eran dos implementaciones separadas de lo mismo.

**Asincronía.** Una consulta pone la pieza en `BLOCKED_ON_HUMAN` y el planificador sigue con las demás; los gates sí bloquean el proyecto. Sin esto, una duda sobre una pieza congelaría las otras seis — y el caso de uso es precisamente que no estés delante del PC.

**Peticiones de cambio.** Un cambio pedido por ti es **un defecto con autor humano** y entra por la maquinaria de reapertura existente (reglas 3 y 4), con sus límites de iteración. No hay camino paralelo.

**Seguridad.** Este canal es entrada no confiable a un sistema que puede ejecutar código (ADR-002). Lista blanca obligatoria; el texto entrante es dato y nunca instrucción de sistema; una petición de cambio nunca abre la escotilla de Python sin gate; el filtro de salida de DeepSeek se aplica también aquí.

---

## ADR-007 · Dos modelos residentes, configurados por perfil

**Estado:** aceptada · **Afecta a:** § 6.1; F0.3

**Contexto.** Hardware confirmado: RTX 5090 (32 GB VRAM) y 92 GB de RAM. El documento original estaba calibrado para `qwen3:8b`.

**Decisión.** `qwen3.8` (27B, con `tools`, `thinking` y `vision`, 16.5 GB) para todos los roles de diseño, y `gemma3:12b` (~8 GB, también con visión) residente para QA. Total ~25 GB de 32 GB. `config/models.yaml` define perfiles `prod` y `dev` para poder desarrollar en un portátil sin GPU.

**Por qué importa la visión.** Habilita la capa 3 del QA (ADR-003). Sin ella, `section_view` producía imágenes que nadie podía mirar.

**Riesgo específico del hardware.** La 5090 es Blackwell (`sm_120`) y requiere CUDA 12.8+. Una versión antigua de Ollama **no falla: cae a CPU en silencio**. F0.3 debe verificar explícitamente el uso de GPU, o se perderán horas creyendo que el modelo es lento.

**Nota.** Estas elecciones son configuración, no arquitectura. Ninguna de las decisiones ADR-001 a ADR-006 depende de qué modelo se use — que es la señal de que las fronteras están en el sitio correcto.

### ADR-007b · El perfil `dev` usa DeepSeek — temporal, con fecha de caducidad

**Estado:** aceptada, **temporal** · **Afecta a:** § 6.1.1; `config/models.yaml`, `.env`

**Problema.** El desarrollo empezó en un portátil sin GPU y la máquina de destino (RTX 5090) no estaba disponible. Todo lo que necesita un LLM —F1.3 salida estructurada, F1.4 Requirements, F1.10 Part Designer, F1.11 bucle de error— quedaba bloqueado.

**Decisión.** El perfil `dev` apunta a `deepseek/deepseek-chat` en la nube, con la clave en `.env` (no versionado). El perfil `prod` no cambia.

**Esto incumple la primera restricción del sistema.** "Local primero" (§ 1) dice que DeepSeek es *solo* escalamiento. Aquí es el proveedor principal. Se acepta como **deuda declarada, no como diseño**, y la migración está escrita en § 6.1.1 con su lista de pasos.

**Por qué es tolerable.** Porque las fronteras están donde deben: los agentes referencian roles (`$design`, `$qa`), no modelos. Migrar es cambiar una variable de entorno. Si el diseño hubiera acoplado agentes a modelos concretos, esta decisión sería irreversible en vez de temporal.

**Lo que no se puede dar por bueno hasta migrar.** `deepseek-chat` sigue esquemas mejor que `qwen3.8`, así que **es un suelo optimista**: lo que falle aquí fallará más en local, pero lo que funcione aquí no está validado. Además quedan sin probar la capa 3 del QA (DeepSeek no tiene visión), el RAG (sin embeddings) y toda medida de rendimiento.

**Riesgo principal.** Que el perfil `dev` se quede. La mitigación es que esté escrito como deuda en tres sitios —aquí, en § 6.1.1 y en `models.yaml`— en vez de ser un detalle de configuración que nadie recuerda.

---

## ADR-008 · Fase de admisión conversacional, con `submit()` en el `HumanPort`

**Estado:** aceptada · **Afecta a:** § 4.1, § 8.5, § 5.2; F1.5, F5.2, F5.3

**Problema.** El `HumanPort` de ADR-006 solo cubría la dirección sistema → humano (`ask`, `notify`). Las peticiones de cambio iban de humano a sistema, pero **solo sobre un proyecto existente**. No había forma de *arrancar* uno salvo el comando de consola `intelliprint new`, que obliga a estar delante del PC para empezar y luego permite seguirlo desde el móvil — al revés de como se usa en la práctica.

**Decisión.** Se añade una tercera operación al mismo puerto:

```
ask(pregunta, adjuntos) -> respuesta     sistema → humano
notify(evento)                           sistema → humano
submit(texto, adjuntos) -> proyecto      humano  → sistema
```

Y un estado `INTAKE` delante de todo, donde el Requirements Agent **conversa** hasta completar la spec y el usuario confirma explícitamente antes de que empiece el diseño.

**Por qué un estado y no una convención.** El requisito era "que me pregunte cosas antes de que el sistema empiece a diseñar". Si eso depende de que un agente recuerde preguntar, fallará. Como estado del grafo, **no existe la transición de `INTAKE` a diseño sin confirmación**: es imposible saltárselo.

**Consecuencias.**
- La admisión no consume GPU: no abre FreeCAD ni diseña. Puede haber varias conversaciones abiertas a la vez.
- Es asíncrona, como `BLOCKED_ON_HUMAN`: un proyecto puede esperar días en `INTAKE`.
- Los **adjuntos son entrada de diseño real**, no decoración, porque el stack tiene visión (ADR-007): fotos del sitio de montaje, croquis a mano con cotas, o un STL con el que la pieza debe encajar.
- Tres reglas de seguridad nuevas (5–7 de § 8.5): lista blanca de tipos y tamaño, el contenido de una imagen es dato (un modelo de visión lee el texto escrito dentro de una foto, así que la inyección por imagen es real), y los adjuntos no se ejecutan ni salen de `workspace/`.

---

## ADR-009 · Registro global de proyectos

**Estado:** aceptada · **Afecta a:** § 5.1, regla 9 de § 4; F5.1, F5.4

**Problema.** El diseño original asumía un proyecto cada vez: un directorio `workspace/projects/<proyecto>/` con su `state.sqlite`. El uso real es **muchos proyectos simultáneos y heterogéneos** —una garra, un soporte para un carruaje, un brazo— y no había forma de preguntar qué hay en marcha ni cuál espera algo del usuario.

**Decisión.** `workspace/registry.sqlite` como índice global, con identificadores **fecha + slug** (`2026-09-21-soporte-vaso-carruaje`): legibles, ordenables y sin colisiones.

El registro guarda por proyecto: id, nombre, clase, estado, fechas, coste acumulado de DeepSeek y **qué espera de ti**. Ese último campo es el que hace útil preguntar "¿qué tengo pendiente?" desde el móvil.

**Enmienda (2026-09-20): el registro no es una base de datos, y «en marcha» hay que medirlo.** No existe `registry.sqlite`. `orchestrator/registry.py` clasifica cada proyecto por **lo que hay dentro de su carpeta** —`rounds.json`, `design_cost.json`, `job.json`, los artefactos—, y escribe un `INDEX.md` legible. Un índice aparte se desincroniza con la realidad; la carpeta no puede.

Lo caro fue acertar con **«en marcha»**, porque de eso depende que el canal humano diga «sigue trabajando» o «se colgó». Tres cosas que costaron un fallo cada una:

- **Estar en la tabla de procesos no es estar trabajando.** Un proceso terminado cuyo padre no ha recogido queda **zombi**, y `os.kill(pid, 0)` responde que sí existe. El mecanismo de Ginebra falló a las 09:42 y seis horas después el registro seguía diciendo «en marcha». Ahora se mira además el estado con `ps`: una `Z` es un muerto.
- **Llevar mucho tiempo no es estar colgado.** La primera regla miraba el tiempo total y Crafty avisó de un cuelgue con el trinquete trabajando bien desde hacía 53 minutos. Lo que vale es **cuánto lleva sin escribir**: `parece_colgado` son 12 minutos sin tocar un archivo.
- **Esa señal de vida hay que dejarla salir.** Python bufera 8 KB cuando la salida va a un archivo, así que `run.log` se quedaba vacío rondas enteras: ningún archivo tocado, proyecto aparentemente colgado, y quien preguntaba por el estado no tenía nada que leer. Los trabajos arrancan sin búfer (`PYTHONUNBUFFERED`).

Y una regla que no es técnica: **archivar no es borrar**. Lo no aprobado se **mueve** a `archivo/` con todo dentro, porque un intento fallido es la única prueba de por qué algo no funcionó.

**Consecuencia.** Aparece `MAX_CONCURRENT_PROJECTS`, distinto de `MAX_PARALLEL_PARTS`: uno limita cuántos proyectos avanzan, el otro cuántas piezas dentro de cada uno. Confundirlos satura la GPU o desaprovecha la CPU.

---

## ADR-010 · Clases de producto y fases condicionales

**Estado:** aceptada · **Afecta a:** § 4.2, § 2; F1.4, F4.10

**Problema.** La arquitectura era **robot-céntrica**. La Fase 2 son tres agentes —Kinematics, Actuation, Electronics— y para un soporte estático los tres sobran. El coste no es el tiempo: es que **un agente al que se le pide la cinemática de un soporte se la inventa**, y esa invención entra en las interfaces y contamina el diseño.

**Decisión.** El Requirements Agent clasifica el producto durante la admisión, y el grafo salta las fases que no aplican:

| Clase | Fase 2 |
|---|---|
| `static_part` | se salta entera |
| `mechanism` | solo Actuation |
| `robot` | Kinematics + Actuation + Electronics |

**Por qué es una decisión de corrección y no de rendimiento.** Quita la oportunidad de alucinar en lugar de intentar detectarla después. **Un agente que no corre no puede inventar un dato.** Es la misma estrategia que ADR-002 (si no hay Python, no hay Python malo) y ADR-003 (si el LLM no puede aprobar, no aprueba de más): eliminar la posibilidad en vez de vigilarla.

**Efecto secundario.** Las piezas sencillas —la mayoría del uso real— dejan de pagar el peaje de un pipeline diseñado para un brazo de 6 ejes.

**Riesgo residual.** Una clasificación errónea salta una fase que sí hacía falta. Mitigación: la clase aparece en el resumen que confirmas al final de la admisión, así que la corriges antes de que cueste nada.

**Enmienda (2026-09-19): un mecanismo sí necesita cinemática.** La tabla decía que un `mechanism` solo corre Actuation. Al construir la biela-manivela-corredera (F3.14 (mecanismo)) se vio que sin cinemática no se puede ni colocar la biela: su ángulo y la posición de la corredera dependen del ángulo de la manivela. Además, el único choque que apareció, el eje del pivote contra la biela, solo ocurre entre 165° y 195°.

La corrección mantiene el principio de la ADR. **La cinemática de un mecanismo de 1 GDL es una fórmula cerrada, no un juicio**, así que la calcula código determinista (`mcp/sim/sim/linkages.py`) y no un agente. El Kinematics Agent sigue reservado a `robot`, donde elegir eslabones y grados de libertad sí es diseño. Para `mechanism`, la Fase 2 queda así: **cinemática determinista + Actuation**.

---

## ADR-012 · El canal de Telegram nace abierto — deuda con fecha

**Estado:** **ABIERTO POR DECISIÓN DEL USUARIO (2026-09-21)** · **Afecta a:** § 8.5; F5.6, F5.9, `.env`

> **Enmienda (2026-09-21).** El 2026-09-20 se implementó F5.10 y la lista se hizo
> obligatoria, entendiendo el «haz todo» del usuario como que incluía esta tarea.
> **Él no lo había aprobado** y pidió quitarla: el canal vuelve a ir abierto. La
> lista queda como **opción** (vacía = abierto; con ids = solo ellos) y la regla 1
> de § 8.5 deja de aplicarse por decisión suya. Lo de abajo sigue siendo cierto y
> por eso se conserva: un bot de Telegram lo puede encontrar cualquiera, y sin
> lista cualquiera puede lanzar diseños con el saldo de DeepSeek.


> **Saldada por F5.10 (lista).** `TELEGRAM_ALLOWED_USERS` es obligatoria y es la
> **única** fuente de quién puede escribir: cierra el bot propio de Intelliprint
> y a Crafty, con la misma lista. Vacía no significa «todos», significa que nadie
> decidió: sin lista, ninguno de los dos arranca. Solo ids numéricos, porque un
> @alias se cambia y lo puede coger otra persona. Al ajeno no se le contesta nada,
> ni «no tienes permiso»: contestar confirma que el bot existe y está vivo. Y en un
> grupo cuenta quién escribe, no el grupo. Lo de abajo se conserva porque explica
> **por qué** había que cerrarlo.

**Decisión.** Durante el desarrollo, el bot acepta mensajes de cualquiera: sin lista blanca. **Antes de usarlo de verdad hay que cerrarlo** a `TELEGRAM_ALLOWED_USERS`.

**Esto incumple la regla 1 de § 8.5**, que dice que sin lista blanca el canal no arranca. Se acepta como deuda declarada, igual que ADR-007b, y por el mismo motivo: desbloquear trabajo ahora y saldarlo con una tarea propia.

**Una corrección de premisa que conviene dejar escrita**, porque es el error que hace que esto parezca inofensivo:

> Un bot de Telegram **no es local aunque corra en tu PC**. No escucha en tu red: hace *polling* contra los servidores de Telegram, que le entregan los mensajes de quien sea, desde donde sea. Que la máquina esté apagada protege; que el bot sea "local" no. Es seguridad por oscuridad: nadie da con el bot por casualidad, pero nada detiene a quien lo encuentre, y el nombre del bot va dentro del token.

**Lo que queda expuesto mientras la deuda viva:**

| Riesgo | Alcance |
|---|---|
| Crear proyectos | Gasta saldo de DeepSeek y GPU de la máquina |
| Adjuntos | Escriben archivos dentro de `workspace/` |
| Contestar las barreras | **Las tres barreras de § 4 las contesta quien responda primero** |
| Escotilla de Python | Una de esas barreras es la que la guarda (§ 6.3) |

El último punto es el que cambia de categoría: pasa de *"un desconocido me gasta dinero"* a *"un desconocido puede aprobar la ejecución de código"*.

**Lo que NO se relaja.** Las reglas 2 a 7 de § 8.5 siguen: el texto y el contenido de las imágenes son dato y nunca instrucción, los adjuntos no se ejecutan ni salen de `workspace/`, y el filtro de salida sigue activo. La deuda es **solo** la lista blanca.

**Cómo se salda (F5.10).** Poner el chat ID propio —y los que se quieran— en `TELEGRAM_ALLOWED_USERS` y devolver la regla 1 a obligatoria. Es una línea de configuración y una condición en el adaptador. **No requiere autenticación de ninguna clase**: el usuario no teclea códigos, el bot simplemente ignora a quien no esté en la lista.

---

## ADR-011 · El QA busca la geometría por contrato, no por etiqueta

**Estado:** aceptada · **Afecta a:** § 3.2, § 3.3, § 7.1; F2.13, F3.1, F3.3

**Problema.** `derive_assertions` produce *"agujero Ø22.10 ±0.05 en el frame de IF-003"*. Para comprobarlo hay que **localizar esa geometría** dentro del `.FCStd` de la pieza. Ninguna tarea lo hacía, y sin ese puente la capa 1 del QA no tiene valores que comparar: ADR-003 se queda sin datos.

**Decisión.** El QA **busca la geometría donde el contrato dice que debe estar**. La aserción lleva, además de la cota, una *consulta* derivada del tipo de interfaz: para un `bearing_seat`, "cara cilíndrica con eje paralelo al del frame, centrada en él, de mayor radio dentro de la profundidad". Si no encuentra nada, **eso es un FAIL**, no un error.

**Alternativa descartada: etiquetar durante la construcción.** Lo obvio es que el generador nombre la cara `IF-003__bore` y el QA la busque por nombre. Es inequívoco, barato — y **circular**.

Si el generador etiqueta una cara como el asiento de IF-003 pero la cortó 40 mm desplazada, el QA mide esa cara, obtiene Ø22.10 y da PASS. Habría verificado **lo que el constructor afirma haber construido, no lo que hay**. Es exactamente el fallo de ADR-003 un nivel más abajo: el constructor aportando la prueba de su propio trabajo.

Buscar por contrato no tiene esa debilidad. Un agujero en el sitio equivocado no produce "medida correcta en la cara equivocada": produce "no hay agujero donde el contrato dice", que es un FAIL con el motivo correcto.

**Lo que NO cambia.** La interfaz ya tiene `frame`: no necesita guardar referencias a las features que genera. ADR-001 se queda como está.

**Lo que SÍ cambia: los sistemas de coordenadas.** Los `frame` están en coordenadas del **ensamble** (§ 3.2), pero el QA mide una pieza **sola**, construida en sus propias coordenadas. Nadie definía la transformación entre ambos.

Por eso **cada pieza necesita una `placement`** en el ensamble, y **la asigna la resolución de interfaces** (F3.3), no el `Assembly` Agent. El motivo es de orden: Assembly corre *después* del QA de piezas, así que si la placement viniera de ahí habría que medir en el ensamble en vez de al construir, retrasando la detección de errores justo hasta donde son más caros de arreglar. Es la misma lección que ADR-001.

Para `static_part` de una sola pieza la placement es la identidad, así que en la Fase 1 no cuesta nada — pero el esquema la lleva desde el principio, que es lo que evita descubrirlo en la semana 10 con la garra a medias.

---

## ADR-013 · Mechanism Designer: el agente declara el mecanismo, el código lo verifica

**Estado:** aceptada · **Afecta a:** F3.15, ADR-010 (enmienda), `config/models.yaml`

**Problema.** Para probar mecanismos (retos de bisagra, trinquete, gato de tijera, prensa y leva), la disposición de cada uno la estaba escribiendo a mano quien desarrolla el sistema. El resultado se veía bien, pero no medía lo que Intelliprint sabe hacer: el mecanismo lo diseñaba una persona.

**Decisión.** Un agente, el Mechanism Designer, convierte la petición en texto en un `MechanismSpec`. El agente **declara** y el código **calcula y verifica**:

| Declara el agente | Lo comprueba el código |
|---|---|
| Piezas con su enunciado y su caja envolvente | La pieza dibujada por el Part Designer ocupa esa caja |
| Árbol cinemático con fórmulas | Un intérprete con lista blanca las evalúa en todo el recorrido; nunca `eval` |
| Requisitos medibles (carrera, giro) | Se miden con la cinemática |
| Pares en contacto, fijos y topes | Barrido en FreeCAD: contacto ≤ 0.05 mm, nada se atraviesa, el tope toca y bloquea |
| Articulaciones de giro | La pieza tiene un agujero o un saliente en su eje |

Lo que falla vuelve al agente como motivo concreto, hasta 3 rondas. El ensamble se guarda siempre.

**Modelo.** Con `deepseek-chat`, la bisagra no se cerró en 3 rondas: los fallos eran de geometría espacial (cuerpos que solo se tocan en una arista, un enunciado que se contradice sobre el origen). Se añade el rol `reason`: `deepseek-reasoner` en dev y `qwen3.8` con thinking en prod. Con él, la bisagra salió en la primera ronda.

**Medido al integrarlo** (y por eso está en el código):
- El modelo de razonamiento piensa unos 30 000 tokens. Con `max_tokens` 32K devolvía vacío, y con el modo JSON no terminaba ni con 64K. Va sin modo JSON y con 64K; una respuesta cortada se distingue de un JSON mal formado y se reintenta pidiendo brevedad.
- Cada ronda del Mechanism Designer tarda unos 4 minutos.

**Movimiento por contacto, no por fórmula (ampliación).** La primera versión dejaba que el agente escribiera la fórmula de cualquier pieza. Eso permitió un trinquete que "bloqueaba" porque su fórmula decía que la rueda se quedaba quieta: el ensamble no demostraba nada. Se añaden dos cosas:

- `joint.rest_on`: la pieza no lleva fórmula, se mueve hasta **apoyarse** en otra. El valor lo busca la geometría real en FreeCAD, en cada posición del ciclo (dos pasadas, malla gruesa y fina). Si no llega a apoyarse, es un fallo con su motivo.
- `blocks`: el sistema fuerza la articulación de una pieza `delta` y comprueba que **se atravesaría** con la que la frena. Un trinquete que no bloquea se cae aquí.

Lo que sigue sin verificarse, y por eso el informe lo dice explícitamente: el movimiento de las piezas motrices (la manivela que alguien gira) es una fórmula impuesta, no un efecto del mecanismo.

**Enmienda (2026-09-20): cuando el razonador no cabe, contesta el que no piensa.** El mecanismo de Ginebra gastó 187 000 tokens de salida y 0.08 USD en tres llamadas al razonador, cortadas las tres por `max_tokens`, y no dejó ni un diseño: el proyecto murió en la ronda 1.

Pedirle brevedad no sirve. El pensamiento de un razonador cuenta dentro de `max_tokens` y **lo decide él**, no el prompt; 64K es además el techo de DeepSeek, así que no hay margen que subir. Insistir es repetir lo que ya falló dos veces, pagándolo cada vez.

Por eso, tras **dos** cortes, la tercera llamada la responde un modelo **sin pensamiento** (el rol `design`, `deepseek-chat`), que tiene todo el presupuesto para el JSON. Un diseño de un modelo más flojo es mejor que ningún diseño, y si además falla, falla por su contenido y con motivo, no por longitud.

Es una decisión de **agotamiento, no de preferencia**: el razonador sigue siendo quien diseña mecanismos (esta ADR, § Modelo). La reserva solo entra cuando ya se demostró que no cabe.

**Enmienda (2026-09-20, noche): dos cosas de esta ADR no eran ciertas.** Se vieron al mudar el sistema a otra máquina y llamar a la API con la clave.

1. **`deepseek-chat` y `deepseek-reasoner` no son dos modelos.** DeepSeek los retiró el 2026-07-24 y los mantiene como alias: a los dos los sirve `deepseek-flash` (V4.1 Flash), el primero con el pensamiento apagado y el segundo encendido. La respuesta de la API lo dice: `"model": "deepseek-flash"`. Todo este repositorio se escribió después, así que *«con `deepseek-chat` la bisagra no cerró, con el razonador salió a la primera»* compara **el mismo modelo con y sin pensamiento**. La conclusión práctica aguanta —pensar ayuda en geometría espacial—; la explicación, no. La reserva de la enmienda anterior sigue teniendo sentido: tras dos cortes contesta el mismo modelo sin pensar.

2. **64K no era el techo.** La API contesta a un valor mayor con *«the valid range of max_tokens is [1, 393216]»*. El Ginebra no murió contra un límite de DeepSeek, sino contra uno puesto aquí. Por decisión del usuario, el razonador pide ahora el máximo, 393 216, y el plazo de la llamada sube de 20 a 45 minutos: a la velocidad medida (318 tokens/s) generar el techo entero lleva ~21, y con el plazo antiguo el techo real se quedaba en ~381 000. Subir uno sin el otro habría sido un techo de adorno. El coste lo sigue acotando el tope por proyecto: una llamada llena son ~0.47 USD en hora punta.

Y una consecuencia en el coste: los precios configurados eran 0.28 / 0.42 USD por millón, y la salida de Flash cuesta 1.20 en hora punta (0.60 fuera). Los informes de coste salían entre 1.4 y 2.9 veces cortos; los 0.08 USD del Ginebra fueron en realidad entre 0.11 y 0.23.

**Enmienda (2026-09-21): solo la pieza motriz se mueve por fórmula.** El trinquete salió «resuelto» en la ronda 12 (0.93 USD, sin choques, 18 requisitos cumplidos según el revisor) con la rueda girando por `30 * min(t, 90) / 90` y las uñas siguiéndola por contacto. La regla de la ampliación anterior —no declarar que algo bloquea a una pieza movida por fórmula— la esquivó sin declarar ningún bloqueo. El prompt ya le decía que `rest_on` con `carry` era «la única forma honesta de declarar el avance de una rueda de trinquete»; lo leyó y no lo hizo. Un consejo no basta: tiene que ser una regla.

Por decisión del usuario, **una especificación con más de una pieza movida por fórmula se rechaza** antes de dibujar nada. La motriz es la que mueve la persona; el resto se mueve porque otra la empuja (`rest_on`), va unido a algo que se mueve (`parent`) o está fijo. Los resortes no cuentan: su `stretch` es deformación. El coste conocido: los mecanismos de lazo cerrado (el gato de tijera) quizá no puedan expresarse con apoyos y cuesten más rondas, o no salgan.

**Design Reviewer (ampliación).** Un agente compara la petición literal, requisito por requisito, con lo que MIDIÓ el código. Sus veredictos son `cumple`, `no_cumple` y `no_verificable`; este último es el importante, porque marca lo que hoy nadie comprueba. **No aprueba nada** (ADR-003): es un informe para la persona. Cuando el perfil tenga modelo con visión podrá mirar además los fotogramas.

**Límite conocido.** Que un diseño pase todas las comprobaciones no significa que sea lo que el usuario imaginaba. La primera bisagra aprobada era en realidad un pivote en plano. Juzgar eso necesita un revisor con visión (capa 3 del QA, § 7.1), que el perfil dev no tiene. Hasta entonces, el GIF lo revisa el usuario.


---

## ADR-014 · FreeCAD dentro del contenedor, PrusaSlicer fuera

**Estado:** aceptada · **Afecta a:** § 8.1, § 8.2, § 8.4; F0.2, F0.4, F0.5, F0.7, ADR-004 (enmienda)

**Problema.** El sistema solo existía como instalación hecha a mano en un ordenador: rutas absolutas en el registro del MCP, un LaunchAgent que solo existe en macOS, secretos copiados a mano, y ningún test que lo cubriera. Era la deuda que más se parecía a volverse permanente, porque no duele hasta el día que cambias de máquina. Ese día llegó: el proyecto se movió a la PC de la RTX 5090, con Windows.

**Lo que la arquitectura decía (§ 8.2).** FreeCAD y PrusaSlicer se quedan en el host y se exponen por HTTP con `mcp-proxy`; el orquestador, dentro del contenedor, «solo ve URLs». Nunca se construyó. Al mirar el código se ve por qué nadie lo echó de menos: **no hay una sola llamada a `FreeCADGui` en producción**. `build.py`, `assembly.py` y `animation.py` lanzan `freecadcmd`, que es headless.

**Decisión.** Los dos programas no juegan el mismo papel, así que no reciben el mismo trato:

| | Papel | Dónde vive | Por qué |
|---|---|---|---|
| **FreeCAD** | Herramienta **interna**: construye y calla | **Dentro** del contenedor | Nadie la mira trabajar. Meterla dentro es lo que hace el sistema reproducible |
| **PrusaSlicer** | Donde la persona **mira qué va a imprimir** antes de mandarlo | **Fuera**, en el PC | Tiene que ser el suyo, con su versión y sus ajustes, no una copia escondida en una imagen |

Va FreeCAD **1.1.3**, la misma versión que el escritorio. Debian empaqueta la 1.0 y el código se escribió contra la 1.1: bajar de versión separaría lo que construye el sistema de lo que abre la persona, justo lo que el contenedor viene a evitar.

**El puente.** El contenedor le pide el laminado al host por un MCP propio (`scripts/host_bridge.py`, puerto 8102, el que F0.4 reservaba para PrusaSlicer), que arranca `scripts/start-host-mcps.ps1` —el script que `scripts/README.md` prometía desde el primer día—. El orquestador traduce las rutas con `HOST_WORKSPACE` (F0.7) antes de llamar. El puente **vuelve a comprobarlas**, aunque el otro lado ya lo haya hecho: el que ejecuta no puede delegar la comprobación en el que pide. Y el perfil de laminado se pide **por nombre**, resuelto en `config/slicing/`; si el contenedor pudiera mandar la ruta, estaría eligiendo qué archivo del host se lee.

**Lo que no se construyó, y por qué no.** No hay puente para FreeCAD (F0.5 hablaba de «ambos MCP»). Un MCP entre el orquestador y `freecadcmd`, que están en el **mismo** contenedor, sería una capa sin consumidor.

**Enmienda a ADR-004.** «Construcción headless, inspección con GUI» sigue en pie, pero la instancia con interfaz ya no es del sistema: es el FreeCAD del escritorio, con el que la persona abre los `.FCStd` que el contenedor deja en `workspace/`, montado desde el host. Ningún código lanza una GUI.

**Medido al montarlo:**
- Suite nativa en Windows: **19 fallos**, ninguno del sistema. Tres cosas del sistema operativo: `open()` sin `encoding` se lee como cp1252 y no como UTF-8 (con `PYTHONUTF8=1` bajan a 9), algún test llama a `/bin/sh`, y un proceso zombi no se comporta igual. En el contenedor: **verde**. El contenedor es donde la suite dice la verdad sobre el código.
- `core.autocrlf=true` entregó el corpus de referencia con CRLF y su SHA256 dejó de cuadrar. El archivo estaba intacto; lo había tocado git. Lo arregla `.gitattributes`.
- Windows PowerShell 5.1 lee un `.ps1` sin BOM como cp1252: un guion largo acabó en `0x94`, que allí es una comilla doble, y el script no llegó a analizarse. Un test exige que todo `.ps1` sea ASCII puro.

**Lo que sigue sin resolverse.** El PrusaSlicer del PC es **2.9.6** y el laminado lo hace él; no hay una segunda versión en juego. Pero si alguien levanta esto en una máquina sin PrusaSlicer, no hay laminado: el puente es obligatorio, no opcional. Se ve en la suite, donde tres tests se saltan dentro del contenedor y solo pasan en el host.

**Enmienda (2026-11-09): el diseño no lamina.** Decidido por el usuario. Cada pieza se laminaba al terminar con el perfil activo, y salían gramos, tiempo y G-code de una impresora que quizá no es la que se va a usar: él tiene varias y al diseñar no se sabe en cuál se imprimirá. Ahora se lamina cuando la persona abre la pieza en PrusaSlicer desde la web, y la página dice «gramos y tiempo, al abrirla en PrusaSlicer» en vez de inventarlos. El banco lamina **al juzgar**, y solo si el encargo pide «sin soportes». Así esa respuesta sigue viniendo de PrusaSlicer, un oráculo que no es el propio sistema. Un detector de voladizos escrito aquí habría sido el sistema juzgándose a sí mismo. `intelliprint new` (el flujo de consola con confirmación) sigue laminando; nadie lo usa ya.

---

## ADR-015 · Ingeniero primero, CAD después

**Estado:** aceptada · **Afecta a:** § 4.1, § 4.2; F3.17, F3.18, F3.19, F3.20

**Problema.** Lo que salía era inusable, y no por falta de FreeCAD. Nadie pensaba la pieza. El Part Designer recibía la petición en prosa y dibujaba cajas. Lo midió el banco (F6.1, 45 %):
- la escuadra «para 5 kg» salía con el espesor que se le ocurría al modelo;
- el gancho, sin agujeros;
- el adaptador de tubo, sin holgura.

Además, la petición viajaba como texto. No se sabía qué cota era un agujero y cuál un fondo, y las modificaciones se apilaban: Ø34 y Ø40 convivieron en el mismo prompt del sargento.

**Decisión.** Entre la especificación y el CAD entra un paso de ingeniería, con tres reglas:

1. **Requisitos con nombre** (`Requisito` en `spec.py`). Cada uno lleva `id`, tipo, valor y origen. El código comprueba dos cosas que el modelo no puede saltarse:
   - que lo que dice venir del usuario es una **cita literal** de la petición;
   - que **ninguna cota en mm de la petición** se queda sin requisito.

   Los dos errores vuelven al modelo dentro del bucle de `structured`, con el valor exacto.
2. **Un ingeniero que decide cómo se resuelve** (`IngenieroAgent`, rol `reason`). Propone un `Concepto` con estas partes:
   - la idea;
   - el camino de carga;
   - la orientación de impresión y por qué;
   - las fijaciones, con los diámetros de la tabla del perfil;
   - los casos de carga;
   - una o dos alternativas;
   - como mucho tres preguntas, solo por cotas críticas.

   Recibe el perfil activo entero. Hasta ahora `M3_through_mm` no le llegaba a nadie que diseñara.
3. **Lo que se puede contar lo cuenta el código** (`orchestrator/ingenieria.py`). El ingeniero plantea el caso de carga y el código calcula la flexión del voladizo. Usa la resistencia del material del perfil, entre capas si la orientación las pone a tracción. Si no llega al factor de seguridad, el concepto vuelve con el canto que haría falta. Un modelo se equivoca en una potencia y no se nota; esta cuenta tiene tests hechos a mano.

**La barrera del concepto.** Una pieza no se modela sin visto bueno. Por consola va en la misma confirmación de la admisión. Por la web y Telegram, la pieza para en «por aprobar» con `concepto.md`.

Contestar a las preguntas **no aprueba**. Las respuestas se añaden literales a la petición y el ingeniero propone otro concepto, que vuelve a esperar: lo que se modela tiene que ser algo que la persona haya visto. Es la misma regla que las otras barreras humanas (ADR-008): el silencio no aprueba.

**Lo que no cubre.**
- El cálculo es un voladizo de sección rectangular. No ve esquinas vivas, pandeo, fatiga ni fluencia: los absorbe un factor de seguridad alto (3). Un FEM con CalculiX queda como seguimiento.
- La resistencia del material es una estimación conservadora **sin ensayar**, como las holguras (F2.18).
- Los mecanismos todavía no pasan por el ingeniero.
- Nadie **mide** aún que la pieza cumpla cada requisito. Eso es F2.6 y F2.12: ahora tienen por dónde agarrarlo.

---

## ADR-016 · El componente es geometría con ficha; el programa solo dice dónde va

**Estado:** aceptada · **Afecta a:** § 4.2, § 7.1; F2.2, F6.11, F6.7, F3.21

**Problema.** El soporte del HC-SR04 (2026-11-05) salió «resuelto, listo para imprimir» y el sensor no entraba. Medido en FreeCAD:
- con el sensor real (PCB de 45, transductores de Ø16) el PCB no cabía, los transductores chocaban contra agujeros de Ø8 y los integrados de atrás, contra un canal de 0.2 mm;
- **ni con sus propios números** (43 y Ø8) se podía meter: el canal se abría por arriba y los transductores atravesaban la pared de delante.

Faltaban tres cosas:
- **No existía el componente.** Había trece cifras de internet convertidas en requisitos sueltos: de ahí salieron cuatro agujeros de Ø1 que el concepto decía que no habría, y el «Ø8», que en el plano de la UPV era el radio. Nada decía que el sensor lleva integrados detrás, pines abajo y un cable.
- **Nada lo comprobaba.** El bucle medía agujeros contra los rasgos que declaraba el propio programa, y aristas.
- **El banco no lo veía.** Pedía por el flujo viejo, sin investigador ni ingeniero, y ninguno de sus encargos llevaba un PCB.

**Decisión.** Un componente comprado es **geometría con ficha y fuente** (`library/components/*.yaml`):
- `cuerpos`: lo que choca;
- `despejar`: lo que hay que dejar libre, cada zona con su porqué (cable, haz, enchufes);
- `fijacion`: dónde se atornilla;
- las fuentes citadas, y `verificado: false` hasta que alguien lo mida con calibre.

Lo que el plano dibuja sin acotar lo dice su `porque` («a escala»). Si dos fabricantes no coinciden, la ficha toma lo mayor.

El programa del diseñador **solo dice dónde va y por dónde entra** (`kit.componente(id, en, girar, entra_por)`). La forma no la dibuja él. Así se concilia con ADR-011: el rasgo del componente es una declaración de *posición*, no de *forma*. La sonda mete en la pieza la forma de la ficha, que el programa no puede tocar:
- `componente_cabe`: ningún cuerpo ni zona libre se mete en la pieza, y la pieza lo toca;
- `componente_entra`: el barrido exacto desde `entra_por` hasta su sitio no atraviesa nada.

Las dos corren **dentro del bucle**, y el choque vuelve al diseñador con nombre: «"integrados de atrás" choca 552 mm³».

Un programa que no coloca un componente que el concepto nombra no queda «sin comprobar»: es un defecto.

**Quién decide qué es un componente.** El código, por los alias de la ficha, no el modelo. Lo que tiene ficha:
- no se busca en internet;
- no se convierte en requisitos sueltos;
- llega al ingeniero con su resumen, y el concepto tiene que decir cómo entra y cómo se sujeta.

Si la persona PREGUNTA por unas medidas, se sigue buscando.

**Alternativa descartada: ventanas con medidas.** La sonda `ventana` ya existía y comprueba que una sección pase por una abertura. No ve lo que sobresale por detrás, ni los pines, ni por dónde entra, y el soporte del HC-SR04 la habría pasado con sus números.

**Lo que no cubre.**
- Las fichas son cajas y cilindros alineados con los ejes, y los giros, de 90 en 90°: es lo que hace exacto el barrido.
- Ninguna ficha está medida con calibre.
- Un clip elástico que se monta forzando choca a propósito y la sonda no lo distingue de un choque de verdad.
- Un componente sin ficha sigue por el camino de antes, con cifras sueltas. El borrador de ficha que la persona revisa y aprueba (plan, fase 6) está pendiente.

**Enmienda (2026-11-06): sin holgura donde el componente solo se apoya.** El banco `1105-2120` sacó cinco piezas con entre un 18 % y un 43 % de aristas vivas. Gran parte venía del propio `hueco()`: sumaba la holgura en todas las caras, también en las que el componente solo se apoya en la pieza. Así tallaba rebajes de 0.1 mm: bajo el NEMA 17, en la cara de la cama, y en el respaldo contra el perfil 2020. No se imprimen (la capa es de 0.2), y OCC no sabe redondear sus aristas.

Ahora `quitar` rehace el hueco contra la pieza:
- una primitiva que queda entera fuera de la pieza y la toca por un lado no lleva holgura en ese lado;
- la que se mete en la pieza (el resalte del motor, un PCB entre guías) talla su propio alojamiento y la lleva en todas sus caras.

Un componente que solo se apoya no quita nada, y no es error; uno que ni toca la pieza sí lo es. Y `acabar()` achaflana con un corte booleano las aristas rectas que OCC no redondea: el chaflán de 45° no cuenta como arista viva.

---

## ADR-017 · El código ROS 2 del robot se prueba en Gazebo antes de imprimir

**Estado:** aceptada (2026-11-08) · **Afecta a:** § 1 del plan, Fase 4; F4.6, F4.7, F4.8, F4.11–F4.17, ADR-014, ADR-016

**Problema.** Para la clase `robot` el plan comprobaba la **mecánica**: URDF, autocolisiones y vuelco con PyBullet (F4.6–F4.8). Nada comprobaba el **programa** que va a mover el robot. Un brazo puede pasar todas esas pruebas y aun así:
- su control mandar una articulación fuera de rango y chocar contra su propia base;
- pedir una trayectoria que el servo no aguanta con la carga, y quedarse a medio camino;
- volcar al frenar de golpe, aunque estático no vuelque.

Eso se descubre hoy con el robot ya impreso, que es justo lo que Intelliprint existe para evitar: **demostrar que funciona antes de que nadie imprima nada**.

Y una realidad del punto de partida: la clase `robot` solo existe en `spec.py`. La Fase 4 está sin empezar.

**Decisión.** Decidida con el usuario el 2026-11-08.

1. **El código que se prueba es el del usuario: nodos ROS 2 (Python).** El mismo paquete mueve el robot simulado y el real. Lo que cambia entre uno y otro es solo la interfaz de hardware de `ros2_control`: en simulación, `gz_ros2_control`; en el robot, un puente a los servos (PCA9685 en una Pi, o un ESP32 con micro-ROS). El ESP32 solo hace de puente; la lógica vive en ROS 2. Así lo que pasa en Gazebo es lo mismo que se ejecutará después, no una reescritura.
2. **Dos simuladores, cada uno para una cosa.**

   | | Para qué | Dónde corre |
   |---|---|---|
   | **PyBullet** | Comprobaciones rápidas **dentro del bucle de diseño**: colisiones en el rango, vuelco, par (F4.6–F4.8). Sin ROS | En el contenedor del orquestador |
   | **Gazebo** | Ejecutar **el código del usuario** contra el URDF exportado, con `joint_trajectory_controller` | En un contenedor propio, `sim-ros` |

   Los dos leen **el mismo URDF** (F4.6), que es la única fuente del robot simulado.
3. **El servo simulado tiene el par de su ficha.** El límite de esfuerzo de cada articulación del URDF sale del par del servo que la mueve, con fuente citada (ADR-016). Un servo que no puede con la carga **no llega** a la pose: el fallo lo produce la física, no una cuenta aparte. Las fichas de servos aún no llevan par (F4.12).
4. **Gazebo corre sin ventana**, como FreeCAD (ADR-014): es una herramienta que comprueba y calla. Deja:
   - un **informe** (`simulacion.md`): por cada objetivo, la pose pedida y la alcanzada, choques entre eslabones, articulaciones con el par saturado y vuelco;
   - un **vídeo**: se graban `/joint_states` y los contactos, y se dibujan con la misma ruta que las animaciones de mecanismos (`orchestrator/animation.py`), sin GPU. Lo que se ve es lo que Gazebo calculó.
5. **La persona lo ve en la web, y con GPU solo si quiere.** Cada proyecto tiene una pestaña «Simulación» con el vídeo y el informe, y un botón «Abrir en Gazebo» que lanza la interfaz de Gazebo **en el escritorio**, con la GPU. Va por el puente del host (`scripts/host_bridge.py`), como «Slice in PrusaSlicer»: el puente recibe el **nombre** del proyecto, comprueba que está dentro de `workspace/` y lanza el contenedor con interfaz (`--gpus all`, pantalla por WSLg). El contenedor web **nunca** monta el socket de Docker: quien pudiera escribir en esa página tendría la máquina entera.

**Por qué sin ventana por defecto.** La 5090 está casi llena (31 de 32 GB, con vllm y hunyuan3d). Una simulación que necesitara la GPU para comprobar dependería de qué más esté corriendo; dibujando las poses grabadas, la prueba es la misma esté la tarjeta como esté. La GPU es para mirar, cuando la persona decida dejársela.

**Versiones.** ROS 2 Jazzy con Gazebo Harmonic es la pareja oficial confirmada. Lyrical (la LTS de 2026) aparece con Jetty en la tabla de plataformas de Lyrical, pero la guía de Gazebo aún no la recoge (comprobado el 2026-11-08). Se fija al construir la imagen (F4.11), con la fuente citada en el Dockerfile.

**Alternativas descartadas.**
- **Solo Gazebo**, sustituyendo a PyBullet. Un solo motor de física es más coherente, pero arrancar Gazebo en cada ronda del bucle de diseño es lento y mete ROS donde no hace falta. La decisión del usuario fue tener los dos.
- **Probar el firmware del ESP32.** Gazebo no ejecuta firmware de un microcontrolador. Emularlo sería otro proyecto; con la lógica en ROS 2, el firmware queda en un puente fino.
- **La ventana de Gazebo dentro de la página web** (gzweb y similares). Más piezas y la GPU igualmente ocupada; la persona ya tiene escritorio.

**Lo que no cubre.**
- **El servo es ideal**: control de posición con un límite de esfuerzo. Sin holgura del engranaje, sin zona muerta, sin caída de velocidad con la carga ni calentamiento.
- **Las masas son estimadas**: el volumen de FreeCAD por la densidad del material y el relleno del perfil. No se pesan piezas.
- **El plástico no flexa**: los eslabones son rígidos. Un brazo largo de PLA que cede no se ve aquí; es lo que mide la sección (F6.12) con su factor de seguridad.
- **Sin sensores** (cámaras, lidar) de momento: el robot de referencia (H4) solo tiene servos.
- Que el límite de esfuerzo del URDF frene de verdad a una articulación mandada **en posición** depende de cómo `gz_ros2_control` lo traslade al motor de física. Por eso F4.13 lo comprueba con un servo sembrado demasiado débil, que tiene que quedarse corto; si no se queda, la articulación se manda en esfuerzo con un PID.

**Enmienda (2026-11-10): ROS 2 y Gazebo salen de Intelliprint.** Decidido por el usuario el mismo día: «separémoslo, yo trabajo todo lo de código y ROS y simulación en Gazebo por aparte; lo que sí quiero es el estudio de movimientos». Intelliprint diseña, comprueba la mecánica, hace el **estudio de movimientos** y entrega el **URDF** (F4.6), que es la frontera: el repo del usuario lo lee y hace lo demás. Quedan fuera F4.11 y F4.13–F4.17 (el contenedor `sim-ros`, probar su código, el vídeo, la pestaña y «Abrir en Gazebo»); se quedan F4.6–F4.8 y F4.12, que son mecánica. Lo que llevó a decidirlo: Hablado al pedir el inventario de inventos (F7.8 (inventario)). Lo que dijo:

1. Ver Gazebo con una simulación y **dejarla corriendo**, para que un robot **aprenda** a hacer cosas, y ver qué hace antes de probarlo en algo real (puso de ejemplo un dron). Así no gasta en piezas que se rompan.
2. El código lo pone él, por aparte. Coincide con el punto 1 de la decisión.
3. Preguntó qué diferencia hay entre verlo «en la web» y «en el PC». Es la misma máquina; la diferencia es dónde se dibuja la ventana. El punto 5 ya lo resolvió: la web enseña el vídeo y el informe, y «Abrir en Gazebo» saca la ventana en su escritorio con la GPU, por el puente del host.

Por qué separarlo, y no meterlo aquí:

- **Correr mucho tiempo y aprender** no es lo mismo que una prueba que arranca y para. Aprender por refuerzo pide muchas simulaciones sin ventana y más rápidas que el tiempo real. Es un contenedor de entrenamiento que se queda vivo, y usa la GPU para la red, no solo para mirar.
  - Esto choca con el «Por qué sin ventana por defecto» de arriba: la 5090 estaba casi llena.
  - Mirar lo que hace es otra cosa: se abre la ventana, o se graba un episodio.
- **Un dron** es otra clase de robot.
  - Lo estándar es PX4 en SITL con Gazebo Harmonic.
  - Ni la Fase 4 ni los kits de la Fase 8 (ADR-019) lo contemplan, y su URDF no sale de las articulaciones de una obra.
- Lo que ya existe y sirve para todo lo anterior es el **árbol cinemático de una obra**, verificado en FreeCAD:
  - qué pieza va sobre cuál;
  - cada articulación con su eje y su recorrido;
  - las mallas de cada sólido (`ensamble.json`, F7.9 (visor)).

  Es la materia prima del URDF de F4.6.

---

## ADR-018 · Una pieza terminada es una ficha: los proyectos se diseñan por partes

**Estado:** aceptada (2026-11-09) · **Afecta a:** Fase 7 (F7.1–F7.5), ADR-011, ADR-013, ADR-016

**Problema.** Las piezas sueltas salen: el banco va al 100 % y el soporte del 608ZZ fue útil al tercer intento. Los mecanismos no. `MechanismDesignerAgent.design` pide en **una sola llamada** todo el mecanismo (piezas, juntas, apoyos y bloqueos). La Ginebra murió ahí: el razonador se cortó tres veces. Y las piezas de un mecanismo se dibujan **a ciegas**: ninguna se diseña contra la forma real de otra, y ninguna pasa por las sondas del kit.

**Decisión.** Decidida con el usuario el 2026-11-09.

1. **Un proyecto grande se parte en un árbol** de nodos (pieza o conjunto), y se diseña **un nodo cada vez**, con el visto bueno de la persona en cada paso. Cada hoja es del tamaño de un encargo del banco, que es lo que ya sale.
2. **Una pieza terminada es una ficha** (`orchestrator/obra.py:fichar`). Guarda su STEP construido y sus agujeros con nombre. La siguiente pieza la coloca con `kit.componente` y se mide con `componente_cabe` y `componente_entra`, igual que un 608ZZ comprado.
3. **Sin simulación fuera de los mecanismos.** Una pieza sola solo se **mide** (cabe, entra, tornillo accesible, pared). El barrido de posiciones, los apoyos y los bloqueos son de los nodos `conjunto`.
4. **«Lista» la decide la persona** con su visto bueno en la web. «Impresa y probada» es otra marca, que no frena el avance.

**Por qué no es el etiquetado circular de ADR-011.** La ficha de una pieza impresa es su **geometría construida**, el STEP que salió de FreeCAD, no lo que el programa dijo haber hecho. Medir la pieza B contra esa forma es medir contra algo que existe. Lo único que viene del programa son los **nombres** de sus agujeros, igual que en ADR-016: el programa declara *dónde*, y la forma se mide.

**Límites conocidos.**
- **El hueco de una pieza impresa es su envolvente.** Barrer de forma exacta una forma cualquiera no sale barato: con el soporte del 608ZZ, extruir sus caras falló en 2 de 3 ejes, y unir copias desplazadas tardó 4 minutos por eje. Así que `hueco()` talla la caja envolvente con holgura. Para casar dos piezas impresas se usan sus agujeros y `punto()`. Si una entra de verdad lo mide `componente_entra`, con la forma real cada 0,5 mm.
- **Solo los agujeros de eje alineado** pasan a la ficha: son los que una ficha sabe girar en cuartos de vuelta.

**Enmienda (2026-11-10): una pieza que gira se mueve dentro de su propio bucle (ADR-020).** El punto 3 dejaba todo el movimiento para el nodo `conjunto`, que llega cuando las piezas ya tienen el visto bueno. En el pan-tilt `1110-0313` eso enseñó el choque cuando ya no tenía arreglo barato: las tres piezas estaban dadas por buenas y la que había que cambiar era la segunda. Sigue sin simularse nada que no esté construido, pero una pieza que el plan dice que gira se barre contra lo ya construido en cuanto se construye, F9.5 (parcial), y el choque vuelve a su diseñador como cualquier otra medida. El nodo `conjunto` sigue siendo la verificación del todo.

---

## ADR-019 · Lo que se entrega es un kit para montar

**Estado:** aceptada (2026-11-09), corregida el mismo día · **Afecta a:** Fase 8 (F8.1–F8.11), F5.15 (movida a F8.6 (montaje)), F5.16, ADR-018

**Corrección.** La primera versión de esta ADR suponía que los clientes imprimían el kit en su casa. Planteaba un perfil para impresoras ajenas y laminar con las de otros fabricantes. El usuario lo corrigió: «son mías, yo las voy a imprimir para armar kits», y «la impresora yo la voy a setear». Lo que sigue es la decisión corregida. F8.2 (ajena) y F8.3 (otras) quedan en el plan como descartadas.

**Problema.** El usuario va a montar una empresa de robótica infantil:

- **él diseña los kits** con Intelliprint;
- **los imprime en sus impresoras** y los mete en una caja con lo comprado;
- **el cliente monta** el robot, y puede ser un niño;
- la programación de los robots se mira **después**.

Hoy Intelliprint saca piezas listas para imprimir y nada más. Para vender un kit faltan cuatro cosas:

- la lista de lo que hay que comprar;
- unas instrucciones que alguien que no ha visto el diseño pueda seguir;
- avisos de lo que no conviene en las manos de un niño;
- lo que cuesta cada kit.

Lo que descarga hoy la web es la carpeta del proyecto con su historial, no algo que se pueda meter en una caja.

**Decisión.** Decidida con el usuario el 2026-11-09.

1. **Un kit sale de una obra terminada** (ADR-018). El árbol de la obra ya tiene lo que el kit necesita:
   - las piezas, con su STEP construido;
   - lo comprado, en la `compra` de cada nodo;
   - el orden de montaje, en las dependencias.

   No se empaqueta nada que no haya salido entero como obra.
2. **Se imprime en las impresoras del usuario, con su perfil.** El kit se diseña y se lamina con el perfil activo de `config/impresion.yaml`, como cualquier pieza. La impresora la configura y la calibra el usuario: él decide cuándo imprimir la pieza de F2.18 (calibración) y qué valores salen. El asistente no cambia holguras por su cuenta, y `M3_through_mm: 3.3` sigue igual hasta entonces.
3. **El paquete tiene dos partes.**
   - **Producción**, para el usuario: piezas en STL y 3MF, el G-code de su máquina, la lista de compras, y el coste y las horas por kit.
   - **La caja**, para el cliente: las instrucciones y la lista de piezas y compras, sin nada interno.
4. **Las instrucciones son para quien monta, no para quien diseña.** El orden sale del árbol. Cada paso tiene sus piezas numeradas y una imagen. Van imágenes antes que texto.
5. **Las reglas de montaje infantil son avisos, no una certificación.** El código revisa y avisa de:
   - piezas que caben en el cilindro de piezas pequeñas (16 CFR 1501);
   - más tipos de tornillo de los decididos;
   - aristas vivas;
   - pasos que necesitan pegamento.

   La seguridad de un juguete la certifica un laboratorio con EN 71 o ASTM F963. Intelliprint no lo sustituye, y el kit no debe decir que cumple nada que no se haya certificado.
6. **El coste por kit sale de lo medido**: los gramos del laminado al precio por kilo del filamento, más lo comprado a sus precios. Los precios los pone el usuario en F8.1 (cliente).
7. **La programación queda fuera de esta fase**, por decisión del usuario. Lo de ADR-017 (Gazebo) sigue siendo para probar el código del usuario. Un entorno para que programen los niños es otro producto, sin diseñar.

**Preguntas abiertas**, que decide el usuario en F8.1 (cliente) y no el asistente por defecto:

- **Quién monta.** La edad de quien monta, y qué herramientas se permiten (destornillador sí o no).
- **Lo comprado.** Si los servos, los tornillos y la electrónica van en la caja.
- **Las instrucciones.** El formato: PDF impreso en la caja, página web con un código QR, o las dos.
- **Los precios.** El precio por kilo del filamento y el de cada componente comprado, para el coste por kit.

**Alternativas descartadas.**
- **Perfil genérico para impresoras ajenas** (la primera versión de esta ADR). No hace falta: el kit sale de las impresoras del usuario.
- **Instrucciones escritas a mano por kit.** No escalan, y se quedan viejas en cuanto cambia una pieza. Generadas desde el árbol, cambian con él.

**Lo que no cubre.**
- **Si un niño de esa edad sabe montarlo** no lo mide ningún test. Lo dice la prueba de F8.10 (prueba) y lo que se registra en F8.9 (reportes).
- **El coste no incluye** la luz, el desgaste de la impresora, las horas del usuario ni el embalaje. Es el coste de material.

---

## ADR-020 · El plan mecánico decide las uniones y el sitio de cada giro; el código lo valida y lo mide

**Estado:** aceptada (2026-11-10) · **Afecta a:** Fase 9 (F9.1–F9.13), ADR-013, ADR-016, ADR-018, F7.2, F7.4, F7.5, F7.7

**Problema.** El usuario quiere diseñar robots: «tiene que haber un planner que busque las piezas, su footprint, y todos los tornillos, bearings para el diseño mecánico», y poder añadir funciones de varias piezas a un diseño ya hecho. Al revisar por qué el único robot del banco no salía, la causa no fue la tornillería:

- El pan-tilt `1110-0313` falla una sola comprobación, `conjunto_libre`. Su soporte deja **12.7 mm** entre el eje de inclinación y el SG90 de la base: el eje queda a z = 12.2 del soporte, el soporte se coloca a −33.6 de la base y la carcasa del servo de abajo llega a 33.1. Ninguna plataforma con una cámara cabe en ese radio.
- La regla de F7.7 (culpable) mandó corregir la plataforma, «la que va después». Bajó su radio de 68.4 a 37.7 mm y no podía bajar más. La pieza que tenía que cambiar era el soporte.
- El desglose lo había dicho en texto libre («espacio para inclinar la plataforma 180°») y el concepto del soporte lo repitió sin cifra. **Nadie decidió cuánto sitio necesita cada giro, y nadie lo midió en la pieza que monta el actuador.**

Y lo que sí faltaba de tornillería:

- `Obra` no tiene uniones. `ofrece` y `necesita` son texto libre, y el desglosador deja los tornillos «al diseño de la pieza».
- El diseñador de una pieza no recibe la métrica de los tornillos de una ficha (`resumen()` no la imprime) ni el eje sobre el que gira (la ficha de una pieza impresa no conserva las salidas de lo que monta).
- La lista de compras se deduce al final (`tornilleria.py`): el soporte sujetó su SG90 con dos M3 que lo empujan porque el perfil no tabula M2, y la plataforma taladró Ø3.3 para un cuerno con agujeros de Ø1.0.

**Decisión.** Decidida con el usuario el 2026-11-10.

1. **El desglose pasa a ser el plan mecánico.** El mismo agente y la misma llamada proponen los nodos y sus **uniones**. No es un agente nuevo ni una segunda llamada: nodos y uniones son la misma decisión, y sin coordenadas la salida es corta (unos 2 000 tokens para ocho piezas).
2. **Dos tipos de unión, los que el sistema sabe comprobar.**
   - `fija`: en qué nodo apoya la cabeza, en cuál agarra (o en el exterior), la métrica, cuántos y el **agarre** —tuerca cautiva, inserto o rosca en el plástico—. El agarre lo propone el plan en cada unión y el usuario lo ve antes de aprobar.
   - `gira`: qué nodo gira, sobre qué salida de qué componente montado por qué nodo, cuánto recorre y **cuánto radio libre** necesita alrededor del eje.
3. **Las fijaciones de lo comprado no las planifica el modelo.** Salen de la `fijacion` de su ficha (los dos M2 que trae un SG90).
4. **El plan no lleva coordenadas.** El modelo dice quién se une a quién y con qué; dónde cae cada cosa sale de la geometría construida, como hasta ahora (ADR-016, ADR-018).
5. **El radio libre es un presupuesto de diseño, no una medida.** Lo propone el plan y lo aprueba el usuario, como las cotas de un concepto. Lo que el código **mide** es si se cumple, en las dos piezas: la que monta el actuador no mete nada en ese cilindro, ni lo hace lo que tiene debajo en ningún ángulo de los giros anteriores; la que gira no pasa de él. Esto no contradice que las cifras de un robot no las diga un modelo: las que salen de la geometría las sigue dando el código.
6. **El culpable de un choque es quien incumple su presupuesto.** Si el sitio medido es menor que el pedido, la culpa es de quien monta el actuador, aunque vaya antes en el árbol.
7. **Las uniones llegan a cada pieza como datos, no en su petición.** La petición la lee el agente de requisitos, que convierte cada cifra en un requisito (`obra.peticion_del_nodo` lo documenta). Van en `nodos/<id>/uniones.json` al ingeniero, al diseñador y a las medidas.
8. **Solo gira lo que el plan dice que gira.** Hasta ahora giraba cualquier pieza a menos de 5 mm de una salida.
9. **Lo previsto se compara con lo medido.** Lo que el plan pidió y `tornilleria.py` no encuentra en lo construido es un defecto del nodo.
10. **Un invento se amplía con el mismo plan.** La propuesta —nodos nuevos, uniones nuevas y las piezas listas que habría que corregir— espera el visto bueno aparte, sin tocar el plan vigente. Y corregir una pieza ya no archiva todo lo que se diseñó contra ella: se revalida y solo se rehace lo que falla.
11. **Un componente sin ficha entra como borrador** por plantilla de su clase, con sus fuentes; el usuario lo aprueba viendo la huella, y el invento queda marcado mientras no esté medido.

**Alternativas descartadas.**
- **Un esqueleto global** con ejes y volúmenes reservados en coordenadas. Obliga al modelo a dar posiciones que nadie puede validar antes de construir. Un radio por giro ataca la causa medida y se comprueba con una resta.
- **Una segunda llamada para las uniones.** Duplica el coste y deja que el árbol y las uniones no casen.
- **Meter las uniones en la petición de cada nodo.** Cada cifra acabaría de requisito suelto, que es lo que ADR-016 quitó para los componentes.
- **Añadir comprobaciones de tornillería al encargo del pan-tilt antes de que se mueva.** Subiría la nota sin arreglar el choque.
- **Un catálogo de tornillería aparte.** Los largos ya están en `tornilleria.py` y los diámetros son del perfil de la impresora, que calibra el usuario.

**Lo que no cubre.**
- **Solo árboles de giros** sobre la salida de algo comprado. Ni correderas, ni engranajes, ni cadenas cerradas: una pinza de dos dedos con un solo servo no sale.
- **El radio libre es un cilindro** desde la cara de la salida hacia fuera. Una horquilla en U que abrace al actuador no cabe en esa descripción.
- **`radio_libre()` mide con cajas**, así que es prudente de más: puede rechazar lo que no chocaría. La medida exacta sigue siendo el barrido.
- **Las métricas que el perfil no tabula** (M2, M2.5) no se pueden proponer hasta que el usuario las mida, F9.8 (métricas).
- **Si el pan-tilt no pasa sus cinco comprobaciones** con una corrida y dos reanudaciones, se para: es la regla que puso el usuario.
