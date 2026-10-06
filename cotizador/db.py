"""Persistencia SQLite (solo stdlib) para CotizadorPro.

Decisiones:
- Montos guardados como INTEGER en centavos: SQLite no tiene decimal exacto y
  guardar texto flotante reintroduce el error de redondeo.
- ``PRAGMA foreign_keys=ON`` para que un item sin cotizacion no exista.
- Conexion unica compartida con ``check_same_thread=False`` (compatible con
  FastAPI/TestClient y con el pool de hilos de la CLI).
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

from cotizador import moneda
from cotizador.modelo import (
    Cliente,
    Cotizacion,
    EstadoCotizacion,
    ItemCotizacion,
    Producto,
    TipoDescuento,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS clientes (
    nit              TEXT PRIMARY KEY,
    nombre           TEXT NOT NULL,
    email            TEXT DEFAULT '',
    telefono         TEXT DEFAULT '',
    descuento_global INTEGER NOT NULL DEFAULT 0,
    activo           INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS productos (
    sku             TEXT PRIMARY KEY,
    nombre          TEXT NOT NULL,
    precio_unitario INTEGER NOT NULL,
    unidad          TEXT NOT NULL DEFAULT 'und',
    categoria       TEXT NOT NULL DEFAULT 'general',
    activo          INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS cotizaciones (
    numero                   TEXT PRIMARY KEY,
    cliente_nit              TEXT NOT NULL REFERENCES clientes(nit),
    estado                   TEXT NOT NULL,
    validez_dias             INTEGER NOT NULL,
    observaciones            TEXT DEFAULT '',
    fecha_emision            TEXT NOT NULL,
    descuento_adicional      INTEGER NOT NULL DEFAULT 0,
    tipo_descuento_adicional TEXT NOT NULL DEFAULT 'porcentaje',
    creado_en                TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cotizacion      TEXT NOT NULL REFERENCES cotizaciones(numero) ON DELETE CASCADE,
    sku             TEXT NOT NULL REFERENCES productos(sku),
    cantidad        TEXT NOT NULL,
    descuento_pct   TEXT NOT NULL DEFAULT '0',
    tipo_descuento  TEXT NOT NULL DEFAULT 'porcentaje',
    valor_descuento TEXT NOT NULL DEFAULT '0',
    bonificacion    INTEGER NOT NULL DEFAULT 0,
    orden           INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS ix_items_cotizacion ON items(cotizacion, orden);
CREATE INDEX IF NOT EXISTS ix_cotizaciones_estado ON cotizaciones(estado);
"""


