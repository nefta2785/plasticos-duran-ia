from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .captura_entrega import FORMATO_TOKEN


class CapturaCobro(models.Model):
    """ Bitácora de los cobros hechos en el tianguis desde /captura (modo
    Cobro). Un registro por cada vez que se confirma el cobro a un cliente:
    cuánto se le mostró por cobrar, cuánto pagó en efectivo, las facturas que
    se crearon y el pago que se registró.

    El token único evita cobrar dos veces lo mismo (doble toque o reintento sin
    señal). Quien cobra solo puede crear y ver los suyos; no puede modificarlos
    ni borrarlos. Sirve también para el arqueo: el efectivo que cobró cada
    quien en el día. """

    _name = "duran.captura.cobro"
    _description = "Cobro en tianguis"
    _order = "fecha desc, id desc"

    token = fields.Char(
        string="Token de captura",
        required=True,
        readonly=True,
        copy=False,
        help="Identificador del envío desde /captura. Evita cobrar dos veces si se toca "
        "Confirmar dos veces o se reintenta después de perder la señal.",
    )
    fecha = fields.Datetime(string="Fecha", required=True, readonly=True, default=fields.Datetime.now)
    user_id = fields.Many2one(
        "res.users", string="Cobró", required=True, readonly=True, index=True,
        default=lambda self: self.env.user, ondelete="restrict",
    )
    partner_id = fields.Many2one(
        "res.partner", string="Cliente", required=True, readonly=True, index=True, ondelete="restrict",
    )
    zona_id = fields.Many2one(
        "res.partner.category", string="Zona", required=True, readonly=True, index=True, ondelete="restrict",
    )
    company_id = fields.Many2one(
        "res.company", string="Compañía", required=True, readonly=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(related="company_id.currency_id")
    tipo = fields.Selection(
        [
            ("todo", "Pagó todo"),
            ("parte", "Pagó una parte"),
            ("nada", "No pagó hoy"),
        ],
        string="Cómo pagó", required=True, readonly=True,
    )
    total_entregado = fields.Monetary(
        string="Entregado sin facturar", readonly=True,
        help="Lo entregado que se facturó en este cobro.",
    )
    saldo_anterior = fields.Monetary(
        string="Saldo anterior", readonly=True,
        help="Lo que el cliente debía de facturas anteriores.",
    )
    creditos = fields.Monetary(
        string="Saldo a favor", readonly=True,
        help="Notas de crédito o pagos sin aplicar del cliente, que se restaron del total.",
    )
    total_a_cobrar = fields.Monetary(
        string="Total a cobrar", readonly=True,
        help="Total que se le mostró a quien cobraba al confirmar.",
    )
    monto_recibido = fields.Monetary(
        string="Efectivo recibido", readonly=True,
        help="Efectivo que se registró como pago en el diario de efectivo.",
    )
    saldo_pendiente = fields.Monetary(
        string="Queda pendiente", readonly=True,
        help="Lo que el cliente quedó debiendo después de este cobro.",
    )
    linea_ids = fields.One2many("duran.captura.cobro.linea", "cobro_id", string="Documentos", readonly=True)
    invoice_ids = fields.Many2many(
        "account.move", string="Facturas", compute="_compute_invoice_ids", store=True,
        help="Facturas creadas en este cobro. Se calcula (como superusuario, igual que cualquier "
        "campo calculado guardado) desde los documentos del cobro, porque pueden ser de otro "
        "vendedor, que quien cobra no puede leer: guardarlas directamente en un Many2many lo "
        "rechazaría Odoo.",
    )
    # Many2one: Odoo no exige poder leer el pago para guardarlo.
    payment_id = fields.Many2one("account.payment", string="Pago", readonly=True, copy=False, ondelete="restrict")
    nota = fields.Text(string="Notas", readonly=True)

    _token_uniq = models.Constraint(
        "UNIQUE (token)",
        "Este cobro de la captura ya se había registrado.",
    )

    @api.depends("linea_ids.move_id", "linea_ids.tipo")
    def _compute_invoice_ids(self):
        for cobro in self:
            cobro.invoice_ids = cobro.linea_ids.filtered(lambda l: l.tipo == "nueva").move_id

    @api.constrains("token")
    def _check_formato_token(self):
        for cobro in self:
            if not FORMATO_TOKEN.match(cobro.token or ""):
                raise ValidationError(_("El token del cobro no es válido."))

    @api.depends("partner_id", "fecha")
    def _compute_display_name(self):
        for cobro in self:
            fecha = fields.Datetime.context_timestamp(cobro, cobro.fecha) if cobro.fecha else None
            cobro.display_name = " · ".join(filter(None, [
                cobro.partner_id.display_name,
                fecha and fecha.strftime("%d/%m/%Y %H:%M"),
            ])) or _("Cobro en tianguis")


class CapturaCobroLinea(models.Model):
    """ Un documento del cobro: una factura creada en el cobro, una factura
    anterior con saldo, o un saldo a favor (nota de crédito o pago sin
    aplicar), con su saldo antes y después del cobro. """

    _name = "duran.captura.cobro.linea"
    _description = "Documento de un cobro en tianguis"
    _order = "cobro_id, id"

    cobro_id = fields.Many2one(
        "duran.captura.cobro", string="Cobro", required=True, index=True, ondelete="cascade",
    )
    currency_id = fields.Many2one(related="cobro_id.currency_id")
    # Many2one: Odoo no exige poder leer el documento para guardarlo.
    move_id = fields.Many2one("account.move", string="Documento", required=True, ondelete="restrict")
    tipo = fields.Selection(
        [
            ("nueva", "Factura de este cobro"),
            ("anterior", "Saldo anterior"),
            ("credito", "Saldo a favor"),
        ],
        string="Tipo", required=True,
    )
    saldo_antes = fields.Monetary(string="Saldo antes")
    aplicado = fields.Monetary(string="Aplicado", help="Lo que se pagó o se aplicó de este documento.")
    saldo_despues = fields.Monetary(string="Saldo después")
