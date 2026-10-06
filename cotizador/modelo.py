"""Modelos de dominio de CotizadorPro.

Dataclasses puras, sin dependencias de persistencia: el motor calcula sobre
ellos y la capa SQLite los serializa. Cada entidad tiene ``to_dict`` /
``desde_dict`` para que la CLI, la API y la demo web compartan contrato.
"""

from __future__ import annotations

import datetime as dt
import itertools
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

from cotizador import moneda


class EstadoCotizacion(str, Enum):
    BORRADOR = "borrador"
    ENVIADA = "enviada"
    ACEPTADA = "aceptada"
    RECHAZADA = "rechazada"
    VENCIDA = "vencida"

    @property
    def es_editable(self) -> bool:
        """Solo el borrador admite cambios de Items."""
        return self is EstadoCotizacion.BORRADOR

    @property
    def etiqueta(self) -> str:
        return {
            "borrador": "Borrador",
            "enviada": "Enviada",
            "aceptada": "Aceptada",
            "rechazada": "Rechazada",
            "vencida": "Vencida",
        }[self.value]


class TipoDescuento(str, Enum):
    NINGUNO = "ninguno"
    PORCENTAJE = "porcentaje"
    VALOR_FIJO = "valor_fijo"

    @property
    def etiqueta(self) -> str:
        return {
            "ninguno": "Sin descuento",
            "porcentaje": "Descuento %",
            "valor_fijo": "Descuento fijo",
        }[self.value]


def _hoy() -> dt.date:
    return dt.date.today()


@dataclass(slots=True)
class Producto:
    sku: str
    nombre: str
    precio_unitario: Decimal
    unidad: str = "und"
    categoria: str = "general"
    activo: bool = True

    def __post_init__(self) -> None:
        self.precio_unitario = moneda.q2(self.precio_unitario)
        if self.precio_unitario < 0:
            raise ValueError(f"precio negativo en SKU {self.sku}")

    @property
    def precio_str(self) -> str:
        return moneda.formatear(self.precio_unitario)

    def to_dict(self) -> dict:
        return {
            "sku": self.sku,
            "nombre": self.nombre,
            "precio_unitario": str(self.precio_unitario),
            "unidad": self.unidad,
            "categoria": self.categoria,
            "activo": self.activo,
        }


#: Bonificacion aplicada a licencias adicionales: 25% sobre el subtotal del item.
BONIFICACION_PCT = Decimal("25")


@dataclass(slots=True)
class Cliente:
    nit: str
    nombre: str
    email: str = ""
    telefono: str = ""
    descuento_global: Decimal = Decimal("0")
    activo: bool = True

    def __post_init__(self) -> None:
        self.descuento_global = moneda.q2(self.descuento_global)
        if not (0 <= self.descuento_global <= 100):
            raise ValueError("descuento global debe estar entre 0 y 100")

    def to_dict(self) -> dict:
        return {
            "nit": self.nit,
            "nombre": self.nombre,
            "email": self.email,
            "telefono": self.telefono,
            "descuento_global": str(self.descuento_global),
            "activo": self.activo,
        }


