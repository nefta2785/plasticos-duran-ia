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
        (p.zona_id === 1
            ? [
                  { id: 9, nombre: "Doña Carmen" }, // sin historial
                  { id: 7, nombre: "<b>Cliente con HTML</b>" }, // debe verse como texto
                  { id: 12, nombre: "Cliente con historial" },
                  { id: 13, nombre: "Tortillería La Guadalupana de Doña Lupita" }, // nombre largo
              ]
            : []
        ).concat(clientesCreados.filter((c) => c.zona_id === p.zona_id).map(({ id, nombre }) => ({ id, nombre }))),
    "/captura/api/habituales": (p) =>
        p.cliente_id === 12
            ? [
                  { id: 464, nombre: "Estrella 25x35", unidad: "c/u", por_kg: false, es_peso_variable: true, precio: 85, precio_texto: "$85/kg" },
                  { id: 440, nombre: "Blanca #2", unidad: "kg", por_kg: true, es_peso_variable: false, precio: 70, precio_texto: "$70/kg" },
              ]
            : [],
    "/captura/api/catalogo": [
        {
            id: 4,
            nombre: "Bolsas asa",
            productos: [
                { id: 440, nombre: "Blanca #2", unidad: "kg", por_kg: true, es_peso_variable: false, precio: 70, precio_texto: "$70/kg" },
                { id: 409, nombre: "Caja 25x35 (5kg)", unidad: "c/u", por_kg: false, es_peso_variable: false, precio: 325, precio_texto: "$325 c/u" },
                // Se pesa, pero se vende por kg: su cantidad dice kg, no rollos.
                { id: 472, nombre: "Hoja polipapel 25x35 (KG suelto)", unidad: "kg", por_kg: true, es_peso_variable: true, precio: 70, precio_texto: "$70/kg" },
            ],
        },
        {
            id: 8,
            nombre: "Rollos",
            productos: [
                { id: 464, nombre: "Estrella 25x35", unidad: "c/u", por_kg: false, es_peso_variable: true, precio: 85, precio_texto: "$85/kg" },
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

// === Cliente nuevo (modo Pedido) ===

// /captura/api/cliente/nuevo: "ok", o UNA vez "sin-red" (el cliente SÍ se crea,
// pero la respuesta no llega). Parecidos con las mismas reglas que el servidor.
let modoClienteNuevo = "ok";
const clientesCreados = []; // {id, nombre, zona_id, token}
const altasCliente = []; // parámetros de cada alta recibida
const ZONAS_SIM = { 1: "Bosques", 2: "Guadalupana" };
const CONTACTOS_CON_ZONA = () => [
    { id: 9, nombre: "Doña Carmen", zona_id: 1, activo: true },
    { id: 7, nombre: "<b>Cliente con HTML</b>", zona_id: 1, activo: true },
    { id: 12, nombre: "Cliente con historial", zona_id: 1, activo: true },
    { id: 13, nombre: "Tortillería La Guadalupana de Doña Lupita", zona_id: 1, activo: true },
    { id: 31, nombre: "Tortillería El Sol", zona_id: 2, activo: true }, // de otra zona
    { id: 32, nombre: "Tortillería Vieja", zona_id: 1, activo: false }, // archivado
    ...clientesCreados.map((c) => ({ ...c, activo: true })),
];
const normalizarNombre = (texto) =>
    texto.normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase().split(/\s+/).filter(Boolean).join(" ");

function crearClienteSimulado(p) {
    altasCliente.push(p);
    const nombre = (p.nombre || "").trim().split(/\s+/).filter(Boolean).join(" ");
    const error = (mensaje) => ({
        error: { code: 200, message: "Odoo Server Error", data: { name: "odoo.exceptions.UserError", message: mensaje } },
    });
    if (!nombre) return error("Escribe el nombre del cliente.");
    if (/[^\p{L}\p{Nd} .,'\-&#()/]/u.test(nombre)) {
        return error("El nombre solo puede llevar letras, números, espacios y . , ' - & # ( ) /");
    }
    const ya = clientesCreados.find((c) => c.token === p.token);
    if (ya) return { result: { cliente: { id: ya.id, nombre: ya.nombre }, ya_existia: true } };
    const buscado = normalizarNombre(nombre);
    const parecidos = CONTACTOS_CON_ZONA()
        .map((c) => {
            const otro = normalizarNombre(c.nombre);
            const [corto, largo] = [buscado, otro].sort((a, b) => a.length - b.length);
            const identico = otro === buscado;
            if (!identico && !(corto.length >= 4 && largo.includes(corto))) return null;
            const misma = c.zona_id === p.zona_id;
            return {
                id: misma && c.activo ? c.id : false, nombre: c.nombre, zona: ZONAS_SIM[c.zona_id],
                misma_zona: misma, archivado: !c.activo, identico,
            };
        })
        .filter(Boolean)
        .sort((a, b) => (b.identico - a.identico) || (b.misma_zona - a.misma_zona) || (a.archivado - b.archivado))
        .slice(0, 5);
    const bloqueado = parecidos.some((x) => x.identico && x.misma_zona && !x.archivado);
    if (parecidos.length && (!p.es_otro || bloqueado)) {
        return { result: { parecidos, puede_crear: !bloqueado } };
    }
    const nuevo = { id: 900 + clientesCreados.length, nombre, zona_id: p.zona_id, token: p.token };
    clientesCreados.push(nuevo);
    if (modoClienteNuevo === "sin-red") {
        modoClienteNuevo = "ok";
        throw new TypeError("Failed to fetch");
    }
    return { result: { cliente: { id: nuevo.id, nombre }, ya_existia: false } };
}

// === Modo Entrega ===

const ESTRELLA = { id: 464, nombre: "Estrella 25x35", unidad: "c/u", por_kg: false, es_peso_variable: true, precio: 85, precio_texto: "$85/kg" };
const BLANCA = { id: 440, nombre: "Blanca #2", unidad: "kg", por_kg: true, es_peso_variable: false, precio: 70, precio_texto: "$70/kg" };
const CAJA = { id: 409, nombre: "Caja 25x35 (5kg)", unidad: "c/u", por_kg: false, es_peso_variable: false, precio: 325, precio_texto: "$325 c/u" };
const BOLSA_BASURA = { id: 470, nombre: "Bolsa de basura 60x90", unidad: "kg", por_kg: true, es_peso_variable: false, precio: 45, precio_texto: "$45/kg" };
const KG_SUELTO = { id: 472, nombre: "Hoja polipapel 25x35 (KG suelto)", unidad: "kg", por_kg: true, es_peso_variable: true, precio: 70, precio_texto: "$70/kg" };
const SUIZO = { id: 471, nombre: "Suizo 18x25", unidad: "kg", por_kg: true, es_peso_variable: false, precio: 67, precio_texto: "$67/kg" };
const mov = (move_id, cantidad, sin_existencia, precio) => ({
    move_id, cantidad, reservada: sin_existencia ? 0 : cantidad, sin_existencia, precio,
});
let otraPersonaCambio = false; // tras "cambiaron": a Doña Carmen ya no le queda el rollo 102 ni la caja
let otraPersonaEntrego12 = false; // otra persona ya validó todo lo de Cliente con historial
let sinCambiosDonaRosa = false; // aparece Doña Rosa: solo un producto normal (se revisa sin capturar nada)
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
    // Como Mario fruta en duranDEV: líneas entregadas (productos repetidos),
    // saldo anterior y una factura en borrador de otra orden.
    11: () => ({
        cliente: { id: 11, nombre: "Mario fruta" },
        entregado: [
            { linea_id: 331, orden: "S00070", ...BOLSA_BASURA, cantidad: 3, peso: null, importe: 135 },
            { linea_id: 332, orden: "S00070", ...SUIZO, cantidad: 1.5, peso: null, importe: 100.5 },
            { linea_id: 333, orden: "S00070", ...ESTRELLA, precio: 85, cantidad: 1, peso: 0.4, importe: 34 },
            { linea_id: 334, orden: "S00071", ...BOLSA_BASURA, cantidad: 2, peso: null, importe: 90 },
            { linea_id: 335, orden: "S00071", ...SUIZO, cantidad: 1, peso: null, importe: 67 },
        ],
        total_entregado: 426.5,
        saldo_anterior: [{ move_id: 521, folio: "INV/2026/00019", fecha: "2026-09-24", total: 118, saldo: 118 }],
        total_saldo_anterior: 118,
        creditos: [],
        total_creditos: 0,
        total_a_cobrar: 544.5,
        saldo_a_favor: 0,
        borradores: [{ move_id: 602, folio: "Borrador", origen: "S00062", total: 323.5 }],
        devoluciones: [],
        avisos: ["Este cliente tiene una factura en borrador; confírmala o cancélala en Odoo."],
        puede_cobrar: false,
        visto: { lineas: [[331, 3], [332, 1.5], [333, 1], [334, 2], [335, 1]], documentos: [[521, 118]], borradores: [602] },
    }),
    14: () => ({
        cliente: { id: 14, nombre: "Doña Rosa" },
        productos: [{ ...BLANCA, cantidad: 2, sin_existencia: false, movimientos: [mov(301, 2, false, 70)] }],
    }),
    12: () => ({
        cliente: { id: 12, nombre: "Cliente con historial" },
        productos: otraPersonaEntrego12
            ? []
            : [{ ...ESTRELLA, cantidad: 1, sin_existencia: false, movimientos: [mov(201, 1, false, 85)] }],
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
        p.zona_id === 1
            ? [
                  { id: 9, nombre: "Doña Carmen" },
                  { id: 12, nombre: "Cliente con historial" },
                  ...(sinCambiosDonaRosa ? [{ id: 14, nombre: "Doña Rosa" }] : []),
              ]
            : [],
    "/captura/api/entrega/pendiente": (p) => pendientes[p.cliente_id](),
};

// === Modo Cobro ===

let otraPersonaCobro = false; // tras "cambiaron": alguien le abonó $100 a la factura de Doña Carmen
const detallesCobro = {
    9: () => ({
        cliente: { id: 9, nombre: "Doña Carmen" },
        entregado: [
            { linea_id: 301, orden: "S00050", ...ESTRELLA, precio: 85, cantidad: 1, peso: 1.25, importe: 106.25 },
            { linea_id: 302, orden: "S00050", ...BLANCA, precio: 70, cantidad: 3, peso: null, importe: 210 },
        ],
        total_entregado: 316.25,
        saldo_anterior: [
            { move_id: 501, folio: "INV/2026/00012", fecha: "2026-09-20", total: 1000, saldo: otraPersonaCobro ? 900 : 1000 },
        ],
        total_saldo_anterior: otraPersonaCobro ? 900 : 1000,
        creditos: [{ move_id: 502, folio: "RINV/2026/00003", fecha: "2026-09-21", total: 16.25, saldo: 16.25 }],
        total_creditos: 16.25,
        total_a_cobrar: otraPersonaCobro ? 1200 : 1300,
        saldo_a_favor: 0,
        borradores: [],
        devoluciones: [],
        avisos: [],
        puede_cobrar: true,
        visto: { lineas: [[301, 1], [302, 3]], documentos: [[501, otraPersonaCobro ? 900 : 1000], [502, 16.25]], borradores: [] },
    }),
    21: () => ({
        cliente: { id: 21, nombre: "Don Beto" },
        entregado: [{ linea_id: 311, orden: "S00060", ...CAJA, precio: 325, cantidad: 1, peso: null, importe: 325 }],
        total_entregado: 325,
        saldo_anterior: [],
        total_saldo_anterior: 0,
        creditos: [],
        total_creditos: 0,
        total_a_cobrar: 325,
        saldo_a_favor: 0,
        borradores: [{ move_id: 601, folio: "Borrador", origen: "S00058", total: 90 }],
        devoluciones: [],
        avisos: ["Este cliente tiene una factura en borrador; confírmala o cancélala en Odoo."],
        puede_cobrar: false,
        visto: { lineas: [[311, 1]], documentos: [], borradores: [601] },
    }),
    // Como Mario fruta en duranDEV: líneas entregadas (productos repetidos),
    // saldo anterior y una factura en borrador de otra orden.
    11: () => ({
        cliente: { id: 11, nombre: "Mario fruta" },
        entregado: [
            { linea_id: 331, orden: "S00070", ...BOLSA_BASURA, cantidad: 3, peso: null, importe: 135 },
            { linea_id: 332, orden: "S00070", ...SUIZO, cantidad: 1.5, peso: null, importe: 100.5 },
            { linea_id: 333, orden: "S00070", ...ESTRELLA, precio: 85, cantidad: 1, peso: 0.4, importe: 34 },
            { linea_id: 334, orden: "S00071", ...BOLSA_BASURA, cantidad: 2, peso: null, importe: 90 },
            { linea_id: 335, orden: "S00071", ...SUIZO, cantidad: 1, peso: null, importe: 67 },
        ],
        total_entregado: 426.5,
        saldo_anterior: [{ move_id: 521, folio: "INV/2026/00019", fecha: "2026-09-24", total: 118, saldo: 118 }],
        total_saldo_anterior: 118,
        creditos: [],
        total_creditos: 0,
        total_a_cobrar: 544.5,
        saldo_a_favor: 0,
        borradores: [{ move_id: 602, folio: "Borrador", origen: "S00062", total: 323.5 }],
        devoluciones: [],
        avisos: ["Este cliente tiene una factura en borrador; confírmala o cancélala en Odoo."],
        puede_cobrar: false,
        visto: { lineas: [[331, 3], [332, 1.5], [333, 1], [334, 2], [335, 1]], documentos: [[521, 118]], borradores: [602] },
    }),
    12: () => ({
        cliente: { id: 12, nombre: "Cliente con historial" },
        entregado: [],
        total_entregado: 0,
        saldo_anterior: [{ move_id: 511, folio: "INV/2026/00015", fecha: "2026-09-25", total: 150, saldo: 150 }],
        total_saldo_anterior: 150,
        creditos: [],
        total_creditos: 0,
        total_a_cobrar: 150,
        saldo_a_favor: 0,
        borradores: [],
        devoluciones: [{ linea_id: 321, orden: "S00040", nombre: "Blanca #2", cantidad: 1 }],
        avisos: ["Hay devoluciones sin nota de crédito (S00040). No entran en este cobro: haz la nota de crédito en Odoo."],
        puede_cobrar: true,
        visto: { lineas: [], documentos: [[511, 150]], borradores: [] },
    }),
};

// /captura/api/cobro/confirmar: "ok", o UNA vez: "sin-red", "cambiaron".
let modoCobro = "ok";
const cobrosEnviados = []; // parámetros de cada confirmación de cobro
const cobrosPorToken = new Map();
function confirmarCobroSimulado(p) {
    cobrosEnviados.push(p);
    const modo = modoCobro;
    modoCobro = "ok";
    if (cobrosPorToken.has(p.token)) {
        return { result: { ...cobrosPorToken.get(p.token), ya_existia: true } };
    }
    if (modo === "cambiaron") {
        otraPersonaCobro = true;
        return { result: { cambiaron: true, cobro: detallesCobro[p.cliente_id]() } };
    }
    const detalle = detallesCobro[p.cliente_id]();
    const total = detalle.total_a_cobrar;
    const recibido = p.tipo === "todo" ? total : p.tipo === "parte" ? p.monto : 0;
    const resultado = {
        cambiaron: false, id: 1, cliente: detalle.cliente.nombre, tipo: p.tipo, total_a_cobrar: total,
        monto_recibido: recibido, saldo_pendiente: redondear(total - recibido),
        facturas: detalle.entregado.length ? [{ folio: "INV/2026/00020", total: detalle.total_entregado }] : [],
        ya_existia: false,
    };
    cobrosPorToken.set(p.token, resultado);
    if (modo === "sin-red") {
        throw new TypeError("Failed to fetch"); // el cobro SÍ quedó, pero la respuesta no llegó
    }
    return { result: resultado };
}

const datosCobro = {
    "/captura/api/cobro/clientes": (p) =>
        p.zona_id === 1
            ? [
                  { id: 9, nombre: "Doña Carmen" }, { id: 21, nombre: "Don Beto" }, { id: 11, nombre: "Mario fruta" },
                  { id: 12, nombre: "Cliente con historial" },
              ]
            : [],
    "/captura/api/cobro/detalle": (p) => detallesCobro[p.cliente_id](),
};

// === Acomodo de entregas ===

// /captura/api/acomodo: "ok", "vacio" (sin pedidos) o UNA vez "sin-red".
let modoAcomodo = "ok";
const BOSQUES_ACOMODO = [
    { cliente: "Doña Carmen", productos: [
        { ...BLANCA, cantidad: 5 }, { ...ESTRELLA, cantidad: 2 }, { ...CAJA, cantidad: 2 },
    ] },
    { cliente: "Tortillería La Guadalupana de Doña Lupita", productos: [
        { ...BOLSA_BASURA, nombre: "Bolsa de basura jumbo negra extra gruesa 90x120 calibre 300", cantidad: 1.5 },
    ] },
    { cliente: "<b>Cliente con HTML</b>", productos: [{ ...ESTRELLA, cantidad: 1 }] },
    { cliente: "Doña Carmen", productos: [{ ...SUIZO, cantidad: 2 }] }, // volvió a pedir
    { cliente: "Cliente con historial", productos: [{ ...BLANCA, cantidad: 1 }, { ...SUIZO, cantidad: 3 }] },
    { cliente: "Don Beto", productos: [{ ...CAJA, cantidad: 1 }, { ...KG_SUELTO, cantidad: 3 }, { ...ESTRELLA, cantidad: 3 }] },
];
function acomodoSimulado() {
    const modo = modoAcomodo;
    if (modo === "sin-red") {
        modoAcomodo = "ok";
        throw new TypeError("Failed to fetch");
    }
    if (modo === "vacio") {
        return [];
    }
    // Como el servidor: la posición es el orden de entrega (1 = el más antiguo) y
    // la lista va al revés, en el orden de carga del carrito.
    const pedidos = (lista, primerId) => lista.map((p, i) => ({ id: primerId + i, posicion: i + 1, ...p })).reverse();
    return [
        { id: 1, nombre: "Bosques", pedidos: pedidos(BOSQUES_ACOMODO, 60) },
        {
            id: 3, nombre: "Tianguis Mercado Jardines de la Montaña Poniente",
            pedidos: pedidos([{ cliente: "Mario fruta", productos: [{ ...ESTRELLA, cantidad: 3 }] }], 70),
        },
        { id: false, nombre: "Sin zona", pedidos: pedidos([{ cliente: "Cliente sin zona", productos: [{ ...BLANCA, cantidad: 2 }] }], 80) },
    ];
}

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
    } else if (ruta === "/captura/api/cobro/confirmar") {
        await espera(60);
        cuerpo = confirmarCobroSimulado(params);
    } else if (ruta === "/captura/api/cliente/nuevo") {
        await espera(60); // da tiempo al doble toque
        cuerpo = crearClienteSimulado(params);
    } else if (ruta === "/captura/api/acomodo") {
        cuerpo = { result: acomodoSimulado() };
    } else if (datosCobro[ruta]) {
        cuerpo = { result: datosCobro[ruta](params) };
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
    const c = tarjeta(id) && tarjeta(id).querySelector(".producto-cantidad-texto");
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

async function escribirMonto(texto) {
    const campo = q(".monto-campo");
    campo.value = texto;
    campo.dispatchEvent(new Event("input", { bubbles: true }));
    await espera(5);
}

const importesCobro = (selector) =>
    qa(`${selector}`).map((l) => [
        l.querySelector(".resumen-nombre").firstChild.textContent,
        l.querySelector(".resumen-detalle") ? l.querySelector(".resumen-detalle").textContent : null,
        l.querySelector(".resumen-importe").textContent,
    ]);

async function escribirPeso(moveId, texto) {
    const campo = campoPeso(moveId);
    campo.value = texto;
    campo.dispatchEvent(new Event("input", { bubbles: true }));
    await espera(5);
}

function pideConfirmarAlSalir() {
    // Lo que hace el navegador al recargar o cerrar: si la página cancela el
    // evento, pregunta antes de salir.
    const evento = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(evento);
    return evento.defaultPrevented;
}

async function responderModal(si) {
    q(si ? "#modal-si" : "#modal-no").click();
    await espera(150);
}

// Pregunta al salir con algo sin enviar, confirmar o registrar:
// "ahora" (botón verde de arriba), "salir" (contorno, abajo) o "quedarse"
// (tocar el fondo oscuro).
async function responderSalida(opcion) {
    q({ ahora: "#modal-si", salir: "#modal-no", quedarse: "#modal" }[opcion]).click();
    await espera(150);
}

const preguntaAbierta = () => [
    q("#modal").hidden, txt("#modal-titulo"), txt("#modal-texto"), txt("#modal-si"), txt("#modal-no"),
];

const VERDE = "rgb(10, 107, 44)";
const BLANCO = "rgb(255, 255, 255)";

function checkFranja(pantalla, accion, conteo, aviso) {
    // Franja blanca con raya arriba; botón verde real (≥72px, redondeado, con
    // borde, sombra y 16px a los lados), verbo arriba en grande y conteo
    // abajo en chico; y el aviso ámbar justo arriba del botón (o ninguno).
    const franja = q("#barra-pedido");
    const boton = q("#btn-pedido");
    const r = boton.getBoundingClientRect();
    const estilo = getComputedStyle(boton);
    const falta = q("#falta-paso");
    const ancho = document.documentElement.clientWidth;
    check(
        `Franja de abajo: ${pantalla}`,
        [
            franja.hidden,
            getComputedStyle(franja).backgroundColor,
            getComputedStyle(franja).borderTopWidth,
            [txt("#pedido-accion"), txt("#pedido-conteo")],
            [getComputedStyle(q("#pedido-accion")).fontSize, getComputedStyle(q("#pedido-conteo")).fontSize],
            q("#pedido-accion").getBoundingClientRect().bottom <= q("#pedido-conteo").getBoundingClientRect().top + 1,
            r.height >= 72,
            parseFloat(estilo.borderTopLeftRadius) >= 12 && parseFloat(estilo.borderTopWidth) >= 2 && estilo.boxShadow !== "none",
            [Math.round(r.left), Math.round(ancho - r.right)],
            boton.disabled ? null : estilo.backgroundColor,
            falta.hidden ? null : txt("#falta-paso"),
            falta.hidden || falta.getBoundingClientRect().bottom <= r.top,
        ],
        [false, BLANCO, "3px", [accion, conteo], ["26px", "17px"], true, true, true, [16, 16], boton.disabled ? null : VERDE, aviso, true]
    );
}

async function checkNadaTapado(pantalla) {
    // A 393 x 852 y a 393 x 780: deslizando hasta abajo, lo último del
    // contenido queda arriba de la franja (no la toca).
    const marco = window.frameElement;
    const resultados = [];
    for (const alto of [852, 780]) {
        marco.style.height = `${alto}px`;
        await espera(80);
        window.scrollTo(0, document.documentElement.scrollHeight);
        await espera(30);
        const ultimo = q("#contenido").lastElementChild.getBoundingClientRect();
        const franja = q("#barra-pedido").getBoundingClientRect();
        resultados.push([alto, window.innerHeight, ultimo.bottom <= franja.top]);
    }
    marco.style.height = `${CELULAR[1]}px`;
    await espera(80);
    window.scrollTo(0, 0);
    check(`Nada tapado por la franja (852 y 780): ${pantalla}`, resultados, [[852, 852, true], [780, 780, true]]);
}

function checkExito(pantalla, titulo) {
    // Bloque verde claro con borde verde, palomeo de 140px y el título de 34px.
    const bloque = q(".exito");
    const marca = q(".exito-marca");
    check(
        `Éxito inconfundible: ${pantalla}`,
        [
            !!bloque,
            bloque && getComputedStyle(bloque).backgroundColor,
            bloque && getComputedStyle(bloque).borderTopColor,
            marca && [marca.offsetWidth, marca.offsetHeight, marca.textContent],
            bloque && bloque.querySelector("p:nth-child(2)").textContent,
            getComputedStyle(q(".exito-titulo")).fontSize,
            q("#barra-pedido").hidden,
        ],
        [true, "rgb(227, 245, 232)", VERDE, [140, 140, "✓"], titulo, "34px", true]
    );
}

const recordatorios = () => qa(".recordatorio").map((b) => b.textContent);

const llamadasA = (final) => llamadas.filter((ruta) => ruta.endsWith(final)).length;

// "+" de la tarjeta: el redondo sin cantidad o el de la fila [ − ] n [ + ].
const botonMas = (id) => tarjeta(id).querySelector(".producto-mas, .btn-mas");
const botonMenos = (id) => tarjeta(id) && tarjeta(id).querySelector(".btn-menos");

async function tocarProducto(id, veces = 1) {
    for (let i = 0; i < veces; i++) {
        botonMas(id).click();
        await espera(5);
    }
}

async function restarProducto(id, veces = 1) {
    for (let i = 0; i < veces; i++) {
        botonMenos(id).click();
        await espera(5);
    }
}

// Tamaño de diseño (sin la animación «golpe», que encoge la tarjeta un instante).
const medida = (nodo) => [nodo.offsetWidth, nodo.offsetHeight];

async function regresar() {
    q("#btn-regresar").click();
    await espera(120);
}

async function tocarInicio() {
    q("#btn-inicio").click();
    await espera(150);
}

let posicionInicio = null; // la de la primera pantalla; las demás deben coincidir

function checkInicio(pantalla) {
    // INICIO visible, habilitado, grande, arriba a la derecha y siempre en el
    // mismo lugar; sin encimarse con Regresar, el título ni la barra de abajo.
    const inicio = q("#btn-inicio");
    const r = inicio.getBoundingClientRect();
    const posicion = [r.left, r.top, r.width, r.height].map(Math.round);
    posicionInicio = posicionInicio || posicion;
    const regresar = q("#btn-regresar").getBoundingClientRect();
    const barraAbajo = q("#barra-pedido");
    check(
        `INICIO visible y en el mismo lugar: ${pantalla}`,
        [
            inicio.hidden,
            inicio.disabled,
            txt("#btn-inicio"),
            posicion,
            r.height >= 56 && regresar.height >= 56,
            Math.round(r.right) === document.documentElement.clientWidth - 16,
            Math.round(r.top) === Math.round(regresar.top) && r.left > regresar.right,
            r.bottom <= q("#titulo").getBoundingClientRect().top,
            !barraAbajo.hidden && r.bottom > barraAbajo.getBoundingClientRect().top,
        ],
        [false, false, "🏠 INICIO", posicionInicio, true, true, true, true, false]
    );
}

// Colores de las operaciones (captura.css) y el azul de la barra sin operación.
const COLOR_OPERACION = {
    pedido: "rgb(11, 61, 145)", entrega: "rgb(10, 107, 44)", cobro: "rgb(161, 74, 0)", acomodo: "rgb(122, 31, 107)",
};
const AZUL_INICIO = "rgb(11, 61, 145)";
const TEXTO_OPERACION = { pedido: "📝 PEDIDO", entrega: "🚚 ENTREGA", cobro: "💵 COBRO", acomodo: "🛒 ACOMODO" };

function checkOperacion(operacion, pantalla) {
    // La línea de la operación (o ninguna en Inicio), el color de la barra y
    // el de la barra del navegador.
    const linea = q("#operacion");
    const barra = getComputedStyle(q(".barra")).backgroundColor;
    const navegador = q('meta[name="theme-color"]').content;
    if (!operacion) {
        check(
            `Sin operación, barra azul: ${pantalla}`,
            [linea.hidden, document.body.dataset.operacion ?? null, barra, navegador],
            [true, null, AZUL_INICIO, AZUL_INICIO]
        );
        return;
    }
    const r = linea.getBoundingClientRect();
    const estilo = getComputedStyle(linea);
    check(
        `Operación ${TEXTO_OPERACION[operacion]} con su color: ${pantalla}`,
        [
            linea.hidden,
            linea.textContent,
            barra,
            navegador,
            [estilo.fontSize, estilo.fontWeight, estilo.color],
            r.top >= q("#barra-botones").getBoundingClientRect().bottom && r.bottom <= q("#titulo").getBoundingClientRect().top,
        ],
        [false, TEXTO_OPERACION[operacion], COLOR_OPERACION[operacion], COLOR_OPERACION[operacion], ["18px", "800", "rgb(255, 255, 255)"], true]
    );
}

function inicioGris() {
    // Deshabilitado y pintado de gris (rojo = verde = azul).
    const inicio = q("#btn-inicio");
    const [r, g, b] = getComputedStyle(inicio).backgroundColor.match(/\d+/g).map(Number);
    return inicio.disabled && r === g && g === b && r < 255;
}

// Tamaño de pantalla del iPhone 16 (correr.mjs carga la página en un marco de
// este tamaño).
const CELULAR = [393, 852];

function desbordados() {
    // Elementos visibles que se salen por los lados de la pantalla, salvo los
    // que están dentro de algo que se desliza a lo ancho a propósito (pestañas).
    const ancho = document.documentElement.clientWidth;
    return qa("body *")
        .filter((e) => {
            const r = e.getBoundingClientRect();
            if (!r.width || (r.left >= -0.5 && r.right <= ancho + 0.5)) {
                return false;
            }
            for (let p = e.parentElement; p; p = p.parentElement) {
                if (["auto", "scroll"].includes(getComputedStyle(p).overflowX)) {
                    return false;
                }
            }
            return true;
        })
        .map((e) => `${e.tagName.toLowerCase()}.${[...e.classList].join(".")} «${e.textContent.trim().slice(0, 30)}»`);
}

function checkAncho(pantalla) {
    check(
        `Ancho de celular (${CELULAR.join(" x ")}), sin salirse por los lados: ${pantalla}`,
        [[window.innerWidth, window.innerHeight], document.documentElement.scrollWidth <= document.documentElement.clientWidth, desbordados()],
        [CELULAR, true, []]
    );
}

function check(nombre, obtenido, esperado) {
    const ok = JSON.stringify(obtenido) === JSON.stringify(esperado);
    resultados.push(
        `${ok ? "OK   " : "FALLA"} | ${nombre}` +
            (ok ? "" : ` | esperado=${JSON.stringify(esperado)} | obtenido=${JSON.stringify(obtenido)}`)
    );
}
