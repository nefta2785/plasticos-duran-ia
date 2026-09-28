from odoo import api, fields, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    peso_real = fields.Float(
        string="Peso real (kg)",
        digits=(16, 3),
        help="Peso real del rollo, usado para calcular el precio cuando el producto es de peso variable.",
    )
    es_peso_variable = fields.Boolean(
        related="product_id.es_peso_variable",
        string="Es peso variable",
        readonly=True,
    )

    @api.depends("peso_real")
    def _compute_price_unit(self):
        super()._compute_price_unit()
        for line in self:
            if line.es_peso_variable:
                line.price_unit = line.peso_real * line.product_id.precio_por_kg
