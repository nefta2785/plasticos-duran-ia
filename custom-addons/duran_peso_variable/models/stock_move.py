from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import float_compare


class StockMove(models.Model):
    _inherit = "stock.move"

    peso_real = fields.Float(
        string="Peso real (kg)",
        digits=(16, 3),
        help="Peso real capturado del rollo al momento de la entrega.",
    )
    es_peso_variable = fields.Boolean(
        related="product_id.es_peso_variable",
        string="Es peso variable",
        readonly=True,
    )

    @api.constrains("product_uom_qty", "quantity", "product_id")
    def _check_peso_variable_qty_max_1(self):
        for move in self:
            if not move.es_peso_variable:
                continue
            rounding = move.product_uom.rounding
            if (
                float_compare(move.product_uom_qty, 1.0, precision_rounding=rounding) > 0
                or float_compare(move.quantity, 1.0, precision_rounding=rounding) > 0
            ):
                raise ValidationError(_(
                    'El producto "%(product)s" es de peso variable: cada línea de la entrega '
                    "representa 1 rollo y no puede tener una cantidad mayor a 1. "
                    "Corrige la cantidad desde la Orden de Venta, no desde la Entrega.",
                    product=move.product_id.display_name,
                ))
