"""CotizadorPro — interfaz de linea de comandos.

Uso tipico en una sesion de venta::

    python -m cotizador.cli init
    python -m cotizador.cli nueva --cliente 900123456-1
    python -m cotizador.cli agregar COT-2026-000001 --sku HW-NB-14 --cantidad 4 --descuento 5
    python -m cotizador.cli ver COT-2026-000001
    python -m cotizador.cli enviar COT-2026-000001
    python -m cotizador.cli tablero
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from decimal import Decimal

from cotizador import moneda
from cotizador.fachada import Cotizador, ErrorCotizador
from cotizador.modelo import EstadoCotizacion, ItemCotizacion, TipoDescuento

# --- presentacion ----------------------------------------------------------
ANCHO = 78


def _titulo(t: str) -> str:
    return f"\n\033[38;5;179m{t.upper()}\033[0m\n" + "─" * ANCHO


def _linea(etq: str, val: str) -> str:
    return f"  {etq:<26}{val}"


def _tabla(encabezados: list[str], filas: list[list[str]], anchos: list[int]) -> str:
    out = ["  " + "  ".join(h.rjust(a) for h, a in zip(encabezados, anchos))]
    out.append("  " + "  ".join("─" * a for a in anchos))
    for fila in filas:
        out.append("  " + "  ".join(c.rjust(a) for c, a in zip(fila, anchos)))
    return "\n".join(out)


def _estado_color(estado: str) -> str:
    return {
        "borrador": "38;5;244",
        "enviada": "38;5;39",
        "aceptada": "38;5;42",
        "rechazada": "38;5;203",
        "vencida": "38;5;208",
    }.get(estado, "0")


# --- comandos --------------------------------------------------------------
def cmd_init(args, cz: Cotizador) -> int:
    print(_titulo("catalogo inicial cargado"))
    for p in cz.productos():
        print(_linea(p.sku, f"{p.nombre[:44]:<44} {p.precio_str}"))
    print(f"\n  {len(cz.productos())} productos | {len(cz.clientes())} clientes")
    print(f"  Base de datos: {cz.db.path}\n")
    return 0


def cmd_nueva(args, cz: Cotizador) -> int:
    cot = cz.nueva(args.cliente, validez_dias=args.validez)
    print(_titulo(f"cotizacion {cot.numero} creada"))
    print(_linea("cliente", cot.cliente.nombre))
    print(_linea("descuento del cliente", f"{cot.cliente.descuento_global}%"))
    print(_linea("vigencia", f"{cot.validez_dias} dias (hasta {cot.fecha_vencimiento})"))
    print()
    return 0


def cmd_agregar(args, cz: Cotizador) -> int:
    cot = cz.agregar(
        args.numero,
        args.sku,
        args.cantidad,
        descuento_pct=args.descuento,
        bonificacion=args.bonificacion,
    )
    ult = cot.items[-1]
    print(_titulo(f"item agregado a {cot.numero}"))
    print(_linea("producto", f"{ult.producto.sku} - {ult.producto.nombre}"))
    print(_linea("cantidad", f"{ult.cantidad} {ult.producto.unidad}"))
    print(_linea("subtotal", moneda.formatear(ult.subtotal)))
    if ult.bonificacion:
        print(_linea("bonificacion", "-25% (licencia adicional)"))
    print(_linea("total cotizacion", moneda.formatear(cot.total)))
    print()
    return 0


def cmd_quitar(args, cz: Cotizador) -> int:
    cz.quitar(args.numero, args.sku)
    print(f"  OK  {args.sku} retirado de {args.numero}\n")
    return 0


def cmd_descontar(args, cz: Cotizador) -> int:
    tipo = TipoDescuento(args.tipo)
    cot = cz.descontar(args.numero, args.valor, tipo)
    print(_titulo("descuento aplicado"))
    print(_linea("tipo", tipo.etiqueta))
    print(_linea("valor", str(cot.descuento_adicional)))
    print(_linea("descuento cliente", f"{cot.cliente.descuento_global}%"))
    print(_linea("ahorro del cliente", moneda.formatear(cot.ahorro_total)))
    print(_linea("total cotizacion", moneda.formatear(cot.total)))
    print()
    return 0


def cmd_ver(args, cz: Cotizador) -> int:
    cot = cz.cotizacion(args.numero)
    if cot is None:
        print(f"  ERROR  no existe {args.numero}")
        return 1
    if args.json:
        print(json.dumps(cot.to_dict(), indent=2, ensure_ascii=False))
        return 0
    print(_titulo(f"cotizacion {cot.numero}"))
    color = _estado_color(cot.estado.value)
    print(_linea("cliente", f"{cot.cliente.nombre} ({cot.cliente.nit})"))
    print(_linea("estado", f"\033[{color}m{cot.estado.etiqueta}\033[0m"))
    print(_linea("emitida", f"{cot.fecha_emision} (vence {cot.fecha_vencimiento})"))
    print(_linea("vigencia", f"{cot.dias_para_vencer} dias restantes"))
    print()
    filas = []
    for i in cot.items:
        filas.append([
            i.producto.sku,
            f"{i.cantidad} {i.producto.unidad}",
            moneda.formatear(i.producto.precio_unitario),
            ("bonif." if i.bonificacion else (f"-{i.descuento_pct}%" if i.descuento_pct else "-")),
            moneda.formatear(i.total),
        ])
    print(_tabla(
        ["SKU", "CANT", "P. UNIT", "DESC", "TOTAL"],
        filas,
        [11, 10, 16, 8, 16],
    ))
    print()
    print(_linea("subtotal lista", moneda.formatear(cot.subtotal)))
    print(_linea("descuentos items", "-" + moneda.formatear(cot.descuento_items)))
    print(_linea("descuento cliente", "-" + moneda.formatear(cot.monto_descuento_global)))
    print(_linea("subtotal", moneda.formatear(cot.subtotal_final)))
    print(_linea(f"IVA {cot.iva_pct}%", moneda.formatear(cot.iva)))
    print(_linea("TOTAL", moneda.formatear(cot.total)))
    print()
    return 0


def cmd_cambiar(args, cz: Cotizador) -> int:
    cot = cz.cambiar_estado(args.numero, args.estado)
    print(f"  OK  {cot.numero} -> {cot.estado.etiqueta} ({moneda.formatear(cot.total)})\n")
    return 0


def cmd_listar(args, cz: Cotizador) -> int:
    print(_titulo("cartera de cotizaciones"))
    cots = cz.cotizaciones(args.estado)
    if not cots:
        print("  (sin cotizaciones)\n")
        return 0
    filas = []
    for c in cots:
        color = _estado_color(c.estado.value)
        filas.append([
            c.numero,
            c.cliente.nombre[:28],
            str(len(c.items)),
            moneda.formatear(c.total),
            f"\033[{color}m{c.estado.etiqueta}\033[0m",
        ])
    print(_tabla(["NUMERO", "CLIENTE", "ITEMS", "TOTAL", "ESTADO"], filas, [16, 28, 5, 16, 10]))
    tot = sum(c.total for c in cots)
    print(f"\n  {len(cots)} cotizaciones | pipeline: {moneda.formatear(tot)}\n")
    return 0


def cmd_tablero(args, cz: Cotizador) -> int:
    t = cz.tablero()
    print(_titulo("tablero comercial"))
    print(_linea("cotizaciones", str(t["total_cotizaciones"])))
    print(_linea("productos en catalogo", str(t["productos"])))
    print(_linea("clientes activos", str(t["clientes"])))
    print()
    filas = [
        [r["etiqueta"], str(r["cantidad"]), r["monto_legible"]]
        for r in t["por_estado"]
    ]
    print(_tabla(["ESTADO", "CANT", "MONTO"], filas, [12, 5, 18]))
    print()
    return 0


def cmd_cerrar(args, cz: Cotizador) -> int:
    """Ejemplo end-to-end: crea, cotiza y cierra. Util para demostraciones."""
    print(_titulo("cierre de operacion (demo end-to-end)"))
    historial = [
        ("901444777-2", [("SW-LIC-PRO", 15, 8, False), ("HW-MN-27", 15, 0, True),
                          ("SRV-002", 12, 0, False)], 12, "licencias + soporte 12 meses"),
        ("900987654-3", [("HW-DS-10", 8, 3, False), ("HW-RT-06", 8, 0, False)], 30, "renovacion parque TI"),
        ("900123456-1", [("INS-MIG-01", 1, 0, False), ("SRV-001", 1, 0, False)], 20, "migracion + puesta en marcha"),
    ]
    total = Decimal("0.00")
    for nit, items, vigencia, nota in historial:
        cot = cz.nueva(nit, validez_dias=vigencia)
        for sku, cant, desc, bonif in items:
            cot.agregar_item(ItemCotizacion(
                producto=cz.producto(sku),
                cantidad=Decimal(cant),
                descuento_pct=Decimal(desc),
                bonificacion=bonif,
            ))
        cot.observaciones = nota
        # Se persiste antes de transicionar: la fachada siempre recalcula
        # sobre el estado persistido, nunca sobre el objeto en memoria.
        cz.guardar(cot)
        cz.cambiar_estado(cot.numero, EstadoCotizacion.ENVIADA)
        cot = cz.cambiar_estado(cot.numero, EstadoCotizacion.ACEPTADA)
        total += cot.total
        print(_linea(cot.numero, f"{cot.cliente.nombre[:30]:<30} {moneda.formatear(cot.total)}"))
    print()
    print(_linea("cerrado hoy", f"{len(historial)} operaciones"))
    print(_linea("facturacion del dia", moneda.formatear(total)))
    print(f"\n  Fecha: {dt.date.today().isoformat()}\n")
    return 0


# --- parser ----------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cotizador",
        description="CotizadorPro — motor de cotizaciones comerciales",
    )
    p.add_argument("--db", default="cotizador.db", help="ruta de la base SQLite")
    sub = p.add_subparsers(dest="comando", required=True)

    sub.add_parser("init", help="carga el catalogo y muestra los productos").set_defaults(fn=cmd_init)

    q = sub.add_parser("nueva", help="crea una cotizacion para un cliente")
    q.add_argument("--cliente", required=True, metavar="NIT")
    q.add_argument("--validez", type=int, default=15, help="dias de vigencia")
    q.set_defaults(fn=cmd_nueva)

    q = sub.add_parser("agregar", help="agrega un item a la cotizacion")
    q.add_argument("numero")
    q.add_argument("--sku", required=True)
    q.add_argument("--cantidad", type=Decimal, required=True)
    q.add_argument("--descuento", type=Decimal, default=Decimal(0), help="descuento %%")
    q.add_argument("--bonificacion", action="store_true", help="bonificacion -25%% (licencia adicional)")
    q.set_defaults(fn=cmd_agregar)

    q = sub.add_parser("quitar", help="retira un item")
    q.add_argument("numero")
    q.add_argument("--sku", required=True)
    q.set_defaults(fn=cmd_quitar)

    q = sub.add_parser("descontar", help="aplica descuento adicional")
    q.add_argument("numero")
    q.add_argument("--valor", type=Decimal, required=True)
    q.add_argument("--tipo", choices=[t.value for t in TipoDescuento], default="porcentaje")
    q.set_defaults(fn=cmd_descontar)

    q = sub.add_parser("ver", help="muestra una cotizacion completa")
    q.add_argument("numero")
    q.add_argument("--json", action="store_true")
    q.set_defaults(fn=cmd_ver)

    q = sub.add_parser("estado", help="cambia el estado de la cotizacion")
    q.add_argument("numero")
    q.add_argument("estado", choices=[e.value for e in EstadoCotizacion])
    q.set_defaults(fn=cmd_cambiar)

    q = sub.add_parser("listar", help="lista la cartera de cotizaciones")
    q.add_argument("--estado", choices=[e.value for e in EstadoCotizacion])
    q.set_defaults(fn=cmd_listar)

    sub.add_parser("tablero", help="indicadores comerciales").set_defaults(fn=cmd_tablero)
    sub.add_parser("demo", help="cierra una operacion completa de ejemplo").set_defaults(fn=cmd_cerrar)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        with Cotizador(args.db) as cz:
            return args.fn(args, cz)
    except ErrorCotizador as e:
        print(f"  ERROR  {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:  # pragma: no cover
        return 130


if __name__ == "__main__":
    raise SystemExit(main())