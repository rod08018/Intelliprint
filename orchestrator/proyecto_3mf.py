"""Un proyecto .3mf de PrusaSlicer con los ajustes de cada pieza
(F3.16 (usos)).

Abrir las STL sueltas con un perfil aplica el mismo laminado a todas: el
gatillo que aguanta un resorte saldría como la tapa. PrusaSlicer guarda en
sus proyectos los ajustes POR PIEZA (`Metadata/Slic3r_PE_model.config`), y
aquí se escribe ese mismo formato: el proyecto se abre con cada pieza ya
configurada y la configuración base dentro.

Que PrusaSlicer lo lee de verdad lo comprueba un test en el host: laminar
el .3mf da los gramos de laminar cada pieza por separado con sus ajustes.
"""

import re
import struct
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import quoteattr

HUECO_MM = 10.0
"""Entre piezas al colocarlas en fila: PrusaSlicer las puede reordenar, pero
abrirlas una dentro de otra confunde."""


@dataclass
class Pieza:
    nombre: str
    stl: Path
    ajustes: dict[str, str] = field(default_factory=dict)


def leer_stl(ruta: Path) -> tuple[list[tuple[float, float, float]], list[tuple[int, int, int]]]:
    """Vértices (sin repetir) y triángulos de un STL binario o de texto."""
    datos = Path(ruta).read_bytes()
    if len(datos) >= 84 and len(datos) == 84 + 50 * struct.unpack_from("<I", datos, 80)[0]:
        n = struct.unpack_from("<I", datos, 80)[0]
        puntos = [struct.unpack_from("<3f", datos, 84 + 50 * i + 12 + 12 * j)
                  for i in range(n) for j in range(3)]
    else:
        texto = datos.decode("utf-8", errors="ignore")
        puntos = [tuple(map(float, m)) for m in
                  re.findall(r"vertex\s+(\S+)\s+(\S+)\s+(\S+)", texto)]
    indice: dict[tuple, int] = {}
    vertices, triangulos = [], []
    for i in range(0, len(puntos), 3):
        tri = []
        for p in puntos[i:i + 3]:
            clave = tuple(round(c, 6) for c in p)
            if clave not in indice:
                indice[clave] = len(vertices)
                vertices.append(clave)
            tri.append(indice[clave])
        triangulos.append(tuple(tri))
    return vertices, triangulos


def _cama(config: dict[str, str]) -> tuple[float, float]:
    puntos = [tuple(map(float, p.split("x"))) for p in config.get("bed_shape", "0x0,200x200").split(",")]
    return max(x for x, _ in puntos), max(y for _, y in puntos)


def _leer_ini(ruta: Path) -> dict[str, str]:
    config = {}
    for linea in Path(ruta).read_text(encoding="utf-8").splitlines():
        if " = " in linea and not linea.startswith(("#", ";")):
            clave, valor = linea.split(" = ", 1)
            config[clave.strip()] = valor
    return config


def escribir_3mf(piezas: list[Pieza], perfil: Path, destino: Path) -> Path:
    config = _leer_ini(perfil)
    mallas = [leer_stl(p.stl) for p in piezas]
    vacias = [p.nombre for p, (_, triangulos) in zip(piezas, mallas) if not triangulos]
    if vacias:
        raise ValueError(f"piezas sin un solo triángulo: {vacias}")

    # En fila a lo largo de X, centradas en la cama y apoyadas en z = 0.
    cajas = []
    for vertices, _ in mallas:
        xs, ys, zs = zip(*vertices)
        cajas.append((min(xs), max(xs), min(ys), max(ys), min(zs)))
    ancho = sum(c[1] - c[0] for c in cajas) + HUECO_MM * (len(cajas) - 1)
    cama_x, cama_y = _cama(config)
    cursor = (cama_x - ancho) / 2

    objetos, items, metadatos = [], [], []
    for i, (pieza, (vertices, triangulos), caja) in enumerate(zip(piezas, mallas, cajas), 1):
        x0, x1, y0, y1, z0 = caja
        tx, ty, tz = cursor - x0, cama_y / 2 - (y0 + y1) / 2, -z0
        cursor += (x1 - x0) + HUECO_MM
        objetos.append(
            f' <object id="{i}" type="model"><mesh><vertices>'
            + "".join(f'<vertex x="{x:g}" y="{y:g}" z="{z:g}"/>' for x, y, z in vertices)
            + "</vertices><triangles>"
            + "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in triangulos)
            + "</triangles></mesh></object>\n")
        items.append(f'  <item objectid="{i}" transform="1 0 0 0 1 0 0 0 1 {tx:g} {ty:g} {tz:g}" printable="1"/>\n')
        ajustes = "".join(f'  <metadata type="object" key={quoteattr(k)} value={quoteattr(v)}/>\n'
                          for k, v in pieza.ajustes.items())
        metadatos.append(
            f' <object id="{i}" instances_count="1">\n'
            f'  <metadata type="object" key="name" value={quoteattr(pieza.nombre)}/>\n{ajustes}'
            f'  <volume firstid="0" lastid="{len(triangulos) - 1}">\n'
            f'   <metadata type="volume" key="name" value={quoteattr(pieza.nombre)}/>\n'
            f'   <metadata type="volume" key="volume_type" value="ModelPart"/>\n'
            f'  </volume>\n </object>\n')

    modelo = ('<?xml version="1.0" encoding="UTF-8"?>\n'
              '<model unit="millimeter" xml:lang="en-US" '
              'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
              'xmlns:slic3rpe="http://schemas.slic3r.org/3mf/2017/06">\n'
              ' <metadata name="slic3rpe:Version3mf">1</metadata>\n'
              ' <resources>\n' + "".join(objetos) + ' </resources>\n'
              ' <build>\n' + "".join(items) + ' </build>\n</model>\n')
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0" encoding="UTF-8"?>\n<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
        z.writestr("_rels/.rels",
                   '<?xml version="1.0" encoding="UTF-8"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Target="/3D/3dmodel.model" Id="rel-1" '
                   'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
        z.writestr("3D/3dmodel.model", modelo)
        # La configuración base, en el formato de los comentarios del G-code,
        # que es como PrusaSlicer la guarda en sus proyectos.
        z.writestr("Metadata/Slic3r_PE.config",
                   "".join(f"; {k} = {v}\n" for k, v in sorted(config.items())))
        z.writestr("Metadata/Slic3r_PE_model.config",
                   '<?xml version="1.0" encoding="UTF-8"?>\n<config>\n' + "".join(metadatos) + "</config>\n")
    return destino
