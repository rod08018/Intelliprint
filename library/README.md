# library — lo que se compra

Ningún modelo debe sacar de memoria las medidas de un servo. Lo comprado vive aquí. Ver [SISTEMA_MULTIAGENTE.md](../SISTEMA_MULTIAGENTE.md) § 10 y ADR-016.

```
library/
├── components/         una ficha YAML por componente
└── models/reference/   modelos STEP descargados de terceros, con autor y licencia
```

## `components/`: las fichas

Hay siete: `608zz`, `hc-sr04`, `mg996r`, `nema17`, `perfil-2020`, `raspberry-pi-4` y `sg90`. Las lee `orchestrator/componentes.py`.

Una ficha es geometría con fuente, no una lista de cotas:

| Campo | Qué dice |
|---|---|
| `id`, `nombre`, `alias` | Cómo se llama. Por los alias decide el código si una petición lo nombra |
| `fuentes` | La URL y la cita de cada hoja de datos o plano |
| `marco`, `mira` | Dónde está el origen y hacia dónde apunta |
| `cuerpos` | Lo que es sólido: cajas y cilindros, cada uno con su porqué |
| `despejar` | Lo que hay que dejar libre: un cable, el haz de un sensor, el cuerno de un servo |
| `fijacion` | Dónde se atornilla, con qué tornillo y si viene con el componente |
| `salidas` | Lo que mueve: el eje de un servo o el aro de un rodamiento, con su recorrido. Hoy solo las tienen `sg90` y `608zz` |
| `masa_g`, `par_kgf_cm`, `velocidad_s_60` | Para el estudio de movimientos |
| `verificado` | `true` solo si alguien lo midió con calibre |

**Ninguna ficha está medida con calibre**: las siete llevan `verificado: false`. Si dos fabricantes no coinciden, la ficha toma lo mayor y lo dice.

Un componente que no tiene ficha no se puede colocar con `kit.componente`: el diseño sigue con las cifras sueltas que se encuentren en internet. Las fichas se escriben a mano; el borrador de ficha que el usuario aprueba es F9.11 (borrador), pendiente.

## `models/reference/`: referencias independientes

Los modelos de referencia **no los dibuja el sistema**: se descargan de fuentes reconocibles, con autor, licencia y huella SHA-256 (ver `models/reference/README.md`). Si el sistema dibujara también la referencia con sus propios números, que la pieza encajara no demostraría nada. Los usan los tests; el diseño trabaja con las fichas.

Esto ya encontró dos cosas que un modelo propio habría ocultado:
- NEMA 17 normaliza **solo la cara de montaje**. La altura del saliente (1.6 en la referencia, 2.0 en la que se había supuesto) y el largo del eje (20 frente a 24) cambian según el fabricante.
- Al medir se confundía un agujero con un saliente concéntrico mayor, porque las esquinas redondeadas del motor son cilindros en el mismo eje. Arreglado: el extractor distingue caras interiores y exteriores.
