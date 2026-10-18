/** Hoja de carga (Ventas › Órdenes › Hoja de carga): la misma lista que se
 * recarga sola (ListaRecargaController, lista_recarga.js) con un pie propio,
 * una sola fila "Productos totales: N".
 * Solo para la vista con js_class="duran_hoja_carga_lista".
 *
 * N = suma de `productos_totales` (oculto en la vista): kg y piezas valen 1.
 * Agrupada, suma los totales de cada grupo, que manda el servidor aunque el
 * grupo esté cerrado ("Sin zona" incluido); sin agrupar, los renglones
 * cargados. Se recalcula en cada recarga. */
import { registry } from "@web/core/registry";
import { formatInteger } from "@web/views/fields/formatters";
import { ListRenderer } from "@web/views/list/list_renderer";
import { listView } from "@web/views/list/list_view";
import { ListaRecargaController } from "./lista_recarga";

export class HojaCargaRenderer extends ListRenderer {
    static template = "duran_captura_tianguis.HojaCargaRenderer";

    get productosTotales() {
        const { list } = this.props;
        const valores = list.isGrouped
            ? list.groups.map((grupo) => grupo.aggregates.productos_totales)
            : list.records.map((renglon) => renglon.data.productos_totales);
        const total = valores.reduce((suma, valor) => suma + (valor || 0), 0);
        return formatInteger(Math.round(total));
    }
}

registry.category("views").add("duran_hoja_carga_lista", {
    ...listView,
    Controller: ListaRecargaController,
    Renderer: HojaCargaRenderer,
});
