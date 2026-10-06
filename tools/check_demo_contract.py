#!/usr/bin/env python3
"""Verifica que el motor de la demo (`docs/motor.js`) calcula igual que Python.

La demo web reimplementa el contrato de calculo del dominio. Sin esta comprobacion
esos dos motores podrian divergir en silencio y la demoeria del cliente sin que nadie
lo notara. Este script corre un banco de casos por ambos motores y compara centavo a
centavo. Sale con codigo 1 en cuanto hay una diferencia.

    python tools/check_demo_contract.py

Requiere `node` en el PATH.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from cotizador import moneda  # noqa: E402
from cotizador.catalogo import CLIENTES, PRODUCTOS  # noqa: E402
from cotizador.modelo import Cotizacion, ItemCotizacion  # noqa: E402

# Casos que cubre las ramas del motor: descuentos, bonificaciones, sin items,
# descuento adicional, cliente con y sin descuento pactado.
CASOS = [
    {
        "nombre": "licencias + bonificacion + cliente 10%",
        "cliente": "901444777-2",
        "items": [
            {"sku": "SW-LIC-PRO", "cantidad": 15, "descuento_pct": 8},
            {"sku": "HW-MN-27", "cantidad": 15, "bonificacion": True},
            {"sku": "SRV-002", "cantidad": 12},
        ],
    },
    {
        "nombre": "hardware sin descuento",
        "cliente": "900987654-3",
        "items": [
            {"sku": "HW-DS-10", "cantidad": 8, "descuento_pct": 3},
            {"sku": "HW-RT-06", "cantidad": 8},
        ],
    },
    {
        "nombre": "cantidad grande + cliente 0%",
        "cliente": "900123456-1",
        "items": [
            {"sku": "INS-MIG-01", "cantidad": 1},
            {"sku": "SRV-001", "cantidad": 1},
        ],
    },
    {
        "nombre": "desarrollo por usuario-mes",
        "cliente": "830456789-0",
        "items": [
            {"sku": "SW-DEV-STD", "cantidad": 72, "descuento_pct": 4},
            {"sku": "HW-NB-14", "cantidad": 6, "bonificacion": True},
        ],
    },
    {
        "nombre": "cotizacion vacia",
        "cliente": "901444777-2",
        "items": [],
    },
    {
        "nombre": "descuentos al 100%",
        "cliente": "901444777-2",
        "items": [
            {"sku": "SW-LIC-STD", "cantidad": 1, "descuento_pct": 100},
        ],
    },
]

CAMPOS = ("subtotal", "descuentosItems", "baseImponible", "descuentoGlobal", "subtotalFinal", "iva", "total")


def calcular_python(cliente_nit: str, items: list[dict]) -> dict[str, int]:
    """Corre el dominio Python y devuelve los mismos campos, en centavos."""
    clientes = {c.nit: c for c in CLIENTES}
    productos = {p.sku: p for p in PRODUCTOS}
    cot = Cotizacion(numero="COT-TEST", cliente=clientes[cliente_nit])
    for it in items:
        cot.agregar_item(
            ItemCotizacion(
                producto=productos[it["sku"]],
                cantidad=Decimal(str(it["cantidad"])),
                descuento_pct=Decimal(str(it.get("descuento_pct", 0))),
                bonificacion=bool(it.get("bonificacion", False)),
            )
        )
    return {
        "subtotal": moneda.a_centavos(cot.subtotal),
        "descuentosItems": moneda.a_centavos(cot.descuento_items),
        "baseImponible": moneda.a_centavos(cot.base_imponible),
        "descuentoGlobal": moneda.a_centavos(cot.monto_descuento_global),
        "subtotalFinal": moneda.a_centavos(cot.subtotal_final),
        "iva": moneda.a_centavos(cot.iva),
        "total": moneda.a_centavos(cot.total),
    }


def construir_entrada_js(casos: list[dict]) -> list[dict]:
    """Traduce los casos al formato que consume `docs/motor.js` (centavos)."""
    precios = {p.sku: moneda.a_centavos(p.precio_unitario) for p in PRODUCTOS}
    salida = []
    for i, caso in enumerate(casos, start=1):
        salida.append(
            {
                "numero": f"COT-TEST-{i:03d}",
                "clienteNit": caso["cliente"],
                "items": [
                    {
                        "sku": it["sku"],
                        "cantidad": it["cantidad"],
                        "descuentoPct": it.get("descuento_pct", 0),
                        "tipoDescuento": "porcentaje",
                        "valorDescuento": 0,
                        "bonificacion": bool(it.get("bonificacion", False)),
                    }
                    for it in caso["items"]
                ],
                "descuentoAdicional": 0,
                "tipoDescuentoAdicional": "porcentaje",
                "validezDias": 15,
                "fechaEmision": "2026-01-01",
                "estado": "borrador",
                "_precios": precios,  # sanity: los precios deben coincidir
            }
        )
    return salida


def _peso(centavos: int) -> str:
    """Formato legible desde centavos (los motores trabajan en centavos)."""
    return moneda.formatear(moneda.de_centavos(centavos))


def main() -> int:
    if shutil.which("node") is None:
        print("SKIP  node no esta en el PATH; no se pudo verificar la paridad JS.")
        return 0

    entrada = construir_entrada_js(CASOS)
    precios_js = entrada[0]["_precios"]
    precios_py = {p.sku: moneda.a_centavos(p.precio_unitario) for p in PRODUCTOS}
    if precios_js != precios_py:
        print("FALLA  el catalogo de docs/motor.js no coincide con cotizador/catalogo.py")
        for sku in precios_py:
            if precios_js.get(sku) != precios_py[sku]:
                print(f"  {sku}: JS={precios_js.get(sku)} py={precios_py[sku]}")
        return 1

    for caso in entrada:
        caso.pop("_precios")

    runner = Path(__file__).resolve().parent / "_motor_node.js"
    with tempfile.TemporaryDirectory() as tmp:
        ruta = Path(tmp) / "casos.json"
        ruta.write_text(json.dumps(entrada), encoding="utf-8")
        proc = subprocess.run(
            ["node", str(runner), str(ruta)],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    if proc.returncode != 0:
        print("FALLA  no se pudo ejecutar docs/motor.js en node")
        print(proc.stderr.strip())
        return 1

    resultado_js = json.loads(proc.stdout)
    fallos = 0
    for caso, js in zip(CASOS, resultado_js):
        py = calcular_python(caso["cliente"], caso["items"])
        estado = "OK  "
        for campo in CAMPOS:
            if py[campo] != js[campo]:
                fallos += 1
                estado = "FALLA"
                print(
                    f"FALLA  {caso['nombre']}: {campo} "
                    f"python={py[campo]} js={js[campo]} "
                    f"({_peso(py[campo])} vs {_peso(js[campo])})"
                )
        print(f"{estado}    {caso['nombre']:<44} total {_peso(py['total'])}")

    if fallos:
        print(f"\n{fallos} diferencia(s) entre el motor Python y el de la demo.")
        return 1

    print(f"\nOK  {len(CASOS)} casos identicos en Python y en la demo web.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())