# Orquestador de Intelliprint: Python y FreeCAD en la misma imagen
# (F0.2 (docker)).
#
# FREECAD DENTRO, PRUSASLICER FUERA. No es la misma decisión dos veces.
#
# FreeCAD es una HERRAMIENTA INTERNA: construye y calla. En producción no
# hay una sola llamada a FreeCADGui —`build.py`, `assembly.py` y
# `animation.py` lanzan `freecadcmd`, que es headless—, así que cabe dentro,
# y meterlo aquí es lo que de verdad hace el sistema reproducible.
#
# PrusaSlicer NO es interno: es donde la persona comprueba QUÉ va a imprimir
# y CÓMO antes de mandarlo a la máquina. Eso tiene que pasar en SU
# PrusaSlicer, con su versión y sus ajustes, no en una copia distinta
# escondida dentro de una imagen. Se queda en el PC, y el contenedor se lo
# pide por el puente (scripts/host_bridge.py, F0.4 (proxy)).
#
# Lo que la persona abre con el FreeCAD del escritorio —ADR-004— sigue
# igual: los .FCStd quedan en `workspace/`, que se monta desde el host.

FROM debian:trixie-slim

# procps (`ps`) no es opcional: el registro decide si un proyecto sigue en
# marcha mirando el proceso, y sin `ps` se caen tres tests.
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv \
        git ca-certificates curl procps \
        libgl1 libglu1-mesa libxrender1 libxcursor1 libxinerama1 libxi6 \
        libxkbcommon0 libfontconfig1 libdbus-1-3 libegl1 \
    && rm -rf /var/lib/apt/lists/*

# FreeCAD 1.1.3, la MISMA versión que el escritorio. Debian empaqueta la
# 1.0.0, y el código se escribió y se probó contra la 1.1: bajar de versión
# aquí introduciría una diferencia entre lo que construye el sistema y lo
# que abre la persona, justo lo que este contenedor viene a evitar.
#
# `--appimage-extract` desempaqueta sin FUSE, que en un contenedor no hay.
ARG FREECAD_URL=https://github.com/FreeCAD/FreeCAD/releases/download/1.1.3/FreeCAD_1.1.3-Linux-x86_64-py311.AppImage
RUN curl -fsSL -o /tmp/freecad.AppImage "$FREECAD_URL" \
    && chmod +x /tmp/freecad.AppImage \
    && cd /opt && /tmp/freecad.AppImage --appimage-extract > /dev/null \
    && mv squashfs-root freecad \
    && rm /tmp/freecad.AppImage

ENV FREECADCMD=/opt/freecad/usr/bin/freecadcmd

# No hay servidor X aquí: que nada intente abrir una ventana.
ENV QT_QPA_PLATFORM=offscreen

WORKDIR /app

# Las dependencias primero y el código después: cambiar una línea de Python
# no debe reinstalar medio PyPI.
COPY pyproject.toml /app/
COPY orchestrator /app/orchestrator
COPY mcp /app/mcp
RUN pip install --no-cache-dir --break-system-packages -e ".[dev,render,web]"

COPY config /app/config
COPY library /app/library
COPY scripts /app/scripts
COPY tests /app/tests
COPY PLAN_PROYECTO.md DECISIONES.md SISTEMA_MULTIAGENTE.md CLAUDE.md README.md /app/

# El trabajo de la persona vive fuera de la imagen, montado desde el host.
ENV INTELLIPRINT_WORKSPACE=/workspace
VOLUME ["/workspace"]

ENTRYPOINT ["python3", "-m", "orchestrator.cli"]
