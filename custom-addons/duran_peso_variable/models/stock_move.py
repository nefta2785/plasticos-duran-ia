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
    precio_por_kg = fields.Float(
        string="Precio por kg al entregar",
        digits="Product Price",
        readonly=True,
        copy=False,
        help="Precio por kg del producto cuando se validó la entrega al cliente. La factura "
        "usa este precio: si después cambia el precio del producto, lo ya entregado se "
        "sigue cobrando al precio con el que se entregó.",
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

    def _action_done(self, cancel_backorder=False):
        moves = super()._action_done(cancel_backorder=cancel_backorder)
        # Solo las salidas al cliente: en devoluciones y cambios el abono se
        # sigue calculando con el precio vigente (ver duran.cambio.producto).
        entregas = moves.filtered(
            lambda m: m.es_peso_variable and m.location_dest_usage == "customer"
        )
        for move in entregas:
            move.precio_por_kg = move.product_id.precio_por_kg
        entregas._sincronizar_linea_venta()
        return moves

    def _sincronizar_linea_venta(self):
        """ Copia el peso real y el precio por kg congelado de cada rollo
        entregado a su línea de venta, para que la orden muestre el monto real
        (la línea calcula su precio como peso × precio por kg congelado).

        Con sudo porque quien valida puede no poder escribir la orden (un
        vendedor con "solo sus documentos" validando la de otro vendedor; los
        usuarios de almacén sí pueden, por sale_stock). El sudo SOLO escribe
        `peso_real` y `precio_por_kg`, y SOLO en las líneas de estos
        movimientos recién validados; sudo conserva al usuario, así que el
        historial de la orden queda a su nombre. Una línea ya facturada no se
        toca: nunca cambia de precio. """
        for move in self.filtered("sale_line_id"):
            linea = move.sale_line_id.sudo()
            if linea.qty_invoiced > 0:
                continue
            linea.write({"peso_real": move.peso_real, "precio_por_kg": move.precio_por_kg})
