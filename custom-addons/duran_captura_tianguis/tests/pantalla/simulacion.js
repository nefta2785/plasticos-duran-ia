/* Simulación del servidor y ayudantes para las pruebas de pantalla.
 *
 * Reemplaza window.fetch: las rutas /captura/api/* responden con los datos de
 * abajo, sin Odoo. Se carga ANTES que static/src/captura.js (ver correr.mjs). */

const datos = {
    "/captura/api/zonas": [
        { id: 1, nombre: "Bosques" },
        { id: 2, nombre: "Guadalupana" }, // sin clientes
    ],
    "/captura/api/clientes": (p) =>
        p.zona_id === 1
            ? [
                  { id: 9, nombre: "Doña Carmen" }, // sin historial
                  { id: 7, nombre: "<b>Cliente con HTML</b>" }, // debe verse como texto
                  { id: 12, nombre: "Cliente con historial" },
                  { id: 13, nombre: "Tortillería La Guadalupana de Doña Lupita" }, // nombre largo
              ]
            : [],
    "/captura/api/habituales": (p) =>
        p.cliente_id === 12
            ? [
                  { id: 464, nombre: "Estrella 25x35", unidad: "c/u", es_peso_variable: true, precio: 85, precio_texto: "$85/kg" },
                  { id: 440, nombre: "Blanca #2", unidad: "kg", es_peso_variable: false, precio: 70, precio_texto: "$70/kg" },
              ]
            : [],
    "/captura/api/catalogo": [
        {
            id: 4,
            nombre: "Bolsas asa",
            productos: [
                { id: 440, nombre: "Blanca #2", unidad: "kg", es_peso_variable: false, precio: 70, precio_texto: "$70/kg" },
                { id: 409, nombre: "Caja 25x35 (5kg)", unidad: "c/u", es_peso_variable: false, precio: 325, precio_texto: "$325 c/u" },
            ],
        },
        {
            id: 8,
            nombre: "Rollos",
            productos: [
                { id: 464, nombre: "Estrella 25x35", unidad: "c/u", es_peso_variable: true, precio: 85, precio_texto: "$85/kg" },
            ],
        },
    ],
};

// /captura/api/enviar: "ok", o fallar UNA vez sin red ("sin-red") o con error del servidor ("error").
let modoEnvio = "ok";
const envios = []; // parámetros de cada envío recibido
const llamadas = []; // rutas llamadas, en orden
const foliosPorToken = new Map(); // simula el captura_token único del servidor
let siguienteFolio = 50;

function enviarSimulado(params) {
    envios.push(params);
    if (modoEnvio === "sin-red") {
        // El servidor SÍ creó la orden, pero la respuesta no llegó.
        modoEnvio = "ok";
        foliosPorToken.set(params.token, `S000${siguienteFolio++}`);
        throw new TypeError("Failed to fetch");
    }
    if (modoEnvio === "error") {
        modoEnvio = "ok";
        return {
            error: {
                code: 200,
                message: "Odoo Server Error",
                data: {
                    name: "odoo.exceptions.UserError",
                    message: "Estos productos ya no están a la venta: Blanca #2. Quítalos del pedido e intenta de nuevo.",
                },
            },
        };
    }
    const yaExistia = foliosPorToken.has(params.token);
    const nombre = yaExistia ? foliosPorToken.get(params.token) : `S000${siguienteFolio++}`;
    foliosPorToken.set(params.token, nombre);
    return {
        result: {
            id: 1,
            nombre,
            cliente: "Doña Carmen",
            zona: "Bosques",
            productos: params.lineas.reduce((total, l) => total + l.cantidad, 0),
            ya_existia: yaExistia,
        },
    };
}

// === Modo Entrega ===

