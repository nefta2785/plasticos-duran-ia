/* Captura tianguis: Zona → Cliente → Productos, con el pedido en memoria.
 *
 * JavaScript sin frameworks. Los datos vienen de las rutas jsonrpc de
 * controllers/main.py. Todo texto que viene de Odoo se pinta con textContent
 * (nunca como HTML).
 *
 * Cada pantalla es una entrada del historial del navegador: el botón "atrás"
 * del celular hace lo mismo que "Regresar", incluida la confirmación antes de
 * vaciar un pedido. */
(function () {
    "use strict";

    const $ = (id) => document.getElementById(id);
    const ui = {
        barra: document.querySelector(".barra"),
        regresar: $("btn-regresar"),
        titulo: $("titulo"),
        subtitulo: $("subtitulo"),
        categorias: $("categorias"),
        contenido: $("contenido"),
        barraPedido: $("barra-pedido"),
        btnPedido: $("btn-pedido"),
        pedidoConteo: $("pedido-conteo"),
        pedidoAccion: $("pedido-accion"),
        modal: $("modal"),
        modalTexto: $("modal-texto"),
        modalSi: $("modal-si"),
        modalNo: $("modal-no"),
    };

    const estado = {
        pantalla: "zonas", // "zonas" | "clientes" | "productos" | "resumen" | "enviado"
        zona: null, // {id, nombre}
        cliente: null, // {id, nombre}
        categoriaId: null, // pestaña activa: id de categoría o PESTANA_HABITUALES
        pedido: new Map(), // id de producto -> cantidad entera (>= 1)
        habituales: [], // "Lo de siempre" del cliente actual
        clienteDibujado: null, // para abrir "Lo de siempre" al llegar a otro cliente
        token: null, // identifica ESTE pedido ante el servidor (evita duplicados)
        enviando: false,
        errorEnvio: null,
        envio: null, // respuesta del servidor del último pedido enviado
    };
    // Pantallas donde hay un pedido en curso (salir de ellas lo vacía).
    const PANTALLAS_PEDIDO = ["productos", "resumen"];
    const PESTANA_HABITUALES = "habituales";
    let catalogo = null; // [{id, nombre, productos: [...]}], se carga una sola vez
    let numeroVista = 0; // para descartar respuestas de una pantalla que ya se dejó
    let confirmando = false;

    // === Utilidades ===

    function el(tag, props = {}, ...hijos) {
        const nodo = document.createElement(tag);
        for (const [clave, valor] of Object.entries(props)) {
            if (clave === "class") {
                nodo.className = valor;
            } else if (clave === "text") {
                nodo.textContent = valor;
            } else if (clave.startsWith("on")) {
                nodo.addEventListener(clave.slice(2), valor);
            } else if (valor !== false && valor !== null && valor !== undefined) {
                nodo.setAttribute(clave, valor);
            }
        }
        for (const hijo of hijos) {
            if (hijo) {
                nodo.append(hijo);
            }
        }
        return nodo;
    }

    function plural(n, uno, varios) {
        return `${n} ${n === 1 ? uno : varios}`;
    }

    function totalPiezas(productos) {
        // Suma de cantidades: 2 rollos + 3 kg = 5 productos.
        return productos.reduce((total, p) => total + (estado.pedido.get(p.id) || 0), 0);
    }

    function totalPedido() {
        let total = 0;
        for (const cantidad of estado.pedido.values()) {
            total += cantidad;
        }
        return total;
    }

    function lista(nodos) {
        return el("ul", { class: "lista" }, ...nodos.map((nodo) => el("li", {}, nodo)));
    }

    function sinRespuesta(mensaje) {
        // Error sin respuesta clara de Odoo: no se sabe si la petición llegó.
        const error = new Error(mensaje);
        error.sinRespuesta = true;
        return error;
    }

    async function api(ruta, params = {}) {
        let respuesta;
        try {
            respuesta = await fetch(ruta, {
                method: "POST",
                credentials: "same-origin",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ jsonrpc: "2.0", method: "call", id: Date.now(), params }),
            });
        } catch {
            throw sinRespuesta("No hay conexión. Revisa la señal e intenta de nuevo.");
        }
        if (!respuesta.ok) {
            throw sinRespuesta(`Odoo no respondió (error ${respuesta.status}). Intenta de nuevo.`);
        }
        let datos;
        try {
            datos = await respuesta.json();
        } catch {
            throw sinRespuesta("Odoo respondió algo inesperado. Intenta de nuevo.");
        }
        if (datos.error) {
            if (datos.error.code === 100) {
                // Sesión expirada: de vuelta al login y después a /captura.
                window.removeEventListener("beforeunload", avisarAntesDeSalir);
                window.location.href = "/web/login?redirect=" + encodeURIComponent("/captura");
                throw new Error("Tu sesión terminó. Vuelve a entrar.");
            }
            throw new Error((datos.error.data && datos.error.data.message) || datos.error.message);
        }
        return datos.result;
    }

    // === Confirmación (en lugar de window.confirm, que en celular es diminuto) ===

    function confirmar(texto, textoSi, textoNo) {
        confirmando = true;
        return new Promise((resolver) => {
            ui.modalTexto.textContent = texto;
            ui.modalSi.textContent = textoSi;
            ui.modalNo.textContent = textoNo;
            ui.modal.hidden = false;
            ui.modalNo.focus();
            const cerrar = (respuesta) => {
                ui.modal.hidden = true;
                ui.modalSi.onclick = ui.modalNo.onclick = ui.modal.onclick = null;
                confirmando = false;
                resolver(respuesta);
            };
            ui.modalSi.onclick = () => cerrar(true);
            ui.modalNo.onclick = () => cerrar(false);
            ui.modal.onclick = (evento) => {
                if (evento.target === ui.modal) {
                    cerrar(false);
                }
            };
        });
    }

    // === Navegación ===

    function fotoHistorial() {
        return {
            pantalla: estado.pantalla,
            zona: estado.zona,
            cliente: estado.cliente,
            envio: estado.pantalla === "enviado" ? estado.envio : null,
        };
    }

    function irA(pantalla, datos) {
        Object.assign(estado, { pantalla }, datos);
        history.pushState(fotoHistorial(), "");
        dibujar();
    }

    async function alMoverseEnHistorial(evento) {
        const destino = evento.state || { pantalla: "zonas", zona: null, cliente: null };
        if (confirmando || estado.enviando) {
            // "Atrás" mientras se pregunta o mientras se envía: se queda aquí.
            history.pushState(fotoHistorial(), "");
            return;
        }
        const mismoCliente =
            PANTALLAS_PEDIDO.includes(destino.pantalla) &&
            destino.cliente &&
            estado.cliente &&
            destino.cliente.id === estado.cliente.id;
        const dejaElPedido = PANTALLAS_PEDIDO.includes(estado.pantalla) && !mismoCliente;
        if (dejaElPedido && estado.pedido.size) {
            const vaciar = await confirmar(
                `¿Vaciar el pedido de ${estado.cliente.nombre}? ` +
                    `Tiene ${plural(totalPedido(), "producto", "productos")} sin enviar.`,
                "Sí, vaciar el pedido",
                "No, seguir con el pedido"
            );
            if (!vaciar) {
                history.pushState(fotoHistorial(), "");
                return;
            }
        }
        if (dejaElPedido) {
            vaciarPedido();
        }
        Object.assign(estado, {
            pantalla: destino.pantalla,
            zona: destino.zona,
            cliente: destino.cliente,
            envio: destino.envio || null,
        });
        dibujar();
    }

    function alTocarRegresar() {
        if (estado.enviando) {
            return;
        }
        if (estado.pantalla === "zonas") {
            window.location.href = "/odoo";
        } else if (estado.pantalla === "enviado") {
            irA("clientes", { cliente: null }); // al siguiente cliente de la zona
        } else {
            history.back(); // lo resuelve alMoverseEnHistorial
        }
    }

    function vaciarPedido() {
        estado.pedido.clear();
        estado.token = null;
        estado.errorEnvio = null;
    }

    function avisarAntesDeSalir(evento) {
        if (estado.pedido.size) {
            evento.preventDefault();
            evento.returnValue = "";
        }
    }

    // === Dibujo general ===

    function medirBarra() {
        document.documentElement.style.setProperty("--alto-barra", `${ui.barra.offsetHeight}px`);
    }

    function ponerTitulo(titulo, subtitulo) {
        ui.titulo.textContent = titulo;
        ui.subtitulo.textContent = subtitulo || "";
        ui.subtitulo.hidden = !subtitulo;
        medirBarra();
    }

    function mostrar(...nodos) {
        ui.contenido.replaceChildren(...nodos.filter(Boolean));
    }

    function aviso(texto) {
        return el("p", { class: "aviso", text: texto });
    }

    function nuevaVista() {
        numeroVista += 1;
        return numeroVista;
    }

    function vigente(vista) {
        return vista === numeroVista;
    }

    function mostrarError(error, reintentar) {
        mostrar(
            aviso(error.message),
            el("button", {
                type: "button",
                class: "btn btn-primario",
                text: "Intentar de nuevo",
                onclick: reintentar,
            })
        );
    }

    function dibujar() {
        ui.regresar.textContent = estado.pantalla === "zonas" ? "‹ Salir" : "‹ Regresar";
        ui.categorias.hidden = estado.pantalla !== "productos";
        ui.barraPedido.hidden = !PANTALLAS_PEDIDO.includes(estado.pantalla);
        window.scrollTo(0, 0);
        if (estado.pantalla === "zonas") {
            dibujarZonas();
        } else if (estado.pantalla === "clientes") {
            dibujarClientes();
        } else if (estado.pantalla === "resumen") {
            dibujarResumen();
        } else if (estado.pantalla === "enviado") {
            dibujarEnviado();
        } else {
            dibujarProductos();
        }
    }

    // === Pantalla: Zonas ===

    async function dibujarZonas() {
        ponerTitulo("Zonas");
        const vista = nuevaVista();
        mostrar(aviso("Cargando zonas…"));
        let zonas;
        try {
            zonas = await api("/captura/api/zonas");
        } catch (error) {
            if (vigente(vista)) {
                mostrarError(error, dibujarZonas);
            }
            return;
        }
        if (!vigente(vista)) {
            return;
        }
        if (!zonas.length) {
            mostrar(aviso("No hay zonas dadas de alta."));
            return;
        }
        mostrar(
            el("p", { class: "pregunta", text: "¿En qué zona estás?" }),
            lista(
                zonas.map((zona) =>
                    el("button", {
                        type: "button",
                        class: "btn",
                        text: zona.nombre,
                        onclick: () => irA("clientes", { zona, cliente: null }),
                    })
                )
            )
        );
    }

    // === Pantalla: Clientes ===

    async function dibujarClientes() {
        ponerTitulo(estado.zona.nombre, "Zona");
        const vista = nuevaVista();
        mostrar(aviso("Cargando clientes…"));
        let clientes;
        try {
            clientes = await api("/captura/api/clientes", { zona_id: estado.zona.id });
        } catch (error) {
            if (vigente(vista)) {
                mostrarError(error, dibujarClientes);
            }
            return;
        }
        if (!vigente(vista)) {
            return;
        }
        if (!clientes.length) {
            mostrar(
                aviso("Esta zona no tiene clientes"),
                el("button", {
                    type: "button",
                    class: "btn btn-primario",
                    text: "‹ Regresar a zonas",
                    onclick: alTocarRegresar,
                })
            );
            return;
        }
        mostrar(
            el("p", { class: "pregunta", text: "¿Qué cliente?" }),
            lista(
                clientes.map((cliente) =>
                    el("button", {
                        type: "button",
                        class: "btn",
                        text: cliente.nombre,
                        onclick: () => irA("productos", { cliente }),
                    })
                )
            )
        );
    }

    // === Pantalla: Productos ===

    async function dibujarProductos() {
        const cliente = estado.cliente;
        ponerTitulo(cliente.nombre, estado.zona && estado.zona.nombre);
        actualizarPedido();
        const vista = nuevaVista();
        ui.categorias.replaceChildren();
        mostrar(aviso("Cargando productos…"));
        let habituales;
        try {
            // El catálogo se pide una sola vez; "Lo de siempre", cada vez que
            // se entra a un cliente (así refleja sus órdenes más recientes).
            [catalogo, habituales] = await Promise.all([
                catalogo || api("/captura/api/catalogo"),
                api("/captura/api/habituales", { cliente_id: cliente.id }),
            ]);
        } catch (error) {
            if (vigente(vista)) {
                mostrarError(error, dibujarProductos);
            }
            return;
        }
        if (!vigente(vista)) {
            return;
        }
        estado.habituales = habituales;
        if (estado.clienteDibujado !== cliente.id) {
            // Cliente nuevo: se abre la primera pestaña ("Lo de siempre" si hay).
            estado.clienteDibujado = cliente.id;
            estado.categoriaId = null;
        }
        const todas = pestanas();
        if (!todas.length) {
            mostrar(aviso("No hay productos a la venta."));
            return;
        }
        if (!todas.some((pestana) => pestana.id === estado.categoriaId)) {
            estado.categoriaId = todas[0].id;
        }
        dibujarCategorias(true);
        dibujarListaProductos();
    }

    function pestanas() {
        // "Lo de siempre" va primero y solo existe si el cliente tiene historial.
        const habituales = estado.habituales.length
            ? [{ id: PESTANA_HABITUALES, nombre: "⭐ Lo de siempre", productos: estado.habituales }]
            : [];
        return habituales.concat(catalogo);
    }

    function categoriaActual() {
        return pestanas().find((pestana) => pestana.id === estado.categoriaId);
    }

    function dibujarCategorias(centrarActiva) {
        ui.categorias.replaceChildren(
            ...pestanas().map((categoria) => {
                const enPedido = totalPiezas(categoria.productos);
                return el(
                    "button",
                    {
                        type: "button",
                        class: "categoria",
                        role: "tab",
                        "aria-selected": String(categoria.id === estado.categoriaId),
                        onclick: () => elegirCategoria(categoria.id),
                    },
                    categoria.nombre,
                    enPedido ? el("span", { class: "categoria-conteo", text: String(enPedido) }) : null
                );
            })
        );
        const activa = ui.categorias.querySelector('[aria-selected="true"]');
        if (centrarActiva && activa) {
            activa.scrollIntoView({ block: "nearest", inline: "center" });
        }
    }

    function elegirCategoria(categoriaId) {
        estado.categoriaId = categoriaId;
        dibujarCategorias(true);
        dibujarListaProductos();
        window.scrollTo(0, 0);
    }

    function dibujarListaProductos() {
        mostrar(lista(categoriaActual().productos.map(tarjetaProducto)));
    }

    function tarjetaProducto(producto) {
        const cantidad = estado.pedido.get(producto.id) || 0;
        const tarjeta = el("div", {
            class: cantidad ? "producto con-cantidad" : "producto",
            "data-producto": producto.id,
        });
        tarjeta.append(
            el(
                "button",
                {
                    type: "button",
                    class: "producto-sumar",
                    "aria-label": `Agregar 1 a ${producto.nombre}`,
                    onclick: () => cambiarCantidad(producto, 1),
                },
                el(
                    "span",
                    { class: "producto-textos" },
                    el("span", { class: "producto-nombre", text: producto.nombre }),
                    el("span", { class: "producto-precio", text: producto.precio_texto })
                ),
                cantidad
                    ? el("span", { class: "producto-cantidad", text: `${cantidad} ${producto.unidad}` })
                    : el("span", { class: "producto-mas", "aria-hidden": "true", text: "+" })
            )
        );
        if (cantidad) {
            tarjeta.append(
                el(
                    "div",
                    { class: "producto-controles" },
                    el("button", {
                        type: "button",
                        class: "btn btn-restar",
                        text: "− 1",
                        "aria-label": `Restar 1 a ${producto.nombre}`,
                        onclick: () => cambiarCantidad(producto, -1),
                    }),
                    el("button", {
                        type: "button",
                        class: "btn btn-quitar",
                        text: "✕ Quitar",
                        "aria-label": `Quitar ${producto.nombre} del pedido`,
                        onclick: () => quitarProducto(producto),
                    })
                )
            );
        }
        return tarjeta;
    }

    function cambiarCantidad(producto, cambio) {
        // Siempre de 1 en 1 y siempre entero; en 0 el producto sale del pedido.
        const cantidad = (estado.pedido.get(producto.id) || 0) + cambio;
        if (cantidad > 0) {
            estado.pedido.set(producto.id, cantidad);
        } else {
            estado.pedido.delete(producto.id);
        }
        if (cambio > 0 && navigator.vibrate) {
            navigator.vibrate(15);
        }
        pedidoCambiado();
        redibujarProducto(producto);
    }

    function quitarProducto(producto) {
        estado.pedido.delete(producto.id);
        pedidoCambiado();
        redibujarProducto(producto);
    }

    function pedidoCambiado() {
        // Un pedido distinto es un envío distinto: token nuevo al enviar.
        estado.token = null;
        estado.errorEnvio = null;
    }

    function redibujarProducto(producto) {
        const actual = ui.contenido.querySelector(`[data-producto="${producto.id}"]`);
        if (actual) {
            const nueva = tarjetaProducto(producto);
            nueva.classList.add("golpe");
            actual.replaceWith(nueva);
        }
        dibujarCategorias(false);
        actualizarPedido();
    }

    function actualizarPedido() {
        const productos = totalPedido();
        const enResumen = estado.pantalla === "resumen";
        ui.pedidoConteo.textContent = productos
            ? `${plural(productos, "producto", "productos")} en el pedido`
            : "Pedido vacío";
        ui.pedidoAccion.hidden = !productos;
        if (estado.enviando) {
            ui.pedidoAccion.textContent = "Enviando…";
        } else {
            ui.pedidoAccion.textContent = enResumen ? "✓ Enviar pedido" : "Revisar pedido ›";
        }
        ui.btnPedido.disabled = !productos || estado.enviando;
        ui.barraPedido.classList.toggle("con-productos", productos > 0);
        ui.barraPedido.classList.toggle("para-enviar", enResumen && productos > 0);
    }

    function alTocarBarraPedido() {
        if (estado.pantalla === "productos") {
            irA("resumen", {});
        } else if (estado.pantalla === "resumen") {
            enviarPedido();
        }
    }

    // === Pantalla: Resumen ===

    function lineasDelPedido() {
        // En el orden del catálogo (por categoría), no en el orden de los toques.
        const lineas = [];
        for (const categoria of catalogo || []) {
            for (const producto of categoria.productos) {
                const cantidad = estado.pedido.get(producto.id);
                if (cantidad) {
                    lineas.push({ producto, cantidad });
                }
            }
        }
        return lineas;
    }

    function dibujarResumen() {
        ponerTitulo(estado.cliente.nombre, estado.zona && estado.zona.nombre);
        nuevaVista();
        actualizarPedido();
        const lineas = lineasDelPedido();
        if (!lineas.length) {
            mostrar(
                aviso("El pedido está vacío."),
                el("button", {
                    type: "button",
                    class: "btn btn-primario",
                    text: "‹ Agregar productos",
                    onclick: alTocarRegresar,
                })
            );
            return;
        }
        mostrar(
            el("p", { class: "pregunta", text: "Revisa el pedido" }),
            lista(
                lineas.map(({ producto, cantidad }) =>
                    el(
                        "div",
                        { class: "resumen-linea" },
                        el("span", { class: "resumen-nombre", text: producto.nombre }),
                        el("span", { class: "resumen-cantidad", text: `${cantidad} ${producto.unidad}` })
                    )
                )
            ),
            estado.errorEnvio
                ? el("p", { class: "error-envio", role: "alert", text: estado.errorEnvio })
                : null,
            el("p", { class: "nota", text: "Para cambiar algo, toca Regresar." })
        );
    }

    function nuevoToken() {
        // crypto.getRandomValues funciona también en http:// (el celular en
        // la WiFi); crypto.randomUUID solo en https.
        const bytes = new Uint8Array(16);
        crypto.getRandomValues(bytes);
        return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
    }

    async function enviarPedido() {
        const lineas = lineasDelPedido();
        if (estado.enviando || !lineas.length) {
            return;
        }
        estado.enviando = true; // antes de cualquier await: bloquea el doble toque
        estado.errorEnvio = null;
        estado.token = estado.token || nuevoToken();
        dibujarResumen();
        let envio;
        try {
            envio = await api("/captura/api/enviar", {
                cliente_id: estado.cliente.id,
                zona_id: estado.zona.id,
                token: estado.token,
                lineas: lineas.map(({ producto, cantidad }) => ({ producto_id: producto.id, cantidad })),
            });
        } catch (error) {
            estado.enviando = false;
            estado.errorEnvio = error.sinRespuesta
                ? "No se pudo confirmar si el pedido llegó. Toca «Enviar pedido» otra vez: " +
                  "si ya había llegado, no se duplica."
                : `No se envió el pedido: ${error.message}`;
            dibujarResumen();
            return;
        }
        estado.enviando = false;
        vaciarPedido();
        estado.envio = envio;
        estado.pantalla = "enviado";
        // Reemplaza el Resumen en el historial: "atrás" ya no regresa a él.
        history.replaceState(fotoHistorial(), "");
        dibujar();
    }

    // === Pantalla: Pedido enviado ===

    function dibujarEnviado() {
        nuevaVista();
        const envio = estado.envio;
        ponerTitulo("Pedido enviado", estado.zona && estado.zona.nombre);
        if (!envio || !estado.zona) {
            mostrar(
                aviso("Pedido enviado."),
                el("button", {
                    type: "button",
                    class: "btn btn-primario",
                    text: "Ir a zonas",
                    onclick: () => irA("zonas", { zona: null, cliente: null }),
                })
            );
            return;
        }
        mostrar(
            el(
                "div",
                { class: "enviado", role: "status" },
                el("p", { class: "enviado-marca", "aria-hidden": "true", text: "✓" }),
                el("p", { class: "enviado-titulo", text: `Pedido ${envio.nombre} enviado` }),
                el("p", {
                    class: "enviado-detalle",
                    text: `${envio.cliente} · ${plural(envio.productos, "producto", "productos")}`,
                })
            ),
            lista([
                el("button", {
                    type: "button",
                    class: "btn btn-primario",
                    text: `Siguiente cliente de ${estado.zona.nombre}`,
                    onclick: () => irA("clientes", { cliente: null }),
                }),
                el("button", {
                    type: "button",
                    class: "btn btn-secundario",
                    text: "Cambiar de zona",
                    onclick: () => irA("zonas", { zona: null, cliente: null }),
                }),
            ])
        );
    }

    // === Arranque ===

    ui.regresar.addEventListener("click", alTocarRegresar);
    ui.btnPedido.addEventListener("click", alTocarBarraPedido);
    window.addEventListener("popstate", alMoverseEnHistorial);
    window.addEventListener("beforeunload", avisarAntesDeSalir);
    window.addEventListener("resize", medirBarra);
    history.replaceState(fotoHistorial(), "");
    dibujar();
})();
