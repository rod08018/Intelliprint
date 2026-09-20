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

    @classmethod
    def from_config(cls, config: dict) -> "Presupuesto":
        return cls(
            float(config.get("escalation", {}).get("max_usd_per_project", 2.0)),
            config.get("pricing", {}),
        )

    def vigila(self, cliente) -> None:
        self._clientes.append(cliente)

    def gastado_usd(self) -> float:
        total = 0.0
        for cliente in self._clientes:
            precio = self._precios.get(getattr(cliente, "modelo", ""), None)
            if precio is None:
                continue  # modelo sin precio (local o nuevo): no se puede contar
            uso = cliente.tokens
            total += (uso["entrada"] * precio["in_usd_per_mtok"] / 1e6
                      + uso["salida"] * precio["out_usd_per_mtok"] / 1e6)
        return total

    def queda_usd(self) -> float:
        return self.limite_usd - self.gastado_usd()

    def comprobar(self) -> None:
        gastado = self.gastado_usd()
        if gastado >= self.limite_usd:
            raise PresupuestoAgotado(
                f"el proyecto lleva {gastado:.2f} USD y el tope está en "
                f"{self.limite_usd:.2f}. Se para aquí: sube el tope si quieres que siga."
            )
