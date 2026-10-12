/** Listas de Ventas › Órdenes que se recargan solas mientras se ven (Hoja de
 * carga, Pendiente de cobro, Entregas en tianguis, Resumen de ventas), para
 * que el papá vea lo que la mamá sigue enviando desde la app.
 * Solo para las vistas con js_class="duran_lista_recarga".
 *
 * - Se pausa con la página oculta (otra pestaña, celular bloqueado) y recarga
 *   una vez al volver a verse.
 * - No recarga mientras se ejecuta un toque de botón (Acomodado / Quitar).
 * - No recarga mientras hay otra carga en curso: un filtro o búsqueda
 *   (`model.load`, que solo respeta la última: KeepLast en concurrency.js) o
 *   un orden, página o grupo abierto (`model._updateConfig`). Si no, la
 *   recarga saldría con la configuración anterior y taparía la nueva.
 * - No recarga con renglones seleccionados (se perdería la selección), salvo
 *   en los modelos de REFRESCA_CON_SELECCION.
 * - `model.load()` reutiliza la configuración actual: los grupos abiertos
 *   siguen abiertos (relational_model.js, `_webReadGroup`, opening_info).
 * - Falla en silencio: si una recarga falla (sin conexión, error del
 *   servidor) no se avisa nada y se intenta en la siguiente vuelta. Las
 *   lecturas de esta lista son "silent" (orm_service.js): una recarga lenta
 *   no muestra el aviso "Cargando". Los toques de botón no pasan por aquí. */
import { onMounted, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { ListController } from "@web/views/list/list_controller";
import { listView } from "@web/views/list/list_view";

// Cada cuántos segundos se recarga la lista mientras se ve.
export const SEGUNDOS_RECARGA = 5;

// Modelos que se recargan aunque haya renglones seleccionados: en la Hoja de
// carga las casillas no se usan para nada y el papá debe ver siempre lo nuevo.
const REFRESCA_CON_SELECCION = ["duran.hoja.carga"];

export class ListaRecargaController extends ListController {
    setup() {
        super.setup();
        this.model.orm = this.model.orm.silent;
        this.tocando = 0;
        this.recargaIniciada = null;
        this.vigilarCargasAjenas();
        const alCambiarVisibilidad = () => {
            if (document.visibilityState === "visible") {
                this.recargar();
            }
        };
        onMounted(() => {
            this.intervalo = setInterval(() => this.recargar(), SEGUNDOS_RECARGA * 1000);
            document.addEventListener("visibilitychange", alCambiarVisibilidad);
        });
        onWillUnmount(() => {
            clearInterval(this.intervalo);
            document.removeEventListener("visibilitychange", alCambiarVisibilidad);
        });
    }

    vigilarCargasAjenas() {
        // Cuenta las cargas que no lanzó la recarga. Una carga que otra
        // reemplazó nunca termina (KeepLast): pasado un ciclo desde la última
        // que empezó, ya no se espera.
        this.cargasAjenas = 0;
        this.ultimaCargaAjena = 0;
        const vigilar = (metodo, esCarga) => {
            const original = this.model[metodo].bind(this.model);
            this.model[metodo] = async (...args) => {
                if (this.recargando || !esCarga(...args)) {
                    return original(...args);
                }
                this.cargasAjenas++;
                this.ultimaCargaAjena = Date.now();
                try {
                    return await original(...args);
                } finally {
                    this.cargasAjenas--;
                }
            };
        };
        vigilar("load", () => true);
        vigilar("_updateConfig", (config, patch, { reload = true } = {}) => reload);
    }

    get hayCargaAjena() {
        return this.cargasAjenas > 0 && Date.now() - this.ultimaCargaAjena < SEGUNDOS_RECARGA * 1000;
    }

    get haySeleccion() {
        const { root } = this.model;
        return !REFRESCA_CON_SELECCION.includes(root.resModel) && (root.selection.length > 0 || root.isDomainSelected);
    }

    async recargar() {
        const ahora = Date.now();
        // Una recarga que otra carga reemplazó nunca termina (KeepLast en
        // concurrency.js): pasado un ciclo, ya no se espera.
        const enCurso = this.recargaIniciada && ahora - this.recargaIniciada < SEGUNDOS_RECARGA * 1000;
        if (document.visibilityState !== "visible" || this.tocando || enCurso || this.hayCargaAjena || this.haySeleccion) {
            return;
        }
        this.recargaIniciada = ahora;
        this.recargando = true;
        let carga;
        try {
            carga = this.model.load();
        } finally {
            this.recargando = false;
        }
        try {
            await carga;
        } catch {
            // Sin conexión u otro error pasajero: se intenta en la siguiente vuelta.
        } finally {
            if (this.recargaIniciada === ahora) {
                this.recargaIniciada = null;
            }
        }
    }

    async beforeExecuteActionButton(clickParams) {
        this.tocando++;
        const seguir = await super.beforeExecuteActionButton(clickParams);
        if (seguir === false) {
            this.tocando--;
        }
        return seguir;
    }

    async afterExecuteActionButton(clickParams) {
        this.tocando = Math.max(0, this.tocando - 1);
        return super.afterExecuteActionButton(clickParams);
    }
}

registry.category("views").add("duran_lista_recarga", {
    ...listView,
    Controller: ListaRecargaController,
});
