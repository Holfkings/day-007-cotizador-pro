"""Catalogo de productos y clientes semilla.

El catalogo se carga en la BD solo si esta vacia (``catalogo.seed``), de modo
que la CLI arranca con datos de trabajo sin que el usuario teclee 20 SKUs.
"""

from __future__ import annotations

from decimal import Decimal

from cotizador.modelo import Cliente, Producto

PRODUCTOS: list[Producto] = [
    Producto("SRV-001", "Instalacion y puesta en marcha", "1850000", "serv", "servicios"),
    Producto("SRV-002", "Soporte tecnico mensual", "420000", "mes", "servicios"),
    Producto("SRV-003", "Capacitacion por jornada", "1350000", "jorn", "servicios"),
    Producto("HW-NB-14", "Portatil corporativo 14\" i5 / 16 GB", "2350000", "und", "hardware"),
    Producto("HW-MN-27", "Monitor 27\" IPS QHD", "980000", "und", "hardware"),
    Producto("HW-DS-10", "Estacion de trabajo SSD 1 TB NVMe", "760000", "und", "hardware"),
    Producto("HW-RT-06", "Ruteador empresarial 6 puertos", "540000", "und", "hardware"),
    Producto("SW-LIC-STD", "Licencia anual gestion de activos", "890000", "lic", "software"),
    Producto("SW-LIC-PRO", "Licencia anual gestion de activos (Pro)", "1490000", "lic", "software"),
    Producto("SW-DEV-STD", "Licencia desarrollador - usuario/mes", "68000", "usr-mes", "software"),
    Producto("INS-BC-20", "Plan de continuidad - hasta 20 usuarios", "1750000", "plan", "infraestructura"),
    Producto("INS-MIG-01", "Migracion de datos historicos", "2950000", "serv", "infraestructura"),
]

CLIENTES: list[Cliente] = [
    Cliente("900123456-1", "Comercializadora del Norte S.A.S.", "compras@comercializadora.example", "+57 300 555 0142"),
    Cliente("900987654-3", "Distribuidora Andes Ltda.", "logistica@andes.example", "+57 311 555 0198", Decimal("3")),
    Cliente("830456789-0", "Grupo Salinas&Marmol S.A.S.", "purchasing@salinosmarmol.example", "+57 315 555 0177", Decimal("5")),
    Cliente("901444777-2", "Clinicas Vida S.A.S.", "compras@clinicasvida.example", "+57 320 555 0110", Decimal("10")),
]

__all__ = ["PRODUCTOS", "CLIENTES"]