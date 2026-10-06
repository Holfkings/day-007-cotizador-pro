/* CotizadorPro — demo interactiva.

La aritmetica vive en `motor.js` (mismo contrato que `cotizador/modelo.py`).
Este archivo solo maneja DOM, estado y presentacion.                   */

const { PRODUCTOS, CLIENTES, formatear, calcularCotizacion } = window.CotizadorPro;

const ESTADOS = [
  { id: "borrador", label: "Borrador" },
  { id: "enviada", label: "Enviada" },
  { id: "aceptada", label: "Aceptada" },
  { id: "rechazada", label: "Rechazada" },
  { id: "vencida", label: "Vencida" },
];

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

const CLAVE = "cotizadorpro:v1";
const hoyISO = () => new Date().toISOString().slice(0, 10);
const anioActual = () => new Date().getFullYear();

let cots = cargar();
let actual = cots[0] ? cots[0].numero : null;
let cantidad = 1;
let descuentoItem = 0;
let bonificacion = false;

// --- Persistencia ----------------------------------------------------------
function seed() {
  const base = [
    { nit: "901444777-2", items: [["SW-LIC-PRO", 15, 8, false], ["HW-MN-27", 15, 0, true], ["SRV-002", 12, 0, false]], estado: "aceptada", validez: 12 },
    { nit: "900987654-3", items: [["HW-DS-10", 8, 3, false], ["HW-RT-06", 8, 0, false]], estado: "enviada", validez: 30 },
    { nit: "900123456-1", items: [["INS-MIG-01", 1, 0, false], ["SRV-001", 1, 0, false]], estado: "borrador", validez: 20 },
    { nit: "830456789-0", items: [["HW-NB-14", 6, 4, false], ["SW-DEV-STD", 72, 0, false]], estado: "rechazada", validez: 10 },
  ];
  return base.map((b, i) => ({
    numero: `COT-${anioActual()}-${String(i + 1).padStart(6, "0")}`,
    clienteNit: b.nit,
    items: b.items.map(([sku, cant, desc, bonif]) => ({
      sku, cantidad: cant, descuentoPct: desc, tipoDescuento: "porcentaje", valorDescuento: 0, bonificacion: bonif,
    })),
    estado: b.estado,
    validezDias: b.validez,
    descuentoAdicional: 0,
    tipoDescuentoAdicional: "porcentaje",
    fechaEmision: hoyISO(),
  }));
}

function cargar() {
  try {
    const crudo = localStorage.getItem(CLAVE);
    const datos = crudo ? JSON.parse(crudo) : null;
    return datos && datos.length ? datos : seed();
  } catch {
    return seed();
  }
}

function guardar(lista) {
  localStorage.setItem(CLAVE, JSON.stringify(lista));
}

function nuevaCot(nit) {
  return {
    numero: `COT-${anioActual()}-${String(cots.length + 1).padStart(6, "0")}`,
    clienteNit: nit,
    items: [],
    estado: "borrador",
    validezDias: 15,
    descuentoAdicional: 0,
    tipoDescuentoAdicional: "porcentaje",
    fechaEmision: hoyISO(),
  };
}

// --- Derivados -------------------------------------------------------------
function actualCot() {
  return cots.find((c) => c.numero === actual) || null;
}

function nombreCliente(nit) {
  return CLIENTES.find((c) => c.nit === nit)?.nombre || nit;
}

function nombreEstado(id) {
  return ESTADOS.find((e) => e.id === id)?.label || id;
}

function conVigencia(calc) {
  const vence = new Date(calc.fechaEmision + "T00:00:00");
  vence.setDate(vence.getDate() + calc.validezDias);
  const hoy = new Date();
  hoy.setHours(0, 0, 0, 0);
  const dias = Math.round((vence - hoy) / 86400000);
  const vigente = dias >= 0 && ["borrador", "enviada"].includes(calc.estado);
  return { ...calc, fechaVencimiento: vence.toISOString().slice(0, 10), diasParaVencer: dias, vigente };
}

// --- Avisos ----------------------------------------------------------------
function aviso(msg) {
  const box = $("#aviso");
  if (!box) return;
  box.textContent = msg;
  box.style.opacity = msg ? "1" : "0";
  clearTimeout(box._t);
  box._t = setTimeout(() => { box.textContent = ""; box.style.opacity = "0"; }, 2600);
}

// --- Render ----------------------------------------------------------------
function persistirYRender() {
  guardar(cots);
  render();
}

function render() {
  renderCatalogo();
  renderCotizacion();
  renderTablero();
}

