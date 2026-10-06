"""Tests del motor de cotizaciones.

Cubren aritmetica monetaria, cascada de descuentos, ciclo de vida y persistencia.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from cotizador import moneda
from cotizador.fachada import ClienteNoExiste, Cotizador, ErrorCotizador, ProductoNoExiste
from cotizador.modelo import (
    Cliente,
    Cotizacion,
    EstadoCotizacion,
    ItemCotizacion,
    Producto,
    TipoDescuento,
)


# --- fixtures --------------------------------------------------------------
@pytest.fixture
def producto() -> Producto:
    return Producto("TST-1", "Licencia anual", Decimal("1000.00"), "lic")


@pytest.fixture
def cliente() -> Cliente:
    return Cliente("NIT-1", "Cliente de Prueba", "c@x.example")


@pytest.fixture
def cot(producto, cliente) -> Cotizacion:
    c = Cotizacion(numero="COT-2026-000001", cliente=cliente)
    c.agregar_item(ItemCotizacion(producto=producto, cantidad=Decimal(2)))
    return c


@pytest.fixture
def cz(tmp_path) -> Cotizador:
    with Cotizador(tmp_path / "t.db") as c:
        yield c


# --- moneda ----------------------------------------------------------------
def test_formateo_usa_punto_miles_y_coma_decimal():
    assert moneda.formatear(Decimal("1234567.891")) == "$1.234.567,89"
    assert moneda.formatear(0) == "$0,00"
    assert moneda.formatear("-2500.5") == "-$2.500,50"


def test_float_no_contamina_el_redondeo():
    # 0.1 + 0.2 == 0.30000000000000004 en float; con Decimal no.
    assert moneda.q2(Decimal("0.1") + Decimal("0.2")) == Decimal("0.30")


def test_a_decimal_acepta_texto_con_simbolo():
    assert moneda.a_decimal("$1.250.500,50".replace(".", "").replace(",", ".")) == Decimal("1250500.50")


def test_round_half_up_comercial():
    assert moneda.q2(Decimal("2.345")) == Decimal("2.35")
    assert moneda.q2(Decimal("2.344")) == Decimal("2.34")


# --- calculo de items ------------------------------------------------------
def test_subtotal_es_precio_por_cantidad(producto):
    item = ItemCotizacion(producto=producto, cantidad=Decimal("3"))
    assert item.subtotal == Decimal("3000.00")


def test_descuento_porcentual(producto):
    item = ItemCotizacion(producto=producto, cantidad=Decimal(2), descuento_pct=Decimal(10))
    assert item.monto_descuento == Decimal("200.00")
    assert item.total == Decimal("1800.00")


def test_descuento_fijo_se_acota_al_subtotal(producto):
    item = ItemCotizacion(
        producto=producto,
        cantidad=Decimal(1),
        tipo_descuento=TipoDescuento.VALOR_FIJO,
        valor_descuento=Decimal("5000"),
    )
    assert item.total == Decimal("0.00")
    assert item.monto_descuento == Decimal("1000.00")


def test_bonificacion_aplica_25_por_ciento(producto):
    item = ItemCotizacion(producto=producto, cantidad=Decimal(2), bonificacion=True)
    assert item.total == Decimal("1500.00")  # 2000 - 25%


def test_cantidad_no_positiva_falla(producto):
    with pytest.raises(ValueError):
        ItemCotizacion(producto=producto, cantidad=Decimal(0))


def test_producto_inactivo_no_entra_a_la_cotizacion(producto, cliente):
    producto.activo = False
    c = Cotizacion(numero="X", cliente=cliente)
    with pytest.raises(ValueError):
        c.agregar_item(ItemCotizacion(producto=producto, cantidad=Decimal(1)))


# --- cascada de la cotizacion ---------------------------------------------
def test_total_incluye_iva_del_19_por_ciento(cot):
    # 2 x 1000 = 2000; cliente sin descuento; iva 19%
    assert cot.subtotal == Decimal("2000.00")
    assert cot.iva == Decimal("380.00")
    assert cot.total == Decimal("2380.00")


def test_descuento_del_cliente_se_aplica_sobre_la_base(producto, cliente):
    cliente.descuento_global = Decimal(10)
    c = Cotizacion(numero="X", cliente=cliente)
    c.agregar_item(ItemCotizacion(producto=producto, cantidad=Decimal(10)))
    assert c.monto_descuento_global == Decimal("1000.00")
    assert c.subtotal_final == Decimal("9000.00")
    assert c.total == Decimal("10710.00")


def test_descuento_item_y_cliente_no_se_solapan(cot, producto):
    cot.items.append(
        ItemCotizacion(producto=producto, cantidad=Decimal(2), descuento_pct=Decimal(50))
    )
    # base imponible 4000 - 1000 de descuento de item
    assert cot.descuento_items == Decimal("1000.00")
    assert cot.base_imponible == Decimal("3000.00")
    assert cot.iva == Decimal("570.00")
    assert cot.total == Decimal("3570.00")


def test_bonificacion_agrupada_no_convierte_el_item_en_cero(producto, cliente):
    """La bonificacion vale 25%, no el 100% del subtotal del item."""
    c = Cotizacion(numero="X", cliente=cliente)
    c.agregar_item(ItemCotizacion(producto=producto, cantidad=Decimal(2), bonificacion=True))
    assert c.descuento_items == Decimal("500.00")  # 25% de 2000
    assert c.base_imponible == Decimal("1500.00")
    assert c.total == Decimal("1785.00")


def test_ahorro_total_es_lista_menos_precio_final(cot):
    cot.cliente.descuento_global = Decimal(20)
    assert cot.ahorro_total == cot.subtotal - cot.subtotal_final


def test_descuento_adicional_se_suma_al_del_cliente(producto, cliente):
    cliente.descuento_global = Decimal(5)
    c = Cotizacion(numero="X", cliente=cliente)
    c.agregar_item(ItemCotizacion(producto=producto, cantidad=Decimal(10)))
    c.aplicar_descuento(Decimal(15), TipoDescuento.PORCENTAJE)
    assert c.monto_descuento_global == Decimal("2000.00")  # 20% de 10000


def test_iva_es_cero_sin_base_imponible(cliente):
    c = Cotizacion(numero="X", cliente=cliente)
    assert c.iva == Decimal("0.00")
    assert c.total == Decimal("0.00")


# --- ciclo de vida ---------------------------------------------------------
def test_vigencia_calcula_vencimiento(cot):
    cot.validez_dias = 10
    assert cot.fecha_vencimiento == cot.fecha_emision + dt.timedelta(days=10)
    assert cot.dias_para_vencer == 10
    assert cot.vigente


def test_cotizacion_vencida_no_esta_vigente(producto, cliente):
    c = Cotizacion(numero="X", cliente=cliente, fecha_emision=dt.date.today() - dt.timedelta(days=40))
    c.agregar_item(ItemCotizacion(producto=producto, cantidad=Decimal(1)))
    c.validez_dias = 5
    assert not c.vigente
    assert c.dias_para_vencer < 0


def test_enviada_bloquea_edicion(cot):
    cot.cambiar_estado(EstadoCotizacion.ENVIADA)
    assert not cot.estado.es_editable
    with pytest.raises(ValueError):
        cot.agregar_item(ItemCotizacion(producto=cot.items[0].producto, cantidad=Decimal(1)))


def test_no_se_acepta_sin_items(cliente):
    c = Cotizacion(numero="X", cliente=cliente)
    with pytest.raises(ValueError):
        c.cambiar_estado(EstadoCotizacion.ACEPTADA)


def test_quitar_item_inexistente_falla(cot):
    with pytest.raises(KeyError):
        cot.quitar_item("NO-EXISTE")


def test_validez_menor_a_un_dia_falla(cliente):
    with pytest.raises(ValueError):
        Cotizacion(numero="X", cliente=cliente, validez_dias=0)


# --- fachada / persistencia ------------------------------------------------
def test_ciclo_completo_en_base_temporal(cz):
    c = cz.nueva("900123456-1", validez_dias=30)
    assert c.numero.startswith("COT-")
    c = cz.agregar(c.numero, "HW-NB-14", 4, descuento_pct=5)
    c = cz.agregar(c.numero, "SRV-002", 12, bonificacion=True)
    cz.cambiar_estado(c.numero, EstadoCotizacion.ENVIADA)
    c = cz.cambiar_estado(c.numero, EstadoCotizacion.ACEPTADA)

    recargada = cz.cotizacion(c.numero)
    assert recargada is not None
    assert recargada.estado is EstadoCotizacion.ACEPTADA
    assert len(recargada.items) == 2
    assert recargada.total == c.total  # el motor es determinista


def test_numeracion_incremental(cz):
    a = cz.nueva("900123456-1").numero
    b = cz.nueva("900123456-1").numero
    assert int(b.rsplit("-", 1)[1]) == int(a.rsplit("-", 1)[1]) + 1


def test_cotizacion_no_acepta_items_cuando_no_es_borrador(cz):
    c = cz.nueva("900123456-1")
    c = cz.agregar(c.numero, "HW-NB-14", 1)
    cz.cambiar_estado(c.numero, EstadoCotizacion.ENVIADA)
    with pytest.raises(ErrorCotizador):
        cz.agregar(c.numero, "HW-NB-14", 1)


def test_cliente_inexistente_da_error_claro(cz):
    with pytest.raises(ClienteNoExiste):
        cz.nueva("000-0")


def test_producto_inexistente_da_error_claro(cz):
    c = cz.nueva("900123456-1")
    with pytest.raises(ProductoNoExiste):
        cz.agregar(c.numero, "SKU-FANTASMA", 1)


def test_catalogo_solo_se_siembra_una_vez(cz):
    antes = len(cz.productos())
    cz.db.sembrar([], [])
    assert len(cz.productos()) == antes


def test_tablero_consolida_por_estado(cz):
    c = cz.nueva("901444777-2")
    cz.agregar(c.numero, "SW-LIC-PRO", 10)
    cz.cambiar_estado(c.numero, EstadoCotizacion.ACEPTADA)
    t = cz.tablero()
    por_estado = {r["estado"]: r for r in t["por_estado"]}
    assert t["total_cotizaciones"] == 1
    assert por_estado["aceptada"]["cantidad"] == 1
    assert por_estado["aceptada"]["monto"] != "0.00"
    assert por_estado["borrador"]["cantidad"] == 0


def test_filtro_por_estado(cz):
    a = cz.nueva("900123456-1")
    b = cz.nueva("900123456-1")
    cz.cambiar_estado(b.numero, EstadoCotizacion.ENVIADA)
    enviadas = cz.cotizaciones("enviada")
    assert [x.numero for x in enviadas] == [b.numero]
    assert a.numero not in [x.numero for x in enviadas]


def test_serializacion_json_lista(cz):
    c = cz.nueva("900987654-3")
    cz.agregar(c.numero, "HW-DS-10", 3)
    data = cz.cotizacion(c.numero).to_dict()
    assert set(data) >= {"numero", "estado", "items", "total", "total_legible"}
    assert data["items"][0]["sku"] == "HW-DS-10"