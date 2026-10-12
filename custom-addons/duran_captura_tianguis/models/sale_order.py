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
    captura_token = fields.Char(
        string="Token de captura",
        copy=False,
        readonly=True,
        help="Identificador del envío desde /captura. Evita crear dos veces la misma orden "
        "si se toca Enviar dos veces o se reintenta después de perder la señal.",
    )

    captura_pedido_extra = fields.Boolean(
        string="Pedido extra de la captura",
        default=False,
        copy=False,
        readonly=True,
        help="Levantado con «El cliente quiere algo más» durante una entrega: no entra en esa "
        "entrega y queda pendiente para la siguiente vuelta del día.",
    )

    _captura_token_uniq = models.Constraint(
        "UNIQUE (captura_token)",
        "Este pedido de la captura ya se había enviado.",
    )
