from odoo import api, fields, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    peso_real = fields.Float(
        string="Peso real (kg)",
        digits=(16, 3),
        help="Peso real del rollo, usado para calcular el precio cuando el producto es de peso variable.",
    )
    precio_por_kg = fields.Float(
        string="Precio por kg",
        digits="Product Price",
        help="Precio por kg con el que se factura el rollo: el congelado al validar la "
        "entrega. Si está vacío se usa el precio vigente del producto.",
    )
    es_peso_variable = fields.Boolean(
        related="product_id.es_peso_variable",
        string="Es peso variable",
        readonly=True,
    )

    @api.depends("peso_real", "precio_por_kg")
    def _compute_price_unit(self):
        super()._compute_price_unit()
        for line in self:
            if line.es_peso_variable:
                line.price_unit = line.peso_real * (line.precio_por_kg or line.product_id.precio_por_kg)