function renderCatalogo() {
  const cont = $("#catalogo");
  if (!cont) return;
  const filtro = ($("#buscar")?.value || "").toLowerCase();
  cont.innerHTML = "";
  const lista = PRODUCTOS.filter(
    (p) => !filtro || p.nombre.toLowerCase().includes(filtro) || p.sku.toLowerCase().includes(filtro)
  );
  if (!lista.length) {
    cont.innerHTML = '<p class="empty">Sin coincidencias.</p>';
    return;
  }
  lista.forEach((p) => {
    const el = document.createElement("button");
    el.className = "prod";
    el.type = "button";
    el.innerHTML = `
      <div>
        <div class="name">${p.nombre}</div>
        <div class="sku">${p.sku} · ${p.categoria}</div>
      </div>
      <div class="price">${formatear(p.precio)}<span class="sku"> / ${p.unidad}</span></div>`;
    el.addEventListener("click", () => agregarProducto(p.sku));
    cont.appendChild(el);
  });
}

function agregarProducto(sku) {
  const c = actualCot();
  if (!c) return aviso("Crea una cotizacion primero");
  if (c.estado !== "borrador") return aviso(`Estado ${c.estado}: la cotizacion ya no admite cambios`);
  if (c.items.some((i) => i.sku === sku)) return aviso(`${sku} ya esta en la cotizacion`);
  c.items.push({
    sku,
    cantidad,
    descuentoPct: descuentoItem,
    tipoDescuento: "porcentaje",
    valorDescuento: 0,
    bonificacion,
  });
  persistirYRender();
}

function renderCotizacion() {
  const sel = $("#selector");
  if (sel) {
    sel.innerHTML = cots
      .map((c) => `<option value="${c.numero}"${c.numero === actual ? " selected" : ""}>${c.numero} — ${nombreCliente(c.clienteNit)}</option>`)
      .join("");
  }
  const c = actualCot();
  const zona = $("#detalle");
  if (!zona) return;
  if (!c) {
    zona.innerHTML = '<p class="empty">No hay cotizaciones. Crea una con el boton «Crear borrador».</p>';
    return;
  }
  const calc = conVigencia(calcularCotizacion(c));
  const editable = c.estado === "borrador";
  const pill = $("#estado-pill");
  if (pill) {
    pill.className = `est-pill ${c.estado}`;
    pill.textContent = nombreEstado(c.estado);
  }

  zona.innerHTML = `
    <div class="row" style="margin-bottom:18px">
      <label class="field"><span>Cliente</span>
        <select id="sel-cliente" ${editable ? "" : "disabled"}>
          ${CLIENTES.map((cl) => `<option value="${cl.nit}"${cl.nit === c.clienteNit ? " selected" : ""}>${cl.nombre}</option>`).join("")}
        </select>
      </label>
      <label class="field"><span>Vigencia (dias)</span>
        <input id="validez" type="number" min="1" max="180" value="${c.validezDias}" ${editable ? "" : "disabled"} />
      </label>
    </div>

    <table>
      <thead><tr><th>Concepto</th><th>Cant.</th><th>P. unit.</th><th>Desc.</th><th>Total</th><th></th></tr></thead>
      <tbody>
        ${calc.items.length === 0
          ? '<tr><td colspan="6" class="empty">Agrega productos desde el catalogo.</td></tr>'
          : calc.items.map((i) => `
            <tr>
              <td>
                <div>${i.producto.nombre}</div>
                <div style="font-size:11px;color:var(--muted)">${i.sku}</div>
              </td>
              <td>${i.cantidad} ${i.producto.unidad}</td>
              <td>${formatear(i.producto.precio)}</td>
              <td>${i.bonificacion ? '<span class="tag-mini bonif">bonif. -25%</span>' : i.descuentoPct ? `<span class="tag-mini">-${i.descuentoPct}%</span>` : "—"}</td>
              <td class="strong">${formatear(i.total)}</td>
              <td>${editable ? `<button class="link" data-quitar="${i.sku}">quitar</button>` : ""}</td>
            </tr>`).join("")}
      </tbody>
    </table>

    <div class="totals">
      <div class="line"><span>Subtotal lista</span><span>${formatear(calc.subtotal)}</span></div>
      <div class="line disc"><span>Descuentos por concepto</span><span>-${formatear(calc.descuentosItems)}</span></div>
      <div class="line disc"><span>Descuento cliente ${calc.cliente.desc}%${c.descuentoAdicional ? " + " + c.descuentoAdicional + "%" : ""}</span><span>-${formatear(calc.descuentoGlobal)}</span></div>
      <div class="line"><span>Subtotal</span><span>${formatear(calc.subtotalFinal)}</span></div>
      <div class="line"><span>IVA 19%</span><span>${formatear(calc.iva)}</span></div>
      <div class="line total"><span>Total</span><span>${formatear(calc.total)}</span></div>
    </div>

    <div class="estados">
      ${ESTADOS.map((e) => `<span class="est-pill ${e.id}" style="${e.id === c.estado ? "" : "opacity:.4"}">${e.label}</span>`).join("")}
    </div>

    <div class="actions">
      <select id="estado-sel" style="max-width:210px">
        ${ESTADOS.map((e) => `<option value="${e.id}"${e.id === c.estado ? " selected" : ""}>Marcar como ${e.label.toLowerCase()}</option>`).join("")}
      </select>
      <button class="primary" id="btn-duplicar">Duplicar como borrador</button>
      <button id="btn-borrar">Eliminar</button>
    </div>

    <p class="note">Vence el ${calc.fechaVencimiento} — ${calc.diasParaVencer} dias.
      ${calc.vigente ? "Cotizacion vigente." : "No vigente."} Numero ${c.numero}, emitida ${c.fechaEmision}.</p>`;

  $$("[data-quitar]").forEach((b) =>
    b.addEventListener("click", () => {
      c.items = c.items.filter((i) => i.sku !== b.dataset.quitar);
      persistirYRender();
    })
  );
  $("#sel-cliente")?.addEventListener("change", (e) => { c.clienteNit = e.target.value; persistirYRender(); });
  $("#validez")?.addEventListener("change", (e) => { c.validezDias = Math.max(1, parseInt(e.target.value, 10) || 15); persistirYRender(); });
  $("#estado-sel")?.addEventListener("change", (e) => { c.estado = e.target.value; persistirYRender(); });
  $("#btn-duplicar").addEventListener("click", () => duplicar(c.numero));
  $("#btn-borrar").addEventListener("click", () => borrar(c.numero));
}

