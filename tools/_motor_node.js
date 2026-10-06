/* Motor de calculo de la demo, ejecutado en Node para comparar contra Python.

   Uso (desde tools/):  node _motor_node.js < caso.json
   Imprime en stdout un JSON con los totales calculados en centavos.        */

const fs = require("fs");
const path = require("path");

// `motor.js` es un script de navegador: se carga inyectando un `window` stub.
global.window = global;
require(path.join(__dirname, "..", "docs", "motor.js"));
const motor = global.CotizadorPro;

const entrada = JSON.parse(fs.readFileSync(process.argv[2], "utf8", "utf8"));
const salida = entrada.map((cot) => {
  const c = motor.calcularCotizacion(cot);
  return {
    numero: cot.numero,
    subtotal: c.subtotal,
    descuentosItems: c.descuentosItems,
    baseImponible: c.baseImponible,
    descuentoGlobal: c.descuentoGlobal,
    subtotalFinal: c.subtotalFinal,
    iva: c.iva,
    total: c.total,
  };
});

process.stdout.write(JSON.stringify(salida));