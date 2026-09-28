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
        pedidoConteo: $("pedido-conteo"),
        modal: $("modal"),
        modalTexto: $("modal-texto"),
        modalSi: $("modal-si"),
        modalNo: $("modal-no"),
    };

    const estado = {
        pantalla: "zonas", // "zonas" | "clientes" | "productos"
        zona: null, // {id, nombre}
        cliente: null, // {id, nombre}
        categoriaId: null, // pestaña activa: id de categoría o PESTANA_HABITUALES
        pedido: new Map(), // id de producto -> cantidad entera (>= 1)
        habituales: [], // "Lo de siempre" del cliente actual
        clienteDibujado: null, // para abrir "Lo de siempre" al llegar a otro cliente
    };
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

    function lista(nodos) {
        return el("ul", { class: "lista" }, ...nodos.map((nodo) => el("li", {}, nodo)));
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
            throw new Error("No hay conexión. Revisa la señal e intenta de nuevo.");
        }
        if (!respuesta.ok) {
            throw new Error(`Odoo no respondió (error ${respuesta.status}). Intenta de nuevo.`);
        }
        const datos = await respuesta.json();
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
        return { pantalla: estado.pantalla, zona: estado.zona, cliente: estado.cliente };
    }

    function irA(pantalla, datos) {
        Object.assign(estado, { pantalla }, datos);
        history.pushState(fotoHistorial(), "");
        dibujar();
    }

    async function alMoverseEnHistorial(evento) {
        const destino = evento.state || { pantalla: "zonas", zona: null, cliente: null };
        if (confirmando) {
            // "Atrás" otra vez mientras se pregunta: se ignora y se queda aquí.
            history.pushState(fotoHistorial(), "");
            return;
        }
        const mismoCliente =
            destino.pantalla === "productos" &&
            destino.cliente &&
            estado.cliente &&
            destino.cliente.id === estado.cliente.id;
        const dejaElPedido = estado.pantalla === "productos" && !mismoCliente;
        if (dejaElPedido && estado.pedido.size) {
            const vaciar = await confirmar(
                `¿Vaciar el pedido de ${estado.cliente.nombre}? ` +
                    `Tiene ${plural(estado.pedido.size, "producto", "productos")} sin enviar.`,
                "Sí, vaciar el pedido",
                "No, seguir con el pedido"
            );
            if (!vaciar) {
                history.pushState(fotoHistorial(), "");
                return;
            }
        }
        if (dejaElPedido) {
            estado.pedido.clear();
        }
        Object.assign(estado, {
            pantalla: destino.pantalla,
            zona: destino.zona,
            cliente: destino.cliente,
        });
        dibujar();
    }

    function alTocarRegresar() {
        if (estado.pantalla === "zonas") {
            window.location.href = "/odoo";
        } else {
            history.back(); // lo resuelve alMoverseEnHistorial
        }
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
        ui.contenido.replaceChildren(...nodos);
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
        ui.barraPedido.hidden = estado.pantalla !== "productos";
        window.scrollTo(0, 0);
        if (estado.pantalla === "zonas") {
            dibujarZonas();
        } else if (estado.pantalla === "clientes") {
            dibujarClientes();
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
                const enPedido = categoria.productos.filter((p) => estado.pedido.has(p.id)).length;
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
        redibujarProducto(producto);
    }

    function quitarProducto(producto) {
        estado.pedido.delete(producto.id);
        redibujarProducto(producto);
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
        const productos = estado.pedido.size;
        ui.pedidoConteo.textContent = productos
            ? `${plural(productos, "producto", "productos")} en el pedido`
            : "Pedido vacío";
        ui.barraPedido.classList.toggle("con-productos", productos > 0);
    }

    // === Arranque ===

    ui.regresar.addEventListener("click", alTocarRegresar);
    window.addEventListener("popstate", alMoverseEnHistorial);
    window.addEventListener("beforeunload", avisarAntesDeSalir);
    window.addEventListener("resize", medirBarra);
    history.replaceState(fotoHistorial(), "");
    dibujar();
})();
