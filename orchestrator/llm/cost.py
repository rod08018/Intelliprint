"""Presupuesto de un proyecto (F5.12 (tope)).

El sistema no se rinde tras un número fijo de rondas: itera hasta que el
mecanismo funciona. Lo que puede detenerlo es el dinero, y ese tope lo
pone el usuario, no el código.

Los precios son aproximados y solo sirven para este tope: cambian con el
proveedor, así que viven en `config/models.yaml` y no en el código.
"""


class PresupuestoAgotado(RuntimeError):
    pass


class Presupuesto:
    def __init__(self, limite_usd: float, precios: dict[str, dict[str, float]]) -> None:
        self.limite_usd = limite_usd
        self._precios = precios
        self._clientes: list = []
        self._vistos: dict[int, int] = {}
        self._etapa = "inicio"
        self._detalle: list[dict] = []

    @classmethod
    def from_config(cls, config: dict) -> "Presupuesto":
        return cls(
            float(config.get("escalation", {}).get("max_usd_per_project", 2.0)),
            config.get("pricing", {}),
        )

    def vigila(self, cliente, agente: str = "") -> None:
        self._clientes.append((cliente, agente or getattr(cliente, "modelo", "?")))

    def etapa(self, nombre: str) -> None:
        """En qué anda el proyecto ahora. Lo que se gaste a partir de aquí se
        apunta con esta etiqueta."""
        self._recoger()
        self._etapa = nombre

    def _usd(self, modelo: str, entrada: int, salida: int) -> float | None:
        precio = self._precios.get(modelo)
        if precio is None:
            return None
        return entrada * precio["in_usd_per_mtok"] / 1e6 + salida * precio["out_usd_per_mtok"] / 1e6

    def _recoger(self) -> None:
        """Apunta las llamadas nuevas de cada cliente con la etapa actual."""
        for cliente, agente in self._clientes:
            llamadas = getattr(cliente, "llamadas", [])
            desde = self._vistos.get(id(cliente), 0)
            for llamada in llamadas[desde:]:
                usd = self._usd(llamada["modelo"], llamada["entrada"], llamada["salida"])
                self._detalle.append({
                    "agente": agente,
                    "modelo": llamada["modelo"],
                    "etapa": self._etapa,
                    "tokens_entrada": llamada["entrada"],
                    "tokens_salida": llamada["salida"],
                    "usd": usd if usd is not None else 0.0,
                    "con_precio": usd is not None,
                })
            self._vistos[id(cliente)] = len(llamadas)

    def detalle(self) -> list[dict]:
        self._recoger()
        return list(self._detalle)

    def resumen(self) -> dict:
        detalle = self.detalle()
        def agrupa(clave):
            salida: dict[str, dict] = {}
            for d in detalle:
                fila = salida.setdefault(d[clave], {"llamadas": 0, "tokens_entrada": 0,
                                                    "tokens_salida": 0, "usd": 0.0})
                fila["llamadas"] += 1
                fila["tokens_entrada"] += d["tokens_entrada"]
                fila["tokens_salida"] += d["tokens_salida"]
                fila["usd"] += d["usd"]
            return salida
        return {
            "total_usd": sum(d["usd"] for d in detalle),
            "limite_usd": self.limite_usd,
            "llamadas": len(detalle),
            "tokens_entrada": sum(d["tokens_entrada"] for d in detalle),
            "tokens_salida": sum(d["tokens_salida"] for d in detalle),
            "sin_precio": sorted({d["modelo"] for d in detalle if not d["con_precio"]}),
            "por_agente": agrupa("agente"),
            "por_modelo": agrupa("modelo"),
            "por_etapa": agrupa("etapa"),
        }

    def escribir(self, carpeta) -> None:
        """Guarda el coste en la carpeta del proyecto: datos y legible."""
        import json
        from pathlib import Path

        carpeta = Path(carpeta)
        carpeta.mkdir(parents=True, exist_ok=True)
        detalle, resumen = self.detalle(), self.resumen()
        (carpeta / "design_cost.json").write_text(
            json.dumps({"resumen": resumen, "detalle": detalle}, indent=2, ensure_ascii=False),
            encoding="utf-8")

        def tabla(titulo, datos, columna):
            filas = [f"| {columna} | Llamadas | Tokens entrada | Tokens salida | USD |",
                     "|---|---:|---:|---:|---:|"]
            for nombre, f in sorted(datos.items(), key=lambda x: -x[1]["usd"]):
                filas.append(f"| {nombre} | {f['llamadas']} | {f['tokens_entrada']:,} | "
                             f"{f['tokens_salida']:,} | {f['usd']:.4f} |")
            return [f"## {titulo}", "", *filas, ""]

        lineas = [
            "# Coste del diseño", "",
            f"**Total: {resumen['total_usd']:.4f} USD** de un tope de {self.limite_usd:.2f} USD, "
            f"en {resumen['llamadas']} llamadas al modelo "
            f"({resumen['tokens_entrada']:,} tokens de entrada y "
            f"{resumen['tokens_salida']:,} de salida).", "",
        ]
        if resumen["sin_precio"]:
            lineas += [f"> Modelos sin precio conocido, que no cuentan para el tope: "
                       f"{', '.join(resumen['sin_precio'])}.", ""]
        lineas += tabla("Por agente", resumen["por_agente"], "Agente")
        lineas += tabla("Por modelo", resumen["por_modelo"], "Modelo")
        lineas += tabla("Por etapa", resumen["por_etapa"], "Etapa")
        lineas += ["## Llamada a llamada", "",
                   "| # | Etapa | Agente | Modelo | Entrada | Salida | USD |",
                   "|---:|---|---|---|---:|---:|---:|"]
        for i, d in enumerate(detalle, start=1):
            lineas.append(f"| {i} | {d['etapa']} | {d['agente']} | {d['modelo']} | "
                          f"{d['tokens_entrada']:,} | {d['tokens_salida']:,} | {d['usd']:.4f} |")
        (carpeta / "design_cost.md").write_text("\n".join(lineas) + "\n", encoding="utf-8")

    def gastado_usd(self) -> float:
        return sum(d["usd"] for d in self.detalle())

    def queda_usd(self) -> float:
        return self.limite_usd - self.gastado_usd()

    def comprobar(self) -> None:
        gastado = self.gastado_usd()
        if gastado >= self.limite_usd:
            raise PresupuestoAgotado(
                f"el proyecto lleva {gastado:.2f} USD y el tope está en "
                f"{self.limite_usd:.2f}. Se para aquí: sube el tope si quieres que siga."
            )
