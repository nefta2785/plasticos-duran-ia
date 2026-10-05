/* Recorrido de la pantalla /captura como lo haría quien captura, con el
 * servidor simulado (simulacion.js). Cada check() es una verificación; al
 * final se escriben todas en <pre id="resultado-prueba"> para correr.mjs. */

async function pasoInicio() {
    check("Inicio: título", txt("#titulo"), "Captura");
    check("Inicio (administrador): botón superior dice Salir y se ve", [txt("#btn-regresar"), q("#btn-regresar").hidden], ["‹ Salir", false]);
    check("Inicio: sin INICIO (ya está en el Inicio), la fila de Salir sí se ve", [q("#btn-inicio").hidden, q("#barra-botones").hidden], [true, false]);
    check("Inicio: pregunta", txt(".pregunta"), "¿Qué vas a hacer?");
    check(
        "Inicio: cuatro modos, Pedido, Entrega, Cobro y Acomodo de entregas",
        qa(".btn-modo").map((b) => [b.querySelector(".modo-nombre").textContent, b.querySelector(".modo-detalle").textContent]),
        [
            ["Pedido", "Levantar un pedido nuevo"],
            ["Entrega", "Entregar lo que ya pidieron"],
            ["Cobro", "Cobrar lo entregado y lo pendiente"],
            ["Acomodo de entregas", "En qué orden acomodar el carrito"],
        ]
    );
    checkCuatroModosSinDeslizar("Inicio (administrador)");
    check("Inicio: sin barra de pedido ni pestañas", [q("#barra-pedido").hidden, q("#categorias").hidden], [true, true]);
    check(
        "Inicio: los cuatro modos habilitados",
        [modo("Pedido").disabled, modo("Entrega").disabled, modo("Cobro").disabled, modo("Acomodo de entregas").disabled],
        [false, false, false, false]
    );
    check("Inicio: no llama al servidor", llamadas.length, 0);
    checkAncho("Inicio");

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
    checkInicio("Zonas");

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
    checkInicio("Clientes");
}

