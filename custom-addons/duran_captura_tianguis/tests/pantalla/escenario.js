/* Recorrido de la pantalla /captura como lo haría quien captura, con el
 * servidor simulado (simulacion.js). Cada check() es una verificación; al
 * final se escriben todas en <pre id="resultado-prueba"> para correr.mjs. */

async function pasoInicio() {
    check("Inicio: título", txt("#titulo"), "Captura");
    check("Inicio: botón superior dice Salir", txt("#btn-regresar"), "‹ Salir");
    check("Inicio: pregunta", txt(".pregunta"), "¿Qué vas a hacer?");
    check(
        "Inicio: dos modos, Pedido y Entrega",
        qa(".btn-modo").map((b) => [b.querySelector(".modo-nombre").textContent, b.querySelector(".modo-detalle").textContent]),
        [["Pedido", "Levantar un pedido nuevo"], ["Entrega", "Próximamente"]]
    );
    check("Inicio: sin barra de pedido ni pestañas", [q("#barra-pedido").hidden, q("#categorias").hidden], [true, true]);
    check("Inicio: Entrega todavía deshabilitado", modo("Entrega").disabled, true);
    modo("Entrega").click();
    await espera(80);
    check("Inicio: tocar Entrega no hace nada ni llama al servidor", [txt("#titulo"), llamadas.length], ["Captura", 0]);
    check("Inicio: el modo Pedido está habilitado", modo("Pedido").disabled, false);

    modo("Pedido").click();
    await espera(80);
    check("Pedido: lleva a Zonas", [txt("#titulo"), txt("#subtitulo")], ["Zonas", "Pedido"]);
    await regresar();
    check("Regresar desde Zonas vuelve al Inicio", [txt("#titulo"), txt("#btn-regresar")], ["Captura", "‹ Salir"]);
    modo("Pedido").click();
    await espera(80);
}

async function pasoZonas() {
    check("Zonas: título", txt("#titulo"), "Zonas");
    check("Zonas: botón superior dice Regresar", txt("#btn-regresar"), "‹ Regresar");
    check("Zonas: un botón por zona", qa(".lista .btn").map((b) => b.textContent), ["Bosques", "Guadalupana"]);
    check("Zonas: sin barra de pedido", q("#barra-pedido").hidden, true);

    boton("Guadalupana").click();
    await espera(80);
    check("Zona vacía: mensaje", txt(".aviso"), "Esta zona no tiene clientes");
    check("Zona vacía: botón para regresar", !!boton("‹ Regresar a zonas"), true);
    boton("‹ Regresar a zonas").click();
    await espera(120);
    check("Zona vacía: regresar vuelve a Zonas", txt("#titulo"), "Zonas");
}

async function pasoClientes() {
    boton("Bosques").click();
    await espera(80);
    check("Clientes: título es la zona", txt("#titulo"), "Bosques");
    check("Clientes: botón superior dice Regresar", txt("#btn-regresar"), "‹ Regresar");
    check(
        "Clientes: un nombre con HTML se muestra como texto",
        qa(".lista .btn").map((b) => b.textContent),
        ["Doña Carmen", "<b>Cliente con HTML</b>", "Cliente con historial", "Tortillería La Guadalupana de Doña Lupita"]
    );
    check("Clientes: no se crea ningún <b> desde los datos", qa(".lista b").length, 0);
}

