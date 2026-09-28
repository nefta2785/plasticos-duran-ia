import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

FORMATO_TOKEN = re.compile(r"^[0-9a-f]{32}$")


class CapturaEntrega(models.Model):
    """ Bitácora de las entregas hechas en el tianguis desde /captura (modo
    Entrega). Un registro por cada vez que se confirma la entrega a un cliente:
    qué se entregó, a quién, quién lo entregó y el total que se le mostró.

    El token único evita registrar dos veces la misma entrega (doble toque o
    reintento sin señal). Quien captura solo puede crear y ver las suyas; no
    puede modificarlas ni borrarlas. """

    _name = "duran.captura.entrega"
    _description = "Entrega en tianguis"
    _order = "fecha desc, id desc"

    token = fields.Char(
        string="Token de captura",
        required=True,
        readonly=True,
        copy=False,
        help="Identificador del envío desde /captura. Evita registrar dos veces la misma "
        "entrega si se toca Confirmar dos veces o se reintenta después de perder la señal.",
    )
    fecha = fields.Datetime(string="Fecha", required=True, readonly=True, default=fields.Datetime.now)
    user_id = fields.Many2one(
        "res.users", string="Entregó", required=True, readonly=True, index=True,
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
    picking_ids = fields.Many2many("stock.picking", string="Entregas", readonly=True)
    order_ids = fields.Many2many("sale.order", string="Órdenes de venta", readonly=True)
    linea_ids = fields.One2many("duran.captura.entrega.linea", "entrega_id", string="Productos", readonly=True)
    total = fields.Monetary(
        string="Total (informativo)",
        readonly=True,
        help="Total que se le mostró a quien entregaba al confirmar. Es informativo: lo que "
        "se cobra es lo que diga la factura.",
    )
    nota = fields.Text(string="Notas", readonly=True)

    _token_uniq = models.Constraint(
        "UNIQUE (token)",
        "Esta entrega de la captura ya se había registrado.",
    )

    @api.constrains("token")
    def _check_formato_token(self):
        for entrega in self:
            if not FORMATO_TOKEN.match(entrega.token or ""):
                raise ValidationError(_("El token de la entrega no es válido."))

    @api.depends("partner_id", "fecha")
    def _compute_display_name(self):
        for entrega in self:
            fecha = fields.Datetime.context_timestamp(entrega, entrega.fecha) if entrega.fecha else None
            entrega.display_name = " · ".join(filter(None, [
                entrega.partner_id.display_name,
                fecha and fecha.strftime("%d/%m/%Y %H:%M"),
            ])) or _("Entrega en tianguis")


class CapturaEntregaLinea(models.Model):
    """ Un renglón de lo entregado: un rollo de peso variable (con su peso y el
    precio por kg congelado al validar) o la cantidad entregada de un producto
    de peso fijo. """

    _name = "duran.captura.entrega.linea"
    _description = "Producto entregado en tianguis"
    _order = "entrega_id, id"

    entrega_id = fields.Many2one(
        "duran.captura.entrega", string="Entrega", required=True, index=True, ondelete="cascade",
    )
    currency_id = fields.Many2one(related="entrega_id.currency_id")
    product_id = fields.Many2one("product.product", string="Producto", required=True, ondelete="restrict")
    sale_line_id = fields.Many2one("sale.order.line", string="Línea de venta", ondelete="set null")
    move_id = fields.Many2one("stock.move", string="Movimiento", ondelete="set null")
    cantidad = fields.Float(string="Cantidad", digits="Product Unit")
    peso_real = fields.Float(string="Peso real (kg)", digits=(16, 3))
    precio_unitario = fields.Float(
        string="Precio", digits="Product Price",
        help="Precio por kg en productos de peso variable; precio por unidad en los demás.",
    )
    importe = fields.Monetary(string="Importe")
    sin_existencia = fields.Boolean(
        string="Sin existencia en sistema",
        help="Se entregó aunque Odoo no tenía existencia registrada del producto.",
    )
