# Simulación de vuelo del avión: ROS 2, Gazebo y PX4 en una imagen
# (F13.6 (simulación)).
#
# POR QUÉ ESTA PILA Y NO OTRA. Pedido por él el 2026-11-16: URDF, ROS 2,
# Gazebo y PX4. Las versiones van juntas porque así las prueba PX4:
#   - ROS 2 Jazzy (LTS, Ubuntu 24.04) y Gazebo Harmonic, que es su pareja;
#   - PX4 v1.17.0, que trae el puente con Gazebo Harmonic (`gz_bridge`) y
#     un VTOL de ala volante de referencia (`standard_vtol`) del que sale
#     el cableado de nuestro modelo;
#   - el agente Micro XRCE-DDS y `px4_msgs` de la rama 1.17, que son lo que
#     une PX4 con ROS 2 (los temas de PX4 se ven como temas de ROS 2).
#
# Lo nuestro (el modelo, la aeronave de PX4 y las pruebas de vuelo) NO va
# en la imagen: se monta desde `sim/`. Así cambiar el avión no obliga a
# reconstruir una imagen que tarda media hora.

FROM ros:jazzy-ros-base

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

RUN apt-get update && apt-get install -y --no-install-recommends \
        sudo git wget curl ca-certificates lsb-release gnupg \
        python3-pip python3-venv \
        ros-jazzy-robot-state-publisher ros-jazzy-xacro ros-jazzy-rviz2 \
        liburdfdom-tools \
    && rm -rf /var/lib/apt/lists/*

# PX4 con sus submódulos (entre ellos los modelos de Gazebo). Su propio
# guion instala Gazebo Harmonic y lo que pide compilar el SITL; sin NuttX,
# que es para la controladora de verdad.
ARG PX4_VERSION=v1.17.0
RUN git clone --depth 1 --branch ${PX4_VERSION} --recurse-submodules \
        --shallow-submodules https://github.com/PX4/PX4-Autopilot.git /opt/PX4-Autopilot
WORKDIR /opt/PX4-Autopilot
# El numpy de Debian se queda: ROS 2 está compilado contra él. Sin esta
# atadura, pip quería subirlo a la 2.x para pandas y no podía desinstalar el
# de Debian («RECORD file not found»): la primera construcción murió ahí.
RUN echo "numpy==1.26.4" > /opt/pip-restricciones.txt
ENV PIP_CONSTRAINT=/opt/pip-restricciones.txt
RUN bash Tools/setup/ubuntu.sh --no-nuttx && rm -rf /var/lib/apt/lists/*
RUN make px4_sitl && rm -rf build/px4_sitl_default/external

# El agente que pone los temas de PX4 en ROS 2.
RUN git clone --depth 1 --branch v2.4.3 \
        https://github.com/eProsima/Micro-XRCE-DDS-Agent.git /opt/xrce-agent \
    && cmake -S /opt/xrce-agent -B /opt/xrce-agent/build \
    && cmake --build /opt/xrce-agent/build -j"$(nproc)" \
    && cmake --install /opt/xrce-agent/build && ldconfig

# Los mensajes de PX4 compilados para ROS 2.
RUN mkdir -p /opt/ros_ws/src \
    && git clone --depth 1 --branch release/1.17 \
        https://github.com/PX4/px4_msgs.git /opt/ros_ws/src/px4_msgs \
    && . /opt/ros/jazzy/setup.sh \
    && cd /opt/ros_ws && colcon build --symlink-install

# Las pruebas de vuelo hablan MAVLink con PX4; pyulog lee su registro (por
# qué abortó una transición, qué pidió a cada motor).
RUN pip3 install --break-system-packages pymavlink pytest pyulog

# Gazebo en el navegador (pedido por él el 2026-11-16: «quiero poder en mi
# buscador acceder a gazebo y ver la simulación»). Una pantalla virtual
# (Xvfb) con la ventana de Gazebo, servida por VNC y noVNC: se ve la
# interfaz de Gazebo entera en http://localhost:6080, sin instalar nada en
# Windows y sin que la escena salga del PC. Mesa dibuja sin tarjeta gráfica.
RUN apt-get update && apt-get install -y --no-install-recommends \
        xvfb x11vnc novnc websockify openbox libgl1-mesa-dri mesa-utils \
    && rm -rf /var/lib/apt/lists/*

# Lo nuestro, montado desde el repositorio.
ENV PX4_DIR=/opt/PX4-Autopilot \
    INTELLIPRINT_SIM=/sim
COPY docker/sim-entrypoint.sh /usr/local/bin/sim-entrypoint.sh
RUN chmod +x /usr/local/bin/sim-entrypoint.sh
ENTRYPOINT ["/usr/local/bin/sim-entrypoint.sh"]
CMD ["bash"]