async function pasoProductos() {
    boton("Doña Carmen").click();
    await espera(120);
    check("Productos: título es el cliente, subtítulo la zona", [txt("#titulo"), txt("#subtitulo")], ["Doña Carmen", "Bosques"]);
    check("Productos: pestañas de categoría", nombresPestanas(), ["Bolsas asa", "Rollos"]);
    check("Productos: primera categoría activa", txt('.categoria[aria-selected="true"]'), "Bolsas asa");
    check(
        "Productos: nombre y precio",
        [...tarjeta(440).querySelectorAll(".producto-nombre,.producto-precio")].map((e) => e.textContent),
        ["Blanca #2", "$70/kg"]
    );
    check("Productos: precio c/u", tarjeta(409).querySelector(".producto-precio").textContent, "$325 c/u");
    check("Productos: sin cantidad no hay − 1 ni Quitar", tarjeta(440).querySelectorAll(".btn-restar,.btn-quitar").length, 0);
    check("Productos: pedido vacío, botón de abajo deshabilitado", [txt("#pedido-conteo"), q("#btn-pedido").disabled], ["Pedido vacío", true]);

    await tocarProducto(440, 3);
    check("3 toques = 3 kg", cantidad(440), "3 kg");
    check(
        "Con cantidad aparecen − 1 y Quitar",
        [...tarjeta(440).querySelectorAll(".producto-controles .btn")].map((b) => b.textContent),
        ["− 1", "✕ Quitar"]
    );
    check("Indicador suma cantidades: 3 kg = 3 productos", txt("#pedido-conteo"), "3 productos en el pedido");
    check("Pestaña suma cantidades", txt('.categoria[aria-selected="true"] .categoria-conteo'), "3");

    tarjeta(440).querySelector(".btn-restar").click();
    await espera(10);
    check("− 1: 2 kg", cantidad(440), "2 kg");
    await tocarProducto(409, 2);
    check("Piezas: 2 c/u", cantidad(409), "2 c/u");
    check("Indicador: 2 kg + 2 c/u = 4 productos", txt("#pedido-conteo"), "4 productos en el pedido");
    tarjeta(409).querySelector(".btn-restar").click();
    await espera(10);
    tarjeta(409).querySelector(".btn-restar").click();
    await espera(10);
    check("Restar hasta 0 lo saca del pedido", [cantidad(409), txt("#pedido-conteo")], [null, "2 productos en el pedido"]);
    await tocarProducto(409, 4);
    tarjeta(409).querySelector(".btn-quitar").click();
    await espera(10);
    check("Quitar lo saca de golpe", [cantidad(409), txt("#pedido-conteo")], [null, "2 productos en el pedido"]);

    pestana("Rollos").click();
    await espera(20);
    check("Cambiar de pestaña muestra sus productos", qa(".producto-nombre").map((e) => e.textContent), ["Estrella 25x35"]);
    await tocarProducto(464, 2);
    check(
        "Peso variable: 2 c/u con precio $85/kg",
        [cantidad(464), tarjeta(464).querySelector(".producto-precio").textContent],
        ["2 c/u", "$85/kg"]
    );
    pestana("Bolsas asa").click();
    await espera(20);
    check("Al volver a la pestaña la cantidad sigue", cantidad(440), "2 kg");
    check(
        "Cada pestaña suma sus cantidades",
        qa(".categoria").map((b) => [b.firstChild.textContent, b.querySelector(".categoria-conteo")?.textContent ?? null]),
        [["Bolsas asa", "2"], ["Rollos", "2"]]
    );
}

async function pasoConfirmarAntesDeVaciar() {
    await regresar();
    check(
        "Regresar con pedido pide confirmación",
        [q("#modal").hidden, txt("#modal-texto")],
        [false, "¿Vaciar el pedido de Doña Carmen? Tiene 4 productos sin enviar."]
    );
    q("#modal-no").click();
    await espera(80);
    check(
        "Responder No: sigue en productos con el pedido",
        [q("#modal").hidden, txt("#titulo"), cantidad(440), txt("#pedido-conteo")],
        [true, "Doña Carmen", "2 kg", "4 productos en el pedido"]
    );

    history.back(); // botón "atrás" del celular
    await espera(120);
    check("Atrás del celular también pide confirmación", q("#modal").hidden, false);
    q("#modal-si").click();
    await espera(120);
    check("Responder Sí: vuelve a clientes", txt("#titulo"), "Bosques");
    boton("Doña Carmen").click();
    await espera(80);
    check("El pedido quedó vacío", [txt("#pedido-conteo"), cantidad(440)], ["Pedido vacío", null]);
    check("El catálogo se pide al servidor una sola vez", llamadasA("catalogo"), 1);

    await regresar();
    check("Regresar con pedido vacío no pregunta", [q("#modal").hidden, txt("#titulo")], [true, "Bosques"]);
    await regresar();
    check("Regresar desde clientes vuelve a zonas", txt("#titulo"), "Zonas");
    history.back(); // atrás del celular desde Zonas
    await espera(120);
    check("Atrás desde Zonas vuelve al Inicio", txt("#titulo"), "Captura");
    modo("Pedido").click();
    await espera(80);
}

