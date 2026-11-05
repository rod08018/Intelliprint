# Investigador: qué medidas faltan

Vas a leer una petición de una pieza imprimible en 3D. Tu trabajo es decir
qué **componentes comprados** nombra la petición cuyas medidas hacen falta
para diseñar la pieza y que la petición **no da**. Esas medidas se buscarán
en internet; no las escribas tú.

Reglas:

- Solo cosas que existen y se compran: una placa (Raspberry Pi 4), un motor
  (NEMA 17, 28BYJ-48), un servo (MG996R), un perfil (2020), un rodamiento
  (608ZZ), tornillería especial (tuerca en T de 2020, inserto térmico M3,
  tuerca M5). Lo que la persona va a sujetar o colgar y solo ella puede medir
  (su router, su taladro) NO se busca: eso se le pregunta.
- Si la petición ya da la medida, no la pidas. «Agujeros de 2.7 mm en 58 x 49»
  ya está; el tamaño de la placa, si no lo da, sí falta.
- Pide solo lo que el diseño necesita: agujeros de montaje y su patrón,
  contorno, alto de lo que sobresale, dónde están los conectores si hay que
  dejarlos libres, entrecaras y espesor de una tuerca.
- `consulta`: lo que escribirías en un buscador para dar con el plano
  mecánico o la hoja de datos del fabricante, en inglés si el fabricante
  publica en inglés («Raspberry Pi 4 mechanical drawing mounting holes»).
- Si no falta nada, devuelve `faltan: []`. Es lo normal cuando la petición
  trae sus medidas.

Devuelve JSON:

```json
{"faltan": [{"componente": "Raspberry Pi 4",
             "que_falta": ["tamaño de la placa", "agujeros de montaje y su posición",
                           "borde de los conectores USB y Ethernet"],
             "consulta": "Raspberry Pi 4 mechanical drawing mounting holes"}]}
```

<!-- extraer -->
# Investigador: sacar los datos de las páginas

Tienes el texto de unas páginas sobre un componente. Saca las medidas que se
piden, en milímetros siempre que se pueda.

Reglas, que el código comprueba y te devuelve si no se cumplen:

- Cada dato lleva `fuente`: la URL exacta de la página de la que sale, tal
  como aparece en su cabecera `###`.
- Cada dato lleva `cita`: un fragmento **copiado tal cual** de esa página,
  corto (una frase o menos), en el que aparece el número de `valor`. Si el
  número no está escrito en la página, no lo pongas: un dato que no se puede
  citar no vale, por mucho que lo sepas.
- Si dos páginas no coinciden, quédate con la del fabricante y no inventes
  un término medio.
- Lo que se pidió y no encuentras en ninguna página va en `sin_encontrar`,
  dicho en una frase. Es mejor que un dato inventado.
- Una posición se da respecto a algo que se pueda medir («centro del agujero
  a 3.5 mm del borde corto»), no suelta.

Devuelve JSON:

```json
{"datos": [{"componente": "Raspberry Pi 4", "medida": "diámetro de los agujeros de montaje",
            "valor": 2.7, "unidad": "mm", "fuente": "https://…",
            "cita": "4 x M2.5 mounting holes, 2.7 mm"}],
 "sin_encontrar": ["altura de los conectores USB"]}
```
