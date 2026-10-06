"""Fachada de alto nivel: la API que consumen CLI, API HTTP y tests.

Ejemplo::

    from cotizador import Cotizador

    cz = Cotizador("cotizador.db")
    cot = cz.nueva("900123456-1")
    cot.agregar_item("HW-NB-14", 4, descuento_pct=5)
    cot = cz.guardar(cot)
    print(cot.total_legible)
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from cotizador import catalogo
from cotizador.db import Database
from cotizador.modelo import (
    Cliente,
    Cotizacion,
    EstadoCotizacion,
    ItemCotizacion,
    Producto,
    TipoDescuento,
)


class ErrorCotizador(Exception):
    """Error de negocio (no de programacion). La CLI lo muestra limpio."""


class ClienteNoExiste(ErrorCotizador):
    pass


class ProductoNoExiste(ErrorCotizador):
    pass


class Cotizador:
    """Punto unico de entrada al dominio de cotizaciones."""

    def __init__(self, ruta: str | Path = "cotizador.db", *, sembrar: bool = True) -> None:
        self.db = Database(ruta)
        if sembrar:
            self.db.sembrar(catalogo.PRODUCTOS, catalogo.CLIENTES)

    # --- contexto -----------------------------------------------------------
    def cerrar(self) -> None:
        self.db.close()

    def __enter__(self) -> "Cotizador":
        return self

    def __exit__(self, *exc) -> None:
        self.cerrar()

    # --- consultas ----------------------------------------------------------
    def producto(self, sku: str) -> Producto:
        p = self.db.producto(sku)
        if p is None:
            raise ProductoNoExiste(f"SKU no encontrado: {sku}")
        return p

    def productos(self, categoria: str | None = None) -> list[Producto]:
        return self.db.productos(categoria)

    def cliente(self, nit: str) -> Cliente:
        c = self.db.cliente(nit)
        if c is None:
            raise ClienteNoExiste(f"NIT no encontrado: {nit}")
        return c

    def clientes(self) -> list[Cliente]:
        return self.db.clientes()

    def cotizacion(self, numero: str) -> Cotizacion | None:
        return self.db.cotizacion(numero)

    def cotizaciones(self, estado: str | None = None) -> list[Cotizacion]:
        return self.db.cotizaciones(estado)

    def tablero(self) -> dict:
        return self.db.tablero()

    # --- comandos -----------------------------------------------------------
    def nueva(self, nit_cliente: str, *, validez_dias: int = 15, numero: str | None = None) -> Cotizacion:
        """Crea y **reserva** una cotizacion: el numero queda persistido.

        Reservar desde el inicio evita colisiones de consecutivo cuando dos
       dactionistas abren cotizaciones en paralelo.
        """
        cliente = self.cliente(nit_cliente)
        return self.db.guardar(
            Cotizacion(
                numero=numero or self.db.siguiente_numero(),
                cliente=cliente,
                validez_dias=validez_dias,
            )
        )

    def agregar(
        self,
        numero: str,
        sku: str,
        cantidad: object,
        *,
        descuento_pct: object = 0,
        bonificacion: bool = False,
        valor_descuento: object = 0,
        tipo_descuento: TipoDescuento = TipoDescuento.PORCENTAJE,
    ) -> Cotizacion:
        cot = self._exigir(numero)
        producto = self.producto(sku)
        cot.agregar_item(
            ItemCotizacion(
                producto=producto,
                cantidad=Decimal(str(cantidad)),
                descuento_pct=Decimal(str(descuento_pct)),
                valor_descuento=Decimal(str(valor_descuento)),
                tipo_descuento=tipo_descuento,
                bonificacion=bonificacion,
            )
        )
        return self.db.guardar(cot)

    def quitar(self, numero: str, sku: str) -> Cotizacion:
        cot = self._exigir(numero)
        try:
            cot.quitar_item(sku)
        except KeyError as e:
            raise ErrorCotizador(str(e)) from e
        return self.db.guardar(cot)

    def descontar(self, numero: str, valor: object, tipo: TipoDescuento) -> Cotizacion:
        return self.db.guardar(self._exigir(numero).aplicar_descuento(valor, tipo))

    def cambiar_estado(self, numero: str, estado: EstadoCotizacion | str) -> Cotizacion:
        try:
            nuevo = EstadoCotizacion(estado)
        except ValueError as e:
            raise ErrorCotizador(f"estado desconocido: {estado}") from e
        cot = self._exigir(numero, editable=False)
        try:
            cot.cambiar_estado(nuevo)
        except ValueError as e:
            raise ErrorCotizador(str(e)) from e
        return self.db.guardar(cot)

    def guardar(self, cot: Cotizacion) -> Cotizacion:
        return self.db.guardar(cot)

    def _exigir(self, numero: str, *, editable: bool = True) -> Cotizacion:
        cot = self.db.cotizacion(numero)
        if cot is None:
            raise ErrorCotizador(f"cotizacion no encontrada: {numero}")
        if editable and not cot.estado.es_editable:
            raise ErrorCotizador(
                f"la cotizacion {numero} esta '{cot.estado.value}' y no admite cambios"
            )
        return cot