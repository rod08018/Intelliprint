# Intelliprint

Sistema multiagente que diseña piezas imprimibles en 3D —sueltas, o las de un
robot, una a una—, las monta en FreeCAD y **verifica que funcionan** antes de
que nadie imprima nada.

## Cómo se trabaja aquí

- **Todo en español**: la conversación, los comentarios, los docstrings, los
  nombres de los tests y los mensajes de commit.
- **El test primero, y visto fallar.** Un test que nunca se vio en rojo no
  prueba nada. El valor esperado viene de un oráculo independiente —una
  referencia descargada, un cálculo a mano, la petición literal—, nunca de la
  salida del propio sistema.
- **Los comentarios explican el porqué, no el qué.** Cuando un arreglo viene de
  un fallo real, el comentario dice cuál fue: eso es lo que impide que alguien
  lo «simplifique» de vuelta.
- **Commit y push a `main` directamente**, sin preguntar, cuando la suite esté
  en verde. Mensaje en español explicando el porqué, y al final:
  `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`
- **Verificar antes de afirmar.** `pytest … | tail` esconde el código de salida;
  hay que mirarlo. Ya se commiteó una vez con dos tests rojos por eso.

## Reglas que no se rompen

- **Nunca borrar `workspace/`.** Es el trabajo del usuario. Para pruebas, usar
  `INTELLIPRINT_WORKSPACE` apuntando a una carpeta temporal.
- **Nunca imprimir ni commitear `.env`.** Lleva la clave de DeepSeek y el token
  del bot. Antes de cada commit, comprobar que no está en el índice.
- **Archivar no es borrar.** Un intento fallido es la única prueba de por qué
  algo no funcionó.
- **No tocar `M3_through_mm: 3.3`** sin la impresora delante: cambiarlo a ciegas
  es sustituir un valor sin validar por otro igual de sin validar (deuda F2.18).
  Lo cambia el usuario midiendo: lo apunta en la página «Impresora» de la web
  (F2.21 (impresora)), se guarda en `workspace/impresoras/` y manda sobre
  `config/printers/`, que no se toca. La impresora la configura él.

## Órdenes

El sistema vive en contenedores (ADR-014). La suite se corre **ahí**: nativa en
Windows caen 9 tests que no son del código, sino de que `/bin/sh` y los procesos
zombi no existen igual.

```bash
docker compose run --rm suite                       # la suite rápida: 2 min, en 12 procesos
docker compose run --rm orchestrator pieza peticion.md --archivo
docker compose run --rm orchestrator animar <carpeta-del-proyecto>
docker compose up -d web                            # http://localhost:8080
docker compose up -d crafty                         # Telegram
docker compose --profile sim run --rm sim pytest sim/pruebas   # el avión vuela en PX4 + Gazebo
docker compose --profile sim run --rm sim-gui sim/volar.sh     # lo mismo, viendo Gazebo
docker compose --profile sim up -d sim-web                     # Gazebo en http://127.0.0.1:6080
```

