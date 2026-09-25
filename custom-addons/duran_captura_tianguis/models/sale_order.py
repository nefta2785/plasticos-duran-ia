from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    zona_id = fields.Many2one(
        "res.partner.category",
        string="Zona",
        index=True,
        copy=False,
        ondelete="restrict",
        help="Zona (etiqueta de contacto) desde la que se levantó el pedido en el tianguis.",
    )