async function pasoLoDeSiempre() {
    boton("Bosques").click();
    await espera(80);
    boton("Cliente con historial").click();
    await espera(120);
    check("Con historial: Lo de siempre es la primera pestaña", nombresPestanas(), ["⭐ Lo de siempre", "Bolsas asa", "Rollos"]);
    check("Con historial: Lo de siempre está seleccionada al entrar", pestana("⭐ Lo de siempre").getAttribute("aria-selected"), "true");
    check("Lo de siempre: sus productos en su orden", qa(".producto-nombre").map((e) => e.textContent), ["Estrella 25x35", "Blanca #2"]);
    check("Lo de siempre: mismo precio que el catálogo", tarjeta(440).querySelector(".producto-precio").textContent, "$70/kg");
    await tocarProducto(440, 2);
    check("Lo de siempre: tocar suma igual que en el catálogo", cantidad(440), "2 kg");
    check(
        "Lo de siempre: también tiene − 1 y Quitar",
        [...tarjeta(440).querySelectorAll(".producto-controles .btn")].map((b) => b.textContent),
        ["− 1", "✕ Quitar"]
    );
    pestana("Bolsas asa").click();
    await espera(20);
    check("La misma cantidad se ve en su categoría", cantidad(440), "2 kg");
    tarjeta(440).querySelector(".btn-restar").click();
    await espera(10);
    pestana("⭐ Lo de siempre").click();
    await espera(20);
    check("Restar en la categoría se refleja en Lo de siempre", cantidad(440), "1 kg");
    check("Contadores de pestañas", qa(".categoria").map((b) => b.querySelector(".categoria-conteo")?.textContent ?? null), ["1", "1", null]);
    check("El indicador cuenta el producto una sola vez", txt("#pedido-conteo"), "1 producto en el pedido");

    const antes = llamadasA("habituales");
    await regresar();
    q("#modal-si").click();
    await espera(120);
    boton("Doña Carmen").click();
    await espera(120);
    check("Cliente sin historial: sin pestaña Lo de siempre", nombresPestanas(), ["Bolsas asa", "Rollos"]);
    check("Cliente sin historial: abre la primera categoría", txt('.categoria[aria-selected="true"]'), "Bolsas asa");
    check("Lo de siempre se pide al servidor en cada cliente", llamadasA("habituales"), antes + 1);
    await regresar();
    boton("Cliente con historial").click();
    await espera(120);
    check("Al volver a un cliente con historial se abre otra vez Lo de siempre", txt('.categoria[aria-selected="true"]'), "⭐ Lo de siempre");
    check("El catálogo sigue pidiéndose una sola vez", llamadasA("catalogo"), 1);
    await regresar();
}

async function pasoResumen() {
    boton("Doña Carmen").click();
    await espera(120);
    await tocarProducto(409, 1);
    await tocarProducto(440, 2);
    pestana("Rollos").click();
    await espera(20);
    await tocarProducto(464, 1);
    check(
        "Productos: la barra invita a revisar",
        [q("#btn-pedido").disabled, txt("#pedido-accion"), txt("#pedido-conteo")],
        [false, "Revisar pedido ›", "4 productos en el pedido"]
    );
    q("#btn-pedido").click();
    await espera(60);
    check("Resumen: título y subtítulo", [txt("#titulo"), txt("#subtitulo")], ["Doña Carmen", "Bosques"]);
    check("Resumen: sin pestañas", q("#categorias").hidden, true);
    check(
        "Resumen: productos en orden de catálogo, con cantidad y unidad",
        qa(".resumen-linea").map((l) => [l.querySelector(".resumen-nombre").textContent, l.querySelector(".resumen-cantidad").textContent]),
        [["Blanca #2", "2 kg"], ["Caja 25x35 (5kg)", "1 c/u"], ["Estrella 25x35", "1 c/u"]]
    );
    check("Resumen: sin precios ni total", q("#contenido").textContent.includes("$"), false);
    check(
        "Resumen: barra verde con Enviar",
        [txt("#pedido-accion"), q("#barra-pedido").classList.contains("para-enviar")],
        ["✓ Enviar pedido", true]
    );
    await regresar();
    check(
        "Regresar del resumen: vuelve a productos sin preguntar y con el pedido",
        [q("#modal").hidden, txt("#titulo"), txt("#pedido-conteo")],
        [true, "Doña Carmen", "4 productos en el pedido"]
    );
    q("#btn-pedido").click();
    await espera(60);
}