class Database:
    """Envoltura minima sobre ``sqlite3`` con el esquema de CotizadorPro."""

    def __init__(self, path: str | Path = "cotizador.db") -> None:
        self.path = str(path)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    # --- ciclo de vida ------------------------------------------------------
    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:  # pragma: no cover - defensivo
            raise RuntimeError("conexion cerrada")
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.commit()
            self._conn.close()
            self._conn = None

    def sembrar(self, productos: list[Producto], clientes: list[Cliente]) -> None:
        """Inserta catalogo inicial solo si las tablas estan vacias."""
        cur = self.conn.cursor()
        if cur.execute("SELECT COUNT(*) FROM productos").fetchone()[0] == 0:
            cur.executemany(
                "INSERT INTO productos (sku,nombre,precio_unitario,unidad,categoria,activo)"
                " VALUES (?,?,?,?,?,?)",
                [
                    (
                        p.sku,
                        p.nombre,
                        moneda.a_centavos(p.precio_unitario),
                        p.unidad,
                        p.categoria,
                        int(p.activo),
                    )
                    for p in productos
                ],
            )
        if cur.execute("SELECT COUNT(*) FROM clientes").fetchone()[0] == 0:
            cur.executemany(
                "INSERT INTO clientes (nit,nombre,email,telefono,descuento_global,activo)"
                " VALUES (?,?,?,?,?,?)",
                [
                    (
                        c.nit,
                        c.nombre,
                        c.email,
                        c.telefono,
                        moneda.a_centavos(c.descuento_global),
                        int(c.activo),
                    )
                    for c in clientes
                ],
            )
        self.conn.commit()

    # --- productos ----------------------------------------------------------
    def producto(self, sku: str) -> Producto | None:
        fila = self.conn.execute(
            "SELECT * FROM productos WHERE sku=?", (sku,)
        ).fetchone()
        return self._producto(fila) if fila else None

    def productos(self, categoria: str | None = None) -> list[Producto]:
        sql = "SELECT * FROM productos WHERE activo=1"
        args: tuple = ()
        if categoria:
            sql += " AND categoria=?"
            args = (categoria,)
        return [
            self._producto(f)
            for f in self.conn.execute(sql + " ORDER BY categoria, nombre", args)
        ]

    @staticmethod
    def _producto(f: sqlite3.Row) -> Producto:
        return Producto(
            sku=f["sku"],
            nombre=f["nombre"],
            precio_unitario=moneda.de_centavos(f["precio_unitario"]),
            unidad=f["unidad"],
            categoria=f["categoria"],
            activo=bool(f["activo"]),
        )

    # --- clientes -----------------------------------------------------------
    def cliente(self, nit: str) -> Cliente | None:
        fila = self.conn.execute(
            "SELECT * FROM clientes WHERE nit=?", (nit,)
        ).fetchone()
        return self._cliente(fila) if fila else None

    def clientes(self) -> list[Cliente]:
        return [
            self._cliente(f)
            for f in self.conn.execute("SELECT * FROM clientes ORDER BY nombre")
        ]

    @staticmethod
    def _cliente(f: sqlite3.Row) -> Cliente:
        return Cliente(
            nit=f["nit"],
            nombre=f["nombre"],
            email=f["email"],
            telefono=f["telefono"],
            descuento_global=moneda.de_centavos(f["descuento_global"]),
            activo=bool(f["activo"]),
        )

    # --- cotizaciones -------------------------------------------------------
    def siguiente_numero(self, prefijo: str = "COT") -> str:
        import datetime as dt

        anio = dt.date.today().year
        prefijo_anio = f"{prefijo}-{anio}-"
        fila = self.conn.execute(
            "SELECT numero FROM cotizaciones WHERE numero LIKE ?"
            " ORDER BY numero DESC LIMIT 1",
            (prefijo_anio + "%",),
        ).fetchone()
        n = int(fila["numero"].rsplit("-", 1)[1]) + 1 if fila else 1
        return f"{prefijo_anio}{n:06d}"

    def guardar(self, cot: Cotizacion) -> Cotizacion:
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO cotizaciones (numero,cliente_nit,estado,validez_dias,observaciones,"
            "fecha_emision,descuento_adicional,tipo_descuento_adicional,creado_en)"
            " VALUES (?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(numero) DO UPDATE SET estado=excluded.estado,"
            " observaciones=excluded.observaciones, validez_dias=excluded.validez_dias,"
            " descuento_adicional=excluded.descuento_adicional,"
            " tipo_descuento_adicional=excluded.tipo_descuento_adicional",
            (
                cot.numero,
                cot.cliente.nit,
                cot.estado.value,
                cot.validez_dias,
                cot.observaciones,
                cot.fecha_emision.isoformat(),
                moneda.a_centavos(cot.descuento_adicional),
                cot.tipo_descuento_adicional.value,
                cot.creado_en.isoformat(timespec="seconds"),
            ),
        )
        cur.execute("DELETE FROM items WHERE cotizacion=?", (cot.numero,))
        cur.executemany(
            "INSERT INTO items (cotizacion,sku,cantidad,descuento_pct,tipo_descuento,"
            "valor_descuento,bonificacion,orden) VALUES (?,?,?,?,?,?,?,?)",
            [
                (
                    cot.numero,
                    i.producto.sku,
                    str(i.cantidad),
                    str(i.descuento_pct),
                    i.tipo_descuento.value,
                    str(i.valor_descuento),
                    int(i.bonificacion),
                    n,
                )
                for n, i in enumerate(cot.items)
            ],
        )
        self.conn.commit()
        return cot

    def cotizacion(self, numero: str) -> Cotizacion | None:
        fila = self.conn.execute(
            "SELECT * FROM cotizaciones WHERE numero=?", (numero,)
        ).fetchone()
        if fila is None:
            return None
        cliente = self.cliente(fila["cliente_nit"])
        if cliente is None:  # pragma: no cover - FK lo impide
            raise RuntimeError(f"cliente huerfano en {numero}")
        cot = Cotizacion(
            numero=numero,
            cliente=cliente,
            estado=EstadoCotizacion(fila["estado"]),
            validez_dias=fila["validez_dias"],
            observaciones=fila["observaciones"],
            fecha_emision=__import__("datetime").date.fromisoformat(
                fila["fecha_emision"]
            ),
            descuento_adicional=moneda.de_centavos(fila["descuento_adicional"]),
            tipo_descuento_adicional=TipoDescuento(fila["tipo_descuento_adicional"]),
        )
        for it in self.conn.execute(
            "SELECT * FROM items WHERE cotizacion=? ORDER BY orden", (numero,)
        ):
            producto = self.producto(it["sku"])
            if producto is None:  # pragma: no cover - FK lo impide
                continue
            cot.items.append(
                ItemCotizacion(
                    producto=producto,
                    cantidad=Decimal(it["cantidad"]),
                    descuento_pct=Decimal(it["descuento_pct"]),
                    tipo_descuento=TipoDescuento(it["tipo_descuento"]),
                    valor_descuento=Decimal(it["valor_descuento"]),
                    bonificacion=bool(it["bonificacion"]),
                )
            )
        return cot

    def cotizaciones(self, estado: str | None = None) -> list[Cotizacion]:
        sql = "SELECT numero FROM cotizaciones"
        args: tuple = ()
        if estado:
            sql += " WHERE estado=?"
            args = (estado,)
        numeros = [f["numero"] for f in self.conn.execute(sql + " ORDER BY numero DESC", args)]
        return [c for c in (self.cotizacion(n) for n in numeros) if c]

    # --- metricas -----------------------------------------------------------
    def tablero(self) -> dict:
        """Indicadores que alimentan el dashboard de la CLI y la demo web."""
        total = self.conn.execute(
            "SELECT COUNT(*) FROM cotizaciones"
        ).fetchone()[0]
        por_estado = {
            e.value: 0 for e in EstadoCotizacion
        }
        monto = {e.value: Decimal("0.00") for e in EstadoCotizacion}
        for f in self.conn.execute("SELECT * FROM cotizaciones"):
            por_estado[f["estado"]] = por_estado.get(f["estado"], 0) + 1
        # Los totales por estado se calculan con el motor real (no SQL), para
        # que el tablero y la cotizacion nunca discrepen por redondeo.
        montos: dict[str, Decimal] = {e.value: moneda.CERO for e in EstadoCotizacion}
        for numero in [f["numero"] for f in self.conn.execute("SELECT numero FROM cotizaciones")]:
            cot = self.cotizacion(numero)
            if cot is not None:
                montos[cot.estado.value] = moneda.q2(
                    montos.get(cot.estado.value, moneda.CERO) + cot.total
                )
        detalle = [
            {
                "estado": est.value,
                "etiqueta": est.etiqueta,
                "cantidad": por_estado.get(est.value, 0),
                "monto": str(montos[est.value]),
                "monto_legible": moneda.formatear(montos[est.value]),
            }
            for est in EstadoCotizacion
        ]
        return {
            "total_cotizaciones": total,
            "productos": self.conn.execute("SELECT COUNT(*) FROM productos").fetchone()[0],
            "clientes": self.conn.execute("SELECT COUNT(*) FROM clientes").fetchone()[0],
            "por_estado": detalle,
        }