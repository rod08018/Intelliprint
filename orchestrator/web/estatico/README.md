# Archivos estáticos de la web

Servidos tal cual por `/estatico/<nombre>` (`orchestrator/web/app.py`). Solo
los que estén en `ESTATICOS`: el resto da 404.

| Archivo | Qué es | De dónde |
|---|---|---|
| `three.module.min.js` | three.js r170, el visor 3D del ensamble (F7.9 (visor)) | `https://cdn.jsdelivr.net/npm/three@0.170.0/build/three.module.min.js` |
| `OrbitControls.js` | Girar, acercar y desplazar con el ratón o el dedo | `https://cdn.jsdelivr.net/npm/three@0.170.0/examples/jsm/controls/OrbitControls.js` |
| `LICENSE` | La licencia MIT de three.js | el mismo paquete |

Se guardan en el repo, no se piden a un CDN: la web corre en la red de casa
y tiene que funcionar sin internet. Para actualizarlos, se bajan los tres
de la misma versión y se cambia aquí el número.