@dataclass(slots=True)
class ItemCotizacion:
    producto: Producto
    cantidad: Decimal
    descuento_pct: Decimal = Decimal("0")
    tipo_descuento: TipoDescuento = TipoDescuento.PORCENTAJE
    valor_descuento: Decimal = Decimal("0")
    bonificacion: bool = False

    def __post_init__(self) -> None:
        self.cantidad = moneda.a_decimal(self.cantidad)
        if self.cantidad <= 0:
            raise ValueError(f"cantidad invalida para {self.producto.sku}")
        if not (0 <= self.descuento_pct <= 100):
            raise ValueError("descuento % debe estar entre 0 y 100")

    @property
    def subtotal(self) -> Decimal:
        return moneda.q2(self.producto.precio_unitario * self.cantidad)

    @property
    def monto_descuento(self) -> Decimal:
        if self.tipo_descuento is TipoDescuento.PORCENTAJE:
            base = self.subtotal
            pct_aplicado = min(self.descuento_pct, Decimal(100))
            return moneda.q2(base * pct_aplicado / Decimal(100))
        if self.tipo_descuento is TipoDescuento.VALOR_FIJO:
            return moneda.q2(min(self.valor_descuento, self.subtotal))
        return moneda.CERO

    @property
    def total(self) -> Decimal:
        base = self.subtotal - self.monto_descuento
        return moneda.q2(base * Decimal("0.75") if self.bonificacion else base)

    @property
    def descuento_efectivo_pct(self) -> Decimal:
        if self.subtotal == 0:
            return moneda.CERO
        return moneda.pct(self.monto_descuento + (
            self.subtotal if self.bonificacion else Decimal(0)
        ), self.subtotal)

    def to_dict(self) -> dict:
        return {
            "sku": self.producto.sku,
            "nombre": self.producto.nombre,
            "unidad": self.producto.unidad,
            "cantidad": str(self.cantidad),
            "precio_unitario": str(self.producto.precio_unitario),
            "subtotal": str(self.subtotal),
            "descuento_pct": str(self.descuento_pct),
            "tipo_descuento": self.tipo_descuento.value,
            "valor_descuento": str(self.valor_descuento),
            "bonificacion": self.bonificacion,
            "total": str(self.total),
        }