const ESTRELLA = { id: 464, nombre: "Estrella 25x35", unidad: "c/u", es_peso_variable: true, precio: 85, precio_texto: "$85/kg" };
const BLANCA = { id: 440, nombre: "Blanca #2", unidad: "kg", es_peso_variable: false, precio: 70, precio_texto: "$70/kg" };
const CAJA = { id: 409, nombre: "Caja 25x35 (5kg)", unidad: "c/u", es_peso_variable: false, precio: 325, precio_texto: "$325 c/u" };
const mov = (move_id, cantidad, sin_existencia, precio) => ({
    move_id, cantidad, reservada: sin_existencia ? 0 : cantidad, sin_existencia, precio,
});
let otraPersonaCambio = false; // tras "cambiaron": a Doña Carmen ya no le queda el rollo 102 ni la caja
const pendientes = {
    9: () => ({
        cliente: { id: 9, nombre: "Doña Carmen" },
        productos: [
            {
                ...ESTRELLA, cantidad: otraPersonaCambio ? 1 : 2, sin_existencia: !otraPersonaCambio,
                movimientos: otraPersonaCambio ? [mov(101, 1, false, 85)] : [mov(101, 1, false, 85), mov(102, 1, true, 85)],
            },
            { ...BLANCA, cantidad: 3, sin_existencia: false, movimientos: [mov(103, 3, false, 70)] },
            ...(otraPersonaCambio ? [] : [{ ...CAJA, cantidad: 2, sin_existencia: true, movimientos: [mov(104, 2, true, 325)] }]),
        ],
    }),
    12: () => ({
        cliente: { id: 12, nombre: "Cliente con historial" },
        productos: [{ ...ESTRELLA, cantidad: 1, sin_existencia: false, movimientos: [mov(201, 1, false, 85)] }],
    }),
};
const productoDeMovimiento = (moveId) =>
    Object.values(pendientes).flatMap((f) => f().productos).find((p) => p.movimientos.some((m) => m.move_id === moveId));
const redondear = (n) => Math.round(n * 100) / 100;

function revisarPesoSimulado(texto) {
    // Mismas reglas que el servidor con los límites de fábrica (15 / 0.5 / 8).
    const r = { peso: null, bloqueo: null, advertencias: [], sugerencia: null };
    const m = /^(\d+)(?:[.,](\d+))?$/.exec((texto || "").trim());
    if (!m) {
        r.bloqueo = "Escribe el peso en kg, por ejemplo 1.250.";
        return r;
    }
    if (m[2] && m[2].length > 3) {
        r.bloqueo = "El peso lleva máximo 3 decimales.";
        return r;
    }
    r.peso = Number(`${m[1]}.${m[2] || 0}`);
    if (m[2] === undefined && r.peso >= 100) {
        r.sugerencia = r.peso / 1000;
        r.advertencias.push(`¿Quisiste decir ${r.sugerencia.toFixed(3)} kg?`);
    }
    if (r.peso <= 0) r.bloqueo = "El peso debe ser mayor a 0 kg.";
    else if (r.peso > 15) r.bloqueo = "Un rollo no puede pesar más de 15 kg.";
    else if (r.peso < 0.5) r.advertencias.push("Pesa menos de 0.5 kg: revisa que esté bien.");
    else if (r.peso > 8) r.advertencias.push("Pesa más de 8 kg: revisa que esté bien.");
    return r;
}

const vistasPrevias = []; // parámetros de cada vista previa
function vistaPreviaSimulada(p) {
    vistasPrevias.push(p);
    const rollos = p.rollos.map(({ move_id, peso }) => {
        const producto = productoDeMovimiento(move_id);
        const r = revisarPesoSimulado(peso);
        return { move_id, producto_id: producto.id, nombre: producto.nombre, precio: producto.precio, ...r, importe: null };
    });
    const puede = rollos.every((r) => !r.bloqueo);
    const productos = p.productos.map(({ producto_id, cantidad }) => {
        const producto = [BLANCA, CAJA].find((x) => x.id === producto_id);
        return { id: producto_id, nombre: producto.nombre, unidad: producto.unidad, cantidad, importe: puede ? redondear(cantidad * producto.precio) : null };
    });
    if (puede) rollos.forEach((r) => (r.importe = redondear(r.peso * r.precio)));
    const total = puede ? redondear([...rollos, ...productos].reduce((t, x) => t + x.importe, 0)) : null;
    return {
        cliente: pendientes[p.cliente_id]().cliente, rollos, productos,
        total, total_texto: puede ? `$${total.toFixed(2)}` : null, puede_confirmar: puede,
    };
}

// /captura/api/entrega/confirmar: "ok", o fallar UNA vez: "sin-red", "cambiaron".
let modoConfirmar = "ok";
const confirmaciones = []; // parámetros de cada confirmación recibida
const entregasPorToken = new Map();
function confirmarSimulado(p) {
    confirmaciones.push(p);
    const modo = modoConfirmar;
    modoConfirmar = "ok";
    if (entregasPorToken.has(p.token)) {
        return { result: { ...entregasPorToken.get(p.token), ya_existia: true } };
    }
    if (modo === "cambiaron") {
        otraPersonaCambio = true;
        return {
            error: {
                code: 200, message: "Odoo Server Error",
                data: {
                    name: "odoo.exceptions.UserError",
                    message: "Las entregas de este cliente cambiaron desde que se cargaron (alguien más las validó, canceló o modificó). Regresa y vuelve a abrir al cliente.",
                },
            },
        };
    }
    const vista = vistaPreviaSimulada(p);
    vistasPrevias.pop();
    const nada = !p.rollos.length && !p.productos.length;
    const resultado = {
        id: 1, cliente: vista.cliente.nombre, total: vista.total, total_texto: vista.total_texto,
        entregas: [
            { folio: "WH/OUT/00031", orden: "S00050", estado: nada ? "cancelada" : "validada" },
            { folio: "WH/OUT/00032", orden: "S00051", estado: "cancelada" },
        ],
        ya_existia: false,
    };
    entregasPorToken.set(p.token, resultado);
    if (modo === "sin-red") {
        throw new TypeError("Failed to fetch"); // la entrega SÍ quedó, pero la respuesta no llegó
    }
    return { result: resultado };
}

