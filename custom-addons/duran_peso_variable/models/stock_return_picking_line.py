from odoo import models


class StockReturnPickingLine(models.TransientModel):
    _inherit = "stock.return.picking.line"

    def _prepare_move_default_values(self, new_picking):
        vals = super()._prepare_move_default_values(new_picking)
        if self.product_id.es_peso_variable:
            # El asistente de devolución crea el stock.move nuevo con
            # `self.move_id.copy(vals)`: sin esta línea, `peso_real` se
            # copiaría del movimiento de salida original (el peso con el que
            # se despachó), y el usuario vería ese valor prellenado en vez de
            # 0 al abrir la Entrega de devolución. Forzándolo acá, solo se ve
            # afectado el `copy()` que hace este asistente específico — no
            # cualquier otro `copy()` de stock.move en el sistema (ej.
            # duplicar una entrega manualmente sigue copiando peso_real como
            # siempre).
            vals["peso_real"] = 0.0
        return vals
