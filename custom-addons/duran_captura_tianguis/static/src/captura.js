/* Captura tianguis. Inicio → modo Pedido (Zona → Cliente, o "+ Cliente nuevo" → Productos →
 * Resumen → Enviado, con el pedido en memoria), modo Entrega (Zona → Cliente
 * con entregas pendientes → Lo pendiente → Resumen → Entregado), modo Cobro
 * (Zona → Cliente con algo por cobrar → Lo que debe → Confirmación → Cobrado)
 * o Acomodo de entregas (solo lectura: los pedidos del día por zona).
 *
 * JavaScript sin frameworks. Los datos vienen de las rutas jsonrpc de
 * controllers/main.py. Todo texto que viene de Odoo se pinta con textContent
 * (nunca como HTML).
 *
 * Cada pantalla es una entrada del historial del navegador: el botón "atrás"
 * del celular hace lo mismo que "Regresar". INICIO (arriba a la derecha)
 * vuelve de un toque a la primera entrada, la del Inicio. Salir de una
 * operación con algo sin enviar, confirmar o registrar (pendientes()) pregunta
 * antes, ofreciendo hacerlo ahora. */
(function () {
    "use strict";

    const $ = (id) => document.getElementById(id);
    // Lo decide el servidor: el usuario de tianguis no tiene "Salir" (su
    // inicio es esta pantalla y su sesión se queda abierta).
    const puedeSalir = document.body.dataset.salir === "1";
    const ui = {
        barra: document.querySelector(".barra"),
        botonesBarra: $("barra-botones"),
        regresar: $("btn-regresar"),
        inicio: $("btn-inicio"),
        operacion: $("operacion"),
        colorNavegador: document.querySelector('meta[name="theme-color"]'),
        titulo: $("titulo"),
        subtitulo: $("subtitulo"),
        categorias: $("categorias"),
        contenido: $("contenido"),
        barraPedido: $("barra-pedido"),
        faltaPaso: $("falta-paso"),
        btnPedido: $("btn-pedido"),
        pedidoConteo: $("pedido-conteo"),
        pedidoAccion: $("pedido-accion"),
        modal: $("modal"),
        modalTitulo: $("modal-titulo"),
        modalTexto: $("modal-texto"),
        modalSi: $("modal-si"),
        modalNo: $("modal-no"),
    };

    const estado = {
        // "inicio" | "zonas" | "clientes" | "cliente-nuevo" | "productos" | "resumen" | "enviado"
        // | "entrega" | "entrega-resumen" | "entregado"
        // | "cobro" | "cobro-confirmar" | "cobrado" | "acomodo"
        pantalla: "inicio",
        modo: null, // "pedido" | "entrega" | "cobro"
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
        entregado: null, // respuesta del servidor de la última entrega confirmada
        cobrado: null, // respuesta del servidor del último cobro registrado
        revisando: false, // pidiendo la vista previa de la entrega
        nivel: 0, // entradas del historial desde el Inicio con que abrió la app
    };
    // Cada operación con su nombre e ícono (barra superior y botón de Inicio);
    // su color está en captura.css (--color-pedido, …).
    const OPERACIONES = {
        pedido: { nombre: "PEDIDO", icono: "📝", boton: "Pedido", detalle: "Levantar un pedido nuevo" },
        entrega: { nombre: "ENTREGA", icono: "🚚", boton: "Entrega", detalle: "Entregar lo que ya pidieron" },
        cobro: { nombre: "COBRO", icono: "💵", boton: "Cobro", detalle: "Cobrar lo entregado y lo pendiente" },
        acomodo: { nombre: "ACOMODO", icono: "🛒", boton: "Acomodo de entregas", detalle: "En qué orden acomodar el carrito" },
    };
    // Las pantallas de cada operación con un cliente; la última es la final,
    // la del botón verde que envía, confirma o registra.
    const PANTALLAS_OPERACION = {
        pedido: ["productos", "resumen"],
        entrega: ["entrega", "entrega-resumen"],
        cobro: ["cobro", "cobro-confirmar"],
    };
    const PANTALLA_FINAL = { pedido: "resumen", entrega: "entrega-resumen", cobro: "cobro-confirmar" };
    const PANTALLAS_PEDIDO = PANTALLAS_OPERACION.pedido;
    // Pantallas con la franja de abajo (botón verde).
    const PANTALLAS_CON_BARRA = ["productos", "resumen", "entrega", "entrega-resumen", "cobro-confirmar"];
    // Textos de lo que falta: aviso de la franja, pregunta al salir y franja de Inicio.
    const TEXTOS_PENDIENTE = {
        pedido: {
            falta: "Falta un paso: este pedido todavía NO se ha enviado",
            titulo: "Este pedido NO se ha enviado",
            texto: "Si sales ahora, se pierde.",
            ahora: "✓ Enviar pedido ahora",
            revisar: "Revisar y enviar",
            salir: "Salir sin enviar",
            recordatorio: "Pedido sin enviar",
        },
        entrega: {
            falta: "Falta un paso: esta entrega todavía NO se ha confirmado",
            titulo: "Esta entrega NO se ha confirmado",
            texto: "Lo capturado se conserva, pero NO queda registrado en Odoo.",
            ahora: "✓ Confirmar entrega ahora",
            revisar: "Revisar y confirmar",
            salir: "Salir sin confirmar",
            recordatorio: "Entrega sin confirmar",
        },
        cobro: {
            falta: "Falta un paso: este cobro todavía NO se ha registrado",
            titulo: "Este cobro NO se ha registrado",
            texto: "Lo capturado se conserva, pero NO queda registrado en Odoo.",
            ahora: "✓ Registrar cobro ahora",
            revisar: "Revisar y registrar",
            salir: "Salir sin registrar",
            recordatorio: "Cobro sin registrar",
        },
    };
    const PESTANA_HABITUALES = "habituales";
    let catalogo = null; // [{id, nombre, productos: [...]}], se carga una sola vez
    let numeroVista = 0; // para descartar respuestas de una pantalla que ya se dejó
    let confirmando = false;
    let cerrarModal = null; // cierra la pregunta abierta con una respuesta
    let destinoEnPregunta = null; // entrada a la que iba "atrás" cuando se preguntó al salir
    let yendoAlInicio = false; // INICIO ya preguntó: el próximo "popstate" va directo al Inicio

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

    function confirmar({ titulo = "", texto, si, no, claseSi = "btn-peligro" }) {
        // Devuelve "si", "no" o null (tocar el fondo o "atrás": quedarse).
        confirmando = true;
        actualizarInicio();
        return new Promise((resolver) => {
            ui.modalTitulo.textContent = titulo;
            ui.modalTitulo.hidden = !titulo;
            ui.modalTexto.textContent = texto;
            ui.modalSi.textContent = si;
            ui.modalSi.className = `btn ${claseSi}`;
            ui.modalNo.textContent = no;
            ui.modal.hidden = false;
            ui.modalNo.focus();
            cerrarModal = (respuesta) => {
                ui.modal.hidden = true;
                ui.modalSi.onclick = ui.modalNo.onclick = ui.modal.onclick = null;
                cerrarModal = null;
                confirmando = false;
                actualizarInicio();
                resolver(respuesta);
            };
            ui.modalSi.onclick = () => cerrarModal("si");
            ui.modalNo.onclick = () => cerrarModal("no");
            ui.modal.onclick = (evento) => {
                if (evento.target === ui.modal) {
                    cerrarModal(null);
                }
            };
        });
    }

    // === Navegación ===

    function fotoHistorial() {
        return {
            pantalla: estado.pantalla,
            modo: estado.modo,
            zona: estado.zona,
            cliente: estado.cliente,
            envio: estado.pantalla === "enviado" ? estado.envio : null,
            entregado: estado.pantalla === "entregado" ? estado.entregado : null,
            cobrado: estado.pantalla === "cobrado" ? estado.cobrado : null,
            nivel: estado.nivel,
        };
    }

    function irA(pantalla, datos) {
        Object.assign(estado, { pantalla, nivel: estado.nivel + 1 }, datos);
        history.pushState(fotoHistorial(), "");
        dibujar();
    }

    // === Lo que falta enviar, confirmar o registrar ===

    function pendientes() {
        // [{operacion, cliente, zona, pantalla}]: lo capturado que todavía no
        // está en Odoo, con la pantalla a la que lleva "Continuar".
        const lista = [];
        if (estado.pedido.size && estado.cliente) {
            lista.push({
                operacion: "pedido",
                cliente: estado.cliente,
                zona: estado.zona,
                pantalla: estado.pantalla === "resumen" ? "resumen" : "productos",
            });
        }
        for (const captura of capturas.values()) {
            if (entregaPendiente(captura)) {
                lista.push({
                    operacion: "entrega",
                    cliente: captura.cliente,
                    zona: captura.zona,
                    pantalla: captura.vista ? "entrega-resumen" : "entrega",
                });
            }
        }
        for (const c of cobros.values()) {
            if (c.tipo || c.montoTexto.trim()) {
                lista.push({ operacion: "cobro", cliente: c.cliente, zona: c.zona, pantalla: c.tipo ? "cobro-confirmar" : "cobro" });
            }
        }
        return lista;
    }

    function enPantallasDe(p) {
        // ¿Está abierta una pantalla de esa operación con ese cliente?
        return Boolean(
            estado.cliente &&
                estado.cliente.id === p.cliente.id &&
                operacionActual() === p.operacion &&
                PANTALLAS_OPERACION[p.operacion].includes(estado.pantalla)
        );
    }

    function pendienteAqui() {
        // Lo que falta de la operación y el cliente de esta pantalla.
        return pendientes().find(enPantallasDe) || null;
    }

    function saleDeLaOperacion(destino) {
        // Ir a la pantalla anterior de la misma operación y el mismo cliente
        // (Regresar desde el resumen) no es salir.
        const pantallas = PANTALLAS_OPERACION[operacionActual()] || [];
        return !(
            pantallas.includes(destino.pantalla) &&
            destino.cliente &&
            estado.cliente &&
            destino.cliente.id === estado.cliente.id
        );
    }

    function preguntarAntesDeSalir(p) {
        // "si" = hacerlo ahora (hacerAhora), "no" = salir, null = quedarse.
        const textos = TEXTOS_PENDIENTE[p.operacion];
        const enLaFinal = enPantallasDe(p) && estado.pantalla === PANTALLA_FINAL[p.operacion];
        return confirmar({
            titulo: textos.titulo,
            texto: `${p.cliente.nombre}. ${textos.texto}`,
            si: enLaFinal ? textos.ahora : textos.revisar,
            no: textos.salir,
            claseSi: "btn-exito",
        });
    }

    function hacerAhora(p) {
        // Lo mismo que el botón verde de la pantalla; desde antes de la
        // pantalla final, lleva a ella.
        if (!enPantallasDe(p)) {
            continuarCon(p);
            return;
        }
        const acciones = {
            productos: () => irA("resumen", {}),
            resumen: enviarPedido,
            entrega: revisarEntrega,
            "entrega-resumen": confirmarEntrega,
            cobro: () => irA("cobro-confirmar", {}),
            "cobro-confirmar": registrarCobro,
        };
        acciones[estado.pantalla]();
    }

    function continuarCon(p) {
        // Abre lo pendiente armando el historial como si se hubiera llegado
        // tocando (zonas → clientes → pantalla), para que Regresar funcione igual.
        const pasos = [];
        if (estado.pantalla === "inicio") {
            pasos.push({ pantalla: "zonas", modo: p.operacion, zona: null, cliente: null });
        }
        if (estado.pantalla !== "clientes" || !estado.zona || estado.zona.id !== p.zona.id) {
            pasos.push({ pantalla: "clientes", modo: p.operacion, zona: p.zona, cliente: null });
        }
        const anterior = PANTALLAS_OPERACION[p.operacion][0];
        if (p.pantalla !== anterior) {
            pasos.push({ pantalla: anterior, modo: p.operacion, zona: p.zona, cliente: p.cliente });
        }
        for (const paso of pasos) {
            Object.assign(estado, paso, { nivel: estado.nivel + 1 });
            history.pushState(fotoHistorial(), "");
        }
        irA(p.pantalla, { modo: p.operacion, zona: p.zona, cliente: p.cliente });
    }

    async function alMoverseEnHistorial(evento) {
        const destino = evento.state || { pantalla: "inicio", modo: null, zona: null, cliente: null };
        if (yendoAlInicio) {
            // Lo pidió INICIO, que ya preguntó: directo al Inicio.
            yendoAlInicio = false;
            ponerEnInicio();
            return;
        }
        if (confirmando || estado.enviando || estado.revisando) {
            // "Atrás" mientras se pregunta o mientras se envía: se queda aquí
            // (y la pregunta abierta se cierra como "quedarse"). Si la pregunta
            // vino de otro "atrás", se repone primero la entrada que ese ya
            // dejó; la de esta pantalla la repone quien preguntó.
            history.pushState(destinoEnPregunta || fotoHistorial(), "");
            if (cerrarModal) {
                cerrarModal(null);
            }
            return;
        }
        const sale = saleDeLaOperacion(destino);
        const pendiente = sale ? pendienteAqui() : null;
        if (pendiente) {
            destinoEnPregunta = evento.state || { pantalla: "inicio", modo: null, zona: null, cliente: null, nivel: 0 };
            const respuesta = await preguntarAntesDeSalir(pendiente);
            destinoEnPregunta = null;
            if (respuesta !== "no") {
                history.pushState(fotoHistorial(), "");
                if (respuesta === "si") {
                    hacerAhora(pendiente);
                }
                return;
            }
        }
        if (sale && PANTALLAS_PEDIDO.includes(estado.pantalla)) {
            vaciarPedido(); // "Salir sin enviar": el pedido se pierde
        }
        Object.assign(estado, {
            pantalla: destino.pantalla,
            modo: destino.modo || null,
            zona: destino.zona,
            cliente: destino.cliente,
            envio: destino.envio || null,
            entregado: destino.entregado || null,
            cobrado: destino.cobrado || null,
            nivel: destino.nivel || 0,
        });
        dibujar();
    }

    function inicioBloqueado() {
        return confirmando || estado.enviando || estado.revisando;
    }

    async function alTocarInicio() {
        if (estado.pantalla === "inicio" || inicioBloqueado() || yendoAlInicio) {
            return;
        }
        // Con algo sin enviar, confirmar o registrar, pregunta antes. Al salir,
        // solo el pedido se pierde: lo capturado de una entrega o un cobro se
        // conserva en memoria (y el Inicio lo recuerda).
        const pendiente = pendienteAqui();
        if (pendiente) {
            const respuesta = await preguntarAntesDeSalir(pendiente);
            if (respuesta === "si") {
                hacerAhora(pendiente);
            }
            if (respuesta !== "no") {
                return;
            }
        }
        if (PANTALLAS_PEDIDO.includes(estado.pantalla)) {
            vaciarPedido();
        }
        if (estado.nivel > 0) {
            // A la primera entrada del historial: "atrás" en el Inicio se
            // comporta como al abrir la app. Lo termina alMoverseEnHistorial.
            yendoAlInicio = true;
            history.go(-estado.nivel);
            // Chrome guarda máximo 50 entradas: si la primera ya se borró, el
            // salto no lleva a ningún lado (nunca a otra página) y el Inicio
            // se pone aquí mismo.
            setTimeout(() => {
                if (yendoAlInicio) {
                    yendoAlInicio = false;
                    ponerEnInicio();
                }
            }, 600);
        } else {
            ponerEnInicio();
        }
    }

    function ponerEnInicio() {
        Object.assign(estado, {
            pantalla: "inicio",
            modo: null,
            zona: null,
            cliente: null,
            envio: null,
            entregado: null,
            cobrado: null,
            nivel: 0,
        });
        history.replaceState(fotoHistorial(), "");
        dibujar();
    }

    function alTocarRegresar() {
        if (estado.enviando || estado.revisando) {
            return;
        }
        if (estado.pantalla === "inicio") {
            if (puedeSalir) {
                window.location.href = "/odoo";
            }
        } else if (estado.pantalla === "zonas") {
            // Directo al Inicio (para cambiar de modo): por historial pasaría
            // antes por las pantallas de "enviado" o "entregado".
            irA("inicio", { modo: null, zona: null, cliente: null });
        } else if (["enviado", "entregado", "cobrado"].includes(estado.pantalla)) {
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
        // Recargar o cerrar la página perdería el pedido, lo capturado de una
        // entrega o de un cobro.
        if (pendientes().length) {
            evento.preventDefault();
            evento.returnValue = "";
        }
    }

    // === Dibujo general ===

    function medirBarra() {
        document.documentElement.style.setProperty("--alto-barra", `${ui.barra.offsetHeight}px`);
        medirBarraAbajo();
    }

    function medirBarraAbajo() {
        // El contenido deja abajo el alto real de la franja (con su aviso), para
        // que nada quede tapado; sin franja, captura.css deja 16px.
        const alto = ui.barraPedido.hidden ? 0 : ui.barraPedido.offsetHeight;
        document.documentElement.style.setProperty("--alto-barra-abajo", `${alto}px`);
    }

    function ponerBarraAbajo(accion, conteo, deshabilitado, conAviso) {
        // Franja de abajo de las tres operaciones: el verbo grande, debajo el
        // conteo o el total y, en la pantalla final, el aviso de que falta un paso.
        ui.pedidoAccion.textContent = accion;
        ui.pedidoConteo.textContent = conteo;
        ui.pedidoConteo.hidden = !conteo;
        ui.btnPedido.disabled = deshabilitado;
        ui.faltaPaso.textContent = conAviso ? TEXTOS_PENDIENTE[operacionActual()].falta : "";
        ui.faltaPaso.hidden = !conAviso;
        actualizarInicio();
        medirBarraAbajo();
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

    function actualizarInicio() {
        // Gris y sin respuesta mientras se envía, se revisa o hay una pregunta abierta.
        ui.inicio.disabled = inicioBloqueado();
    }

    function operacionActual() {
        // Zonas y clientes son de la operación elegida en Inicio (`modo`); las
        // demás pantallas son de una sola. "El cliente quiere algo más" abre
        // Productos: es PEDIDO, y al regresar vuelve a ENTREGA.
        const pantalla = estado.pantalla;
        if (pantalla === "inicio") {
            return null;
        }
        if (["productos", "resumen", "enviado"].includes(pantalla)) {
            return "pedido";
        }
        if (["entrega", "entrega-resumen", "entregado"].includes(pantalla)) {
            return "entrega";
        }
        if (["cobro", "cobro-confirmar", "cobrado"].includes(pantalla)) {
            return "cobro";
        }
        if (pantalla === "acomodo") {
            return "acomodo";
        }
        return estado.modo; // zonas y clientes
    }

    function ponerOperacion() {
        const operacion = operacionActual();
        if (operacion) {
            document.body.dataset.operacion = operacion;
            const { icono, nombre } = OPERACIONES[operacion];
            ui.operacion.replaceChildren(el("span", { "aria-hidden": "true", text: icono }), ` ${nombre}`);
        } else {
            delete document.body.dataset.operacion;
            ui.operacion.replaceChildren();
        }
        ui.operacion.hidden = !operacion;
        // La barra del navegador (Android) con el mismo color que la barra.
        if (ui.colorNavegador) {
            ui.colorNavegador.content = getComputedStyle(ui.barra).backgroundColor;
        }
    }

    function dibujar() {
        const enInicio = estado.pantalla === "inicio";
        ponerOperacion();
        ui.regresar.textContent = enInicio ? "‹ Salir" : "‹ Regresar";
        ui.regresar.hidden = enInicio && !puedeSalir;
        ui.inicio.hidden = enInicio;
        // Usuario de tianguis en Inicio: sin Salir ni INICIO, la fila no ocupa lugar.
        ui.botonesBarra.hidden = ui.regresar.hidden && ui.inicio.hidden;
        actualizarInicio();
        ui.categorias.hidden = estado.pantalla !== "productos";
        ui.barraPedido.hidden = !PANTALLAS_CON_BARRA.includes(estado.pantalla);
        medirBarraAbajo();
        window.scrollTo(0, 0);
        if (estado.pantalla === "inicio") {
            dibujarInicio();
        } else if (estado.pantalla === "zonas") {
            dibujarZonas();
        } else if (estado.pantalla === "clientes") {
            dibujarClientes();
        } else if (estado.pantalla === "cliente-nuevo") {
            dibujarClienteNuevo();
        } else if (estado.pantalla === "resumen") {
            dibujarResumen();
        } else if (estado.pantalla === "enviado") {
            dibujarEnviado();
        } else if (estado.pantalla === "entrega") {
            dibujarEntrega();
        } else if (estado.pantalla === "entrega-resumen") {
            dibujarEntregaResumen();
        } else if (estado.pantalla === "entregado") {
            dibujarEntregado();
        } else if (estado.pantalla === "cobro") {
            dibujarCobro();
        } else if (estado.pantalla === "cobro-confirmar") {
            dibujarConfirmarCobro();
        } else if (estado.pantalla === "cobrado") {
            dibujarCobrado();
        } else if (estado.pantalla === "acomodo") {
            dibujarAcomodo();
        } else {
            dibujarProductos();
        }
    }

    // === Pantalla: Inicio ===

    function botonModo(operacion, alTocar) {
        // Mismo color, ícono y nombre que la barra de la operación.
        const { icono, boton: nombre, detalle } = OPERACIONES[operacion];
        return el(
            "button",
            {
                type: "button",
                class: "btn btn-modo",
                "data-operacion": operacion,
                disabled: alTocar ? null : "disabled",
                onclick: alTocar,
            },
            el("span", { class: "modo-icono", "aria-hidden": "true", text: icono }),
            el(
                "span",
                { class: "modo-textos" },
                el("span", { class: "modo-nombre", text: nombre }),
                el("span", { class: "modo-detalle", text: detalle })
            )
        );
    }

    function recordatorios() {
        // Entregas y cobros capturados que no están en Odoo (el pedido nunca
        // queda en memoria al salir). Máximo 2 renglones, y "y N más".
        const lista = pendientes().filter((p) => p.operacion !== "pedido");
        if (!lista.length) {
            return null;
        }
        const MAXIMO = 2;
        return el(
            "div",
            { class: "recordatorios", role: "alert" },
            ...lista.slice(0, MAXIMO).map((p) =>
                el(
                    "button",
                    {
                        type: "button",
                        class: "recordatorio",
                        "data-operacion": p.operacion,
                        onclick: () => continuarCon(p),
                    },
                    `⚠ ${TEXTOS_PENDIENTE[p.operacion].recordatorio}: ${p.cliente.nombre} · `,
                    el("span", { class: "recordatorio-continuar", text: "Continuar ›" })
                )
            ),
            lista.length > MAXIMO ? el("p", { class: "recordatorio-mas", text: `y ${lista.length - MAXIMO} más` }) : null
        );
    }

    function dibujarInicio() {
        ponerTitulo("Captura");
        nuevaVista();
        mostrar(
            recordatorios(),
            el("p", { class: "pregunta", text: "¿Qué vas a hacer?" }),
            lista([
                botonModo("pedido", () => irA("zonas", { modo: "pedido", zona: null, cliente: null })),
                botonModo("entrega", () => irA("zonas", { modo: "entrega", zona: null, cliente: null })),
                botonModo("cobro", () => irA("zonas", { modo: "cobro", zona: null, cliente: null })),
                botonModo("acomodo", () => irA("acomodo", { modo: null, zona: null, cliente: null })),
            ])
        );
    }

    // === Pantalla: Zonas ===

    async function dibujarZonas() {
        ponerTitulo("Zonas", { entrega: "Entrega", cobro: "Cobro" }[estado.modo] || "Pedido");
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
        ponerTitulo(estado.zona.nombre);
        const vista = nuevaVista();
        mostrar(aviso("Cargando clientes…"));
        const entrega = estado.modo === "entrega";
        const cobrando = estado.modo === "cobro";
        let clientes;
        try {
            // En Entrega solo los clientes con entregas pendientes; en Cobro,
            // los que tienen algo por cobrar.
            const ruta = entrega
                ? "/captura/api/entrega/clientes"
                : cobrando
                  ? "/captura/api/cobro/clientes"
                  : "/captura/api/clientes";
            clientes = await api(ruta, { zona_id: estado.zona.id });
        } catch (error) {
            if (vigente(vista)) {
                mostrarError(error, dibujarClientes);
            }
            return;
        }
        if (!vigente(vista)) {
            return;
        }
        // Solo en Pedido: dar de alta a quien todavía no está en Odoo.
        const botonNuevo = entrega || cobrando ? null : botonClienteNuevo();
        if (!clientes.length) {
            mostrar(
                aviso(
                    entrega
                        ? "Nadie de esta zona tiene entregas pendientes"
                        : cobrando
                          ? "Nadie de esta zona tiene algo por cobrar"
                          : "Esta zona no tiene clientes"
                ),
                botonNuevo,
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
            el("p", {
                class: "pregunta",
                text: entrega
                    ? "¿A quién le vas a entregar?"
                    : cobrando
                      ? "¿A quién le vas a cobrar?"
                      : "¿A quién le levantas el pedido?",
            }),
            botonNuevo,
            lista(
                clientes.map((cliente) =>
                    el("button", {
                        type: "button",
                        class: "btn",
                        text: cliente.nombre,
                        onclick: () => abrirCliente(cliente, entrega ? "entrega" : cobrando ? "cobro" : "productos"),
                    })
                )
            )
        );
    }

    // === Pantalla: Cliente nuevo (solo Pedido) ===

    // Lo escrito en "Cliente nuevo": se empieza de cero cada vez que se toca
    // "+ Cliente nuevo". No cuenta como algo sin confirmar (pendientes()):
    // escribir un nombre otra vez cuesta poco.
    let clienteNuevo = null; // {nombre, token, parecidos, puedeCrear, error}

    function botonClienteNuevo() {
        return el("button", {
            type: "button",
            class: "btn btn-cliente-nuevo",
            text: "+ Cliente nuevo",
            onclick: () => {
                clienteNuevo = null;
                irA("cliente-nuevo", {});
            },
        });
    }

    function clienteNuevoActual() {
        if (!clienteNuevo) {
            // El token identifica a ESTE cliente ante el servidor (evita
            // duplicados); cambia si cambia el nombre.
            clienteNuevo = { nombre: "", token: nuevoToken(), parecidos: null, puedeCrear: true, error: null };
        }
        return clienteNuevo;
    }

    function quitar(selector) {
        const nodo = ui.contenido.querySelector(selector);
        if (nodo) {
            nodo.remove();
        }
    }

    function dibujarClienteNuevo() {
        ponerTitulo("Cliente nuevo");
        nuevaVista();
        actualizarInicio();
        const c = clienteNuevoActual();
        if (!estado.zona) {
            mostrar(aviso("Toca Regresar para elegir la zona."));
            return;
        }
        const campo = el("input", {
            id: "cliente-nombre",
            class: "campo-texto",
            type: "text",
            name: "nombre",
            maxlength: "60",
            autocapitalize: "words",
            autocomplete: "off",
            autocorrect: "off",
            spellcheck: "false",
            enterkeyhint: "done",
            value: c.nombre,
            disabled: estado.enviando ? "disabled" : null,
            oninput: (evento) => {
                // Otro nombre es otro cliente: token nuevo, y los parecidos ya no valen.
                c.nombre = evento.target.value;
                c.token = nuevoToken();
                c.error = null;
                c.parecidos = null;
                quitar(".parecidos");
                quitar(".form-cliente .error-envio");
            },
        });
        mostrar(
            el("p", { class: "zona-cliente-nuevo" }, "Zona: ", el("strong", { text: estado.zona.nombre })),
            el(
                "form",
                {
                    class: "form-cliente",
                    novalidate: "novalidate",
                    onsubmit: (evento) => {
                        evento.preventDefault();
                        guardarClienteNuevo(false);
                    },
                },
                el("label", { class: "seccion-titulo etiqueta-campo", for: "cliente-nombre", text: "Nombre del cliente" }),
                campo,
                c.error ? el("p", { class: "error-envio", role: "alert", text: c.error }) : null,
                el("button", {
                    type: "submit",
                    class: "btn btn-exito btn-guardar-cliente",
                    text: estado.enviando ? "GUARDANDO…" : "Guardar y levantar pedido",
                    disabled: estado.enviando ? "disabled" : null,
                })
            ),
            c.parecidos ? seccionParecidos(c) : null
        );
    }

    function seccionParecidos(c) {
        // "¿Es alguno de estos?": los de esta zona se pueden tocar; los de otra
        // zona o archivados solo se avisan. Con uno idéntico en esta zona no se
        // ofrece crear otro.
        return el(
            "section",
            { class: "parecidos", role: "alert" },
            el("p", { class: "pregunta", text: "¿Es alguno de estos?" }),
            lista(
                c.parecidos.map((p) =>
                    p.id
                        ? el("button", {
                              type: "button",
                              class: "btn parecido",
                              text: p.identico && !c.puedeCrear ? `Es este: ${p.nombre}` : p.nombre,
                              onclick: () => entrarConCliente({ id: p.id, nombre: p.nombre }),
                          })
                        : el(
                              "div",
                              { class: "parecido-aviso" },
                              el("span", { class: "parecido-nombre", text: p.nombre }),
                              el("span", {
                                  class: "parecido-nota",
                                  text: p.archivado
                                      ? "Hay un cliente archivado con este nombre; pide que lo reactiven"
                                      : `Ya existe en ${p.zona}: búscalo ahí`,
                              })
                          )
                )
            ),
            c.puedeCrear
                ? el("button", {
                      type: "button",
                      class: "btn btn-secundario btn-es-otro",
                      text: "No, es otro cliente",
                      onclick: () => guardarClienteNuevo(true),
                  })
                : el("p", { class: "nota", text: "Si son dos clientes distintos, agrégale un apellido o el nombre del local." })
        );
    }

    async function guardarClienteNuevo(esOtro) {
        const c = clienteNuevoActual();
        if (estado.enviando) {
            return;
        }
        if (!c.nombre.trim()) {
            c.error = "Escribe el nombre del cliente.";
            dibujarClienteNuevo();
            return;
        }
        estado.enviando = true; // antes del await: bloquea el doble toque, INICIO y "atrás"
        c.error = null;
        dibujarClienteNuevo();
        let respuesta;
        try {
            respuesta = await api("/captura/api/cliente/nuevo", {
                zona_id: estado.zona.id,
                nombre: c.nombre,
                token: c.token,
                es_otro: esOtro,
            });
        } catch (error) {
            estado.enviando = false;
            c.error = error.sinRespuesta
                ? "No se pudo confirmar si el cliente se guardó. Toca «Guardar y levantar pedido» otra vez: " +
                  "si ya se había guardado, no se duplica."
                : error.message;
            dibujarClienteNuevo();
            return;
        }
        estado.enviando = false;
        if (respuesta.parecidos) {
            c.parecidos = respuesta.parecidos;
            c.puedeCrear = respuesta.puede_crear;
            dibujarClienteNuevo();
            ui.contenido.querySelector(".parecidos").scrollIntoView({ block: "start" });
            return;
        }
        entrarConCliente(respuesta.cliente);
    }

    function entrarConCliente(cliente) {
        // Directo a sus productos. Reemplaza "Cliente nuevo" en el historial:
        // Regresar desde Productos vuelve a Clientes (que ya lo incluye).
        clienteNuevo = null;
        Object.assign(estado, { pantalla: "productos", modo: "pedido", cliente });
        history.replaceState(fotoHistorial(), "");
        dibujar();
    }

    async function abrirCliente(cliente, pantalla) {
        if (pantalla === "cobro" && !confirmando) {
            // Cobrarle a otro cliente con un cobro sin registrar: se avisa antes.
            const otro = pendientes().find((p) => p.operacion === "cobro" && p.cliente.id !== cliente.id);
            const respuesta = otro ? await preguntarAntesDeSalir(otro) : "no";
            if (respuesta === "si") {
                hacerAhora(otro);
            }
            if (respuesta !== "no") {
                return;
            }
        }
        irA(pantalla, { cliente });
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
        // La tarjeta no es un botón: solo "+" y "−" cambian la cantidad (tocar
        // el nombre o deslizar la lista no suma nada).
        const cantidad = estado.pedido.get(producto.id) || 0;
        const textos = el(
            "span",
            { class: "producto-textos" },
            el("span", { class: "producto-nombre", text: producto.nombre }),
            el("span", { class: "producto-precio", text: producto.precio_texto })
        );
        const sumar = (clase, texto) =>
            el("button", {
                type: "button",
                class: clase,
                text: texto,
                "aria-label": `Agregar 1 a ${producto.nombre}`,
                onclick: () => cambiarCantidad(producto, 1),
            });
        if (!cantidad) {
            return el(
                "div",
                { class: "producto", "data-producto": producto.id },
                el("div", { class: "producto-fila" }, textos, sumar("producto-mas", "+"))
            );
        }
        return el(
            "div",
            { class: "producto con-cantidad", "data-producto": producto.id },
            el("div", { class: "producto-fila" }, textos),
            el(
                "div",
                { class: "cantidad-controles producto-cantidades" },
                el("button", {
                    type: "button",
                    class: "btn btn-menos",
                    text: "−",
                    // En 1, "−" saca el producto del pedido.
                    "aria-label": `Quitar 1 a ${producto.nombre}`,
                    onclick: () => cambiarCantidad(producto, -1),
                }),
                el("span", { class: "producto-cantidad-texto", text: textoCantidad(producto, cantidad) }),
                sumar("btn btn-mas", "+")
            )
        );
    }

    function textoCantidad(producto, cantidad) {
        // Los rollos (se pesan al entregar, pero se venden por pieza) se cuentan
        // por pieza: "1 rollo", "3 rollos". Lo que se vende por kg dice kg, se
        // pese o no ("3 kg"); lo demás, con su unidad ("2 c/u").
        const rollo = producto.es_peso_variable && !producto.por_kg;
        return rollo ? plural(cantidad, "rollo", "rollos") : `${cantidad} ${producto.unidad}`;
    }

    function cambiarCantidad(producto, cambio) {
        // Siempre de 1 en 1 y siempre entero; en 0 el producto sale del pedido.
        const antes = estado.pedido.get(producto.id) || 0;
        const cantidad = antes + cambio;
        if (cantidad > 0) {
            estado.pedido.set(producto.id, cantidad);
        } else {
            estado.pedido.delete(producto.id);
        }
        if (cambio > 0 && navigator.vibrate) {
            navigator.vibrate(15);
        }
        pedidoCambiado();
        // La tarjeta se cambia completa solo al entrar o salir del pedido; si no,
        // solo el número, para que los botones no se reemplacen bajo el dedo y
        // no se pierdan toques rápidos.
        redibujarProducto(producto, !antes || !cantidad);
    }

    function pedidoCambiado() {
        // Un pedido distinto es un envío distinto: token nuevo al enviar.
        estado.token = null;
        estado.errorEnvio = null;
    }

    function redibujarProducto(producto, completa) {
        const actual = ui.contenido.querySelector(`[data-producto="${producto.id}"]`);
        if (actual && completa) {
            const nueva = tarjetaProducto(producto);
            nueva.classList.add("golpe");
            actual.replaceWith(nueva);
        } else if (actual) {
            const numero = actual.querySelector(".producto-cantidad-texto");
            numero.textContent = textoCantidad(producto, estado.pedido.get(producto.id));
            numero.classList.remove("golpe");
            void numero.offsetWidth; // reinicia la animación
            numero.classList.add("golpe");
        }
        dibujarCategorias(false);
        actualizarPedido();
    }

    function actualizarPedido() {
        const productos = totalPedido();
        const enResumen = estado.pantalla === "resumen";
        ponerBarraAbajo(
            estado.enviando ? "ENVIANDO…" : enResumen ? "✓ ENVIAR PEDIDO" : "REVISAR PEDIDO ›",
            productos ? `${plural(productos, "producto", "productos")} en el pedido` : "Pedido vacío",
            !productos || estado.enviando,
            enResumen && productos > 0
        );
    }

    function alTocarBarraPedido() {
        if (estado.pantalla === "productos") {
            irA("resumen", {});
        } else if (estado.pantalla === "resumen") {
            enviarPedido();
        } else if (estado.pantalla === "entrega") {
            revisarEntrega();
        } else if (estado.pantalla === "entrega-resumen") {
            confirmarEntrega();
        } else if (estado.pantalla === "cobro-confirmar") {
            registrarCobro();
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
            el("p", { class: "pregunta", text: "Falta enviar el pedido" }),
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

    // === Pantallas de éxito (pedido enviado, entrega confirmada, cobro registrado) ===

    function pantallaExito(titulo, detalles) {
        // Bloque verde inconfundible: palomeo grande y lo que se hizo en
        // mayúsculas. Sin datos (atrás o adelante), solo el encabezado y
        // "Ir a zonas"; con datos, debajo los detalles y a dónde seguir.
        const encabezado = el(
            "div",
            { class: "exito", role: "status" },
            el("p", { class: "exito-marca", "aria-hidden": "true", text: "✓" }),
            el("p", { class: "exito-titulo", text: titulo }),
            ...(detalles || [])
        );
        if (!detalles || !estado.zona) {
            mostrar(
                encabezado,
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
            encabezado,
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

    // === Pantalla: Pedido enviado ===

    function dibujarEnviado() {
        nuevaVista();
        const envio = estado.envio;
        ponerTitulo("Pedido enviado", estado.zona && estado.zona.nombre);
        pantallaExito(
            "PEDIDO ENVIADO",
            envio && [
                el("p", { class: "enviado-titulo", text: `Pedido ${envio.nombre}` }),
                el("p", {
                    class: "enviado-detalle",
                    text: `${envio.cliente} · ${plural(envio.productos, "producto", "productos")}`,
                }),
            ]
        );
    }

    // =====================================================================
    // === Modo Entrega ===
    // =====================================================================

    // Lo capturado de cada cliente (pesos, "No se lo llevó", cantidades) se
    // conserva mientras la página esté abierta: al ir a "quiere algo más" y
    // regresar, o al recargar lo pendiente, no se pierde. Se borra al
    // confirmar la entrega.
    const capturas = new Map(); // id de cliente -> captura
    const dinero = new Intl.NumberFormat("es-MX", { style: "currency", currency: "MXN" });

    function capturaActual() {
        const id = estado.cliente.id;
        if (!capturas.has(id)) {
            capturas.set(id, {
                cliente: estado.cliente, // para recordarla en Inicio y volver a ella
                zona: estado.zona,
                pendiente: null, // respuesta de /entrega/pendiente
                pesos: new Map(), // move_id -> texto tecleado
                noLlevo: new Set(), // claves de renglón marcadas "No se lo llevó"
                cantidades: new Map(), // id de producto normal -> cantidad (1..pendiente)
                problemas: new Map(), // move_id -> [textos] (bloqueo o advertencia a corregir)
                faltanPesos: false, // se intentó revisar con pesos vacíos
                vista: null, // respuesta de /entrega/vista_previa
                token: null,
                aviso: null, // mensaje arriba de la lista
                error: null, // mensaje en el resumen
            });
        }
        return capturas.get(id);
    }

    function claveRollo(movimiento) {
        return `m${movimiento.move_id}`;
    }

    function claveProducto(producto) {
        return `p${producto.id}`;
    }

    function leerPeso(texto) {
        // Misma forma que acepta el servidor: "1.250", "1,250" o "1250".
        const limpio = (texto || "").trim();
        return /^\d+([.,]\d+)?$/.test(limpio) ? Number(limpio.replace(",", ".")) : null;
    }

    function ecoPeso(texto, precio) {
        if (!(texto || "").trim()) {
            return "Escribe el peso";
        }
        const peso = leerPeso(texto);
        return peso === null ? "Peso no válido" : `${peso.toFixed(3)} kg · ${dinero.format(peso * precio)}`;
    }

    function rollosPendientes(captura) {
        // [{producto, movimiento, numero}] de los productos de peso variable.
        const rollos = [];
        for (const producto of captura.pendiente.productos) {
            if (producto.es_peso_variable) {
                producto.movimientos.forEach((movimiento, i) => rollos.push({ producto, movimiento, numero: i + 1 }));
            }
        }
        return rollos;
    }

    function productosNormales(captura) {
        return captura.pendiente.productos.filter((producto) => !producto.es_peso_variable);
    }

    function totalRenglones(captura) {
        return rollosPendientes(captura).length + productosNormales(captura).length;
    }

    function entregaPendiente(captura) {
        // Ya llegó al Resumen (aunque no haya cambiado nada), o tiene algún peso
        // escrito, "No se lo llevó" o cantidad cambiada sin confirmar.
        const conPeso = [...captura.pesos.values()].some((texto) => texto.trim());
        const cantidadCambiada =
            captura.pendiente &&
            productosNormales(captura).some((producto) => captura.cantidades.get(producto.id) !== producto.cantidad);
        return Boolean(captura.vista || conPeso || captura.noLlevo.size || cantidadCambiada);
    }

    function podarCaptura(captura) {
        // Al recargar lo pendiente, se borra lo capturado de lo que ya no está
        // pendiente (otra persona lo validó o canceló): no son entregas por
        // confirmar. Si algo se borró, la revisión anterior ya no vale.
        const movimientos = new Set();
        const claves = new Set();
        const productos = new Set();
        for (const producto of captura.pendiente.productos) {
            if (producto.es_peso_variable) {
                for (const movimiento of producto.movimientos) {
                    movimientos.add(movimiento.move_id);
                    claves.add(claveRollo(movimiento));
                }
            } else {
                productos.add(producto.id);
                claves.add(claveProducto(producto));
            }
        }
        let podado = false;
        const podar = (coleccion, sigue) => {
            for (const clave of [...coleccion.keys()]) {
                if (!sigue.has(clave)) {
                    coleccion.delete(clave);
                    podado = true;
                }
            }
        };
        podar(captura.pesos, movimientos);
        podar(captura.problemas, movimientos);
        podar(captura.noLlevo, claves);
        podar(captura.cantidades, productos);
        if (podado || !captura.pendiente.productos.length) {
            capturaCambiada(captura);
        }
    }

    function capturaCambiada(captura) {
        // Otra entrega distinta: token nuevo al confirmar.
        captura.token = null;
        captura.vista = null;
        captura.error = null;
    }

    function paramsEntrega(captura) {
        return {
            cliente_id: estado.cliente.id,
            zona_id: estado.zona.id,
            rollos: rollosPendientes(captura)
                .filter(({ movimiento }) => !captura.noLlevo.has(claveRollo(movimiento)))
                .map(({ movimiento }) => ({
                    move_id: movimiento.move_id,
                    peso: captura.pesos.get(movimiento.move_id) || "",
                })),
            productos: productosNormales(captura)
                .filter((producto) => !captura.noLlevo.has(claveProducto(producto)))
                .map((producto) => ({ producto_id: producto.id, cantidad: captura.cantidades.get(producto.id) })),
        };
    }

    function ajustarCantidades(captura) {
        // Arranca en lo pendiente; si lo pendiente bajó al recargar, se ajusta.
        for (const producto of productosNormales(captura)) {
            const actual = captura.cantidades.has(producto.id) ? captura.cantidades.get(producto.id) : producto.cantidad;
            captura.cantidades.set(producto.id, Math.max(1, Math.min(actual, producto.cantidad)));
        }
    }

    // === Pantalla: Lo pendiente del cliente ===

    async function dibujarEntrega() {
        const cliente = estado.cliente;
        const captura = capturaActual();
        ponerTitulo(cliente.nombre, estado.zona && estado.zona.nombre);
        const vista = nuevaVista();
        actualizarBarraEntrega();
        mostrar(aviso("Cargando lo pendiente…"));
        let pendiente;
        try {
            // Siempre se vuelve a pedir: refleja lo que otros hayan validado.
            pendiente = await api("/captura/api/entrega/pendiente", {
                cliente_id: cliente.id,
                zona_id: estado.zona.id,
            });
        } catch (error) {
            if (vigente(vista)) {
                mostrarError(error, dibujarEntrega);
            }
            return;
        }
        if (!vigente(vista)) {
            return;
        }
        captura.pendiente = pendiente;
        captura.zona = estado.zona;
        podarCaptura(captura);
        ajustarCantidades(captura);
        dibujarListaEntrega();
    }

    function dibujarListaEntrega() {
        const captura = capturaActual();
        actualizarBarraEntrega();
        const productos = captura.pendiente.productos;
        if (!productos.length) {
            mostrar(
                captura.aviso ? el("p", { class: "error-envio", role: "alert", text: captura.aviso }) : null,
                aviso("Este cliente ya no tiene nada pendiente de entregar."),
                lista([
                    el("button", {
                        type: "button",
                        class: "btn btn-primario",
                        text: "‹ Regresar a clientes",
                        onclick: alTocarRegresar,
                    }),
                    botonAlgoMas(),
                ])
            );
            return;
        }
        mostrar(
            captura.aviso ? el("p", { class: "error-envio aviso-entrega", role: "alert", text: captura.aviso }) : null,
            el("p", { class: "pregunta", text: "¿Qué se lleva?" }),
            lista(productos.map(grupoEntrega)),
            el("div", { class: "algo-mas" }, botonAlgoMas())
        );
    }

    function botonAlgoMas() {
        return el("button", {
            type: "button",
            class: "btn btn-secundario btn-algo-mas",
            text: "➕ El cliente quiere algo más",
            // Al Modo Pedido con este cliente ya elegido; "Regresar" vuelve aquí.
            onclick: () => irA("productos", { modo: "pedido" }),
        });
    }

    function grupoEntrega(producto) {
        const captura = capturaActual();
        return el(
            "div",
            { class: "entrega-producto", "data-grupo": producto.id },
            el(
                "div",
                { class: "entrega-encabezado" },
                el("span", { class: "producto-nombre", text: producto.nombre }),
                el("span", { class: "producto-precio", text: producto.precio_texto })
            ),
            ...(producto.es_peso_variable
                ? producto.movimientos.map((movimiento, i) => renglonRollo(captura, producto, movimiento, i + 1))
                : [renglonProducto(captura, producto)])
        );
    }

    function redibujarGrupo(producto) {
        const actual = ui.contenido.querySelector(`[data-grupo="${producto.id}"]`);
        if (actual) {
            actual.replaceWith(grupoEntrega(producto));
        }
        actualizarBarraEntrega();
    }

    function marcaSinExistencia() {
        return el("span", { class: "marca-sin-existencia", text: "Sin existencia en sistema" });
    }

    function botonNoLlevo(clave, marcado, producto) {
        return el("button", {
            type: "button",
            class: "btn btn-no-llevo",
            "aria-pressed": String(marcado),
            text: marcado ? "✓ No se lo llevó · tocar para deshacer" : "✕ No se lo llevó",
            onclick: () => {
                const captura = capturaActual();
                if (captura.noLlevo.has(clave)) {
                    captura.noLlevo.delete(clave);
                } else {
                    captura.noLlevo.add(clave);
                }
                capturaCambiada(captura);
                redibujarGrupo(producto);
            },
        });
    }

    function renglonRollo(captura, producto, movimiento, numero) {
        const clave = claveRollo(movimiento);
        const noLlevo = captura.noLlevo.has(clave);
        const texto = captura.pesos.get(movimiento.move_id) || "";
        const problemas = captura.problemas.get(movimiento.move_id) || [];
        const faltaPeso = captura.faltanPesos && !noLlevo && !texto.trim();
        const mensaje = faltaPeso ? "Falta el peso de este rollo." : problemas.join(" ");
        const renglon = el("div", {
            class: ["renglon", noLlevo ? "no-llevo" : "", mensaje && !noLlevo ? "con-problema" : ""].join(" ").trim(),
            "data-renglon": clave,
        });
        const encabezado = el(
            "div",
            { class: "renglon-titulo" },
            el("span", { class: "renglon-nombre", text: `Rollo ${numero}` }),
            movimiento.sin_existencia ? marcaSinExistencia() : null
        );
        if (noLlevo) {
            renglon.append(encabezado, botonNoLlevo(clave, true, producto));
            return renglon;
        }
        const campo = el("input", {
            type: "text",
            inputmode: "decimal",
            autocomplete: "off",
            class: "peso-campo",
            placeholder: "0.000",
            value: texto,
            "aria-label": `Peso en kg del rollo ${numero} de ${producto.nombre}`,
        });
        const eco = el("span", { class: "peso-eco", text: ecoPeso(texto, producto.precio) });
        const nodoMensaje = el("p", {
            class: "renglon-mensaje",
            role: "alert",
            text: mensaje,
            hidden: mensaje ? null : "hidden",
        });
        campo.addEventListener("input", () => {
            captura.pesos.set(movimiento.move_id, campo.value);
            captura.problemas.delete(movimiento.move_id);
            capturaCambiada(captura);
            eco.textContent = ecoPeso(campo.value, producto.precio);
            renglon.classList.remove("con-problema");
            nodoMensaje.hidden = true;
        });
        renglon.append(
            encabezado,
            el("label", { class: "peso" }, campo, el("span", { class: "peso-unidad", text: "kg" })),
            eco,
            nodoMensaje,
            botonNoLlevo(clave, false, producto)
        );
        return renglon;
    }

    function renglonProducto(captura, producto) {
        const clave = claveProducto(producto);
        const noLlevo = captura.noLlevo.has(clave);
        const cantidad = captura.cantidades.get(producto.id);
        const renglon = el("div", { class: noLlevo ? "renglon no-llevo" : "renglon", "data-renglon": clave });
        renglon.append(
            el(
                "div",
                { class: "renglon-titulo" },
                el("span", { class: "renglon-nombre", text: `Pendiente: ${producto.cantidad} ${producto.unidad}` }),
                producto.sin_existencia ? marcaSinExistencia() : null
            )
        );
        if (!noLlevo) {
            const cambiar = (cambio) => {
                // Entre 1 y lo pendiente: para no entregar se usa "No se lo llevó".
                const nueva = Math.max(1, Math.min(producto.cantidad, cantidad + cambio));
                if (nueva !== cantidad) {
                    captura.cantidades.set(producto.id, nueva);
                    capturaCambiada(captura);
                    redibujarGrupo(producto);
                }
            };
            renglon.append(
                el(
                    "div",
                    { class: "cantidad-controles" },
                    el("button", {
                        type: "button",
                        class: "btn btn-menos",
                        text: "−",
                        "aria-label": `Uno menos de ${producto.nombre}`,
                        disabled: cantidad <= 1 ? "disabled" : null,
                        onclick: () => cambiar(-1),
                    }),
                    el("span", { class: "cantidad-entrega", text: `${cantidad} ${producto.unidad}` }),
                    el("button", {
                        type: "button",
                        class: "btn btn-mas",
                        text: "+",
                        "aria-label": `Uno más de ${producto.nombre}`,
                        disabled: cantidad >= producto.cantidad ? "disabled" : null,
                        onclick: () => cambiar(1),
                    })
                )
            );
        }
        renglon.append(botonNoLlevo(clave, noLlevo, producto));
        return renglon;
    }

    function actualizarBarraEntrega() {
        const captura = estado.cliente && capturas.get(estado.cliente.id);
        if (estado.pantalla === "entrega-resumen") {
            const vista = captura && captura.vista;
            ponerBarraAbajo(
                estado.enviando ? "CONFIRMANDO…" : "✓ CONFIRMAR ENTREGA",
                vista ? `Total ${vista.total_texto}` : "",
                !vista || estado.enviando,
                Boolean(vista)
            );
            return;
        }
        const cargado = captura && captura.pendiente;
        const total = cargado ? totalRenglones(captura) : 0;
        const llevados = cargado
            ? rollosPendientes(captura).filter(({ movimiento }) => !captura.noLlevo.has(claveRollo(movimiento))).length +
              productosNormales(captura).filter((producto) => !captura.noLlevo.has(claveProducto(producto))).length
            : 0;
        ponerBarraAbajo(
            estado.revisando ? "REVISANDO…" : "REVISAR ENTREGA ›",
            !cargado ? "Cargando…" : `Se lleva ${llevados} de ${plural(total, "renglón", "renglones")}`,
            !total || estado.revisando,
            false
        );
    }

    function senalarPrimerProblema() {
        const primero = ui.contenido.querySelector(".renglon.con-problema, .aviso-entrega");
        if (primero) {
            primero.scrollIntoView({ block: "center" });
        }
    }

    async function revisarEntrega() {
        const captura = capturaActual();
        if (!captura.pendiente || estado.revisando || estado.enviando) {
            return;
        }
        // Un peso vacío NO es "no entregado": hay que escribirlo o marcar "No se lo llevó".
        const sinPeso = rollosPendientes(captura).filter(
            ({ movimiento }) =>
                !captura.noLlevo.has(claveRollo(movimiento)) && !(captura.pesos.get(movimiento.move_id) || "").trim()
        );
        if (sinPeso.length) {
            captura.faltanPesos = true;
            captura.aviso =
                `Falta capturar el peso de ${plural(sinPeso.length, "rollo", "rollos")}. ` +
                "Si no se lo llevó, toca «No se lo llevó».";
            dibujarListaEntrega();
            senalarPrimerProblema();
            return;
        }
        captura.faltanPesos = false;
        captura.aviso = null;
        estado.revisando = true;
        actualizarBarraEntrega();
        const cliente = estado.cliente;
        let vista;
        try {
            vista = await api("/captura/api/entrega/vista_previa", paramsEntrega(captura));
        } catch (error) {
            estado.revisando = false;
            captura.aviso = error.sinRespuesta ? error.message : `No se pudo revisar la entrega: ${error.message}`;
            if (estado.pantalla === "entrega" && estado.cliente.id === cliente.id) {
                // Un error del servidor puede venir de un cambio de otra persona: se recarga.
                error.sinRespuesta ? dibujarListaEntrega() : dibujarEntrega();
            }
            return;
        }
        estado.revisando = false;
        if (estado.pantalla !== "entrega" || estado.cliente.id !== cliente.id) {
            return;
        }
        captura.problemas = new Map(
            vista.rollos.filter((rollo) => rollo.bloqueo).map((rollo) => [rollo.move_id, [rollo.bloqueo, ...rollo.advertencias]])
        );
        if (!vista.puede_confirmar) {
            captura.aviso = "Corrige el peso de los rollos marcados.";
            dibujarListaEntrega();
            senalarPrimerProblema();
            return;
        }
        captura.vista = vista;
        irA("entrega-resumen", {});
    }

    // === Pantalla: Resumen de la entrega ===

    function lineaResumenEntrega(nombre, detalle, importe, advertencias) {
        return el(
            "div",
            { class: "resumen-linea resumen-entrega" },
            el(
                "span",
                { class: "resumen-nombre" },
                nombre,
                el("span", { class: "resumen-detalle", text: detalle }),
                ...(advertencias || []).map((texto) => el("span", { class: "resumen-advertencia", text: `⚠ ${texto}` }))
            ),
            el("span", { class: "resumen-importe", text: importe })
        );
    }

    function noLlevados(captura) {
        const nombres = [];
        for (const { producto, movimiento, numero } of rollosPendientes(captura)) {
            if (captura.noLlevo.has(claveRollo(movimiento))) {
                nombres.push(`${producto.nombre} · rollo ${numero}`);
            }
        }
        for (const producto of productosNormales(captura)) {
            if (captura.noLlevo.has(claveProducto(producto))) {
                nombres.push(`${producto.nombre} · ${producto.cantidad} ${producto.unidad}`);
            }
        }
        return nombres;
    }

    function dibujarEntregaResumen() {
        ponerTitulo(estado.cliente.nombre, estado.zona && estado.zona.nombre);
        nuevaVista();
        const captura = capturaActual();
        actualizarBarraEntrega();
        const vista = captura.vista;
        if (!vista || !captura.pendiente) {
            mostrar(
                aviso("Toca Regresar para revisar la entrega."),
                el("button", { type: "button", class: "btn btn-primario", text: "‹ Regresar", onclick: alTocarRegresar })
            );
            return;
        }
        const pendientePor = new Map(productosNormales(captura).map((producto) => [producto.id, producto.cantidad]));
        const lineas = [
            ...vista.rollos.map((rollo) =>
                lineaResumenEntrega(rollo.nombre, `${rollo.peso.toFixed(3)} kg`, dinero.format(rollo.importe), rollo.advertencias)
            ),
            ...vista.productos.map((producto) =>
                lineaResumenEntrega(
                    producto.nombre,
                    `${producto.cantidad} ${producto.unidad}` +
                        (producto.cantidad < pendientePor.get(producto.id) ? ` de ${pendientePor.get(producto.id)}` : ""),
                    dinero.format(producto.importe)
                )
            ),
        ];
        const noSeLlevo = noLlevados(captura);
        mostrar(
            el("p", { class: "pregunta", text: "Falta confirmar la entrega" }),
            lineas.length ? lista(lineas) : aviso("No se lleva nada."),
            noSeLlevo.length ? el("p", { class: "seccion-titulo", text: "No se lo llevó" }) : null,
            noSeLlevo.length ? lista(noSeLlevo.map((texto) => el("div", { class: "resumen-no-llevo", text: texto }))) : null,
            el(
                "div",
                { class: "total-entrega" },
                el("span", { class: "total-etiqueta", text: "Total" }),
                el("span", { class: "total-monto", text: vista.total_texto })
            ),
            captura.error ? el("p", { class: "error-envio", role: "alert", text: captura.error }) : null,
            el("p", { class: "nota", text: "Para cambiar algo, toca Regresar." })
        );
    }

    async function confirmarEntrega() {
        const captura = capturaActual();
        const vista = captura.vista;
        if (!vista || estado.enviando || confirmando) {
            return;
        }
        if (!vista.rollos.length && !vista.productos.length) {
            const seguro = await confirmar({
                texto: `${estado.cliente.nombre} no se lleva nada. Se cancelarán todas sus entregas pendientes.`,
                si: "Sí, cancelar sus entregas",
                no: "No, regresar",
            });
            if (seguro !== "si") {
                return;
            }
        }
        for (const rollo of vista.rollos) {
            for (const advertencia of rollo.advertencias) {
                const bien = await confirmar({
                    texto: `${rollo.nombre}: ${rollo.peso.toFixed(3)} kg. ${advertencia}`,
                    si: "El peso está bien",
                    no: "Corregir el peso",
                });
                if (bien !== "si") {
                    captura.problemas.set(rollo.move_id, [advertencia]);
                    captura.aviso = "Corrige el peso del rollo marcado.";
                    history.back(); // a la lista, con el rollo señalado
                    return;
                }
            }
        }
        if (estado.enviando) {
            return;
        }
        estado.enviando = true; // antes del await: bloquea el doble toque
        captura.error = null;
        captura.token = captura.token || nuevoToken();
        dibujarEntregaResumen();
        const cliente = estado.cliente;
        let resultado;
        try {
            resultado = await api("/captura/api/entrega/confirmar", {
                ...paramsEntrega(captura),
                movimientos_vistos: captura.pendiente.productos.flatMap((p) => p.movimientos.map((m) => m.move_id)),
                token: captura.token,
            });
        } catch (error) {
            estado.enviando = false;
            if (error.sinRespuesta) {
                captura.error =
                    "No se pudo confirmar si la entrega llegó. Toca «Confirmar entrega» otra vez: " +
                    "si ya había llegado, no se duplica.";
                dibujarEntregaResumen();
            } else if (/cambiaron|ya no está pendiente/.test(error.message)) {
                // Otra persona validó o cambió algo: se recarga lo pendiente,
                // conservando lo capturado de lo que siga pendiente.
                capturaCambiada(captura);
                captura.aviso =
                    "Otra persona ya validó o cambió entregas de este cliente. " +
                    "Se volvió a cargar lo pendiente: revisa y confirma otra vez.";
                history.back();
            } else {
                captura.error = `No se confirmó la entrega: ${error.message}`;
                dibujarEntregaResumen();
            }
            return;
        }
        estado.enviando = false;
        capturas.delete(cliente.id);
        estado.entregado = resultado;
        estado.pantalla = "entregado";
        // Reemplaza el Resumen en el historial: "atrás" ya no regresa a él.
        history.replaceState(fotoHistorial(), "");
        dibujar();
    }

    // === Pantalla: Entrega confirmada ===

    function dibujarEntregado() {
        nuevaVista();
        const entregado = estado.entregado;
        ponerTitulo("Entrega confirmada", estado.zona && estado.zona.nombre);
        pantallaExito(
            "ENTREGA CONFIRMADA",
            entregado && [
                el("p", { class: "cobrar", text: `Cobrar: ${entregado.total_texto}` }),
                el("p", { class: "enviado-detalle", text: entregado.cliente }),
                el(
                    "ul",
                    { class: "folios" },
                    ...entregado.entregas.map((entrega) =>
                        el("li", {
                            text:
                                `${entrega.folio} · ${entrega.orden}` +
                                (entrega.estado === "cancelada" ? " (cancelada)" : ""),
                        })
                    )
                ),
            ]
        );
    }

    // =====================================================================
    // === Modo Cobro ===
    // =====================================================================

    // El cobro de cada cliente: lo que devolvió /cobro/detalle, cómo pagó y el
    // monto tecleado. Se conserva mientras la página esté abierta (al ir y
    // volver entre el detalle y la confirmación, o al cobrarle a otro); se
    // borra al registrar el cobro.
    const cobros = new Map(); // id de cliente -> cobro
    const TIPOS_COBRO = { todo: "Pagó todo", parte: "Pagó una parte", nada: "No pagó hoy" };

    function cobroActual() {
        const id = estado.cliente.id;
        if (!cobros.has(id)) {
            cobros.set(id, {
                cliente: estado.cliente, // para recordarlo en Inicio y volver a él
                zona: estado.zona,
                detalle: null, // respuesta de /cobro/detalle
                tipo: null, // "todo" | "parte" | "nada"
                montoTexto: "", // lo tecleado en "Pagó una parte"
                token: null,
                aviso: null, // mensaje arriba del detalle
                error: null, // mensaje en la confirmación
                mostrarProblema: false, // se intentó registrar un monto inválido
            });
        }
        const cobro = cobros.get(id);
        cobro.zona = estado.zona;
        return cobro;
    }

    function redondearCentavos(n) {
        return Math.round(n * 100) / 100;
    }

    function fechaCorta(iso) {
        // "2026-09-20" -> "20/09/2026"
        const [anio, mes, dia] = (iso || "").split("-");
        return dia ? `${dia}/${mes}/${anio}` : "";
    }

    function precioTexto(renglon) {
        const sufijo = renglon.es_peso_variable ? "/kg" : renglon.unidad === "c/u" ? " c/u" : `/${renglon.unidad}`;
        return dinero.format(renglon.precio) + sufijo;
    }

    function revisarMonto(texto, total) {
        // {monto} si se puede registrar; {problema} si no. Punto o coma decimal,
        // máximo 2 decimales, mayor a 0 y sin pasar del total.
        const limpio = (texto || "").trim();
        if (!limpio) {
            return { problema: "Escribe cuánto pagó.", vacio: true };
        }
        if (!/^\d+([.,]\d{1,2})?$/.test(limpio)) {
            return { problema: "Escribe el importe con máximo 2 decimales, por ejemplo 150.50." };
        }
        const monto = redondearCentavos(Number(limpio.replace(",", ".")));
        if (monto <= 0) {
            return { problema: "El importe debe ser mayor a $0." };
        }
        if (monto > total) {
            return {
                problema: `No puede ser más que el total a cobrar (${dinero.format(total)}). Si pagó todo, regresa y toca «Pagó todo».`,
            };
        }
        return { monto };
    }

    function montoDelCobro(c) {
        // Efectivo que se registrará (o null si el monto de "una parte" no es válido).
        const total = c.detalle.total_a_cobrar;
        if (c.tipo === "todo") {
            return total;
        }
        if (c.tipo === "nada") {
            return 0;
        }
        const revision = revisarMonto(c.montoTexto, total);
        return revision.problema ? null : revision.monto;
    }

    // === Pantalla: Lo que hay que cobrarle al cliente ===

    async function dibujarCobro() {
        const cliente = estado.cliente;
        const c = cobroActual();
        ponerTitulo(cliente.nombre, estado.zona && estado.zona.nombre);
        const vista = nuevaVista();
        mostrar(aviso("Cargando lo que debe…"));
        let detalle;
        try {
            // Siempre se vuelve a pedir: refleja lo que otros hayan facturado o cobrado.
            detalle = await api("/captura/api/cobro/detalle", { cliente_id: cliente.id, zona_id: estado.zona.id });
        } catch (error) {
            if (vigente(vista)) {
                mostrarError(error, dibujarCobro);
            }
            return;
        }
        if (!vigente(vista)) {
            return;
        }
        c.detalle = detalle;
        dibujarDetalleCobro();
    }

    function lineaCobro(nombre, detalle, importe, clase) {
        return el(
            "div",
            { class: `resumen-linea ${clase || ""}` },
            el("span", { class: "resumen-nombre" }, nombre, detalle ? el("span", { class: "resumen-detalle", text: detalle }) : null),
            el("span", { class: "resumen-importe", text: importe })
        );
    }

    function dibujarDetalleCobro() {
        const c = cobroActual();
        const d = c.detalle;
        const entregado = d.entregado.map((r) =>
            lineaCobro(
                r.nombre,
                (r.es_peso_variable ? `${r.peso.toFixed(3)} kg` : `${r.cantidad} ${r.unidad}`) + ` · ${precioTexto(r)}`,
                dinero.format(r.importe),
                "cobro-entregado"
            )
        );
        const anteriores = d.saldo_anterior.map((f) =>
            lineaCobro(f.folio, `Del ${fechaCorta(f.fecha)}`, dinero.format(f.saldo), "cobro-anterior")
        );
        const aFavor = d.creditos.map((f) =>
            lineaCobro(f.folio, `Del ${fechaCorta(f.fecha)}`, `−${dinero.format(f.saldo)}`, "cobro-credito")
        );
        const bloqueado = d.borradores.length > 0;
        // El servidor pone primero el aviso de la factura en borrador (el que bloquea).
        const avisos = d.avisos.map((texto, i) =>
            el("p", { class: bloqueado && i === 0 ? "aviso-cobro bloquea" : "aviso-cobro informativo", role: "alert", text: texto })
        );
        let acciones;
        if (d.puede_cobrar) {
            acciones = lista([
                el("button", { type: "button", class: "btn btn-primario btn-pago-todo", text: TIPOS_COBRO.todo, onclick: () => elegirPago("todo") }),
                el("button", { type: "button", class: "btn btn-secundario", text: TIPOS_COBRO.parte, onclick: () => elegirPago("parte") }),
                el("button", { type: "button", class: "btn btn-secundario", text: TIPOS_COBRO.nada, onclick: () => elegirPago("nada") }),
            ]);
        } else if (!bloqueado) {
            acciones = aviso("No hay nada que cobrarle.");
        }
        mostrar(
            c.aviso ? el("p", { class: "aviso-cobro", role: "alert", text: c.aviso }) : null,
            ...avisos,
            entregado.length ? el("p", { class: "seccion-titulo", text: "Entregado sin facturar" }) : null,
            entregado.length ? lista(entregado) : null,
            anteriores.length ? el("p", { class: "seccion-titulo", text: "Saldo anterior" }) : null,
            anteriores.length ? lista(anteriores) : null,
            aFavor.length ? el("p", { class: "seccion-titulo", text: "Saldo a favor (se descuenta)" }) : null,
            aFavor.length ? lista(aFavor) : null,
            el(
                "div",
                { class: "total-entrega total-cobro" },
                el("span", { class: "total-etiqueta", text: "Total a cobrar" }),
                el("span", { class: "total-monto", text: dinero.format(d.total_a_cobrar) })
            ),
            d.saldo_a_favor > 0 ? el("p", { class: "nota", text: `Le quedan ${dinero.format(d.saldo_a_favor)} a favor.` }) : null,
            // Cobro bloqueado: se repite el aviso debajo del total, donde irían
            // los botones de pago (con muchas líneas, el de arriba ya no se ve).
            bloqueado ? el("p", { class: "aviso-cobro bloquea bajo-total", text: d.avisos[0] }) : null,
            acciones ? el("div", { class: "acciones-cobro" }, acciones) : null
        );
    }

    function elegirPago(tipo) {
        const c = cobroActual();
        c.tipo = tipo;
        c.error = null;
        c.aviso = null;
        c.mostrarProblema = false;
        irA("cobro-confirmar", {});
    }

    // === Pantalla: Confirmación del cobro ===

    function dibujarConfirmarCobro() {
        ponerTitulo(estado.cliente.nombre, estado.zona && estado.zona.nombre);
        nuevaVista();
        const c = cobroActual();
        actualizarBarraCobro();
        if (!c.detalle || !c.tipo) {
            mostrar(
                aviso("Toca Regresar para ver lo que debe."),
                el("button", { type: "button", class: "btn btn-primario", text: "‹ Regresar", onclick: alTocarRegresar })
            );
            return;
        }
        const total = c.detalle.total_a_cobrar;
        const nodos = [
            el("p", { class: "pregunta", text: "Falta registrar el cobro" }),
            el("p", { class: "cobro-tipo", text: TIPOS_COBRO[c.tipo] }),
        ];
        let campo = null;
        if (c.tipo === "parte") {
            campo = el("input", {
                class: "peso-campo monto-campo",
                type: "text",
                inputmode: "decimal",
                autocomplete: "off",
                "aria-label": "Efectivo recibido",
                placeholder: "0.00",
                value: c.montoTexto,
                oninput: (evento) => {
                    c.montoTexto = evento.target.value;
                    c.mostrarProblema = false;
                    actualizarEcoMonto();
                },
            });
            nodos.push(
                el("label", { class: "seccion-titulo", text: "¿Cuánto pagó?" }),
                el("div", { class: "peso" }, el("span", { class: "peso-unidad", text: "$" }), campo),
                el("p", { class: "peso-eco monto-eco" }),
                el("p", { class: "renglon-mensaje monto-mensaje", hidden: "hidden" })
            );
        }
        nodos.push(
            lista([
                lineaCobro("Total a cobrar", null, dinero.format(total), "cobro-total"),
                lineaCobro("Efectivo recibido", null, "", "cobro-recibido"),
                lineaCobro("Queda debiendo", null, "", "cobro-debe"),
            ]),
            c.error ? el("p", { class: "error-envio", role: "alert", text: c.error }) : null,
            el("p", { class: "nota", text: "Para cambiar algo, toca Regresar." })
        );
        mostrar(...nodos);
        actualizarEcoMonto();
    }

    function actualizarBarraCobro() {
        // "✓ REGISTRAR COBRO" en la franja de abajo, con el efectivo que se registrará.
        const c = cobroActual();
        const listo = Boolean(c.detalle && c.tipo);
        const monto = listo ? montoDelCobro(c) : null;
        ponerBarraAbajo(
            estado.enviando ? "REGISTRANDO…" : "✓ REGISTRAR COBRO",
            !listo ? "" : monto === null ? "Falta escribir cuánto pagó" : `Efectivo recibido: ${dinero.format(monto)}`,
            !listo || estado.enviando,
            listo
        );
    }

    function actualizarEcoMonto() {
        // Eco en vivo de lo que se registrará.
        const c = cobroActual();
        const total = c.detalle.total_a_cobrar;
        const monto = montoDelCobro(c);
        actualizarBarraCobro();
        const recibido = ui.contenido.querySelector(".cobro-recibido .resumen-importe");
        const debe = ui.contenido.querySelector(".cobro-debe .resumen-importe");
        recibido.textContent = monto === null ? "—" : dinero.format(monto);
        debe.textContent = monto === null ? "—" : dinero.format(redondearCentavos(total - monto));
        const eco = ui.contenido.querySelector(".monto-eco");
        const mensaje = ui.contenido.querySelector(".monto-mensaje");
        if (!eco) {
            return;
        }
        const revision = revisarMonto(c.montoTexto, total);
        eco.textContent = revision.problema
            ? revision.vacio
                ? "Escribe cuánto pagó"
                : "Importe no válido"
            : `Recibe ${dinero.format(revision.monto)} · Queda debiendo ${dinero.format(redondearCentavos(total - revision.monto))}`;
        mensaje.textContent = revision.problema || "";
        mensaje.hidden = !(c.mostrarProblema && revision.problema);
    }

    async function registrarCobro() {
        const c = cobroActual();
        if (!c.detalle || !c.tipo || estado.enviando || confirmando) {
            return;
        }
        const monto = montoDelCobro(c);
        if (monto === null) {
            c.mostrarProblema = true;
            actualizarEcoMonto();
            const campo = ui.contenido.querySelector(".monto-campo");
            if (campo) {
                campo.focus();
            }
            return;
        }
        if (c.tipo === "nada") {
            const seguro = await confirmar({
                texto: `La deuda de ${dinero.format(c.detalle.total_a_cobrar)} quedará pendiente.`,
                si: "Sí, no pagó hoy",
                no: "No, regresar",
            });
            if (seguro !== "si" || estado.enviando) {
                return;
            }
        }
        estado.enviando = true; // antes del await: bloquea el doble toque
        c.error = null;
        c.token = c.token || nuevoToken();
        dibujarConfirmarCobro();
        const cliente = estado.cliente;
        let resultado;
        try {
            resultado = await api("/captura/api/cobro/confirmar", {
                cliente_id: cliente.id,
                zona_id: estado.zona.id,
                tipo: c.tipo,
                visto: c.detalle.visto,
                token: c.token,
                ...(c.tipo === "parte" ? { monto } : {}),
            });
        } catch (error) {
            estado.enviando = false;
            c.error = error.sinRespuesta
                ? "No se pudo confirmar si el cobro llegó. Toca «Registrar cobro» otra vez: si ya había llegado, no se duplica."
                : `No se registró el cobro: ${error.message}`;
            dibujarConfirmarCobro();
            return;
        }
        estado.enviando = false;
        if (resultado.cambiaron) {
            // Otra persona facturó o cobró: se muestra lo nuevo, sin registrar nada.
            c.detalle = resultado.cobro;
            c.token = null;
            c.tipo = null;
            c.aviso =
                "Otra persona facturó o cobró a este cliente mientras tanto. " +
                "Se volvió a cargar lo que debe: revisa el total y cobra otra vez.";
            history.back();
            return;
        }
        cobros.delete(cliente.id);
        estado.cobrado = resultado;
        estado.pantalla = "cobrado";
        // Reemplaza la confirmación en el historial: "atrás" ya no regresa a ella.
        history.replaceState(fotoHistorial(), "");
        dibujar();
    }

    // === Pantalla: Cobro registrado ===

    function dibujarCobrado() {
        nuevaVista();
        const cobrado = estado.cobrado;
        ponerTitulo("Cobro registrado", estado.zona && estado.zona.nombre);
        pantallaExito(
            "COBRO REGISTRADO",
            cobrado && [
                el("p", { class: "cobrar", text: `Cobrado: ${dinero.format(cobrado.monto_recibido)}` }),
                cobrado.saldo_pendiente > 0
                    ? el("p", { class: "queda-debiendo", text: `Queda debiendo: ${dinero.format(cobrado.saldo_pendiente)}` })
                    : null,
                el("p", { class: "enviado-detalle", text: `${cobrado.cliente} · ${TIPOS_COBRO[cobrado.tipo]}` }),
                cobrado.facturas.length
                    ? el("ul", { class: "folios" }, ...cobrado.facturas.map((f) => el("li", { text: `Factura ${f.folio}` })))
                    : null,
            ]
        );
    }

    // =====================================================================
    // === Acomodo de entregas (solo lectura) ===
    // =====================================================================

    // Los pedidos del día operativo con algo pendiente, por zona, en el orden en
    // que se carga el carrito (lo decide el servidor): del más reciente, que va
    // hasta el fondo, al más antiguo; el número es la posición de entrega (el 1
    // se entrega primero y queda hasta arriba). Cada vez que se abre se piden
    // datos frescos al servidor.
    async function dibujarAcomodo() {
        ponerTitulo("Acomodo de entregas");
        const vista = nuevaVista();
        mostrar(aviso("Cargando pedidos…"));
        let zonas;
        try {
            zonas = await api("/captura/api/acomodo");
        } catch (error) {
            if (vigente(vista)) {
                mostrarError(error, dibujarAcomodo);
            }
            return;
        }
        if (!vigente(vista)) {
            return;
        }
        if (!zonas.length) {
            mostrar(el("p", { class: "aviso aviso-grande", text: "Hoy no hay pedidos pendientes de entregar." }));
            return;
        }
        mostrar(...zonas.map(seccionAcomodo));
    }

    function seccionAcomodo(zona) {
        return el(
            "section",
            { class: "acomodo-zona" },
            el("h2", { class: "acomodo-zona-nombre", text: zona.nombre }),
            el("p", {
                class: "acomodo-instruccion",
                text: "Carga en este orden: el primero de la lista va hasta el fondo del carrito",
            }),
            el(
                "div",
                { class: "acomodo-columnas", "aria-hidden": "true" },
                el("span", { text: "Producto" }),
                el("span", { text: "Cantidad" })
            ),
            el("ol", { class: "acomodo-pedidos" }, ...zona.pedidos.map(pedidoAcomodo))
        );
    }

    function pedidoAcomodo(pedido) {
        return el(
            "li",
            { class: "acomodo-pedido", "data-pedido": pedido.id },
            el(
                "div",
                { class: "acomodo-cliente" },
                el("span", { class: "acomodo-posicion", text: String(pedido.posicion) }),
                el("span", { class: "acomodo-cliente-nombre", text: pedido.cliente })
            ),
            el(
                "ul",
                { class: "acomodo-productos" },
                ...pedido.productos.map((producto) =>
                    el(
                        "li",
                        { class: "acomodo-producto" },
                        el("span", { class: "acomodo-producto-nombre", text: producto.nombre }),
                        el("span", { class: "acomodo-cantidad", text: textoCantidad(producto, producto.cantidad) })
                    )
                )
            )
        );
    }

    // === Arranque ===

    ui.regresar.addEventListener("click", alTocarRegresar);
    ui.inicio.addEventListener("click", alTocarInicio);
    ui.btnPedido.addEventListener("click", alTocarBarraPedido);
    window.addEventListener("popstate", alMoverseEnHistorial);
    window.addEventListener("beforeunload", avisarAntesDeSalir);
    window.addEventListener("resize", medirBarra);
    history.replaceState(fotoHistorial(), "");
    dibujar();
})();
