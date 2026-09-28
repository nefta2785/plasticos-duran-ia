from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    es_peso_variable = fields.Boolean(
        string="Es peso variable",
        default=False,
        help="Indica si este producto se factura según su peso real y no según su cantidad de venta fija.",
    )
    precio_por_kg = fields.Monetary(
        string="Precio por kg",
        currency_field="currency_id",
        help="Precio por kilogramo, aplicable a todas las variantes de este producto.",
    )
    peso_referencia = fields.Float(
        string="Peso de referencia (kg)",
        digits=(16, 3),
        help="Peso del producto completo (no de peso variable). Se usa para calcular el "
        "abono proporcional cuando se devuelve una unidad parcialmente usada, por "
        "ejemplo en un cambio de producto.",
    )
