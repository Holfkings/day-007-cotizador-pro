/* CotizadorPro — motor de calculo (puro, sin DOM).
   Este modulo replica `cotizador/modelo.py`. Es la version que corre la demo
   web y la que `tools/check_demo_contract.py` contrasta contra Python: si el
   navegador y la libreria divergen, el CI falla.

   Aritmetica en centavos enteros. Nunca float para dinero.               */

const IVA_PCT = 19;
const BONIFICACION_PCT = 25;

const PRODUCTOS = [
  { sku: "SRV-001", nombre: "Instalacion y puesta en marcha", precio: 185000000, unidad: "serv", categoria: "servicios" },
  { sku: "SRV-002", nombre: "Soporte tecnico mensual", precio: 42000000, unidad: "mes", categoria: "servicios" },
  { sku: "SRV-003", nombre: "Capacitacion por jornada", precio: 135000000, unidad: "jorn", categoria: "servicios" },
  { sku: "HW-NB-14", nombre: 'Portatil corporativo 14" i5 / 16 GB', precio: 235000000, unidad: "und", categoria: "hardware" },
  { sku: "HW-MN-27", nombre: 'Monitor 27" IPS QHD', precio: 98000000, unidad: "und", categoria: "hardware" },
  { sku: "HW-DS-10", nombre: "Estacion de trabajo SSD 1 TB NVMe", precio: 76000000, unidad: "und", categoria: "hardware" },
  { sku: "HW-RT-06", nombre: "Ruteador empresarial 6 puertos", precio: 54000000, unidad: "und", categoria: "hardware" },
  { sku: "SW-LIC-STD", nombre: "Licencia anual gestion de activos", precio: 89000000, unidad: "lic", categoria: "software" },
  { sku: "SW-LIC-PRO", nombre: "Licencia anual gestion de activos (Pro)", precio: 149000000, unidad: "lic", categoria: "software" },
  { sku: "SW-DEV-STD", nombre: "Licencia desarrollador - usuario/mes", precio: 6800000, unidad: "usr-mes", categoria: "software" },
  { sku: "INS-BC-20", nombre: "Plan de continuidad - hasta 20 usuarios", precio: 175000000, unidad: "plan", categoria: "infraestructura" },
  { sku: "INS-MIG-01", nombre: "Migracion de datos historicos", precio: 295000000, unidad: "serv", categoria: "infraestructura" },
];

const CLIENTES = [
  { nit: "900123456-1", nombre: "Comercializadora del Norte S.A.S.", desc: 0 },
  { nit: "900987654-3", nombre: "Distribuidora Andes Ltda.", desc: 3 },
  { nit: "830456789-0", nombre: "Grupo Salinas&Marmol S.A.S.", desc: 5 },
  { nit: "901444777-2", nombre: "Clinicas Vida S.A.S.", desc: 10 },
];

const q = (n) => Math.round(n);

function formatear(centavos) {
  const neg = centavos < 0;
  const abs = Math.abs(q(centavos));
  const miles = Math.floor(abs / 100);
  const resto = abs % 100;
  const grupos = [];
  let n = miles;
  while (n > 999) { grupos.unshift(String(n % 1000).padStart(3, "0")); n = Math.floor(n / 1000); }
  grupos.unshift(String(n));
  return `${neg ? "-" : ""}$${grupos.join(".")},${String(resto).padStart(2, "0")}`;
}

function calcularItem(item, producto) {
  const subtotal = q(producto.precio * item.cantidad);
  let montoDescuento;
  if (item.tipoDescuento === "valor_fijo") {
    montoDescuento = Math.min(item.valorDescuento, subtotal);
  } else {
    montoDescuento = q((subtotal * item.descuentoPct) / 100);
  }
  const base = subtotal - montoDescuento;
  const total = item.bonificacion ? q((base * (100 - BONIFICACION_PCT)) / 100) : base;
  return { ...item, producto, subtotal, montoDescuento, total };
}

function calcularCotizacion(cot) {
  const cliente = CLIENTES.find((c) => c.nit === cot.clienteNit) || CLIENTES[0];
  const items = cot.items.map((i) => calcularItem(i, PRODUCTOS.find((p) => p.sku === i.sku)));
  const subtotal = items.reduce((a, i) => a + i.subtotal, 0);
  const descuentosItems = items.reduce(
    (a, i) => a + i.montoDescuento + (i.bonificacion ? q((i.subtotal * BONIFICACION_PCT) / 100) : 0),
    0
  );
  const baseImponible = subtotal - descuentosItems;

  let descuentoGlobal;
  if (cot.tipoDescuentoAdicional === "valor_fijo") {
    descuentoGlobal = Math.min(cot.descuentoAdicional, baseImponible);
  } else {
    const pct = Math.min(cliente.desc + cot.descuentoAdicional, 100);
    descuentoGlobal = q((baseImponible * pct) / 100);
  }

  const subtotalFinal = baseImponible - descuentoGlobal;
  const iva = subtotalFinal > 0 ? q((subtotalFinal * IVA_PCT) / 100) : 0;
  const total = subtotalFinal + iva;

  return {
    ...cot,
    cliente,
    items,
    subtotal,
    descuentosItems,
    baseImponible,
    descuentoGlobal,
    subtotalFinal,
    iva,
    total,
  };
}

/* Expuesto como global para la pagina y para `tools/check_demo_contract.py`. */
window.CotizadorPro = { IVA_PCT, BONIFICACION_PCT, PRODUCTOS, CLIENTES, formatear, calcularItem, calcularCotizacion };