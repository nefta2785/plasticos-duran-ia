from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    captura_token = fields.Char(
        string="Token de captura",
        copy=False,
        readonly=True,
        help="Identificador del alta del cliente desde /captura. Evita crear dos veces el mismo "
        "cliente si se toca Guardar dos veces o se reintenta después de perder la señal.",
    )

    _captura_token_uniq = models.Constraint(
        "UNIQUE (captura_token)",
        "Este cliente de la captura ya se había creado.",
    )