async function pasoEnviar() {
    // Sin señal al enviar: el pedido se conserva y el reintento no duplica.
    modoEnvio = "sin-red";
    q("#btn-pedido").click();
    q("#btn-pedido").click(); // doble toque
    await espera(10);
    check("Enviando: botón deshabilitado", [q("#btn-pedido").disabled, txt("#pedido-accion")], [true, "Enviando…"]);
    history.back();
    await espera(30);
    check("Enviando: el botón atrás no sale de la pantalla", txt("#titulo"), "Doña Carmen");
    await espera(200);
    check("Doble toque: una sola petición", envios.length, 1);
    const primero = envios[0];
    check(
        "Datos enviados: cliente, zona, cantidades enteras y token de 32 hex",
        [primero.cliente_id, primero.zona_id, primero.lineas, /^[0-9a-f]{32}$/.test(primero.token)],
        [9, 1, [{ producto_id: 440, cantidad: 2 }, { producto_id: 409, cantidad: 1 }, { producto_id: 464, cantidad: 1 }], true]
    );
    check(
        "Sin señal: mensaje claro y el pedido sigue",
        [txt(".error-envio"), txt("#pedido-conteo"), q("#btn-pedido").disabled],
        [
            "No se pudo confirmar si el pedido llegó. Toca «Enviar pedido» otra vez: si ya había llegado, no se duplica.",
            "4 productos en el pedido",
            false,
        ]
    );
    q("#btn-pedido").click();
    await espera(250);
    check("Reintento: mismo token (el servidor no duplica)", [envios.length, envios[1].token === primero.token], [2, true]);
    check(
        "Enviado: pantalla de éxito con folio, cliente y productos",
        [txt("#titulo"), txt(".enviado-titulo"), txt(".enviado-detalle")],
        ["Pedido enviado", "Pedido S00050 enviado", "Doña Carmen · 4 productos"]
    );
    check("Enviado: sin barra del pedido", q("#barra-pedido").hidden, true);
    check(
        "Enviado: botones siguiente cliente y cambiar de zona",
        qa(".lista .btn").map((b) => b.textContent),
        ["Siguiente cliente de Bosques", "Cambiar de zona"]
    );

    history.back();
    await espera(150);
    check(
        "Atrás desde Enviado: productos del mismo cliente, pedido vacío, sin preguntar",
        [q("#modal").hidden, txt("#titulo"), txt("#pedido-conteo")],
        [true, "Doña Carmen", "Pedido vacío"]
    );

    // Error del servidor: mensaje legible; si se cambia el pedido, el token cambia.
    pestana("Bolsas asa").click();
    await espera(20);
    await tocarProducto(440, 1);
    q("#btn-pedido").click();
    await espera(60);
    modoEnvio = "error";
    q("#btn-pedido").click();
    await espera(250);
    check(
        "Error del servidor: mensaje legible",
        txt(".error-envio"),
        "No se envió el pedido: Estos productos ya no están a la venta: Blanca #2. Quítalos del pedido e intenta de nuevo."
    );
    const tokenConError = envios[envios.length - 1].token;
    await regresar();
    await tocarProducto(409, 1);
    q("#btn-pedido").click();
    await espera(60);
    check("Al cambiar el pedido, el error desaparece", q(".error-envio"), null);
    q("#btn-pedido").click();
    await espera(250);
    check("Pedido distinto: token nuevo", envios[envios.length - 1].token !== tokenConError, true);
    check("Segundo pedido enviado", [txt(".enviado-titulo"), txt(".enviado-detalle")], ["Pedido S00051 enviado", "Doña Carmen · 2 productos"]);

    boton("Siguiente cliente de Bosques").click();
    await espera(120);
    check("Siguiente cliente: lista de clientes de la zona", [txt("#titulo"), qa(".lista .btn").length], ["Bosques", 4]);
    boton("Doña Carmen").click();
    await espera(120);
    await tocarProducto(440, 1);
    await regresar();
    check("Salir con pedido sin enviar sigue preguntando", q("#modal").hidden, false);
    q("#modal-si").click();
    await espera(120);

    boton("Tortillería La Guadalupana de Doña Lupita").click();
    await espera(120);
    const barra = q(".barra").getBoundingClientRect().bottom;
    const pestanas = q("#categorias").getBoundingClientRect().top;
    check("Nombre largo: las pestañas quedan debajo de la barra, sin taparse", Math.abs(pestanas - barra) <= 1, true);
}

window.addEventListener("load", async () => {
    try {
        await espera(80);
        await pasoInicio();
        await pasoZonas();
        await pasoClientes();
        await pasoProductos();
        await pasoConfirmarAntesDeVaciar();
        await pasoLoDeSiempre();
        await pasoResumen();
        await pasoEnviar();
    } catch (error) {
        resultados.push(`FALLA | excepción en el recorrido | ${error.stack}`);
    }
    const salida = document.createElement("pre");
    salida.id = "resultado-prueba";
    salida.textContent = resultados.join("\n");
    document.body.append(salida);
});
