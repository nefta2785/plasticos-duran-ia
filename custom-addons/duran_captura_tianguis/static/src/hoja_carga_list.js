/** Hoja de carga (Ventas › Órdenes › Hoja de carga): la lista se recarga sola
 * mientras se ve, para que el papá vea los pedidos que la mamá sigue enviando.
 * Solo para la vista con js_class="hoja_carga_list".
 *
 * - Se pausa con la página oculta (otra pestaña, celular bloqueado) y recarga
 *   una vez al volver a verse.
 * - No recarga mientras se ejecuta un toque de botón (Acomodado / Quitar).
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
export const SEGUNDOS_RECARGA = 30;

export class HojaCargaListController extends ListController {
    setup() {
        super.setup();
        this.model.orm = this.model.orm.silent;
        this.tocando = 0;
        this.recargaIniciada = null;
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

    async recargar() {
        const ahora = Date.now();
        // Una recarga que otra carga reemplazó nunca termina (KeepLast en
        // concurrency.js): pasado un ciclo, ya no se espera.
        const enCurso = this.recargaIniciada && ahora - this.recargaIniciada < SEGUNDOS_RECARGA * 1000;
        if (document.visibilityState !== "visible" || this.tocando || enCurso) {
            return;
        }
        this.recargaIniciada = ahora;
        try {
            await this.model.load();
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

registry.category("views").add("hoja_carga_list", {
    ...listView,
    Controller: HojaCargaListController,
});