function duplicar(numero) {
  const src = cots.find((c) => c.numero === numero);
  if (!src) return;
  const copia = JSON.parse(JSON.stringify(src));
  copia.numero = `COT-${anioActual()}-${String(cots.length + 1).padStart(6, "0")}`;
  copia.estado = "borrador";
  copia.fechaEmision = hoyISO();
  cots.push(copia);
  actual = copia.numero;
  persistirYRender();
  aviso(`Borrador ${copia.numero} creado`);
}

function borrar(numero) {
  if (!confirm(`Eliminar ${numero}?`)) return;
  cots = cots.filter((c) => c.numero !== numero);
  if (actual === numero) actual = cots[0]?.numero || null;
  persistirYRender();
}

function renderTablero() {
  const calc = cots.map(conVigencia);
  const total = calc.reduce((a, c) => a + c.total, 0);
  const pipeline = calc.filter((c) => c.estado === "enviada").reduce((a, c) => a + c.total, 0);
  const ahorro = calc.reduce((a, c) => a + (c.subtotal - c.subtotalFinal), 0);
  const ganadas = calc.filter((c) => c.estado === "aceptada").length;

  $("#kpi-total").textContent = formatear(total);
  $("#kpi-pipeline").textContent = formatear(pipeline);
  $("#kpi-ahorro").textContent = formatear(ahorro);
  $("#kpi-aceptadas").textContent = String(ganadas);

  const monto = (id) => calc.filter((c) => c.estado === id).reduce((a, c) => a + c.total, 0);
  const max = Math.max(...ESTADOS.map((e) => monto(e.id)), 1);
  $("#funnel").innerHTML = ESTADOS.map((e) => `
    <div class="fbar">
      <span class="lbl">${e.label}</span>
      <span class="track"><span class="fill" style="width:${(monto(e.id) / max) * 100}%"></span></span>
      <span class="amt">${formatear(monto(e.id))} · ${calc.filter((c) => c.estado === e.id).length}</span>
    </div>`).join("");
}

// --- Arranque --------------------------------------------------------------
function init() {
  $("#selector")?.addEventListener("change", (e) => { actual = e.target.value; render(); });
  $("#buscar")?.addEventListener("input", renderCatalogo);

  $("#cantidad")?.addEventListener("input", (e) => { cantidad = Math.max(1, parseInt(e.target.value, 10) || 1); });
  $("#desc-item")?.addEventListener("input", (e) => { descuentoItem = Math.min(100, Math.max(0, parseFloat(e.target.value) || 0)); });
  $("#bonif")?.addEventListener("change", (e) => { bonificacion = e.target.checked; });

  $("#btn-nueva")?.addEventListener("click", () => {
    const c = nuevaCot($("#sel-cliente-nueva")?.value || CLIENTES[0].nit);
    cots.push(c);
    actual = c.numero;
    persistirYRender();
    aviso(`Cotizacion ${c.numero} creada`);
  });

  $("#btn-desc-global")?.addEventListener("click", () => {
    const c = actualCot();
    if (!c) return;
    if (c.estado !== "borrador") return aviso(`Estado ${c.estado}: la cotizacion ya no admite cambios`);
    c.descuentoAdicional = Math.min(100, Math.max(0, parseFloat($("#desc-global").value) || 0));
    persistirYRender();
    aviso("Descuento adicional aplicado");
  });

  $("#btn-reset")?.addEventListener("click", () => {
    if (!confirm("Restablecer la demo a los datos de ejemplo?")) return;
    cots = seed();
    actual = cots[0].numero;
    persistirYRender();
  });

  const selNueva = $("#sel-cliente-nueva");
  if (selNueva) selNueva.innerHTML = CLIENTES.map((c) => `<option value="${c.nit}">${c.nombre}</option>`).join("");
  render();
}

document.addEventListener("DOMContentLoaded", init);