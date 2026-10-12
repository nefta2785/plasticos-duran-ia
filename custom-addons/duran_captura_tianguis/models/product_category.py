from odoo import fields, models


class ProductCategory(models.Model):
    _inherit = "product.category"

    captura_orden = fields.Integer(
        string="Orden en la app",
        help="Orden del botón de esta categoría en la pantalla Pedido de la app de captura: 1 va "
        "primero (después de \"Lo de siempre\"). Con 0 o vacío va al final, en orden alfabético.",
    )