@dataclass(slots=True)
class Cotizacion:
    numero: str
    cliente: Cliente
    items: list[ItemCotizacion] = field(default_factory=list)
    estado: EstadoCotizacion = EstadoCotizacion.BORRADOR
    validez_dias: int = 15
    observaciones: str = ""
    fecha_emision: dt.date = field(default_factory=_hoy)
    descuento_adicional: Decimal = Decimal("0")
    tipo_descuento_adicional: TipoDescuento = TipoDescuento.PORCENTAJE
    creado_en: dt.datetime = field(default_factory=lambda: dt.datetime.now())

    def __post_init__(self) -> None:
        self.descuento_adicional = moneda.q2(self.descuento_adicional)
        if self.validez_dias < 1:
            raise ValueError("la validez debe ser de al menos 1 dia")

    # --- Subtotales ---------------------------------------------------------
    @property
    def subtotal(self) -> Decimal:
        return moneda.q2(sum((i.subtotal for i in self.items), Decimal("0")))

    @property
    def descuento_items(self) -> Decimal:
        """Descuentos aplicados a nivel de item, sin el descuento global.

        La bonificacion (licencia adicional) equivale al 25% del subtotal, no
        al 100%: por eso se calcula sobre el neto del item, no sobre ``subtotal``.
        """
        bonificaciones = moneda.q2(
            sum(
                (
                    moneda.q2(i.subtotal * BONIFICACION_PCT / Decimal(100))
                    for i in self.items
                    if i.bonificacion
                ),
                Decimal("0"),
            )
        )
        return moneda.q2(
            sum((i.monto_descuento for i in self.items), Decimal("0")) + bonificaciones
        )

    @property
    def base_imponible(self) -> Decimal:
        """Subtotal menos lo descontado a nivel de item."""
        return moneda.q2(self.subtotal - self.descuento_items)

    @property
    def monto_descuento_global(self) -> Decimal:
        """Descuento del cliente + descuento adicional de la cotizacion."""
        base = self.base_imponible
        if self.tipo_descuento_adicional is TipoDescuento.PORCENTAJE:
            pct_total = min(
                self.cliente.descuento_global + self.descuento_adicional,
                Decimal(100),
            )
            return moneda.q2(base * pct_total / Decimal(100))
        if self.tipo_descuento_adicional is TipoDescuento.VALOR_FIJO:
            return moneda.q2(min(self.descuento_adicional, base))
        return moneda.q2(base * self.cliente.descuento_global / Decimal(100))

    @property
    def subtotal_final(self) -> Decimal:
        return moneda.q2(self.base_imponible - self.monto_descuento_global)

    @property
    def iva_pct(self) -> Decimal:
        return Decimal("19") if self.base_imponible > 0 else Decimal("0")

    @property
    def iva(self) -> Decimal:
        return moneda.q2(self.subtotal_final * self.iva_pct / Decimal(100))

    @property
    def total(self) -> Decimal:
        return moneda.q2(self.subtotal_final + self.iva)

    @property
    def ahorro_total(self) -> Decimal:
        """Cuanto se Ahorro el cliente frente a la lista."""
        lista = self.subtotal
        return moneda.q2(lista - self.subtotal_final)

    @property
    def fecha_vencimiento(self) -> dt.date:
        return self.fecha_emision + dt.timedelta(days=self.validez_dias)

    @property
    def dias_para_vencer(self) -> int:
        return (self.fecha_vencimiento - _hoy()).days

    @property
    def vigente(self) -> bool:
        return (
            self.estado in (EstadoCotizacion.BORRADOR, EstadoCotizacion.ENVIADA)
            and self.dias_para_vencer >= 0
        )

    # --- API ----------------------------------------------------------------
    def agregar_item(self, item: ItemCotizacion) -> "Cotizacion":
        self._exigir_borrador()
        if not item.producto.activo:
            raise ValueError(f"producto inactivo: {item.producto.sku}")
        self.items.append(item)
        return self

    def quitar_item(self, sku: str) -> "Cotizacion":
        self._exigir_borrador()
        antes = len(self.items)
        self.items = [i for i in self.items if i.producto.sku != sku]
        if len(self.items) == antes:
            raise KeyError(f"item no encontrado: {sku}")
        return self

    def cambiar_estado(self, nuevo: EstadoCotizacion) -> "Cotizacion":
        if nuevo is EstadoCotizacion.ACEPTADA and not self.items:
            raise ValueError("no se puede aceptar una cotizacion sin items")
        self.estado = nuevo
        return self

    def aplicar_descuento(self, valor: object, tipo: TipoDescuento) -> "Cotizacion":
        self._exigir_borrador()
        self.descuento_adicional = moneda.q2(valor)
        self.tipo_descuento_adicional = tipo
        return self

    def _exigir_borrador(self) -> None:
        if not self.estado.es_editable:
            raise ValueError(
                f"cotizacion {self.numero} en estado '{self.estado.value}' no admite cambios"
            )

    # --- Serializacion ------------------------------------------------------
    def resumen(self) -> dict:
        return {
            "numero": self.numero,
            "cliente": self.cliente.nombre,
            "cliente_nit": self.cliente.nit,
            "estado": self.estado.value,
            "estado_etiqueta": self.estado.etiqueta,
            "items": len(self.items),
            "subtotal": str(self.subtotal),
            "descuentos": str(moneda.q2(self.descuento_items + self.monto_descuento_global)),
            "iva": str(self.iva),
            "total": str(self.total),
            "total_legible": moneda.formatear(self.total),
            "validez_dias": self.validez_dias,
            "fecha_emision": self.fecha_emision.isoformat(),
            "fecha_vencimiento": self.fecha_vencimiento.isoformat(),
            "dias_para_vencer": self.dias_para_vencer,
            "vigente": self.vigente,
        }

    def to_dict(self) -> dict:
        data = self.resumen()
        data["observaciones"] = self.observaciones
        data["items"] = [i.to_dict() for i in self.items]
        return data


def consecutivo(prefijo: str = "COT", year: int | None = None) -> str:
    """Genera ``COT-2026-000123`` con un contador global de proceso.

    En produccion el numero debe venir de la BD; este helper cubre CLI y tests.
    """
    year = year or dt.date.today().year
    n = next(_CONTADOR)
    return f"{prefijo}-{year}-{n:06d}"


_CONTADOR = itertools.count(1)