async function pasoProductos() {
    boton("Doña Carmen").click();
    await espera(120);
    check("Productos: título es el cliente, subtítulo la zona", [txt("#titulo"), txt("#subtitulo")], ["Doña Carmen", "Bosques"]);
    check("Productos: pestañas de categoría", nombresPestanas(), ["Bolsas asa", "Rollos"]);
    checkInicio("Productos");
    check("Productos: primera categoría activa", txt('.categoria[aria-selected="true"]'), "Bolsas asa");
    check(
        "Productos: nombre y precio",
        [...tarjeta(440).querySelectorAll(".producto-nombre,.producto-precio")].map((e) => e.textContent),
        ["Blanca #2", "$70/kg"]
    );
    check("Productos: precio c/u", tarjeta(409).querySelector(".producto-precio").textContent, "$325 c/u");
    check(
        "Productos sin cantidad: solo un «+» redondo de 64 x 64, sin «−» ni número",
        [txt('[data-producto="440"] .producto-mas'), medida(botonMas(440)), getComputedStyle(botonMas(440)).borderTopWidth, botonMenos(440), cantidad(440)],
        ["+", [64, 64], "3px", null, null]
    );
    check("La tarjeta no es un botón: solo «+» y «−» lo son", [tarjeta(440).closest("button"), tarjeta(440).querySelectorAll("button").length], [null, 1]);
    for (const parte of [".producto-nombre", ".producto-precio", ".producto-fila"]) {
        tarjeta(440).querySelector(parte).click();
    }
    tarjeta(440).click();
    await espera(10);
    check("Tocar el nombre, el precio o la tarjeta no suma nada", [cantidad(440), txt("#pedido-conteo")], [null, "Pedido vacío"]);
    check("Productos: pedido vacío, botón de abajo deshabilitado", [txt("#pedido-conteo"), q("#btn-pedido").disabled], ["Pedido vacío", true]);
    check("Pedido vacío: recargar no pregunta", pideConfirmarAlSalir(), false);

    await tocarProducto(440, 3);
    check("3 toques = 3 kg", cantidad(440), "3 kg");
    check("Con pedido: recargar la página pregunta antes", pideConfirmarAlSalir(), true);
    check(
        "Con cantidad: fila [ − ] 3 kg [ + ], sin «Quitar» ni etiqueta arriba",
        [
            [...tarjeta(440).querySelectorAll(".producto-cantidades > *")].map((e) => e.textContent),
            tarjeta(440).classList.contains("con-cantidad"),
            q('[data-producto="440"] .producto-fila button'),
            /Quitar/.test(tarjeta(440).textContent),
        ],
        [["−", "3 kg", "+"], true, null, false]
    );
    check(
        "Botones «−» y «+» de 72 x 60 (al menos 64 x 56), contorno de 3 px, número de 28 px",
        [medida(botonMenos(440)), medida(botonMas(440)), getComputedStyle(botonMas(440)).borderTopWidth, getComputedStyle(q('[data-producto="440"] .producto-cantidad-texto')).fontSize],
        [[72, 60], [72, 60], "3px", "28px"]
    );
    check(
        "Botones con nombre para el lector de pantalla",
        [botonMenos(440).getAttribute("aria-label"), botonMas(440).getAttribute("aria-label")],
        ["Quitar 1 a Blanca #2", "Agregar 1 a Blanca #2"]
    );
    check("Indicador suma cantidades: 3 kg = 3 productos", txt("#pedido-conteo"), "3 productos en el pedido");
    check("Pestaña suma cantidades", txt('.categoria[aria-selected="true"] .categoria-conteo'), "3");

    await restarProducto(440);
    check("«−»: 2 kg", cantidad(440), "2 kg");
    await tocarProducto(409, 2);
    check("Piezas: 2 c/u", cantidad(409), "2 c/u");
    check("Indicador: 2 kg + 2 c/u = 4 productos", txt("#pedido-conteo"), "4 productos en el pedido");
    await restarProducto(409);
    check("«−» en 2 deja 1", cantidad(409), "1 c/u");
    await restarProducto(409);
    check(
        "«−» en 1 lo saca del pedido, sin preguntar, y vuelve el «+» redondo",
        [cantidad(409), txt("#pedido-conteo"), q("#modal").hidden, !!q('[data-producto="409"] .producto-mas')],
        [null, "2 productos en el pedido", true, true]
    );

    // Toques rápidos: el «+» no se reemplaza bajo el dedo y no se pierde ninguno.
    await tocarProducto(409, 1);
    const mas = botonMas(409);
    for (let i = 0; i < 9; i++) {
        botonMas(409).click(); // sin esperar entre toques
    }
    await espera(10);
    check(
        "10 toques seguidos dan 10, con el mismo botón «+»",
        [cantidad(409), mas.isConnected, txt('.categoria[aria-selected="true"] .categoria-conteo'), txt("#pedido-conteo")],
        ["10 c/u", true, "12", "12 productos en el pedido"]
    );
    await restarProducto(409, 10);
    check("10 veces «−» lo saca otra vez", [cantidad(409), txt("#pedido-conteo")], [null, "2 productos en el pedido"]);

    pestana("Rollos").click();
    await espera(20);
    check("Cambiar de pestaña muestra sus productos", qa(".producto-nombre").map((e) => e.textContent), ["Estrella 25x35"]);
    await tocarProducto(464, 1);
    check("Rollo en singular: 1 rollo", cantidad(464), "1 rollo");
    await tocarProducto(464, 1);
    check(
        "Rollos en plural, con el precio por kg sin cambio",
        [cantidad(464), tarjeta(464).querySelector(".producto-precio").textContent],
        ["2 rollos", "$85/kg"]
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
    check("Con la pregunta de Regresar abierta, INICIO queda gris", inicioGris(), true);
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
    check("Lo de siempre: «+» suma igual que en el catálogo", cantidad(440), "2 kg");
    check(
        "Lo de siempre: misma fila [ − ] 2 kg [ + ], y el rollo con su «+» redondo",
        [[...tarjeta(440).querySelectorAll(".producto-cantidades > *")].map((e) => e.textContent), !!q('[data-producto="464"] .producto-mas')],
        [["−", "2 kg", "+"], true]
    );
    tarjeta(440).querySelector(".producto-nombre").click();
    await espera(10);
    check("Lo de siempre: tocar el nombre no suma", cantidad(440), "2 kg");
    pestana("Bolsas asa").click();
    await espera(20);
    check("La misma cantidad se ve en su categoría", cantidad(440), "2 kg");
    await restarProducto(440);
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
    checkInicio("Resumen");
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
    check("Enviando: INICIO gris y deshabilitado", inicioGris(), true);
    q("#btn-inicio").click();
    await espera(30);
    check("Enviando: tocar INICIO no sale de la pantalla", [txt("#titulo"), q("#modal").hidden], ["Doña Carmen", true]);
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
    check("Después del error, INICIO vuelve a estar habilitado", q("#btn-inicio").disabled, false);
    q("#btn-pedido").click();
    await espera(250);
    check("Reintento: mismo token (el servidor no duplica)", [envios.length, envios[1].token === primero.token], [2, true]);
    check(
        "Enviado: pantalla de éxito con folio, cliente y productos",
        [txt("#titulo"), txt(".enviado-titulo"), txt(".enviado-detalle")],
        ["Pedido enviado", "Pedido S00050 enviado", "Doña Carmen · 4 productos"]
    );
    check("Enviado: sin barra del pedido", q("#barra-pedido").hidden, true);
    checkInicio("Pedido enviado");
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

async function pasoInicioConPedido() {
    // Sigue en Productos del cliente de nombre largo, con el pedido vacío.
    const cliente = "Tortillería La Guadalupana de Doña Lupita";
    await tocarProducto(440, 2);
    q("#btn-inicio").click();
    await espera(30);
    check(
        "INICIO con pedido: la misma pregunta, con botones para ir al inicio o seguir",
        [q("#modal").hidden, txt("#modal-texto"), txt("#modal-si"), txt("#modal-no")],
        [false, `¿Vaciar el pedido de ${cliente}? Tiene 2 productos sin enviar.`, "Sí, vaciar e ir al inicio", "No, seguir con el pedido"]
    );
    check("Con la pregunta de INICIO abierta, INICIO queda gris", inicioGris(), true);
    await responderModal(false);
    check(
        "INICIO, responder No: sigue en Productos con el pedido",
        [q("#modal").hidden, txt("#titulo"), txt("#pedido-conteo"), q("#btn-inicio").disabled],
        [true, cliente, "2 productos en el pedido", false]
    );

    const largo = history.length;
    const nivel = history.state.nivel;
    q("#btn-inicio").click();
    await espera(30);
    await responderModal(true);
    check(
        "INICIO, responder Sí: en el Inicio, sin INICIO y sin pedido",
        [txt("#titulo"), q("#btn-inicio").hidden, q("#modal").hidden, pideConfirmarAlSalir(), location.pathname.endsWith("captura.html")],
        ["Captura", true, true, false, true]
    );
    check("INICIO deja la primera entrada del historial como Inicio", [history.state.pantalla, history.state.nivel], ["inicio", 0]);
    // "Atrás" del celular aquí sale a la página anterior (como al abrir la app);
    // en el marco de la prueba eso saca a la página de prueba, así que se
    // comprueba con el largo del historial: lo de adelante se borra al seguir.
    modo("Pedido").click();
    await espera(80);
    check(
        "Al seguir, el historial vuelve a empezar desde el Inicio (se borra lo de adelante)",
        [history.length, history.state.nivel],
        [largo - nivel + 1, 1]
    );
    boton("Bosques").click();
    await espera(80);
    boton("Doña Carmen").click();
    await espera(120);
    check("El pedido que se vació no reaparece", txt("#pedido-conteo"), "Pedido vacío");

    // Pantalla final: sale directo, sin preguntar.
    await tocarProducto(409, 1);
    q("#btn-pedido").click();
    await espera(60);
    q("#btn-pedido").click();
    await espera(250);
    check("Pedido enviado otra vez", txt("#titulo"), "Pedido enviado");
    await tocarInicio();
    check("INICIO desde Pedido enviado: directo, sin preguntar", [txt("#titulo"), q("#modal").hidden], ["Captura", true]);
}

// === Modo Entrega ===

async function irAInicio() {
    // Como lo haría quien captura después de enviar pedidos.
    for (let intentos = 0; txt("#titulo") !== "Captura" && intentos < 10; intentos++) {
        if (boton("Cambiar de zona")) {
            boton("Cambiar de zona").click();
            await espera(120);
        } else {
            await regresar();
        }
        if (!q("#modal").hidden) {
            await responderModal(true);
        }
    }
}

async function pasoEntregaClientes() {
    // Después de enviar pedidos: "Cambiar de zona" y "Regresar" llevan al Inicio.
    await irAInicio();
    check("Desde Zonas, Regresar lleva al Inicio aunque antes se enviaron pedidos", txt("#titulo"), "Captura");
    modo("Entrega").click();
    await espera(80);
    check("Entrega: Zonas con subtítulo Entrega", [txt("#titulo"), txt("#subtitulo")], ["Zonas", "Entrega"]);
    boton("Guadalupana").click();
    await espera(80);
    check("Entrega: zona sin pendientes", txt(".aviso"), "Nadie de esta zona tiene entregas pendientes");
    await regresar();
    boton("Bosques").click();
    await espera(80);
    check(
        "Entrega: solo clientes con entregas pendientes (ruta de Entrega)",
        [qa(".lista .btn").map((b) => b.textContent), llamadasA("entrega/clientes")],
        [["Doña Carmen", "Cliente con historial"], 2]
    );
    boton("Doña Carmen").click();
    await espera(120);
}

async function pasoEntregaLista() {
    check("Lista: título cliente y zona", [txt("#titulo"), txt("#subtitulo")], ["Doña Carmen", "Bosques"]);
    checkInicio("Entrega: lo pendiente");
    check(
        "Lista: agrupada por producto con su precio",
        qa(".entrega-encabezado").map((e) => [e.querySelector(".producto-nombre").textContent, e.querySelector(".producto-precio").textContent]),
        [["Estrella 25x35", "$85/kg"], ["Blanca #2", "$70/kg"], ["Caja 25x35 (5kg)", "$325 c/u"]]
    );
    check("Lista: un renglón por rollo y uno por producto normal", qa(".renglon").map((r) => r.dataset.renglon), ["m101", "m102", "p440", "p409"]);
    check("Lista: todos los renglones tienen «No se lo llevó»", qa(".renglon .btn-no-llevo").length, 4);
    check(
        "Lista: campo de peso con teclado decimal",
        [campoPeso(101).getAttribute("inputmode"), campoPeso(101).value, ecoDe(101)],
        ["decimal", "", "Escribe el peso"]
    );
    check(
        "Lista: marca «Sin existencia en sistema» (rollo 2 y caja)",
        ["m101", "m102", "p440", "p409"].map((c) => !!renglon(c).querySelector(".marca-sin-existencia")),
        [false, true, false, true]
    );
    check("Lista: la barra invita a revisar", [txt("#pedido-conteo"), txt("#pedido-accion")], ["Se lleva 4 de 4 renglones", "Revisar entrega ›"]);
    check("Entrega sin capturar nada: recargar no pregunta", pideConfirmarAlSalir(), false);

    // Productos normales: arranca en lo pendiente; "−" se detiene en 1.
    renglon("p440").querySelector(".btn-menos").click();
    await espera(5);
    check("Cantidad cambiada: recargar pregunta antes", pideConfirmarAlSalir(), true);
    renglon("p440").querySelector(".btn-mas").click();
    await espera(5);
    check("Cantidad de vuelta a lo pendiente: recargar no pregunta", pideConfirmarAlSalir(), false);
    check("Cantidad arranca en lo pendiente, «+» deshabilitado", [cantidadEntrega("p440"), renglon("p440").querySelector(".btn-mas").disabled], ["3 kg", true]);
    renglon("p440").querySelector(".btn-menos").click();
    await espera(5);
    renglon("p440").querySelector(".btn-menos").click();
    await espera(5);
    check("«−» baja de 1 en 1 hasta 1 y ahí se deshabilita", [cantidadEntrega("p440"), renglon("p440").querySelector(".btn-menos").disabled], ["1 kg", true]);
    renglon("p440").querySelector(".btn-menos").click();
    await espera(5);
    check("«−» nunca llega a 0", cantidadEntrega("p440"), "1 kg");

    // Peso vacío: bloquea y señala los rollos.
    q("#btn-pedido").click();
    await espera(80);
    check(
        "Peso vacío bloquea: no pasa al resumen ni pide la vista previa",
        [txt("#titulo"), llamadasA("vista_previa"), txt(".aviso-entrega")],
        ["Doña Carmen", 0, "Falta capturar el peso de 2 rollos. Si no se lo llevó, toca «No se lo llevó»."]
    );
    check("Peso vacío: señala cada rollo", [mensajeDe("m101"), mensajeDe("m102")], ["Falta el peso de este rollo.", "Falta el peso de este rollo."]);

    // Eco del peso.
    await escribirPeso(101, "1,250");
    check("Eco: peso interpretado e importe", ecoDe(101), "1.250 kg · $106.25");
    check("Con un peso escrito: recargar la página pregunta antes", pideConfirmarAlSalir(), true);
    check("Al escribir se quita la marca de falta", mensajeDe("m101"), null);
    await escribirPeso(101, "1.2.5");
    check("Eco: peso no válido", ecoDe(101), "Peso no válido");

    // "No se lo llevó" en un rollo y en un producto normal, y deshacer.
    botonNoLlevo("m102").click();
    await espera(10);
    check(
        "Rollo «No se lo llevó»: sin campo de peso, botón marcado",
        [!!campoPeso(102), botonNoLlevo("m102").getAttribute("aria-pressed"), renglon("m102").classList.contains("no-llevo")],
        [false, "true", true]
    );
    check("La barra cuenta lo que se lleva", txt("#pedido-conteo"), "Se lleva 3 de 4 renglones");
    botonNoLlevo("m102").click();
    await espera(10);
    check("Deshacer: vuelve el campo", [!!campoPeso(102), botonNoLlevo("m102").getAttribute("aria-pressed")], [true, "false"]);
    botonNoLlevo("m102").click();
    await espera(10);
    botonNoLlevo("p409").click();
    await espera(10);
    check("Producto «No se lo llevó»: sin − ni +", [!!renglon("p409").querySelector(".cantidad-controles"), botonNoLlevo("p409").getAttribute("aria-pressed")], [false, "true"]);
    botonNoLlevo("p409").click();
    await espera(10);
    check("Deshacer en producto: vuelve su cantidad", cantidadEntrega("p409"), "2 c/u");

    // Peso bloqueado: regresa a la lista señalando el rollo y el motivo.
    await escribirPeso(101, "1250");
    q("#btn-pedido").click();
    check("Revisando la entrega: INICIO gris y deshabilitado", inicioGris(), true);
    await espera(120);
    check(
        "Peso bloqueado: se queda en la lista con el motivo y la sugerencia",
        [txt("#titulo"), mensajeDe("m101"), renglon("m101").classList.contains("con-problema")],
        ["Doña Carmen", "Un rollo no puede pesar más de 15 kg. ¿Quisiste decir 1.250 kg?", true]
    );
    check("Peso bloqueado: aviso arriba", txt(".aviso-entrega"), "Corrige el peso de los rollos marcados.");

    // INICIO a media entrega: sale sin preguntar y lo capturado se conserva.
    await tocarInicio();
    check("INICIO con pesos capturados: directo, sin preguntar", [txt("#titulo"), q("#modal").hidden], ["Captura", true]);
    check("En el Inicio, recargar sigue avisando (hay pesos sin confirmar)", pideConfirmarAlSalir(), true);
    modo("Entrega").click();
    await espera(80);
    boton("Bosques").click();
    await espera(80);
    boton("Doña Carmen").click();
    await espera(120);
    check(
        "De vuelta en el cliente: el peso y la cantidad siguen ahí",
        [campoPeso(101).value, cantidadEntrega("p440"), cantidadEntrega("p409")],
        ["1250", "1 kg", "2 c/u"]
    );
}

async function pasoEntregaResumen() {
    // Advertencia que se corrige.
    await escribirPeso(101, "9");
    q("#btn-pedido").click();
    await espera(150);
    check("Resumen: título", [txt("#titulo"), txt(".pregunta")], ["Doña Carmen", "Revisa la entrega"]);
    checkInicio("Entrega: resumen");
    check(
        "Resumen: cada línea con su importe",
        qa(".resumen-entrega").map((l) => [l.querySelector(".resumen-detalle").textContent, l.querySelector(".resumen-importe").textContent]),
        [["9.000 kg", "$765.00"], ["1 kg de 3", "$70.00"], ["2 c/u", "$650.00"]]
    );
    check("Resumen: lo que no se llevó, aparte", qa(".resumen-no-llevo").map((e) => e.textContent), ["Estrella 25x35 · rollo 2"]);
    check("Resumen: TOTAL grande", txt(".total-monto"), "$1485.00");
    check("Resumen: advertencia visible", txt(".resumen-advertencia"), "⚠ Pesa más de 8 kg: revisa que esté bien.");
    check("Resumen: barra verde Confirmar", [txt("#pedido-accion"), q("#barra-pedido").classList.contains("para-enviar")], ["✓ Confirmar entrega", true]);
    q("#btn-pedido").click();
    await espera(30);
    check("Advertencia: pide confirmación", [q("#modal").hidden, txt("#modal-texto")], [false, "Estrella 25x35: 9.000 kg. Pesa más de 8 kg: revisa que esté bien."]);
    await responderModal(false);
    check(
        "Corregir: regresa a la lista con el rollo señalado y el peso conservado",
        [txt("#titulo"), q(".pregunta") && txt(".pregunta"), mensajeDe("m101"), campoPeso(101).value, confirmaciones.length],
        ["Doña Carmen", "¿Qué se lleva?", "Pesa más de 8 kg: revisa que esté bien.", "9", 0]
    );

    // Dos advertencias aceptadas una por una; otra persona cambió algo.
    botonNoLlevo("m102").click();
    await espera(10);
    await escribirPeso(102, "0.4");
    q("#btn-pedido").click();
    await espera(150);
    modoConfirmar = "cambiaron";
    q("#btn-pedido").click();
    await espera(30);
    check("Primera advertencia", txt("#modal-texto"), "Estrella 25x35: 9.000 kg. Pesa más de 8 kg: revisa que esté bien.");
    await responderModal(true);
    check("Segunda advertencia", [q("#modal").hidden, txt("#modal-texto")], [false, "Estrella 25x35: 0.400 kg. Pesa menos de 0.5 kg: revisa que esté bien."]);
    check("Con advertencias pendientes no se envía", confirmaciones.length, 0);
    await responderModal(true);
    await espera(250);
    check(
        "Otra persona cambió algo: mensaje claro y lista recargada",
        [txt("#titulo"), txt(".aviso-entrega"), qa(".renglon").map((r) => r.dataset.renglon)],
        ["Doña Carmen", "Otra persona ya validó o cambió entregas de este cliente. Se volvió a cargar lo pendiente: revisa y confirma otra vez.", ["m101", "p440"]]
    );
    check("Se conservan el peso y la cantidad de lo que sigue pendiente", [campoPeso(101).value, cantidadEntrega("p440")], ["9", "1 kg"]);
}

async function pasoEntregaConfirmar() {
    await escribirPeso(101, "1.250");
    q("#btn-pedido").click();
    await espera(150);
    check("Sin advertencias: TOTAL", txt(".total-monto"), "$176.25");
    const antes = confirmaciones.length;
    modoConfirmar = "sin-red";
    q("#btn-pedido").click();
    q("#btn-pedido").click(); // doble toque
    await espera(10);
    check("Confirmando: botón bloqueado", [q("#btn-pedido").disabled, txt("#pedido-accion")], [true, "Confirmando…"]);
    check("Confirmando la entrega: INICIO gris y deshabilitado", inicioGris(), true);
    history.back();
    await espera(30);
    check("Confirmando: atrás no sale de la pantalla", txt(".pregunta"), "Revisa la entrega");
    await espera(200);
    check("Doble toque: una sola confirmación", confirmaciones.length, antes + 1);
    const enviada = confirmaciones[confirmaciones.length - 1];
    check(
        "Datos enviados: rollos, productos, movimientos vistos y token",
        [enviada.rollos, enviada.productos, enviada.movimientos_vistos, /^[0-9a-f]{32}$/.test(enviada.token)],
        [[{ move_id: 101, peso: "1.250" }], [{ producto_id: 440, cantidad: 1 }], [101, 103], true]
    );
    check(
        "Sin señal: mismo mensaje que en Pedido",
        txt(".error-envio"),
        "No se pudo confirmar si la entrega llegó. Toca «Confirmar entrega» otra vez: si ya había llegado, no se duplica."
    );
    q("#btn-pedido").click();
    await espera(250);
    check("Reintento: mismo token", confirmaciones[confirmaciones.length - 1].token, enviada.token);
    check(
        "Éxito: Cobrar en grande, cliente y folios",
        [txt("#titulo"), txt(".cobrar"), txt(".enviado-detalle"), qa(".folios li").map((l) => l.textContent)],
        ["Entrega confirmada", "Cobrar: $176.25", "Doña Carmen", ["WH/OUT/00031 · S00050", "WH/OUT/00032 · S00051 (cancelada)"]]
    );
    check("Éxito: botones", qa(".lista .btn").map((b) => b.textContent), ["Siguiente cliente de Bosques", "Cambiar de zona"]);
    check("Éxito: sin barra", q("#barra-pedido").hidden, true);
    checkInicio("Entrega confirmada");
    check("Entrega confirmada: recargar ya no pregunta", pideConfirmarAlSalir(), false);
    boton("Siguiente cliente de Bosques").click();
    await espera(120);
    check("Siguiente cliente: clientes con pendientes de la zona", [txt("#titulo"), txt("#subtitulo")], ["Bosques", "Zona"]);
}

async function pasoEntregaAlgoMasYNada() {
    boton("Cliente con historial").click();
    await espera(120);
    botonNoLlevo("m201").click();
    await espera(10);
    boton("➕ El cliente quiere algo más").click();
    await espera(150);
    check(
        "Algo más: Modo Pedido con el cliente ya elegido",
        [txt("#titulo"), q("#categorias").hidden, nombresPestanas()[0]],
        ["Cliente con historial", false, "⭐ Lo de siempre"]
    );
    check("Solo «No se lo llevó» también cuenta como capturado", pideConfirmarAlSalir(), true);
    await tocarProducto(440, 1);
    q("#btn-inicio").click();
    await espera(30);
    check("Algo más: INICIO con pedido también pregunta", txt("#modal-texto"), "¿Vaciar el pedido de Cliente con historial? Tiene 1 producto sin enviar.");
    await responderModal(false);
    check(
        "Algo más: la misma tarjeta [ − ] 1 kg [ + ]",
        [...tarjeta(440).querySelectorAll(".producto-cantidades > *")].map((e) => e.textContent),
        ["−", "1 kg", "+"]
    );
    await restarProducto(440);
    check("Algo más: «−» en 1 lo quita", [cantidad(440), txt("#pedido-conteo")], [null, "Pedido vacío"]);
    await regresar();
    check(
        "Regresar: vuelve a la entrega con lo capturado",
        [txt(".pregunta"), botonNoLlevo("m201").getAttribute("aria-pressed")],
        ["¿Qué se lleva?", "true"]
    );

    // No se lleva nada: no pide peso, y confirmar pide una confirmación extra.
    q("#btn-pedido").click();
    await espera(150);
    check("Nada: resumen sin líneas y total $0", [txt(".aviso"), txt(".total-monto")], ["No se lleva nada.", "$0.00"]);
    const antes = confirmaciones.length;
    q("#btn-pedido").click();
    await espera(30);
    check(
        "Nada: confirmación extra",
        txt("#modal-texto"),
        "Cliente con historial no se lleva nada. Se cancelarán todas sus entregas pendientes."
    );
    await responderModal(false);
    check("Responder No: no se envía", [confirmaciones.length, txt(".pregunta")], [antes, "Revisa la entrega"]);
    q("#btn-pedido").click();
    await espera(30);
    await responderModal(true);
    await espera(200);
    const enviada = confirmaciones[confirmaciones.length - 1];
    check("Responder Sí: se envía sin rollos ni productos", [confirmaciones.length, enviada.rollos, enviada.productos, enviada.movimientos_vistos], [antes + 1, [], [], [201]]);
    check("Nada: éxito con Cobrar $0.00", txt(".cobrar"), "Cobrar: $0.00");
    await tocarInicio();
    check("INICIO desde Entrega confirmada: directo, sin preguntar", [txt("#titulo"), q("#modal").hidden], ["Captura", true]);
}

// === Modo Cobro ===

const hayBoton = (texto) => Boolean(boton(texto));
const importeDe = (clase) => txt(`.${clase} .resumen-importe`);
const mensajeMonto = () => {
    const nodo = q(".monto-mensaje");
    return nodo && !nodo.hidden ? nodo.textContent : null;
};

function checkAvisoBajoTotal(cliente) {
    // Justo debajo del total, el mismo texto del aviso que bloquea de arriba.
    const arriba = qa(".aviso-cobro.bloquea");
    const bajoTotal = q(".total-cobro").nextElementSibling;
    check(
        `${cliente}: debajo del total se repite el aviso que bloquea`,
        [arriba.length, bajoTotal && bajoTotal.matches(".aviso-cobro.bloquea") ? bajoTotal.textContent : null],
        [2, "Este cliente tiene una factura en borrador; confírmala o cancélala en Odoo."]
    );
    check(`${cliente}: el aviso de abajo es el mismo que el de arriba`, arriba[0].textContent === arriba[1]?.textContent, true);
}

async function pasoCobroClientes() {
    await irAInicio();
    modo("Cobro").click();
    await espera(80);
    check("Cobro: Zonas con subtítulo Cobro", [txt("#titulo"), txt("#subtitulo")], ["Zonas", "Cobro"]);
    boton("Guadalupana").click();
    await espera(80);
    check("Cobro: zona sin nada por cobrar", txt(".aviso"), "Nadie de esta zona tiene algo por cobrar");
    await regresar();
    boton("Bosques").click();
    await espera(80);
    check(
        "Cobro: solo clientes con algo por cobrar (ruta de Cobro)",
        [qa(".lista .btn").map((b) => b.textContent), llamadasA("cobro/clientes")],
        [["Doña Carmen", "Don Beto", "Mario fruta", "Cliente con historial"], 2]
    );
}

async function pasoCobroAvisos() {
    boton("Don Beto").click();
    await espera(120);
    check(
        "Borrador: aviso que bloquea, con el texto acordado",
        txt(".aviso-cobro.bloquea"),
        "Este cliente tiene una factura en borrador; confírmala o cancélala en Odoo."
    );
    check(
        "Borrador: sin botones de pago",
        [hayBoton("Pagó todo"), hayBoton("Pagó una parte"), hayBoton("No pagó hoy"), q(".acciones-cobro")],
        [false, false, false, null]
    );
    check("Borrador: el total se ve", txt(".total-cobro .total-monto"), "$325.00");
    checkAvisoBajoTotal("Borrador");
    checkAncho("detalle de cobro bloqueado (Don Beto)");
    await regresar();

    // Regresión (Mario fruta en duranDEV): líneas entregadas, con productos
    // repetidos, más saldo anterior y una factura en borrador. Con tantas
    // líneas el aviso de arriba no se ve junto al total: debajo del total,
    // donde irían los botones, debe decir por qué no se puede cobrar.
    boton("Mario fruta").click();
    await espera(120);
    check(
        "Mario fruta: 5 líneas entregadas, saldo anterior y total",
        [qa(".cobro-entregado").length, importesCobro(".cobro-anterior"), txt(".total-cobro .total-monto")],
        [5, [["INV/2026/00019", "Del 24/09/2026", "$118.00"]], "$544.50"]
    );
    check(
        "Mario fruta: sin botones de pago",
        [hayBoton("Pagó todo"), hayBoton("Pagó una parte"), hayBoton("No pagó hoy"), q(".acciones-cobro")],
        [false, false, false, null]
    );
    checkAvisoBajoTotal("Mario fruta");
    checkAncho("detalle de cobro de Mario fruta");
    await regresar();
    boton("Cliente con historial").click();
    await espera(120);
    check(
        "Devolución sin nota de crédito: aviso informativo, con botones de pago",
        [txt(".aviso-cobro.informativo"), q(".aviso-cobro.bloquea"), hayBoton("Pagó todo")],
        ["Hay devoluciones sin nota de crédito (S00040). No entran en este cobro: haz la nota de crédito en Odoo.", null, true]
    );
    check(
        "Solo saldo anterior: sin sección de entregado",
        [qa(".cobro-entregado").length, importesCobro(".cobro-anterior")],
        [0, [["INV/2026/00015", "Del 25/09/2026", "$150.00"]]]
    );
    await regresar();
}

async function pasoCobroDetalle() {
    boton("Doña Carmen").click();
    await espera(120);
    check("Detalle: título cliente y zona", [txt("#titulo"), txt("#subtitulo")], ["Doña Carmen", "Bosques"]);
    checkInicio("Cobro: lo que debe");
    check(
        "Detalle: entregado sin facturar con pesos, precios e importes",
        importesCobro(".cobro-entregado"),
        [["Estrella 25x35", "1.250 kg · $85.00/kg", "$106.25"], ["Blanca #2", "3 kg · $70.00/kg", "$210.00"]]
    );
    check("Detalle: saldo anterior con fecha y saldo", importesCobro(".cobro-anterior"), [["INV/2026/00012", "Del 20/09/2026", "$1,000.00"]]);
    check("Detalle: saldo a favor restado", importesCobro(".cobro-credito"), [["RINV/2026/00003", "Del 21/09/2026", "−$16.25"]]);
    check("Detalle: TOTAL A COBRAR grande, con formato $1,234.50", [txt(".total-cobro .total-etiqueta"), txt(".total-cobro .total-monto")], ["Total a cobrar", "$1,300.00"]);
    const botones = qa(".acciones-cobro .btn");
    check(
        "Detalle: «Pagó todo» principal; las otras dos, secundarias",
        botones.map((b) => [b.textContent, b.classList.contains("btn-primario"), b.classList.contains("btn-secundario")]),
        [["Pagó todo", true, false], ["Pagó una parte", false, true], ["No pagó hoy", false, true]]
    );
    check("Detalle: recargar no pregunta", pideConfirmarAlSalir(), false);
}

async function pasoCobroParte() {
    boton("Pagó una parte").click();
    await espera(80);
    check("Una parte: título y campo con teclado decimal", [txt(".pregunta"), q(".monto-campo").getAttribute("inputmode")], ["Pagó una parte", "decimal"]);
    check("Una parte: sin monto, el eco lo pide", txt(".monto-eco"), "Escribe cuánto pagó");
    checkInicio("Cobro: confirmación");
    check("Una parte vacía: recargar no pregunta", pideConfirmarAlSalir(), false);
    await escribirMonto("100,5");
    check(
        "Eco en vivo (con coma decimal)",
        [txt(".monto-eco"), importeDe("cobro-total"), importeDe("cobro-recibido"), importeDe("cobro-debe")],
        ["Recibe $100.50 · Queda debiendo $1,199.50", "$1,300.00", "$100.50", "$1,199.50"]
    );
    check("Con un monto escrito: recargar pregunta antes", pideConfirmarAlSalir(), true);
    await tocarInicio();
    check("INICIO con monto escrito: directo, sin preguntar", [txt("#titulo"), q("#modal").hidden], ["Captura", true]);
    modo("Cobro").click();
    await espera(80);
    boton("Bosques").click();
    await espera(80);
    boton("Doña Carmen").click();
    await espera(120);
    boton("Pagó una parte").click();
    await espera(80);
    check("De vuelta en el cobro: el monto sigue ahí", [q(".monto-campo").value, importeDe("cobro-recibido")], ["100,5", "$100.50"]);
    for (const [texto, mensaje] of [
        ["0", "El importe debe ser mayor a $0."],
        ["", "Escribe cuánto pagó."],
        ["1300.01", "No puede ser más que el total a cobrar ($1,300.00). Si pagó todo, regresa y toca «Pagó todo»."],
        ["12.345", "Escribe el importe con máximo 2 decimales, por ejemplo 150.50."],
    ]) {
        await escribirMonto(texto);
        check(`Monto «${texto}»: sin mensaje hasta intentar registrar`, mensajeMonto(), null);
        boton("✓ Registrar cobro").click();
        await espera(30);
        check(`Monto «${texto}»: no continúa, mensaje claro`, [mensajeMonto(), cobrosEnviados.length, txt(".pregunta")], [mensaje, 0, "Pagó una parte"]);
    }
    check("Monto de más: el eco no lo acepta", txt(".monto-eco"), "Importe no válido");
    await escribirMonto("1,300");
    check("La coma es decimal (no de miles): «1,300» no es válido", txt(".monto-eco"), "Importe no válido");
    await escribirMonto("1300");
    check("Justo el total: queda debiendo $0.00", txt(".monto-eco"), "Recibe $1,300.00 · Queda debiendo $0.00");

    // Otra persona facturó o cobró mientras tanto.
    await escribirMonto("250");
    modoCobro = "cambiaron";
    boton("✓ Registrar cobro").click();
    await espera(250);
    const enviado = cobrosEnviados[0];
    check(
        "Datos enviados: tipo, monto, lo visto y token",
        [enviado.tipo, enviado.monto, enviado.visto.documentos, /^[0-9a-f]{32}$/.test(enviado.token)],
        ["parte", 250, [[501, 1000], [502, 16.25]], true]
    );
    check(
        "Cambiaron: mensaje claro y detalle recargado con los datos nuevos",
        [txt("#titulo"), txt(".aviso-cobro"), txt(".total-cobro .total-monto"), !!q(".acciones-cobro")],
        [
            "Doña Carmen",
            "Otra persona facturó o cobró a este cliente mientras tanto. Se volvió a cargar lo que debe: revisa el total y cobra otra vez.",
            "$1,200.00",
            true,
        ]
    );
    check("Cambiaron: saldo anterior nuevo", importesCobro(".cobro-anterior")[0][2], "$900.00");
}

async function pasoCobroEnviar() {
    const tokenCambiaron = cobrosEnviados[0].token;
    boton("Pagó una parte").click();
    await espera(80);
    check("Se conserva el monto, con el total nuevo", [q(".monto-campo").value, txt(".monto-eco")], ["250", "Recibe $250.00 · Queda debiendo $950.00"]);
    const antes = cobrosEnviados.length;
    modoCobro = "sin-red";
    boton("✓ Registrar cobro").click();
    q(".btn-registrar-cobro").click(); // doble toque
    await espera(10);
    check("Registrando: botón bloqueado", [q(".btn-registrar-cobro").disabled, txt(".btn-registrar-cobro")], [true, "Registrando…"]);
    check("Registrando el cobro: INICIO gris y deshabilitado", inicioGris(), true);
    history.back();
    await espera(30);
    check("Registrando: atrás no sale de la pantalla", txt(".pregunta"), "Pagó una parte");
    await espera(200);
    check("Doble toque: un solo envío", cobrosEnviados.length, antes + 1);
    const primero = cobrosEnviados[cobrosEnviados.length - 1];
    check("Token nuevo después de «cambiaron»", primero.token !== tokenCambiaron, true);
    check(
        "Sin señal: mensaje y reintento seguro",
        txt(".error-envio"),
        "No se pudo confirmar si el cobro llegó. Toca «Registrar cobro» otra vez: si ya había llegado, no se duplica."
    );
    boton("✓ Registrar cobro").click();
    await espera(250);
    check("Reintento: mismo token", cobrosEnviados[cobrosEnviados.length - 1].token, primero.token);
    check(
        "Éxito: Cobrado en grande, queda debiendo, cliente y factura",
        [txt("#titulo"), txt(".cobrar"), txt(".queda-debiendo"), txt(".enviado-detalle"), qa(".folios li").map((l) => l.textContent)],
        ["Cobro registrado", "Cobrado: $250.00", "Queda debiendo: $950.00", "Doña Carmen · Pagó una parte", ["Factura INV/2026/00020"]]
    );
    check("Éxito: botones", qa(".lista .btn").map((b) => b.textContent), ["Siguiente cliente de Bosques", "Cambiar de zona"]);
    check("Cobro registrado: recargar ya no pregunta", pideConfirmarAlSalir(), false);
    checkInicio("Cobro registrado");
    boton("Siguiente cliente de Bosques").click();
    await espera(120);
    // Pedidos: Guadalupana, Bosques, tres «Regresar», la vuelta desde INICIO y este.
    check("Siguiente cliente: clientes por cobrar de la zona", [txt("#titulo"), llamadasA("cobro/clientes")], ["Bosques", 7]);
}

async function pasoCobroTodoYNada() {
    boton("Cliente con historial").click();
    await espera(120);
    boton("Pagó todo").click();
    await espera(80);
    check(
        "Pagó todo: resumen sin campo de monto",
        [txt(".pregunta"), q(".monto-campo"), importeDe("cobro-recibido"), importeDe("cobro-debe")],
        ["Pagó todo", null, "$150.00", "$0.00"]
    );
    boton("✓ Registrar cobro").click();
    await espera(200);
    const todo = cobrosEnviados[cobrosEnviados.length - 1];
    check("Pagó todo: se envía sin monto", [todo.tipo, "monto" in todo], ["todo", false]);
    check("Pagó todo: éxito sin «queda debiendo»", [txt(".cobrar"), q(".queda-debiendo")], ["Cobrado: $150.00", null]);

    await tocarInicio();
    check("INICIO desde Cobro registrado: directo, sin preguntar", [txt("#titulo"), q("#modal").hidden], ["Captura", true]);
    modo("Cobro").click();
    await espera(80);
    boton("Bosques").click();
    await espera(80);
    boton("Doña Carmen").click();
    await espera(120);
    boton("No pagó hoy").click();
    await espera(80);
    check("No pagó hoy: resumen", [importeDe("cobro-recibido"), importeDe("cobro-debe")], ["$0.00", "$1,200.00"]);
    const antes = cobrosEnviados.length;
    boton("✓ Registrar cobro").click();
    await espera(30);
    check("No pagó hoy: confirmación extra", [q("#modal").hidden, txt("#modal-texto")], [false, "La deuda de $1,200.00 quedará pendiente."]);
    await responderModal(false);
    check("Responder No: no se envía", [cobrosEnviados.length, txt(".pregunta")], [antes, "No pagó hoy"]);
    boton("✓ Registrar cobro").click();
    await espera(30);
    await responderModal(true);
    await espera(200);
    check("Responder Sí: se envía «nada»", [cobrosEnviados.length, cobrosEnviados[cobrosEnviados.length - 1].tipo], [antes + 1, "nada"]);
    check("No pagó hoy: éxito", [txt(".cobrar"), txt(".queda-debiendo")], ["Cobrado: $0.00", "Queda debiendo: $1,200.00"]);
    boton("Cambiar de zona").click();
    await espera(120);
    check("Cambiar de zona: Zonas de Cobro", [txt("#titulo"), txt("#subtitulo")], ["Zonas", "Cobro"]);
}

// === Historial de más de 50 pantallas (Chrome borra las más antiguas) ===

async function enviarUnPedido() {
    await tocarProducto(409, 1);
    q("#btn-pedido").click();
    await espera(40);
    q("#btn-pedido").click();
    await espera(120);
}

async function pasoHistorialLargo() {
    await irAInicio();
    modo("Pedido").click();
    await espera(60);
    boton("Bosques").click();
    await espera(60);
    boton("Doña Carmen").click();
    await espera(100);
    await enviarUnPedido();
    for (let i = 0; i < 16; i++) {
        boton("Siguiente cliente de Bosques").click();
        await espera(60);
        boton("Doña Carmen").click();
        await espera(100);
        await enviarUnPedido();
    }
    check(
        "Historial largo: Chrome guarda máximo 50 y la app lleva más de 50 pantallas",
        [history.length, history.state.nivel > history.length, txt("#titulo")],
        [50, true, "Pedido enviado"]
    );
    await tocarInicio();
    check("Historial largo: INICIO no sale de la página", location.pathname.endsWith("captura.html"), true);
    await espera(750); // la primera entrada ya no existe: entra el respaldo de 600 ms
    check(
        "Historial largo: INICIO llega al Inicio",
        [txt("#titulo"), q("#btn-inicio").hidden, history.state.pantalla, history.state.nivel],
        ["Captura", true, "inicio", 0]
    );
    modo("Pedido").click();
    await espera(80);
    check("Después del respaldo, la app navega normal", [txt("#titulo"), history.state.nivel], ["Zonas", 1]);
    await tocarInicio();
    check("Y el siguiente INICIO va directo, sin respaldo", txt("#titulo"), "Captura");
}

// === Acomodo de entregas ===

function checkCuatroModosSinDeslizar(pantalla) {
    const ultimo = modo("Acomodo de entregas").getBoundingClientRect();
    check(
        `${pantalla}: los 4 botones caben sin deslizar (393 x 852)`,
        [ultimo.bottom <= window.innerHeight, document.documentElement.scrollHeight <= window.innerHeight],
        [true, true]
    );
}

const renglonesAcomodo = (pedidoId) =>
    qa(`[data-pedido="${pedidoId}"] .acomodo-producto`).map((r) => [
        r.querySelector(".acomodo-producto-nombre").textContent,
        r.querySelector(".acomodo-cantidad").textContent,
    ]);

async function pasoAcomodo() {
    await irAInicio();
    const antes = llamadasA("acomodo");
    modo("Acomodo de entregas").click();
    await espera(80);
    check(
        "Acomodo: título, sin subtítulo, sin barra de abajo ni pestañas",
        [txt("#titulo"), q("#subtitulo").hidden, q("#barra-pedido").hidden, q("#categorias").hidden],
        ["Acomodo de entregas", true, true, true]
    );
    check("Acomodo: abre directo, pidiendo los datos al servidor", llamadasA("acomodo"), antes + 1);
    checkInicio("Acomodo de entregas");
    check(
        "Acomodo: un encabezado grande por zona, en el orden del servidor",
        qa(".acomodo-zona-nombre").map((e) => e.textContent),
        ["Bosques", "Tianguis Mercado Jardines de la Montaña Poniente", "Sin zona"]
    );
    check(
        "Acomodo: en cada zona, las etiquetas Producto y Cantidad",
        qa(".acomodo-columnas").map((e) => [...e.children].map((c) => c.textContent)),
        [["Producto", "Cantidad"], ["Producto", "Cantidad"], ["Producto", "Cantidad"]]
    );
    check(
        "Acomodo: la posición reinicia en 1 en cada zona",
        qa(".acomodo-zona").map((z) => [...z.querySelectorAll(".acomodo-posicion")].map((e) => e.textContent)),
        [["1", "2", "3", "4", "5", "6"], ["1"], ["1"]]
    );
    check(
        "Acomodo: clientes en el orden de llegada (un cliente que vuelve a pedir sale otra vez)",
        [...qa(".acomodo-zona")[0].querySelectorAll(".acomodo-cliente-nombre")].map((e) => e.textContent),
        ["Doña Carmen", "Tortillería La Guadalupana de Doña Lupita", "<b>Cliente con HTML</b>", "Doña Carmen", "Cliente con historial", "Don Beto"]
    );
    check("Acomodo: un nombre con HTML se muestra como texto", qa(".acomodo-pedido b").length, 0);
    check(
        "Acomodo: renglones del pedido con su cantidad (rollos por pieza, sin peso)",
        renglonesAcomodo(60),
        [["Blanca #2", "5 kg"], ["Estrella 25x35", "2 rollos"], ["Caja 25x35 (5kg)", "2 c/u"]]
    );
    check(
        "Acomodo: lo que se pesa pero se vende por kg dice kg; un rollo normal, rollos",
        renglonesAcomodo(65),
        [["Caja 25x35 (5kg)", "1 c/u"], ["Hoja polipapel 25x35 (KG suelto)", "3 kg"], ["Estrella 25x35", "3 rollos"]]
    );
    check("Acomodo: un rollo en singular y decimales como en Entrega", [renglonesAcomodo(62), renglonesAcomodo(61)[0][1]], [[["Estrella 25x35", "1 rollo"]], "1.5 kg"]);
    check("Acomodo: sin totales ni precios", [/total/i.test(txt("#contenido")), txt("#contenido").includes("$")], [false, false]);
    const cantidad = q('[data-pedido="60"] .acomodo-cantidad');
    const nombre = q('[data-pedido="60"] .acomodo-producto-nombre');
    check(
        "Acomodo: cantidad a la derecha, más grande y en negritas que el producto",
        [
            cantidad.getBoundingClientRect().right > nombre.getBoundingClientRect().right,
            parseFloat(getComputedStyle(cantidad).fontSize) > parseFloat(getComputedStyle(nombre).fontSize),
            Number(getComputedStyle(cantidad).fontWeight) >= 700,
            Number(getComputedStyle(q(".acomodo-cliente-nombre")).fontWeight) >= 700,
        ],
        [true, true, true, true]
    );
    checkAncho("Acomodo con nombres largos");
    window.scrollTo(0, 400);
    await espera(30);
    check(
        "Acomodo: al deslizar, el nombre de la zona se queda pegado bajo la barra",
        Math.abs(qa(".acomodo-zona-nombre")[0].getBoundingClientRect().top - q(".barra").getBoundingClientRect().bottom) <= 1,
        true
    );
    checkInicio("Acomodo de entregas, deslizada");

    await regresar();
    check("Acomodo: Regresar vuelve al Inicio", txt("#titulo"), "Captura");
    modo("Acomodo de entregas").click();
    await espera(80);
    check("Acomodo: al volver a abrir pide datos frescos (sin botón Actualizar)", [llamadasA("acomodo"), !!boton("Actualizar")], [antes + 2, false]);
    await tocarInicio();
    check("Acomodo: INICIO vuelve al Inicio", [txt("#titulo"), history.state.nivel], ["Captura", 0]);

    modoAcomodo = "vacio";
    modo("Acomodo de entregas").click();
    await espera(80);
    check(
        "Acomodo sin pedidos: mensaje claro y grande",
        [txt(".aviso-grande"), parseFloat(getComputedStyle(q(".aviso-grande")).fontSize) >= 24, qa(".acomodo-zona").length],
        ["Hoy no hay pedidos pendientes de entregar.", true, 0]
    );
    await tocarInicio();

    modoAcomodo = "sin-red";
    modo("Acomodo de entregas").click();
    await espera(80);
    check("Acomodo sin señal: mensaje y botón para reintentar", [txt(".aviso"), !!boton("Intentar de nuevo")], ["No hay conexión. Revisa la señal e intenta de nuevo.", true]);
    boton("Intentar de nuevo").click();
    await espera(80);
    check("Acomodo: Intentar de nuevo carga la lista", qa(".acomodo-zona").length, 3);
    await tocarInicio();
}

// === Tarjetas con cantidades grandes y nombres largos ===

function checkTarjetaSinEncimarse(id, pantalla) {
    // Dentro de la tarjeta y sin encimarse: [ − ] número [ + ], y el nombre arriba.
    const t = tarjeta(id).getBoundingClientRect();
    const menos = botonMenos(id).getBoundingClientRect();
    const mas = botonMas(id).getBoundingClientRect();
    const numero = q(`[data-producto="${id}"] .producto-cantidad-texto`);
    const n = numero.getBoundingClientRect();
    const nombre = q(`[data-producto="${id}"] .producto-nombre`).getBoundingClientRect();
    check(
        `Sin encimarse a 393 x 852: ${pantalla}`,
        [
            menos.left >= t.left && mas.right <= t.right,
            menos.right <= n.left && n.right <= mas.left,
            numero.scrollWidth <= numero.clientWidth,
            nombre.bottom <= Math.min(menos.top, mas.top) && nombre.right <= t.right,
        ],
        [true, true, true, true]
    );
}

async function pasoTarjetasGrandes() {
    await irAInicio();
    modo("Pedido").click();
    await espera(80);
    boton("Bosques").click();
    await espera(80);
    boton("Doña Carmen").click();
    await espera(120);
    await tocarProducto(472, 3);
    check(
        "KG suelto (se pesa, pero se vende por kg): «3 kg», con su precio por kg",
        [cantidad(472), tarjeta(472).querySelector(".producto-precio").textContent],
        ["3 kg", "$70/kg"]
    );
    pestana("Rollos").click();
    await espera(20);
    await tocarProducto(464, 3);
    check("Un rollo normal sigue diciendo «3 rollos»", cantidad(464), "3 rollos");
    await restarProducto(464, 3);
    pestana("Bolsas asa").click();
    await espera(20);
    await restarProducto(472, 3);
    for (let i = 0; i < 999; i++) {
        botonMas(409).click();
    }
    await espera(10);
    check("999 toques: 999 c/u, con la pestaña y la barra al día", [cantidad(409), txt('.categoria[aria-selected="true"] .categoria-conteo'), txt("#pedido-conteo")], ["999 c/u", "999", "999 productos en el pedido"]);
    // El catálogo de prueba no tiene nombres largos: se alarga el de la tarjeta
    // para revisar cómo se acomoda.
    q('[data-producto="409"] .producto-nombre').textContent = "Bolsa de basura jumbo negra extra gruesa 90x120 calibre 300";
    checkTarjetaSinEncimarse(409, "nombre largo y 999 c/u");
    pestana("Rollos").click();
    await espera(20);
    for (let i = 0; i < 999; i++) {
        botonMas(464).click();
    }
    await espera(10);
    check("999 toques en un rollo: 999 rollos", cantidad(464), "999 rollos");
    q('[data-producto="464"] .producto-nombre').textContent = "Bolsa de basura 90x120";
    checkTarjetaSinEncimarse(464, "Bolsa de basura 90x120 y 999 rollos");
    checkAncho("tarjetas con 999");
    q("#btn-inicio").click();
    await espera(30);
    await responderModal(true);
    check("Al salir con INICIO se vacía el pedido grande", [txt("#titulo"), pideConfirmarAlSalir()], ["Captura", false]);
}

// === Usuario de tianguis (sin data-salir en <body>) ===

async function pasoTianguisSinSalir() {
    await espera(80);
    check("Tianguis: Inicio sin botón Salir", [txt("#titulo"), q("#btn-regresar").hidden, !!boton("‹ Salir")], ["Captura", true, false]);
    check("Tianguis: en Inicio la fila de botones no ocupa lugar", [q("#barra-botones").hidden, q("#btn-inicio").hidden], [true, true]);
    checkCuatroModosSinDeslizar("Inicio de tianguis");
    checkAncho("Inicio de tianguis");
    q("#btn-regresar").click(); // aunque se tocara, no sale de la pantalla
    await espera(120);
    check("Tianguis: tocar el botón escondido no sale de Inicio", [location.pathname.endsWith("tianguis.html"), txt("#titulo")], [true, "Captura"]);
    modo("Pedido").click();
    await espera(80);
    check("Tianguis: en Zonas sí hay «Regresar»", [txt("#titulo"), q("#btn-regresar").hidden, txt("#btn-regresar")], ["Zonas", false, "‹ Regresar"]);
    checkInicio("Zonas (tianguis)");
    await tocarInicio();
    check(
        "Tianguis: INICIO vuelve al Inicio sin salir de la página, y la fila se oculta otra vez",
        [txt("#titulo"), location.pathname.endsWith("tianguis.html"), q("#barra-botones").hidden],
        ["Captura", true, true]
    );
    modo("Pedido").click();
    await espera(80);
    await regresar();
    check("Tianguis: de vuelta en Inicio, otra vez sin botón", [txt("#titulo"), q("#btn-regresar").hidden], ["Captura", true]);
}

const PASOS_TIANGUIS = [pasoTianguisSinSalir];

const PASOS = [
    pasoInicio, pasoZonas, pasoClientes, pasoProductos, pasoConfirmarAntesDeVaciar, pasoLoDeSiempre,
    pasoResumen, pasoEnviar, pasoInicioConPedido, pasoEntregaClientes, pasoEntregaLista, pasoEntregaResumen,
    pasoEntregaConfirmar, pasoEntregaAlgoMasYNada,
    pasoCobroClientes, pasoCobroAvisos, pasoCobroDetalle, pasoCobroParte, pasoCobroEnviar, pasoCobroTodoYNada,
    pasoHistorialLargo, pasoAcomodo, pasoTarjetasGrandes,
];

window.addEventListener("load", async () => {
    let pasoActual = "arranque";
    // Si un paso se queda esperando (p. ej. un modal sin responder), se
    // publican los resultados de todos modos, diciendo en qué paso se atoró.
    const limite = new Promise((resolver) => setTimeout(() => resolver("tiempo"), 45000));
    const recorrido = (async () => {
        await espera(80);
        for (const paso of document.body.dataset.salir === "1" ? PASOS : PASOS_TIANGUIS) {
            pasoActual = paso.name;
            await paso();
            checkAncho(`al terminar ${paso.name} (${txt("#titulo")})`);
        }
    })();
    try {
        if ((await Promise.race([recorrido, limite])) === "tiempo") {
            resultados.push(`FALLA | el recorrido se atoró en ${pasoActual} | pantalla: ${txt("#titulo")}`);
        }
    } catch (error) {
        resultados.push(`FALLA | excepción en ${pasoActual} | ${error.stack}`);
    }
    const salida = document.createElement("pre");
    salida.id = "resultado-prueba";
    salida.textContent = resultados.join("\n");
    document.body.append(salida);
});
