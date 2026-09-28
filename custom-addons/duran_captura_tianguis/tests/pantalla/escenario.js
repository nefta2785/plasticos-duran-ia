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
        [["Pedido", "Levantar un pedido nuevo"], ["Entrega", "Entregar lo que ya pidieron"]]
    );
    check("Inicio: sin barra de pedido ni pestañas", [q("#barra-pedido").hidden, q("#categorias").hidden], [true, true]);
    check("Inicio: los dos modos habilitados", [modo("Pedido").disabled, modo("Entrega").disabled], [false, false]);
    check("Inicio: no llama al servidor", llamadas.length, 0);

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
    check("Pedido vacío: recargar no pregunta", pideConfirmarAlSalir(), false);

    await tocarProducto(440, 3);
    check("3 toques = 3 kg", cantidad(440), "3 kg");
    check("Con pedido: recargar la página pregunta antes", pideConfirmarAlSalir(), true);
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
    await espera(120);
    check(
        "Peso bloqueado: se queda en la lista con el motivo y la sugerencia",
        [txt("#titulo"), mensajeDe("m101"), renglon("m101").classList.contains("con-problema")],
        ["Doña Carmen", "Un rollo no puede pesar más de 15 kg. ¿Quisiste decir 1.250 kg?", true]
    );
    check("Peso bloqueado: aviso arriba", txt(".aviso-entrega"), "Corrige el peso de los rollos marcados.");
}

async function pasoEntregaResumen() {
    // Advertencia que se corrige.
    await escribirPeso(101, "9");
    q("#btn-pedido").click();
    await espera(150);
    check("Resumen: título", [txt("#titulo"), txt(".pregunta")], ["Doña Carmen", "Revisa la entrega"]);
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
}

const PASOS = [
    pasoInicio, pasoZonas, pasoClientes, pasoProductos, pasoConfirmarAntesDeVaciar, pasoLoDeSiempre,
    pasoResumen, pasoEnviar, pasoEntregaClientes, pasoEntregaLista, pasoEntregaResumen,
    pasoEntregaConfirmar, pasoEntregaAlgoMasYNada,
];

window.addEventListener("load", async () => {
    let pasoActual = "arranque";
    // Si un paso se queda esperando (p. ej. un modal sin responder), se
    // publican los resultados de todos modos, diciendo en qué paso se atoró.
    const limite = new Promise((resolver) => setTimeout(() => resolver("tiempo"), 25000));
    const recorrido = (async () => {
        await espera(80);
        for (const paso of PASOS) {
            pasoActual = paso.name;
            await paso();
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