const datosEntrega = {
    "/captura/api/entrega/clientes": (p) =>
        p.zona_id === 1 ? [{ id: 9, nombre: "Doña Carmen" }, { id: 12, nombre: "Cliente con historial" }] : [],
    "/captura/api/entrega/pendiente": (p) => pendientes[p.cliente_id](),
};

window.fetch = async (ruta, opciones) => {
    const params = JSON.parse(opciones.body).params;
    llamadas.push(ruta);
    let cuerpo;
    if (ruta === "/captura/api/enviar") {
        await espera(60); // el servidor tarda un poco: da tiempo al doble toque
        cuerpo = enviarSimulado(params);
    } else if (ruta === "/captura/api/entrega/confirmar") {
        await espera(60);
        cuerpo = confirmarSimulado(params);
    } else if (ruta === "/captura/api/entrega/vista_previa") {
        await espera(20);
        cuerpo = { result: vistaPreviaSimulada(params) };
    } else if (datosEntrega[ruta]) {
        cuerpo = { result: datosEntrega[ruta](params) };
    } else {
        const d = datos[ruta];
        cuerpo = { result: typeof d === "function" ? d(params) : d };
    }
    return { ok: true, json: async () => ({ jsonrpc: "2.0", id: null, ...cuerpo }) };
};

// === Ayudantes ===

const resultados = [];
const espera = (ms = 30) => new Promise((resolver) => setTimeout(resolver, ms));
const q = (selector) => document.querySelector(selector);
const qa = (selector) => [...document.querySelectorAll(selector)];
const txt = (selector) => (q(selector) ? q(selector).textContent.trim() : null);
const boton = (texto) => qa("button").find((b) => b.textContent.trim() === texto && b.offsetParent !== null);
const pestana = (nombre) => qa(".categoria").find((b) => b.firstChild.textContent === nombre);
const nombresPestanas = () => qa(".categoria").map((b) => b.firstChild.textContent);
const modo = (nombre) => qa(".btn-modo").find((b) => b.querySelector(".modo-nombre").textContent === nombre);
const tarjeta = (id) => q(`[data-producto="${id}"]`);
const cantidad = (id) => {
    const c = tarjeta(id) && tarjeta(id).querySelector(".producto-cantidad");
    return c ? c.textContent : null;
};
const renglon = (clave) => q(`[data-renglon="${clave}"]`);
const campoPeso = (moveId) => q(`[data-renglon="m${moveId}"] .peso-campo`);
const ecoDe = (moveId) => txt(`[data-renglon="m${moveId}"] .peso-eco`);
const mensajeDe = (clave) => {
    const nodo = renglon(clave) && renglon(clave).querySelector(".renglon-mensaje");
    return nodo && !nodo.hidden ? nodo.textContent : null;
};
const botonNoLlevo = (clave) => renglon(clave).querySelector(".btn-no-llevo");
const cantidadEntrega = (clave) => txt(`[data-renglon="${clave}"] .cantidad-entrega`);

async function escribirPeso(moveId, texto) {
    const campo = campoPeso(moveId);
    campo.value = texto;
    campo.dispatchEvent(new Event("input", { bubbles: true }));
    await espera(5);
}

async function responderModal(si) {
    q(si ? "#modal-si" : "#modal-no").click();
    await espera(150);
}

const llamadasA = (final) => llamadas.filter((ruta) => ruta.endsWith(final)).length;

async function tocarProducto(id, veces = 1) {
    for (let i = 0; i < veces; i++) {
        tarjeta(id).querySelector(".producto-sumar").click();
        await espera(5);
    }
}

async function regresar() {
    q("#btn-regresar").click();
    await espera(120);
}

function check(nombre, obtenido, esperado) {
    const ok = JSON.stringify(obtenido) === JSON.stringify(esperado);
    resultados.push(
        `${ok ? "OK   " : "FALLA"} | ${nombre}` +
            (ok ? "" : ` | esperado=${JSON.stringify(esperado)} | obtenido=${JSON.stringify(obtenido)}`)
    );
}