En el PC, para que el contenedor pueda laminar en tu PrusaSlicer:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start-host-mcps.ps1
```

Los tests `gui` abren ventanas de FreeCAD y **solo pueden correr en el host**,
igual que los que laminan de verdad; los `llm` cuestan dinero. Hay que pasarlos
antes de cerrar una tarea que toque FreeCAD, el laminado o un agente:

```powershell
$env:FREECADCMD = "C:\Program Files\FreeCAD 1.1\bin\freecadcmd.exe"
$env:FREECAD_GUI = "C:\Program Files\FreeCAD 1.1\bin\freecad.exe"
$env:PRUSASLICER = "C:\Program Files\Prusa3D\PrusaSlicer\prusa-slicer-console.exe"
$env:PYTHONUTF8 = "1"
.venv\Scripts\python.exe -m pytest -m "gui or llm" -q -n 7
```

Con `-n 7` son 3 min 31 s en vez de 12 min 8 s (los `llm` esperan a
DeepSeek cada uno por su lado). Cuestan unos 0,06 USD la pasada.

**Sin `FREECAD_GUI` los dos tests `gui` se saltan en silencio** (buscan el
FreeCAD de Mac por defecto): el código de salida sale 0 sin haberlos corrido.

**En Windows hace falta `PYTHONUTF8=1`.** Sin él, Python lee los archivos como
cp1252 y cualquier acento del repo revienta: son 10 tests de diferencia.

## Dónde está escrito qué

| Archivo | Qué contiene |
|---|---|
| `PLAN_PROYECTO.md` | Las tareas con su ID (`F3.15`), el criterio de aceptación y **la tabla de deuda técnica declarada** |
| `DECISIONES.md` | Las ADR: por qué el sistema es como es, con sus enmiendas cuando la realidad las corrigió |
| `SISTEMA_MULTIAGENTE.md` | Cómo es el sistema hoy: los dos flujos, los cinco agentes y lo que mide el código |
| `config/agents/*.md` | El prompt de sistema de cada agente |
| `config/openclaw/` | Crafty, el agente del canal humano (Telegram) |

Al citar un ID en el código va con su palabra clave —`F3.15 (mecanismos)`— y un
test lo comprueba: si la cita no cuadra con el plan, la suite se pone roja.

## Por dónde iba esto

**2026-11-13: Fases 11 a 13 aprobadas por él (ADR-022)**, con «me parece
tu propuesta comienza a trabajar asap»: carcasas con superficies, brazo de
clase Arctos y avión, en ese orden. Están en `PLAN_PROYECTO.md`. Las
filas de la 12 y la 13 se concretan con él al empezarlas; antes del avión
decide si el laminado entra en el diseño, si Gazebo queda fuera y qué
avión. La Fase 10 se cierra con el brazo mediano en 11 de 12 y sin
imprimir; lo que dejó abierto está abajo.

- **Hechas: F11.1 (curvas) y F11.2 (cáscara)** (2026-11-13). El kit
  dibuja secciones (`seccion`, `rectangulo`, `elipse`), las une
  (`transicion`), las lleva por un camino (`barrer`) y deja un cuerpo
  en una pared (`vaciar`). A mano, sin modelo, sale una carcasa curva
  hueca con orejas, tornillos y acabado. Su STL pesaba 216 MB: ahora
  toda pieza se malla a 0,01 mm y en binario. **Sin resolver:** tras
  unir un barrido curvo FreeCAD mide mal el volumen (el informe lo
  contrasta con la malla; lo de dentro del kit que compara volúmenes
  no está revisado). Ningún modelo las ha usado todavía: eso es
  F11.5 (diseñador).
- **Orden cambiado por él el 2026-11-13** («Sí, carcasa primero»):
  F11.5 y F11.4, la medición (F11.6) y, al final, F11.3 (tramos).
- **Hecha: F11.5 (diseñador).** Los prompts del diseñador y del
  ingeniero cuentan las formas curvas, con un ejemplo que un test
  construye. DeepSeek, pedida una tapa abombada, la dibujó con
  `transicion` y `vaciar` a la primera (una petición, una corrida).
- **Hecha a medias: F11.4 (cubre).** Un nodo del plan dice `cubre` y
  a la carcasa se le mide que envuelve lo comprado, que no lo toca,
  que no le tapa el cable y que le deja 1 mm (**el milímetro lo puso
  el asistente**). Probado con un NEMA 17 de pie. **No se hizo para
  el antebrazo del brazo mediano**: ahí el motor ya va dentro de la
  pieza y lo que se ve son la polea y la correa, que no tienen
  cuerpo en el sistema. No mide que esté cerrada ni que no roce con
  lo que gira.
- **Decidido por él el 2026-11-13 («Sí, con 2 USD»): F11.6 se mide
  con el encargo 16**, un NEMA 17 en una escuadra con su carcasa
  atornillada; tope de 2 USD, una corrida y hasta dos reanudaciones.
  El banco tiene la exigencia nueva `cubre`. Hecho a mano, sin
  modelo, pasa 5 de 5 (a la segunda: la carcasa se imprime boca
  abajo, con bridas en vez de orejas). La carcasa del antebrazo
  queda para cuando la polea y la correa tengan cuerpo.
- **El encargo 16, medido, se queda en 3 de 5** (corrida `1114-0023`,
  0,49 USD de los 2). Plan y soporte, a la primera; la carcasa gastó
  sus cinco intentos. No cumple el encaje (un saliente de la escuadra
  no la deja bajar recta: es real, mirado en FreeCAD) ni «sin
  soportes». Tres intentos se fueron en el sistema, y el juez se
  cayó al final. Arreglado: un punto repetido ya no es un error, el
  juez encuentra las fichas, el resumen del plan dice qué cubre la
  carcasa y al reanudar se le dice a la pieza lo que dijo
  PrusaSlicer. Sin arreglar: vaciar una forma que se estrecha hasta
  casi cerrarse, y una construcción de más de 180 s.
- **Reanudado una vez, el encargo 16 sigue en 3 de 5** (0,40 USD
  más: 0,89 de los 2; queda una reanudación). El acabado no se podía
  cumplir: el modelo dibujó los arcos con tramos rectos, porque
  quería un radio distinto delante y detrás y `rectangulo` solo
  admitía uno, y una superficie de facetas no se redondea. Y el
  aviso del encaje no decía dónde chocaba. Arreglado: un radio por
  esquina, decírselo al diseñador, y el choque con su sitio.
- **Reanudado por segunda y última vez, pasa 4 de 5** (1,19 USD de
  los 2; no queda más acordado). Ya encaja; falla «sin soportes».
  La carcasa no pasó su bucle por el chaflán de la base (10 de 12
  aristas, sin arreglar). Las construcciones de más de 180 s son el
  acabado sobre programas facetados, no un cambio de hoy.
- **Decidido por él el 2026-11-13, molesto: PrusaSlicer queda fuera
  de todo.** «El slicer no tiene nada que ver con el diseño» y «que
  el banco le ponga nota, pero que no tenga nada que ver con Prusa
  de momento». No volver a proponer laminar. «Sin soportes» se mide
  en la forma de la pieza (`orchestrator/voladizos.py`): seis
  posturas, voladizos de más de 45° y vuelos de más de medio puente
  (5 mm, **regla del asistente**). Con ella se corrige la pieza en
  su bucle y con ella pone el banco la nota; el banco ya no llama a
  PrusaSlicer. Rejuzgado todo: diez piezas 52 de 52, pan-tilt 7 de
  7, brazo de servos 8 de 8, encargo 14 9 de 10, 14b 8 de 9 (baja
  una), brazo mediano 11 de 12 y encargo 16 4 de 5.
- **Reanudado una tercera vez con su «sí», el encargo 16 seguía en
  4 de 5** (1,45 USD de los 2). El fallo era de la medida: la
  carcasa apoya en su brida, que por la holgura con el soporte quedó
  0,18 mm sobre un borde, y se contaba entera como «en el aire».
  Corregido: lo que queda a menos de una capa (0,2 mm) de la cama
  está en la cama. **Rejuzgado sin modelo, pasa 5 de 5.** La medida
  se corrigió después de ver el resultado; **aprobada por él** ese
  día («Si supongo que esta bien»).
- **Pedido por él el 2026-11-13: «mejorar las medidas del inicio
  para que no falle».** Entendido así (interpretación del asistente):
  lo que hoy se le dice a una pieza cuando ya ha fallado, dárselo
  antes de dibujar y con cifras. Hecho, sin correr: a la carcasa se
  le da la caja de lo que cubre y el hueco mínimo; el diseñador y el
  ingeniero saben cómo se mide «sin soportes»; y el acabado trata
  como base lo que queda a menos de una capa del fondo (el último
  programa de la carcasa baja del 56–71 % de aristas vivas al 6 %).
  **Falta medirlo:** una corrida nueva del encargo 16, por acordar.
- **Dicho por él la noche del 2026-11-13 al 14, antes de irse:** la
  corrida nueva del encargo 16, «Si con 2 dolares»; «cuando termines
  todo pasa a la siguiente fase automaticamente no me esperes»; y
  «sube a 15 dolares maximo puedes modificar medidas en caso extremo
  documentalo y me lo dices mañana». Entendido así (interpretación
  del asistente): 15 USD en total de banco desde ese mensaje, y una
  medida solo se cambia si no hay otra salida, apuntada aquí con su
  antes y su después. **Al volver él, el gasto se acuerda otra vez.**
- **La corrida nueva del encargo 16 se paró a mano** (`1114-0535`,
  0,57 USD de los 15): iba a fallar por el sistema. Tres medidas del
  bucle de la pieza **cambiadas sin él, con su permiso de esa noche;
  hay que contárselo**: (1) la tuerca cautiva que el plan pide en una
  pieza para el tornillo de otra ya no cuenta como «brida que no
  aprieta» (al soporte se le pedía y se le reprochaba a la vez, cinco
  intentos); (2) si un requisito nombra un tornillo y trae un
  diámetro que su texto no dice (Ø3.2 para un M3), vale el agujero
  del perfil; (3) un requisito que cita lo que escribe el sistema ya
  no cuenta aunque lo cite entero (la frase nueva del hueco mínimo se
  volvió una «ventana de 44.3 × 44.3» que nadie pidió: fallo del
  cambio del 13). Ninguna cambia lo que juzga el banco. Además el
  aviso de holgura de la carcasa dice con qué cuerpo y dónde.
- **Con esos arreglos, la corrida nueva da 2 de 5** (`1114-0631`,
  0,75 USD; 1,32 de los 15). El soporte salió, con sus tuercas. La
  carcasa, con el motor de eje horizontal esta vez, perdió cuatro de
  cinco intentos al construir: `acabar()` no construía una pieza sin
  arista hacia abajo, y la limpieza de caras de FreeCAD tumbaba una
  resta válida. Arreglados los dos en el kit.
- **Reanudada dos veces, la `1114-0631` pasa 4 de 5** (primero 3 de
  5; `banco_reanudado-2.md`; 1,47 USD la corrida, 2,03 de los 15).
  Solo falla el encaje: 8,3 mm³ de la carcasa se cruzan al meter la
  escuadra. Por el camino, dos intentos se perdieron con FreeCAD
  caído al redondear. Arreglado: si se cae redondeando, se repite
  sin redondear y la pieza se mide igual; y unir las caras de una
  booleana ya no tumba ninguna operación del kit. La carcasa sigue
  sin pasar su bucle (del 12 al 15 % de aristas vivas).
- **Con cuatro reanudaciones, la `1114-0631` pasa 5 de 5**
  (`banco_reanudado-4.md`; 2,02 USD la corrida, 2,59 de los 15). El
  encaje fallaba porque la carcasa se dibujaba dentro de la escuadra
  y le quedaba material en las ranuras de las tuercas, y el aviso
  le decía que el `hueco()` abría el camino, que con una pieza del
  invento no es verdad. **No es a la primera**, y la carcasa no pasa
  su bucle: del 21 al 24 % de aristas vivas, y FreeCAD se cae o
  tarda más de 180 s al redondearla (sin arreglar).
- **Hecha: F11.3 (tramos)** (2026-11-14). `pieza.partir(eje, en,
  lengueta)` corta una pieza que no cabe en la cama; cada tramo va a
  su STL en `tramos/` con una unión a media madera, y se le mide que
  quepa, que se imprima sin soportes y que un tornillo cierre cada
  corte. A mano, un carenado curvo de 400 mm sale en dos tramos sin
  defectos. **Criterio del asistente:** 0,8 mm de labio y de
  lengüeta como poco. Ningún modelo la ha usado y el banco no tiene
  encargo que la pida. Con ella la Fase 11 no tiene más filas.
- **Empezada la Fase 12 sin él, por lo que no depende de su
  respuesta:** la ficha `nema23` (F12.1 (fichas)), con las cotas de
  la hoja del fabricante. Qué NEMA 23 tiene o va a comprar no lo ha
  dicho: es un supuesto. **Las filas de la Fase 12 siguen por
  concretar con él**, y también el tope de gasto de su brazo.
- **Dicho por él el 2026-11-14: «quiero que levante 2 kg el brazo, tú
  propón rodamientos y motores».** Propuesto, **por aprobar** (la
  tabla está en `PLAN_PROYECTO.md`, Fase 12): tramos de 260 + 240 +
  100 mm; base con NEMA 23 de 56 mm y correa 5:1; la muñeca, tres
  NEMA 17 con las cicloidales de hoy (28, 28 y 10 a 1). Rodamientos:
  2 × 6810-2RS en la base, 6806-2RS en hombro, codo, J4 y J6, y
  608ZZ en el cabeceo. Las masas de lo impreso son estimaciones del
  asistente. Hechas las fichas `6806-2rs` y `6810-2rs`. **Aprobada
  por él el 2026-11-14 («Sí, apruebo»).** Falta el tope de gasto del
  brazo. Un giro del plan va sobre un solo componente: nada dice
  todavía que una articulación lleva dos rodamientos. Y la polea
  comprada del sistema es para eje de 5 mm: en el NEMA 23 de la
  base (6,35) no entra; falta su ficha.
- **Hecha a medias: F12.4 (muñeca)** (2026-11-14). Un giro dice
  `a_lo_largo` si su eje sigue al brazo (el del antebrazo, el de la
  herramienta): se le pide lo que al siguiente giro doblado 90°, y
  a su punta se le mide a lo largo del eje. El plan del brazo
  entero, escrito a mano, vale (`tests/test_brazo_grande.py`): el
  hombro pide 21,3 N·m de 32,2 con lo impreso a 0,2 g/mm. **Falta:**
  nada está construido a mano (no se sabe si la muñeca choca).
- **Dicho por él el 2026-11-14: «5 dolares dale»**, al pedirle
  gasto para los tests de pago del desglosador. Entendido así
  (interpretación del asistente): hasta 5 USD para esos tests, no
  para el banco. El desglosador ya escribe `a_lo_largo` (una
  petición, una corrida); los 14 tests del host pasan. **Gastado:
  0,12 USD**, medido en el saldo de DeepSeek. El gasto del banco
  para el brazo sigue por acordar.
- **Acordado con él el 2026-11-14 («Sí, la muñeca»): lo que queda
  de esos 5 USD (4,88) es para medir la muñeca sola en el banco**,
  el encargo 17: una corrida y las reanudaciones que quepan, y parar
  ahí. Antes, construirla a mano y escribir su encargo.
- **La muñeca hecha a mano, sin modelo, pasa 10 de 10** (2026-11-14;
  está en `workspace/projects/2026-11-14-muneca-a-mano-sin-modelo`
  para verla en la web: él preguntó por qué no salía nada del brazo).
  **Hay que decírselo:** de la muñeca a la brida no caben 100 mm,
  hacen falta unos 125 (los tramos del brazo se rehacen con él); y
  **una medida del banco cambiada que no ha visto**: dos agujeros en
  la misma recta a más de 100 mm ya no son el mismo tornillo (los
  del motor de la brida se contaban como del motor del antebrazo, a
  285 mm). No cambia ningún tornillo de las ocho corridas anteriores.
  La muñeca del encargo va sin rodamientos de apoyo.
- **La muñeca, medida con modelo: 8 de 10 a la primera y 10 de 10
  con una reanudación** (corrida `1114-1856`, 1,16 USD; 1,28 de los
  5 con los tests de pago: quedan 3,72 sin usar, y eran para la
  muñeca). A la primera falló solo la «Mano»: soportes, y los M3 de
  su motor taladrados desde el lado del motor. El aviso que recibía
  era engañoso («más estrecho»); ahora dice que van al revés. Las
  cuatro piezas pasan su bucle. Sin el resto del brazo, sin
  rodamientos de apoyo y sin imprimir.
- **Dicho por él el 2026-11-14, al ver la muñeca medida aparte:**
  «no veo por qué son proyectitos separados, cada proyecto puede
  tener mecanismos completos como la muñeca del brazo», y «termina,
  pero lo deseado es como yo lo describí, así que debes arreglar
  eso». **El brazo es UN proyecto, con la muñeca dentro.** La corrida
  de la muñeca (`1114-1856`) se deja terminar como ensayo. Escrito el
  encargo 18, el brazo entero (`brazo_seis_ejes_2kg`), con tramos de
  190 + 285 + 125 mm (la impresora admite 250 y con 260 del hombro
  al codo la pieza no cabía); su plan a mano vale (el hombro pide
  19,87 N·m de 32,19). **Hecho a mano pasa 14 de 18** y los seis
  ejes se mueven sin chocar en lo probado; lo que falta está en
  F12.5 de `PLAN_PROYECTO.md` (el encaje en el rodamiento de la
  base, dos piezas con soportes, el alcance medido en el canto de
  la brida y la placa del brazo, que el estudio da por rota).
  **Por decidir con él:** dibujarlo en reposo hacia arriba, porque
  tumbado el hombro lo baja bajo la mesa. Hecha la polea de 6,35
  para el NEMA 23. **Sin correr: su tope de gasto no está acordado**
  (se le preguntó; quedan 3,72 USD de los 5, que eran para la
  muñeca).
- **Decidido por él el 2026-11-14: en reposo el brazo apunta hacia
  arriba** («Arriba»). El encargo 18 y su plan lo dicen; el antebrazo
  se reparte en 145 + 140 mm y la brida lleva cuatro M3 para la
  herramienta. **De pie y a mano pasa 15 de 18** (llega a 600,5 mm
  y los motores levantan 2,7 kg); tres fallos del dibujo corregidos
  sin volver a juzgar. Está en la web como proyecto
  (`2026-11-14-brazo-de-seis-ejes-a-mano-sin-modelo`): él dijo dos
  veces que no veía el brazo entero ni en el banco ni en sus
  inventos. **En «Banco» no sale hasta correrlo con el modelo, y su
  gasto sigue sin acordar.** **Una medida del banco cambiada que no
  ha aprobado:** la carga que aguanta una pieza cuenta solo la parte
  del peso que va de través (daba «0 g» en la placa del brazo); solo
  puede subir una carga. Y `dimensionar` ya no salta un giro a lo
  largo por ser vertical. La reserva de sitio de cada giro avisa
  por posturas bajo la mesa: sin arreglar. Que tardara (2,5
  millones de posturas con cinco giros debajo) sí: ahora se mide en
  la rejilla del barrido.
- **Acordado con él el 2026-11-14 («Sí, con 3,72»): el brazo entero
  se corre en el banco con los 3,72 USD que quedaban**: una corrida
  y lo que quepa, y parar ahí. Lanzado con el vigilante en 3,2.
  **La primera (`1114-2326`) se cortó al reiniciarse su PC**, con
  solo el plan (0,16 USD). Ese plan le ponía a la brida los mismos
  125 mm hasta la punta que al cabeceo: no se reanudó. Arreglado
  (el plan ya no vale así, y el prompt del desglosador lo explica;
  0,18 USD en tests de pago) y **lanzada de nuevo desde el plan**,
  con el vigilante en 2,9: 0,34 de los 3,72 ya gastados.
  Entendido así (interpretación del asistente): querría además
  aprovechar un mecanismo ya diseñado dentro del proyecto grande;
  hoy cada encargo se diseña de cero y «ampliar» solo añade por
  encima.
- **El brazo entero, medido con modelo, se queda en 0 de 18 y se paró
  solo** (corrida `1115-0138`, 1,44 USD; 1,78 de los 3,72: **quedan
  1,94, sin reanudar**). El plan salió bien. De siete piezas se
  construyeron tres: la base pasó; la torreta y el brazo superior
  gastaron sus cinco intentos con un «sitio para girar» imposible
  (605 mm libres alrededor del hombro con la base a 105); el antebrazo
  no se construyó y sin él no hubo muñeca. Dos de sus cinco intentos
  murieron en FreeCAD («Null shape» al darle holgura al brazo superior)
  y uno por pedir `M4_through_mm`. Arreglado, sin corrida: a un brazo
  (el plan le da `brazo_mm`) le basta un sector libre tan ancho como lo
  que gira más 20° (**el margen lo puso el asistente; cambia lo que se
  le mide a la pieza en su bucle, no lo que juzga el banco**); la forma
  que OCC no sabe hacer crecer crece por donde se pueda; y el agujero
  del perfil se puede pedir con su «_mm». Sin arreglar: la torreta no
  tiene cara para imprimirse sin soportes, y `conjunto._sin_sitio` (a
  quién se culpa de un choque) sigue pidiendo el círculo entero.
- **Dicho por él el 2026-11-14, al ver el brazo «a mano» en la web:**
  «es fea la estructura, demasiado simple… ¿estructuras planas? ¿por
  qué no impresiones cilíndricas como Arctos o como un KUKA? Es un
  brazo a base de paletas y tornillos». Y después: «lo que me cuesta
  entender cuando hablas es si realmente lo estamos haciendo bien o
  estás metiendo mano». **Lo hecho a mano por el asistente no es nota
  del sistema y hay que decirlo cada vez.** El sistema también dibuja
  placas: el brazo superior de la `1115-0138` es una «placa-viga de
  20 mm», y el prompt del ingeniero dice «donde una placa basta, no la
  compliques». Entendido así (interpretación del asistente): quiere
  que cada tramo sea un cuerpo hueco y redondo con el motor dentro.
  **Aprobado por él ese día («Sí, con 4 USD»):** decirlo en el encargo
  18 y en los prompts del ingeniero y del diseñador, y volver a correr
  el brazo, con 4 USD de tope contando los tests de pago. Y después:
  «mejóralo todo en modo automático y por favor no me pidas a mí nada,
  yo ya te apruebo para que hagas el nuevo brazo luego de terminar los
  tests». Entendido así (interpretación del asistente): dentro de esos
  4 USD se corre y se reanuda sin preguntarle; al agotarlos se para.
  Hecho: el encargo pide «un cuerpo hueco y redondeado, de sección
  cerrada… no placas ni vigas planas»; al ingeniero y al diseñador se
  les dice que el tramo de un brazo es un tubo, con un ejemplo que un
  test construye y mide que se imprime sin soportes. **Lo que no hace
  todavía:** meter los motores dentro de carcasas cerradas como Arctos;
  eso pide cáscaras partidas en dos, que son más piezas por tramo. Los
  3 mm de pared mínima del prompt son criterio del asistente. El banco
  no mide la forma: que salga redondo se ve, no se puntúa.
- **El brazo de tubos, en marcha la noche del 14 al 15** (todo con el
  modelo; nada dibujado a mano). La `1115-0432` se paró a mano en su
  primera pieza (0,52 USD): el ingeniero sujetaba el motor bajo orejas
  de 7,5 mm «porque es menos que el puente de 10»; ahora sabe que un
  alero aguanta la mitad. La `1115-0523`, desde cero: la base pasó; la
  plataforma de giro y el brazo superior gastaron sus cinco intentos
  (1,48 USD las tres). **El brazo superior ya es un tubo ovalado hueco
  con una cuna para el motor del codo**: se le mandó foto. Dos de sus
  intentos murieron en OCC (una unión y un taladro «no válidos» sobre
  la cáscara curva): arreglado en el kit (`_booleana`, `limpia` sólido
  a sólido). **Sin arreglar:** el diseñador vuelve a colocar lo
  comprado que ya monta la pieza de abajo y pierde el intento (tres
  entre dos piezas); el perfil no tiene tuerca cautiva de M5 (lo
  apunta él en «Impresora»).
- **Reanudada, el brazo de tubos se queda en 0 de 18 con dos piezas
  buenas de siete, y los 4 USD están gastados** (`banco_reanudado.md`;
  3,07 USD la corrida `1115-0523`; con la `1115-0432` y los tests de
  pago, 3,83 de los 4: **no se reanuda más sin acordarlo**). La nota
  es 0 porque el banco solo puntúa el invento entero y faltan tres
  piezas. Cumplen la base y **el brazo superior, que pasó a la primera
  corrección**. La plataforma de giro solo falla el acabado: FreeCAD se
  cae al redondearla y se entregaba con las aristas vivas (79 %).
  Arreglado sin corrida: cuando se cae, las aristas rectas llevan un
  chaflán hecho por corte, que no pasa por el redondeo de OCC; repetida
  sin modelo, baja al 1 % y cumple el acabado (lo demás de su bucle no
  se ha vuelto a medir, y en el banco sigue como «no cumple» hasta
  reanudar). El antebrazo proximal se
  construyó y no cumple (soportes, una pared de 0,07 mm y dibujado
  encima del motor del codo): es del diseño. El antebrazo distal no se
  construyó, y **cuatro de sus cinco intentos los tumbó el kit**: al
  restar el hueco de la pieza vecina le abría además el camino de
  entrada, de 2 m, al motor que esa vecina ya lleva montado, y el túnel
  se llevaba la brida de los tornillos. Arreglado sin corrida (lo que
  monta una vecina llega puesto: su hueco es su forma con holgura);
  repetidos sin modelo, esos cuatro programas se construyen. **Cambia
  lo que construye el kit, no lo que mide el banco.** El vigilante se
  puso en 2,75 y la corrida llegó a 3,07: solo mira entre pieza y
  pieza, y la penúltima acabó en 2,745. Mano y brida, sin empezar.
- **Reanudada otra vez con su «reanud» y 3 USD de tope nuevo, el brazo
  de tubos pasa 16 de 18** (2026-11-15, `banco_reanudado-2.md`; 1,84
  USD más: 4,91 la corrida `1115-0523`; **quedan 1,16 de esos 3, y
  cada reanudación se acuerda**). Todo lo dibujó el modelo; nada a
  mano. Por primera vez salen las siete piezas y el brazo se monta:
  llega a 636,6 mm, levanta 2 123 g y se mueve sin chocar en lo
  probado (729 poses de 47 millones con los seis giros, cada 90°).
  **Lo que el 16 de 18 no dice:** cuatro de las siete piezas no pasan
  su propio bucle (plataforma, los dos antebrazos y la mano); solo lo
  pasan la base, el brazo superior y la brida. Fallan «sin soportes»
  (plataforma: las alas de un nervio más ancho que la columna empiezan
  en el aire; antebrazo proximal: un tabique plano de 43 × 43 mm
  dentro del tubo; mano: una cara de 1568 mm²) y el encaje del
  antebrazo distal. El arreglo del túnel funcionó (el distal se
  construye), y lo que falla ahora es del modelo: el distal entregado
  declara que el proximal le entra «por +z» teniéndolo debajo, lo
  corrigió al tercer intento y perdió los tres últimos taladrando un
  agujero de la reductora que cae fuera de su pared. **Avisos del
  sistema que no le sirvieron, sin arreglar:** el de soportes habla
  de «una cara inclinada de 4 mm²» y no del borde que empieza en el
  aire; «no toca la pieza» dice «revisa `en` y `eje`»; a una pieza
  que lleva su propio NEMA 17 se le dice «no coloques otro nema17»
  porque la de abajo monta uno; y a la mano se le avisó una vez de
  que la base, 70 cm más abajo, estorba al giro de la brida (sin
  mirar: puede ser de `conjunto.radio_libre`). No sigue pareciendo
  un Arctos: tubos en el brazo superior y los antebrazos, pero la
  plataforma es un nervio con placa y la mano una caja.
- **Dicho por él el 2026-11-15, al ver ese 16 de 18:** «Horrible el
  brazo inusable… solo pusiste cilindros conectados con placas igual.
  Debe ser un brazo robótico, no algo que pareciera que armé a puras
  piezas reusadas de la basura o chatarra». **La nota del banco no
  basta: antes de contarle un resultado, mirar la foto.** Se le
  enseñó un boceto (un tambor en cada articulación, tramos de tambor
  a tambor, motores tapados) y lo aprobó: «Si asi lo quiero».
  **Decidido (ADR-023): la forma de un brazo la pone el código y el
  modelo pone medidas y motores.** Y preguntó «¿lo hiciste tú o
  Intelliprint?»: **hay que decirlo sin que lo pregunte.**
- **Hecho A MANO por el asistente con el kit, sin modelo: el brazo
  con esa forma pasa 18 de 18** (2026-11-15,
  `scripts/brazo_industrial_a_mano.py`; fila F12.6). Las siete piezas
  llevan sus motores, el rodamiento, la polea y los tornillos, y se
  imprimen sin soportes; llega a 609,5 mm y levanta 2 703 g. **No es
  nota del sistema**: el asistente escribió los siete programas y el
  sistema los construyó, midió y juzgó; el modelo no dibujó nada.
  No es todavía el boceto: los motores del hombro y del codo van a
  la vista (faltan tapas) y la muñeca son dos bandejas rectas,
  abiertas por un lado y a 104 mm del eje del antebrazo. **Una
  medida del banco corregida que hay que contarle:** un eje macizo
  dentro de un rodamiento grande (6810) se daba por «apoyado en los
  dos aros» sin tocar ninguno (`sondas._punto_dentro` probaba con el
  centro del anillo, donde está el eje); así fallaba el encaje del
  brazo de pie. Solo puede quitar un «no cumple» falso. **Sin
  arreglar, de las medidas:** la cama solo se prueba en posturas
  rectas (el brazo superior, de 284 mm, cabe en diagonal; **arreglado
  el 2026-11-16** con el avión) y el sitio de un giro cuenta posturas
  con la muñeca bajo la mesa.
- **Hechas: las siete formas del brazo en el kit** (2026-11-15,
  F12.6 (forma), `mech_toolkit/brazo.py`): `kit.brazo_base`,
  `brazo_columna`, `brazo_tramo`, `brazo_antebrazo`, `brazo_muneca`,
  `brazo_mano` y `brazo_brida`. Cada una coloca lo comprado, hace sus
  huecos y tornillos y devuelve la pieza acabada; el programa de una
  pieza es una línea (`return kit.brazo_tramo(abajo, 190,
  "nema23-pg47-56")`). Con esas siete líneas, escritas por el
  asistente y sin modelo, el brazo pasa **18 de 18** en el banco.
  Es una familia (giros tumbados a lo largo de «y», reposo hacia
  arriba), no un diseñador. **Falta para que sea del sistema:**
  contárselas al modelo en los prompts (tests de pago), arreglar las
  dos medidas de arriba, que le harían gastar intentos, las tapas, y
  correrlo con el modelo (gasto por acordar; del tope de 3 USD
  quedan 1,16). **Preguntó por qué el asistente lo hace más rápido
  que Intelliprint y por qué Intelliprint no sabía hacerlo:** se le
  dijo que el asistente es un modelo más capaz que DeepSeek y ve el
  brazo entero, que se le guio por la nota del banco sin mirar la
  forma, y que hay dos caminos: formas en el código familia por
  familia, o un modelo más capaz diseñando (más caro). **Sin
  decidir.** Del avión dijo que «seguro va a ser un super fail».
- **Pedido por él el 2026-11-14: que las pruebas tarden menos** («dura
  demasiado tiempo actualmente»). Hecho para la suite: corre en doce
  procesos (`pytest-xdist`, en la imagen) y baja de 7 min 42 s a
  1 min 51 s con los mismos tests. Un test suelto se pide igual que
  antes; para ir de uno en uno, `-n 0`. **El vigilante de gasto del
  banco para todos los contenedores `suite`**: una suite lanzada con el
  banco en marcha muere si el banco llega a su tope. Los 14 tests del
  host (`gui or llm`), con `-n 7`: de 12 min 8 s a 3 min 31 s.
- **Pedido por él el 2026-11-14, «es importante»: administrar la web
  pieza a pieza**: girar cada pieza y escribirle («agrega una
  rendija que permita el flujo de aire»). Hecho en la página de un
  backlog: «Girar en 3D» en cada tarjeta, «Pedir un cambio a esta
  pieza» a la vista (estaba bajo «Más») y tocar una pieza en el
  ensamble para ir a ella. Probado en el navegador. Falta: las
  piezas sueltas, y elegir una cara o un punto en vez de decirlo
  con palabras.
- **Decidido por él el 2026-11-14: «Ambas compradas y en los bom
  agrega el link de compra de la reductora».** Las reductoras del
  hombro y del codo se compran y F12.2 (reductora) no se hace. Hechas
  sus fichas: `nema23-pg47-76` (hombro: pide 25,1 N·m de 32,2) y
  `nema23-pg47-56` (codo: 10,1 de 21,3), un NEMA 23 con planetaria
  de 46,656:1 ya montada; la pieza gira en su eje, sin `movido_por`.
  Una ficha puede decir dónde se compra (`compra_url`) y la lista
  de materiales lo enseña. Su hoja da hasta 1,5° de juego (15,7 mm
  en la punta por el hombro y 8,9 por el codo), y al proponérselas
  se le había dicho «casi 9 mm». **Dicho y aceptado por él ese día:
  «dale usa esa reductora con el juego».** Las hojas son las de una
  tienda (Oyostepper); la del fabricante no se dejó leer.
- **El avión, dicho por él esa noche:** un VTOL, con una autonomía
  muy buena en horas, hasta 250 km de alcance, hasta 8 libras
  (3,63 kg) de carga, y que lleve hasta dos cámaras y un lidar sin
  perder aerodinámica. La referencia que mandó, «similar a este pero
  mejorado»: el TerraHawk FPV de Nomadium, un VTOL de ala integrada
  con cuatro rotores bajo el ala y hélice de empuje (1,4 m, ~2 kg,
  6S2P, largueros de carbono; su página no da autonomía ni carga).
  Y lo concretó: **envergadura de 2 m o más, 8 libras de carga
  máxima y la autonomía del TerraHawk** (según la captura que mandó,
  sin verificar: más de 3 h y 180–216 km a 72 km/h; el comercial de
  2 m pesa 4 kg y carga 1 kg). **Y bajó la carga esa misma noche:**
  «que sea igual, yo siento que podemos usar lo mismo»: la del
  TerraHawk, no 8 libras (entendido como la del comercial de 2 m,
  hasta 1 kg; sin confirmar). Queda por decidir
  si el laminado entra en el diseño y si Gazebo queda fuera.
- **Dicho por él el 2026-11-16: «hagamos lo mismo con el avión, tú
  diseña y usa lo que habías dicho, quiero que se haga rápido».**
  Hecho A MANO por el asistente, sin modelo: las cuentas con
  AeroSandbox (`scripts/avion_vtol_dimensionar.py`, instalado solo en
  el `.venv` del PC; OpenVSP no se usó) y las 41 piezas con el kit
  (`scripts/avion_vtol_a_mano.py`). VTOL de 2,6 m, cuatro rotores en
  dos vigas de carbono, hélice de empuje, cola en H con timones y
  alerones. Según AeroSandbox y las estimaciones del asistente: 8,7 kg
  al despegar con 1 kg de carga, batería 6S10P de 21700 (972 Wh),
  3,2 h y 232 km a 72 km/h. **Pesa el doble que el TerraHawk de 2 m
  (4 kg)**: con 1 kg de carga, 3 h piden casi 1 kWh de batería.
  Caben las 41 en la cama y 40 se imprimen sin soportes (el cuerpo
  central 3 pide en dos puntos de 38 mm², sin arreglar). Está en la
  web como `2026-11-16-vtol-a-mano-sin-modelo`. **Que vuele no lo
  dice nada**; el banco no tiene encargo de avión y el modelo no sabe
  dibujarlo (F13.2 y F13.3 siguen sin hacer).
- **Dicho por él al verlo, el 2026-11-16:** «5 motores brushless eso
  es caro en batería», «el espacio entre los 3 rotores de atrás parece
  que se traslapa», «¿qué tamaño de hélices?», «mete las formas en
  Intelliprint» y «quiero que lo nuestro sea ligero», «más parecido a
  un avión moderno eficiente» (el Moose de Flightory y el TerraHawk).
  **Rehecho A MANO por el asistente, sin modelo:** un ala volante de
  2,27 m (flecha de 25°, puntas levantadas, fuselaje fundido, sin
  cola), 6,03 kg con 1 kg de carga, 6S6P de 583 Wh, 3,14 h y 226 km
  según AeroSandbox. Los cuatro rotores cuestan 0,8 kg, 60 W de los
  142 del crucero y 49 Wh; hélices de 13″ y de empuje de 10″, con
  88 mm entre los discos de atrás (eran 25). Las derivas bajo las
  vigas lo hacen estable en guiñada y son el tren: se alargaron para
  que la hélice de empuje no toque el suelo (le quedan 30 mm). **La
  forma está en el kit** (`kit.avion_pieza`, `mech_toolkit/avion.py`,
  F13.3 (costillas)): 39 piezas de una línea, en la web como
  `2026-11-16-ala-volante-a-mano-sin-modelo`; caben y ninguna pide
  soportes. Por el camino: los agujeros de los largueros no tenían
  tejado (en la primera, ninguno: por eso pedía soportes su cuerpo
  central 3; en esta, un rombo que se quedaba dentro del círculo), y
  ahora son una gota.
  **Una medida del banco cambiada que hay que contarle:** la cama se
  prueba también girando la pieza sobre ella (`medida.
  no_cabe_en_la_impresora`); un tramo de ala con flecha solo cabe en
  diagonal. Solo puede quitar un «no cumple» falso. Pesa 1,5 veces el
  TerraHawk de 2 m (4 kg), por las 3 h con 1 kg de carga. **Que vuele
  no lo dice nada**, y el modelo no ha usado las formas.
- **Pedido por él el 2026-11-16, cambiando lo de PX4:** «quiero que
  crees los urdf, el docker para levantar la imagen con ROS2, poder
  hacer la simulacion de vuelo con gazebo y que trabajemos con
  integrarlo con px4» (ADR-024, F13.6 (simulación); AVL sigue fuera).
  Y sobre el interior: hueco para controladora, Raspberry Pi,
  variadores y batería; «la batería debe estar en un lugar donde no
  modifique mucho el centro de gravedad»; y cuatro servos, uno por
  elevón. **Hecho A MANO por el asistente, sin modelo:** la carga va
  en el CG (quitarla no lo mueve: margen del 7 % con y sin ella), la
  batería encima, la electrónica en el morro, dos elevones por lado
  con su servo en un hueco por debajo y un canal de Ø6 para los
  cables; las 39 piezas caben y ninguna pide soportes, y lo de dentro
  no atraviesa ninguna (`tests/test_avion_formas.py`). En la web como
  `2026-11-16-ala-volante-con-electronica-a-mano-sin-modelo`. Las
  piezas siguen macizas (faltan piel fina, nervios y tapas).
  **La simulación:** contenedor `sim` (perfil del compose: ROS 2
  Jazzy, Gazebo Harmonic, PX4 v1.17.0, Micro XRCE-DDS, `px4_msgs`);
  `scripts/avion_vtol_aero.py` saca de AeroSandbox las derivadas para
  `AdvancedLiftDrag`; `python -m sim.generar <proyecto> sim` escribe
  el modelo de Gazebo, el URDF y la aeronave 4100 (las mallas, 57 MB,
  fuera de git). El CG del modelo cae a 2,6 mm del dimensionado.
  `sim/volar.sh` lanza PX4 con él y `sim/pruebas/test_vuelo.py` vuela
  una misión. **Siete vuelos hasta la misión entera**, cada fallo con
  su test: la transición se abortaba (gas a tope y 8 s; luego perdía
  altura: pasa a avión a 20 m/s y mezcla a 15); en el primer giro se
  pasaba de 60° de alabeo y caía (`FW_R_LIM` 30); y seguía cayendo
  porque el plugin `AdvancedLiftDrag` mezcla con una sigmoide fija
  (M = 15) que con la pérdida a 0,2 rad ya restaba sustentación a 0°:
  `alpha_stall` se calcula ahora para que el CL máximo del plugin sea
  el del dimensionado (0,309). El sexto voló la misión entera, pero
  en la primera esquina el rumbo de PX4 saltó 150°: el mundo de PX4
  tiene un campo magnético fijo de 14,6° de declinación y PX4 usaba
  la de Zúrich (3°); arreglado en la aeronave. Los ajustes de PX4
  son los del `standard_vtol`, y el empuje y las vueltas de las
  hélices, supuestos del asistente. **Un fallo del dimensionado, sin
  arreglar y por contarle:** el Cn_beta de `request.md` (0,0555) se
  tomó respecto al morro; respecto al CG es 0,0156, poca estabilidad
  de guiñada. **Gazebo en el navegador** (pedido por él ese día):
  `docker compose --profile sim up -d sim-web` y
  `http://127.0.0.1:6080/vnc.html?autoconnect=1&resize=scale`; repite
  la misión sin parar y gasta ~5 núcleos (dibuja sin tarjeta).
  **Que vuele en Gazebo no dice que vuele impreso.**
- **Dicho por él el 2026-11-16, después:** «haz todo lo que haga falta,
  el fallo, los pulidos de las piezas también»; «las alas son de lw pla
  el resto de petg» (Prusament); y al ver 36 celdas, «nunca ha sido tan
  ilógico… tiene más sentido una batería 4s grandecita», «algo de 15k
  mAh para… un poco más de 1 hora… o usemos 6s» y «usemos motores y
  batería que pueda comprar en amazon». Imprime en una **Prusa CORE One
  L+** (300 × 300 × 330; el perfil del sistema sigue siendo el del M5).
  **Rehecho A MANO por el asistente, sin modelo:** piezas huecas (piel,
  alma, nervios, fundas; panza atornillada y tapas de servo), pesadas en
  sus STL (2,37 kg sin guías, no 0,94); derivas de 255 mm por la guiñada respecto
  al CG; LiPo 6S 16 000 mAh y motores 4312 de 400 KV con hélice de 15″,
  con su enlace de Amazon en `scripts/avion_vtol.json` (`compras`): 7,0
  kg, 1,53 h y 110 km, 1,71 veces el peso en empuje, según AeroSandbox y
  las cifras de cada anuncio (sin medir). Los largueros se cortan al
  metro de tubo que se vende. Las piezas huecas pasaban de los 180 s de
  FreeCAD (el primer tramo del ala, 257 s): ahora se vacían con el hueco
  limpio y lo de dentro se suma después. Las 44 piezas caben y ninguna
  pide soportes; están en la web como
  `2026-11-16-ala-volante-lipo-amazon-a-mano-sin-modelo` (con `foto.png`).
  Entre el centro y las raíces hay ahora una costilla en la junta, para
  pegarlas por una cara y no por el canto de la piel. OCC no da siempre el
  mismo sólido: la misma panza, construida doce veces, varía un 0,7 % de
  volumen. **Pedido por él ese día («Sí, añádelas»):** guías entre las
  celdas del cuerpo central, que iban pegadas a tope: 14 trozos de 18 mm
  de varilla de Ø2 en tacos de Ø8 por dentro de la pared (`avion.guias`),
  y dos varillas de 500 mm en la lista de compras en vez de una (con una
  no daban ni los elevones). **Hecho A MANO por el asistente, sin modelo,
  el 2026-11-17:** las 44 piezas caben y ninguna pide soportes
  (`2026-11-17-ala-volante-lipo-guias-a-mano-sin-modelo`, con `foto.png`).
  Lo impreso pesa 2,40 kg; el total, 7,05 kg; siguen 1,53 h y 110 km, con
  1,70 veces el peso en empuje. Los 24 g de más bajan la torsión de la
  punta de −4,0° a −4,5°, y por eso las piezas se construyeron dos veces
  (la primera vuelta queda en la carpeta del 16). La panza se hizo con la
  batería 0,4 mm más atrás que en el dimensionado final; otra vuelta sería
  perseguir el ruido de OCC. Lo que tumbó los tests la noche de la pausa
  no era tiempo: las varillas de un corte, juntas, son varios sólidos, y
  el sistema no construye una pieza que no sea una; ahora se miden de una
  en una (`guia-1-abajo`). **Por contarle:**
  el pitot no tiene hueco en el morro; las hélices de 4 mm pueden no
  entrar en el eje del motor.
- **Dicho por él el 2026-11-17: «¿por qué en Intelliprint hay 6 inventos
  de avión y no un avión con 6 versiones?» y «el brazo no aparece armado
  en los inventos, arregla todo eso».** Cada carpeta hecha a mano traía
  una petición distinta y ningún `proyecto.json`. Arreglado:
  `versiones.marcar_version` la marca como versión de su proyecto y los dos
  scripts a mano la exigen (`-e CAMBIO="…"`). Las versiones se ordenan por
  de cuál parte cada una, no por el nombre (que en lo hecho a mano solo
  lleva la fecha), y la página dice a la vista qué cambia. Marcadas las
  que había: el avión es un invento con 7 versiones y el brazo uno con 3
  (la muñeca de ensayo es la 2). El brazo industrial se había comprobado
  sin animación y no dejó `ensamble.json`, lo que la web pinta montado:
  rehecha con `animar`, y el script ya la hace como proyecto. Y después:
  «también debe mostrarse el ensamble de todo». La imagen de un backlog
  (portada, y página sin visor) eran sus piezas en fila: ahora es el
  invento montado (`vista.montado`), con el conjunto en reposo y lo
  comprado dentro, o, sin conjunto (el avión), cada pieza donde se dibujó.
  Dibujar el avión tarda unos 107 s la primera vez; quedan dibujados.
  **Preguntó también si vuela con 7 kg, imprimiéndolo con poco relleno:**
  el 20 % de relleno ya estaba contado y lo impreso es 2,40 de los 7,05 kg
  (el PETG del cuerpo, 1,87); se le contestó con el desglose. **Sin
  decidir:** pasar el cuerpo a LW-PLA o adelgazarlo.

**2026-11-11 (noche): Fase 10, brazos con transmisión (ADR-021).** Decidido
por él: **el brazo antes que el avión**; empezar por uno pequeño con servos;
la meta de la fase es un brazo mediano solo con NEMA 17 (350–400 mm,
300–500 g, 4–5 ejes); la primera reductora impresa, la cicloidal. El de
clase Arctos es otra fase. El avión irá con **OpenVSP y AeroSandbox**, sin
AVL ni PX4, y no tiene fase. El plan y su orden están en `PLAN_PROYECTO.md`,
Fase 10.

- **Hecho: F10.1 (serie).** Dos exigencias nuevas de backlog, `alcance` y
  `carga`, que salen del estudio de movimientos, y el encargo 13: un brazo
  de 3 ejes con SG90 que llega a 120 mm y levanta 30 g.
- **El encargo 13 pasa 8 de 8** (corrida `1112-0318`, 1,22 USD: la corrida
  y una reanudación de pago; quedó otra sin usar). Antes hubo que arreglar
  dos cosas del sistema: FreeCAD se caía al crecer el hueco de una pieza
  vecina y el diseñador gastaba sus intentos a ciegas (ahora la
  construcción se repite por otro camino), y mover tres giros con piezas
  de verdad pasaba de 600 s (ahora no se miden los pares que no pueden
  tocarse). El alcance (233 mm del eje de la base) salía de un desvío
  lateral, no de un brazo largo. **Decidido por él el 2026-11-12: el
  alcance se mide del hombro a la punta.** Rejuzgada sin modelo sigue en
  8 de 8, con 120,0 mm de los 120 pedidos: sin margen. **Lo que no dice:**
  es un brazo raro (el tramo cuelga a un lado, y sin atornillar vuelca), y
  los M3 de la base no se comprueban.
- **«Banco» en la web enseña una corrida mientras corre**, con «En marcha»
  y recargándose sola; lo pidió él para ver cómo iba el brazo.
- **Hecho: F9.10 (ampliar)** (2026-11-12, `orchestrator/ampliar.py`). A un
  backlog se le añade una función sin pedirlo entero otra vez: la
  propuesta espera en `ampliacion.json` sin tocar el plan, y al aprobarla
  solo se corrige la pieza que la función toca. Desde la web («Añadir una
  función»), Crafty (`ampliar_proyecto`) y `obra --ampliar`.
- **La ampliación, medida, se queda en 7 de 9** (corrida `1112-1359`,
  «pan-tilt con pinza» partiendo de la `1111-1342`; 0,84 USD de los 2
  acordados, y las dos reanudaciones sin usar). El mecanismo funcionó: la
  propuesta valió a la primera, solo se corrigió la plataforma, y la base
  y el soporte siguen idénticos. Falla el diseño: la plataforma puso los
  M3 de la pinza en la cara que da al servo de inclinación, y el soporte
  de la pinza quedó construido encima de él.
- **Tres arreglos que salieron de ahí, aprobados por él el 2026-11-12.**
  A la pieza que taladra primero se le dice que lo que se atornilla
  después necesita sitio al otro lado, y se mide en su bucle
  (`medida.sin_sitio_para_lo_nuevo`); al reanudar, el banco corrige la
  pieza que no dejó el sitio y no la que cayó encima. Y dos del barrido,
  que cambian lo que el banco da por choque: dos piezas sin giro por
  medio pueden tocarse, y un giro se barre lo que pide el plan, la mitad
  a cada lado de como se dibuja (el dedo se barrió 180° pidiendo 60°).
  Rejuzgados con ellos, el pan-tilt sigue en 7 de 7 y el brazo en 8 de 8.
- **Reanudada una vez con ellos, la pinza sube a 8 de 9 y ahí se paró**
  (`banco_rejuzgado-2.md`; 0,83 USD más: 1,67 de los 2 acordados, no
  queda para otra). El banco corrigió la plataforma y no la pinza, y la
  plataforma movió los M3 a la primera. Pero los puso en su cara de
  abajo, y ahí la pinza no cabe: el dedo choca con la base al inclinar.
  La medida del sitio pide 6 mm en 20 de fondo y lo que viene mide
  85 × 73 mm y su dedo necesita 40 mm libres, que solo hay saliendo por
  la cara de fuera. Además, a la pinza nadie le dice de qué lado de los
  agujeros va, y se puso del de la cabeza. **Lo que el 8 de 9 no dice:**
  el encargo no pide los dos M3 de la pinza, y ni ella ni el dedo
  pasaron su propio bucle.
- **Dos arreglos más, aprobados por él el 2026-11-12 con 1 USD más**
  (3 de ampliación en total). Si lo que viene monta un giro, a la que
  taladra primero se le mide que quepa ese eje saliendo de los
  agujeros, y se le dice por qué caras cabe; bajo la base cuenta la
  mesa. Y a la pieza que agarra se le dice de qué lado va: donde sale
  el tornillo, no donde entra la cabeza.
- **Reanudada otra vez con ellos, la pinza baja a 0 de 9 y se paró**
  (`banco_reanudado.md`; 0,76 USD más: 2,43 de los 3, no queda para
  otra). La plataforma no cumplió en cinco intentos (taladró la pared
  del acople hacia +y en vez de ir a la cara de fuera) y el soporte de
  la pinza, rehecho contra ella, falló sus cinco construcciones; el
  dedo no se hizo. La pinza y el dedo del 8 de 9 están en el archivo.
  Los dos arreglos pasan sus tests y en el banco no han ayudado: el
  «4 mm más allá» que se le dice a la pinza es el grueso de una pared,
  no la salida de la pieza, y la mandó dentro de la plataforma. **La
  pinza queda aparcada**; seguir es otro gasto, por acordar.
- **Hecho: F10.2 (transmisión)** (2026-11-12). Un giro dice en
  `movido_por` qué motor lo mueve, si por correa o reductora y con qué
  relación; el motor va en la misma pieza que el rodamiento. El
  estudio lleva el par al eje: el NEMA 17 da 0,400 N·m según su hoja,
  y con correa 4:1 levanta 479,5 g a 150 mm, a mano y en el test. **Dos
  supuestos los puso el asistente y él no los ha decidido:** el
  rendimiento (0,9 la correa, 0,7 la reductora) y pedirle al paso a
  paso como mucho el 50 % de su par de retención. Nadie dibuja aún la
  correa ni las poleas, y no se ha corrido en el banco.
- **Hecho, sin medir en el banco: F10.3 (correa)** (2026-11-12). El kit
  dibuja la polea GT2 (`kit.polea_gt2`); del `movido_por` sale que el
  motor lleva una polea comprada de 20 dientes, la pieza que gira una
  de 20 × relación, y que los ejes van a la distancia de una correa
  cerrada. Cada pieza mide su parte y el banco cuenta la reducción por
  dientes (`reduccion`). **Tres cosas las decidió el asistente y él no
  las ha visto:** sin colisa (ejes fijos, ±0,2 mm), las correas se
  ofrecen de 5 en 5 dientes sin saber cuáles vende su tienda, y la
  ranura del diente es una aproximación (un semicírculo de 0,76 mm).
- **El encargo 14, medido, se queda en 6 de 10 y se paró** (corrida
  `1113-0216`, 0,90 USD de los 2 acordados; quedan 1,10). Hecha a mano
  sin modelo pasa lo que se puede medir; con DeepSeek el plan sale
  igual, pero el soporte se dibujó tumbado, como se imprime: el eje
  queda vertical (se pedía horizontal), la carga se queda en 134 g de
  300, y el eje del motor no asoma por delante, así que la polea del
  brazo no tiene correa posible. Al soporte no se le mide ninguna de
  las dos cosas. Además el eje del brazo entra justo en el rodamiento
  y cuenta como choque. **Por decidir con él** antes de gastar más:
  que el plan diga si un eje va horizontal o vertical, medir que el
  eje del motor asome, y qué hacer con el encaje en el rodamiento.
- **La web tardaba 30 s en abrir un proyecto del banco**: recorría las
  veinte corridas para pintar uno. Arreglado (2026-11-12): 0,7 a 5 s.
- **Docker se cayó** cuando el PC estuvo a punto de apagarse: se
  arregla cerrando Docker Desktop, `wsl --shutdown` y abriéndolo.
- **Pedido por él el 2026-11-12, para cuando acabe la Fase 10:**
  proponerle (sin escribirlas antes) tres fases: carcasas vistosas con
  superficies, el brazo de clase Arctos y el avión. La Fase 10 acaba
  en un brazo mediano funcional, no en uno que se vea como el Arctos.
- **Seis arreglos de ahí, aprobados por él el 2026-11-12:** el plan
  dice `eje` (horizontal o vertical) y se le mide a la pieza que lo
  monta; al soporte se le mide que el eje del motor asome; el
  rodamiento en el que gira una pieza no cuenta para los choques (un
  servo sí); lo que llega una pieza se mide en su malla; el sitio
  libre de un rodamiento empieza donde acaba; y al reanudar se rehace
  la pieza de abajo si es la que no vale.
- **Hecho: F10.4 (dimensionar)** (2026-11-12). El plan lleva la carga
  y lo que mide el brazo desde cada eje, y antes de dibujar se
  comprueba que cada motor puede con lo que cuelga de él. Lo impreso
  se estima en 0,2 g/mm: un supuesto.
- **Ritmo acordado con él el 2026-11-12** («es terrible la cantidad de
  tiempo que gastamos cada fase»): tests de lo que se toca mientras
  se desarrolla; la suite entera y los del host, una vez por tarea;
  la prueba a mano sin modelo en cada tarea; corrida de pago solo al
  final de cada etapa; y no esperar parado mientras corre.
- **Hecho: F10.5 (muestreo)** (2026-11-12). Con más de 8 000
  combinaciones de giros se barre una rejilla más gruesa (cada 45° con
  cinco giros: 3 125 poses de 2,5 millones) y se dice lo que no se
  probó. Una cadena de cinco giros a mano se barre en 6 s. Un choque
  que caiga entre dos puntos de esa rejilla se escapa.
- **Medido otra vez, el encargo 14 pasa 9 de 10** (corrida `1113-0423`,
  0,48 USD; 1,38 de los 2 del encargo). Solo falla el alcance: 149,1
  mm de 150. El plan reservó 150 de radio libre para un brazo de 150 y
  el brazo se quedó corto para no pasarse; nadie le mide que llegue.
  No se ha gastado en corregirlo.
- **Hechas las dos medidas del alcance, sin corrida:** el plan no puede
  reservar un radio que no deje sitio al brazo, y a la pieza de la
  punta se le mide que llega.
- **Hecho: F10.6 (módulo)** (2026-11-12, `orchestrator/modulos.py`).
  Un módulo impreso son varias piezas generadas por código más lo que
  hay que comprar; el backlog lo ve como un componente y la lista de
  materiales lo abre en lo que es. La biblioteca está vacía hasta la
  cicloidal.
- **Hecho, sin banco y sin imprimir: F10.7 (cicloidal)** (2026-11-12).
  El módulo `cicloidal-nema17-10` (y `-20`): carcasa con pernos,
  excéntrica, disco, plato de salida y tapa, generados por código. El
  perfil se compara con la fórmula publicada; construidas y giradas,
  las cinco piezas no se atraviesan (0,14 mm de holgura la de 10:1).
  Un hombro hecho a mano con ella pasa todo y levanta 866 g a 150 mm
  según el estudio. **Nada está impreso**: plástico contra plástico,
  holguras sin medir. El encargo 14b la pide y está sin correr.
- **Hecho: F10.8 (calibrar)** (2026-11-13). `intelliprint calibrar
  transmision` construye la cicloidal de prueba con cuatro discos y
  una polea. **Falta un dato suyo:** imprimirlas y apuntar en
  «Impresora» → «Holgura de las transmisiones» con cuál gira bien;
  hasta entonces las reductoras van con 0,15 mm y el plan lo avisa.
- **Preparado, sin correr: F10.9 (el brazo mediano)** (2026-11-13). El
  encargo 15 está escrito: cuatro ejes con NEMA 17 (base por correa,
  hombro con cicloidal 28:1, codo con 10:1, muñeca por correa), 350 mm
  y 300 g. A mano, los tres motores que levantan pueden con lo suyo
  (el hombro pide 2,4 N·m de 3,6). Son cinco piezas y cuatro giros:
  **el tope y la regla para parar están por acordar con él.** F9.11
  (borrador) no se ha hecho; el encargo usa lo que ya tiene ficha.
- **El encargo 14b, medido, pasa 8 de 9 a la primera** (corrida
  `1113-0605`, 0,34 USD de 1): el hombro con la cicloidal 10:1. Solo
  falla la carga, 212 g de 500, y por el vuelco: el soporte se
  atornilló a un tablero vertical y el estudio solo da por atornillada
  una base con los tornillos hacia abajo. El motor deja 875 g.
- **Decidido por él el 2026-11-13: fijada a un tablero vertical cuenta
  como atornillada** (cambia lo que mide el banco). Rejuzgado sin
  modelo, el 14b pasa 9 de 9 (875 g, lo limita el motor); el pan-tilt
  sigue en 7 de 7, el brazo en 8 de 8 y el encargo 14 en 9 de 10. No
  se mide que esos tornillos aguanten.
- **Acordado con él el 2026-11-13: el encargo 15 (el brazo mediano) se
  corre con 5 USD de tope**: una corrida y dos reanudaciones, y parar
  ahí aunque no pase.
- **El encargo 15, medido, se queda en 0 de 12 y se paró sola**
  (corrida `1113-1330`, 0,95 USD de los 5; sin reanudar). El plan
  salió bien y la base y la torreta también; el brazo superior no
  cumplió en cinco intentos y el antebrazo no pasó de los requisitos.
  Lo de fondo: el sitio de un giro se reserva como un círculo entero
  (`conjunto.radio_libre`), y con tramos largos da una torreta de
  430 mm (no cabe en la impresora, y nadie lo mide) y un codo que no
  puede tener 205 mm libres con el hombro a 150. Además el diseñador
  tumbó la pieza al centro de la cama en el último intento.
- **Arreglado de ahí:** las cifras que el sistema escribe en la
  petición de una pieza (el nombre de una ficha, lo que hace la
  vecina) ya no se le exigen como cotas (`traceability.CONTEXTO`).
- **Tres arreglos más, aprobados por él el 2026-11-13** («Sí, arregla
  y reanuda»): el sitio de un giro cuenta solo lo que queda por
  delante de la cara de salida; cada pieza mide que cabe en la
  impresora (y al reanudar se rehace la de abajo que no cabe); y el
  kit no deja girar ni mover un cuerpo que ya lleva agujeros. A mano,
  una torreta de 124 mm pasa. Rejuzgados, nada de lo que pasaba
  cambia. **Lo que se pierde:** que un brazo dé con la mesa no se
  mide.
- **Reanudado una vez con ellos, el encargo 15 sigue en 0 de 12**
  (0,14 USD más: 1,09 de los 5). La torreta se rehízo y ya cabe
  (103 × 76 × 105 mm, el hombro por fuera de la base). El brazo
  superior no pasó de los requisitos: el modelo citó como «del
  usuario» la instrucción del sistema, abreviada. Arreglado: ese
  requisito se quita (`spec.sin_lo_del_sistema`).
- **La segunda reanudación se paró a mano antes de juzgar** (1,01 USD
  más: 2,10 de los 5). Salió el brazo superior (46 × 100 × 250 mm);
  el antebrazo y la muñeca no, y en cada intento llevaban una orden
  imposible: colocar la reductora de dos piezas más abajo, que el kit
  no deja colocar. Arreglado: lo que monta una pieza a la que esta
  no se une no se le exige (`obra.ajenos`, `lejos`). Lo demás es del
  diseño: el antebrazo apoyaba en los dos aros del rodamiento.
- **Pedido por él el 2026-11-13:** si ya se sabe que una corrida va a
  fallar, no esperarla: pararla, arreglar y volver a correr. Va una
  tercera reanudación del encargo 15, dentro de los 5 USD.
- **Reanudado por tercera vez, el encargo 15 pasa 9 de 12** (0,06 USD
  más: 2,16 de los 5). El antebrazo salió a la primera corrección.
  Falla la muñeca: no se rehízo (revalidarla la dio por buena sin
  haber cumplido nunca) y está doblada hacia el codo, así que el
  brazo no se estira (288 mm de 350). Arreglado: al reanudar se
  corrige también la de encima que no salió, y a la pieza de la
  punta se le mide que pueda ponerse recta con el tramo anterior
  (**medida del asistente, él no la ha visto**; no cambia lo que
  juzga el banco).
- **Reanudado por cuarta vez, con su visto bueno, pasa 10 de 12**
  (`banco_reanudado-3.md`; 0,20 USD más: 2,36 de los 5). La muñeca
  salió al quinto intento y el brazo se mueve sin chocar. Quedan
  dos. El alcance, 340 mm de 350: el banco mide hasta los tornillos
  de la herramienta, que están a 70 mm del eje de la muñeca, y a la
  pieza se le medía la punta del plástico. Arreglado, sin correr: se
  le mide donde va la carga, y al reanudar se busca la pieza que no
  llega. Y la muñeca no se lamina como se dibuja (apoya en el canto
  de la polea): **por decidir con él** quién elige la postura al
  laminar, porque cambia lo que mide el banco.
- **Cada reanudación de pago necesita su «sí»**: el sistema de
  permisos bloqueó lanzar una apoyándose en un visto bueno anterior.
- **Reanudado por quinta vez, con su visto bueno, pasa 11 de 12**
  (`banco_reanudado-4.md`; 0,02 USD más: 2,38 de los 5). La punta
  llega a 350,0 mm y levanta 378 g; no falla nada. Queda sin medir
  «sin soportes» en la muñeca, que no se lamina como se dibuja.
  Tumbada, a mano, sí se lamina, con aviso de puentes largos.
- **«Sin soportes» no medía lo que decía** (visto el 2026-11-13): se
  apuntaba el ajuste `support_material` del perfil, que vale 0, y
  toda pieza que se laminaba salía «sin soportes», desde F1.12.
  **Decidido por él ese día:** lo dice el aviso de PrusaSlicer, y el
  juez prueba la pieza como se dibuja y apoyada en cada una de sus
  otras caras. Rejuzgado sin modelo: los diez encargos de pieza
  bajan a 51 de 52 (el soporte del HC-SR04) y el brazo mediano
  sigue en 11 de 12, ahora con un «no cumple»: la base y la muñeca
  piden soportes en todas las posturas. Lo demás no cambia.
- **El puente de PrusaSlicer hay que reiniciarlo** cuando cambia
  `scripts/host_bridge.py`: parar el `python -m scripts.host_bridge`
  y volver a lanzar `scripts\start-host-mcps.ps1`.
- **Abierto de la Fase 10:** las tres piezas que piden soportes (la
  base y la muñeca del brazo mediano y el soporte del HC-SR04;
  corregirlas es gasto, por acordar), la medida de la punta recta
  que él no ha visto, la pinza aparcada y su dato de la holgura de
  las transmisiones. Las tres fases se le propusieron y las aprobó.

**2026-11-10: Fase 9, robots con plan mecánico (ADR-020).** El usuario quiere
diseñar robots: que el desglose decida antes de dibujar qué gira sobre qué y con
cuánto sitio, qué va atornillado y con qué, y poder añadir funciones a un
invento. El plan aprobado está en `PLAN_PROYECTO.md`, Fase 9, con su orden.

- **El pan-tilt pasa sus cinco comprobaciones** (2026-11-11, corrida
  `1111-1342`, a la primera, 45 min y 0,53 USD). El de `1110-0313` chocaba
  porque el soporte dejaba 12.7 mm entre el eje de inclinación y el servo de
  abajo; ahora el plan reserva el sitio de cada giro y cada pieza lo mide en su
  propio bucle (F9.1 a F9.5). **Es una sola corrida**, y su plataforma es un
  disco coaxial con el eje, que no inclina nada: el banco lo ve desde
  F9.14 (orienta), que pide que quepa una cámara de 25 × 24 en una cara que
  mire de lado respecto al eje. Con esa exigencia y tres reanudaciones (la
  tercera, aprobada aparte por el usuario) **pasa 6 de 6**: 0,93 USD en
  total. Es un solo backlog, una sola corrida y tres correcciones dadas por
  el banco; no dice que acierte a la primera.
- **Con la tornillería contada, ese mismo pan-tilt pasa 7 de 7**, tras
  dos reanudaciones más. Al empezar a contarla quedaba en 6 de 7
  (2026-11-11, F9.6 a F9.8, rejuzgado sin modelo): de los cuatro tornillos
  de sus dos SG90 no agarra ninguno. La base no taladró nada bajo las orejas
  y el soporte taladró Ø2.2 para tornillos de 2. Ahora el plan los prevé (los
  de lo comprado salen de su ficha), cada pieza los cuenta en su bucle y el
  banco los pide. **Reanudado una vez, con su visto bueno** (47 min,
  0,53 USD; 1,46 la corrida entera): ahora los cuatro agarran, pero **sigue
  en 6 de 7**. Corregir la base rehízo el soporte y la plataforma de cero, y
  en la plataforma nueva (30 × 28.5) ya no cabe la cámara de 25 × 24; la
  buena, de 32 × 27, quedó archivada. **Reanudado otra vez, con su visto
  bueno** (15 min, 0,18 USD; 1,64 la corrida entera): la plataforma se
  rehízo desde su concepto, sin el rebaje que partía la cara, y **pasa
  7 de 7** (`banco_reanudado-5.md`). Es un solo backlog y una sola corrida,
  con cinco reanudaciones dadas por el banco; no dice que acierte a la
  primera. Cada reanudación se acuerda antes. **Falta un dato
  suyo:** el agujero de un M2 de rosca, que se apunta en «Impresora» →
  «Apuntar otro tornillo»; el Ø1.7 de ahora lo eligió el diseñador.
- **Corregir una pieza ya no tira lo de encima: lo revalida**
  (F9.9 (revalidar), 2026-11-11, `orchestrator/revalidar.py`). Lo construido
  contra la pieza corregida se queda «por revalidar» y se comprueba sin
  modelo contra la ficha nueva; solo se corrige lo que deja de valer.
  Repetida sin modelo la corrección de la base (en una copia, con el soporte
  y la plataforma del archivo), los dos siguen valiendo y la cámara cabe.
  **Con modelo no se ha ejercitado**: la reanudación que dejó el pan-tilt
  en 7 de 7 corrigió la plataforma, que no tiene piezas encima.
- **A dónde quiere llegar** (2026-11-11): a diseñar brazos como Arctos
  (6 ejes, NEMA 17 y 23, reductoras y correas) y aeronaves como las de
  Flightory (ala fija y VTOL en LW-PLA). El brazo es la Fase 10 (arriba),
  que llega hasta uno mediano; el de clase Arctos y el avión no tienen fase.
  Para el avión faltan superficies y que el laminado sea parte del diseño.
- **Los backlogs están desaparcados**, con la regla de siempre: no relanzar
  corridas enteras para probar un arreglo (`banco --reanudar`).
- **El flujo `mecanismo` ya no existe** (F9.13 (limpieza), 2026-11-11): lo
  decidió él para cuando el pan-tilt subiera. Con él se fueron `new`/`resume`
  (LangGraph), el bot propio y el QA de interfaces, que no llamaba nadie.
  Todo está en git, en la etiqueta `antes-de-fase-9`. Los mecanismos ya hechos
  se siguen viendo en la web. **Lo que se perdió:** engranajes y cadenas
  cerradas; un backlog solo sabe piezas que giran sobre un servo o un
  rodamiento, en árbol.
- **El tope de gasto ahora sí para: 3 USD una pieza y 50 USD un backlog**
  (un robot), decididos por él el 2026-11-11; eran 5 para todo. Solo lo
  comprobaba el flujo de
  mecanismos; una pieza o un backlog nunca se detenían. Cada paso lo mira
  antes de empezar (`cli._apuntar_gasto`).
- **El banco se corre con el código de hoy desde el servicio `suite`**, que lo
  monta en vivo; `orchestrator` y `web` llevan el de su imagen hasta
  reconstruirla (`docker compose build`):
  `docker compose run --rm --entrypoint python3 suite -m orchestrator.cli banco --solo pan_tilt_sg90`
  (en Git Bash, con `MSYS_NO_PATHCONV=1` si se pasa una ruta `/workspace/...`).
  El puente de PrusaSlicer tiene que estar arriba o «sin soportes» sale sin medir.
- **Decidido por él:** el agarre de cada tornillo lo propone el plan en cada
  unión; un componente sin ficha entra como borrador que él aprueba viendo la
  huella; `AGENTS.md` se borra.

**2026-09-20: el sistema se mudó a la PC de la RTX 5090 y entró en contenedores.**

- **FreeCAD dentro, PrusaSlicer fuera** (ADR-014). FreeCAD es una herramienta
  interna —construye y calla—; PrusaSlicer es donde la persona mira qué va a
  imprimir, así que sigue siendo el suyo y el contenedor se lo pide por un
  puente MCP en el host (`scripts/host_bridge.py`).
- **La interfaz web** (F5.5 (web), parcial): lista de proyectos, descarga en zip
  y un botón que abre PrusaSlicer con las piezas y el perfil cargados.
- **El canal de Telegram va ABIERTO, por decisión del usuario** (ADR-012). La
  lista blanca de F5.10 (lista) existe pero es opcional: se había hecho
  obligatoria sin que él lo aprobara, y la quitó.
- **Crafty vive en su contenedor**, con la configuración generada desde el `.env`
  y ningún secreto en `openclaw.json`.

### Lo que quedó pendiente

0. ✅ **Los modelos de DeepSeek funcionan** (comprobado llamándolos el
   2026-10-23). `deepseek-chat` y `deepseek-reasoner` son alias que DeepSeek
   sirve con `deepseek-flash` (sin y con pensamiento), y ya se cobran como
   Flash: está explicado en `config/models.yaml`, junto a los precios.
1. ~~El trinquete, la Ginebra y los demás retos de mecanismos.~~ El flujo
   que los hacía se quitó el 2026-11-11 (arriba). El trinquete salió
   (2026-09-21, 1.17 USD) y sigue en `workspace/`.
3. ~~Decidir el tope de gasto.~~ **Decidido por el usuario: 3 USD una pieza y
   50 USD un backlog** desde el 2026-11-11 (`max_usd_per_project` y
   `max_usd_per_backlog`); antes, 5 USD para todo
   (2026-09-21). Los 2 USD anteriores los había puesto el asistente por defecto.
5. **F0.11 (migrar) es la deuda mayor que queda.** La 5090 está aquí, Ollama
   corre con ella y los dos modelos del perfil `prod` están descargados
   (`qwen3.8` y `gemma3:12b`, comprobado al 100% en GPU). Falta el cliente de
   Ollama y revalidar la suite con modelos locales.

   **Y algo que hay que decidir antes:** el contenedor `ollama` de esta máquina
   no es del compose de Intelliprint —es uno anterior, de otro proyecto— y trae
   `OLLAMA_MAX_LOADED_MODELS=1`. Con ese valor los dos modelos NO conviven:
   cargar el del QA descarga el de diseño, y cada turno que alterne paga una
   recarga de 17 GB. § 6.1 pide dos residentes. Caben (17 + 8.9 GB en 32), pero
   subirlo a 2 obliga a recrear ese contenedor, que es de otro proyecto. Las dos
   salidas: cambiarlo allí, o levantar el servicio `ollama` del compose
   (`docker compose --profile ollama up -d ollama`), que ya lo trae en 2 a costa
   de una segunda copia de los modelos.
6. **Los botones de gate** de la interfaz web, que es lo que cierra F5.5 (web).
7. **Kits para montar** (Fase 8, ADR-019): el usuario diseña kits de
   robótica infantil, **los imprime en sus impresoras** y el cliente los
   monta; la programación va después. La impresora la configura y calibra
   él. Se empieza por F8.1 (cliente): las preguntas abiertas de la ADR las
   decide el usuario, no el asistente. Requiere antes el pan-tilt de
   F7.3 (arbol) hecho con DeepSeek.

Cada proyecto deja su coste desglosado en `design_cost.md`, y si se detiene sin
resolver, un parte en `blocked.md` con la imagen de la pose donde falla.
