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

window.fetch = async (ruta, opciones) => {
    const params = JSON.parse(opciones.body).params;
    llamadas.push(ruta);
    let cuerpo;
    if (ruta === "/captura/api/enviar") {
        await espera(60); // el servidor tarda un poco: da tiempo al doble toque
        cuerpo = enviarSimulado(params);
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
const tarjeta = (id) => q(`[data-producto="${id}"]`);
const cantidad = (id) => {
    const c = tarjeta(id) && tarjeta(id).querySelector(".producto-cantidad");
    return c ? c.textContent : null;
};
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
