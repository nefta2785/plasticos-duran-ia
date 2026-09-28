from odoo import api, fields, models
from odoo.tools import float_is_zero, float_round


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    peso_real = fields.Float(
        string="Peso real (kg)",
        digits=(16, 3),
        help="Peso real del rollo, usado para calcular el precio cuando el producto es de peso variable.",
    )
    precio_por_kg = fields.Float(
        string="Precio por kg (congelado)",
        digits="Product Price",
        readonly=True,
        copy=False,
        help="Precio por kg con el que se entregó el rollo, copiado de la Entrega al "
        "validarla. Si está vacío (rollo aún sin entregar) se usa el precio vigente.",
    )
    es_peso_variable = fields.Boolean(
        related="product_id.es_peso_variable",
        string="Es peso variable",
        readonly=True,
    )

    @api.depends("peso_real", "precio_por_kg")
    def _compute_price_unit(self):
        # El precio de un rollo es siempre peso × precio por kg: la tarifa de
        # Odoo (lista de precios, technical_price_unit) no aplica y no se toca.
        peso_variable = self.filtered("es_peso_variable")
        super(SaleOrderLine, self - peso_variable)._compute_price_unit()
        for line in peso_variable:
            # Como Odoo (sale.order.line._compute_price_unit): una línea ya
            # facturada nunca cambia de precio.
            if not line.qty_invoiced > 0:
                line.price_unit = line.peso_real * (line.precio_por_kg or line.product_id.precio_por_kg)

    def _prepare_procurement_values(self):
        values = super()._prepare_procurement_values()
        values["peso_real"] = self.peso_real
        return values

    def _prepare_invoice_line(self, **optional_values):
        vals = super()._prepare_invoice_line(**optional_values)
        if self.es_peso_variable:
            peso_real = self._get_peso_real_for_invoice()
            precio_por_kg = self._get_precio_por_kg_for_invoice()
            vals["peso_real"] = peso_real
            vals["precio_por_kg"] = precio_por_kg
            # `price_unit` es un campo precompute en account.move.line: si va
            # explícito en el create() (como hace el método base con
            # self.price_unit), Odoo lo respeta tal cual y NO dispara el
            # compute, así que hay que recalcularlo aquí mismo para que quede
            # consistente con el peso_real que se está por guardar.
            vals["price_unit"] = peso_real * precio_por_kg
        return vals

    def _get_precio_por_kg_for_invoice(self):
        """ Precio por kg congelado en la Entrega validada (el vigente cuando
        se entregó el rollo), para que un cambio posterior del precio del
        producto no altere lo que ya se entregó.

        En notas de crédito por devolución (`qty_to_invoice < 0`) se usa el
        precio vigente del producto: así lo calcula el Cambio de producto para
        el abono. También se usa el precio vigente si la Entrega se validó
        antes de que existiera el precio congelado. """
        self.ensure_one()
        if self.qty_to_invoice >= 0:
            delivery_move = self._get_delivery_move()
            if delivery_move and delivery_move.precio_por_kg:
                return delivery_move.precio_por_kg
        return self.product_id.precio_por_kg

    def _get_peso_real_for_invoice(self):
        """ Prioriza el peso real capturado en la Entrega (el que de verdad se
        pesó al despachar el rollo).

        Si lo que se está por facturar es en realidad una nota de crédito por
        devolución (`qty_to_invoice < 0`), se usa en cambio el peso real
        capturado en el movimiento de devolución validado, para que el
        crédito refleje el peso que realmente volvió (ej. lo que quedó de un
        rollo defectuoso), no el peso que se había despachado originalmente.

        Si no hay ningún movimiento de devolución que aplique, se cae al peso
        de la Entrega (ver `_get_peso_real_delivered`). """
        self.ensure_one()
        if self.qty_to_invoice < 0:
            return_moves = self.move_ids.filtered(
                lambda m: m.state == "done"
                and m.origin_returned_move_id
                and m.location_dest_usage != "customer"
            )
            if return_moves:
                return return_moves.sorted("date", reverse=True)[0].peso_real
        return self._get_peso_real_delivered()

    def _get_peso_real_delivered(self):
        """ Peso real capturado en la Entrega validada (movimiento de SALIDA
        real hacia el cliente, `location_dest_id.usage == 'customer'`), para
        no tomar por error el peso de una devolución (que en Odoo es también
        un stock.move done del mismo sale_line_id, pero con destino interno).
        Si hay más de un movimiento de salida (p. ej. entregas parciales), se
        usa el más reciente. Si no hay ninguno, se cae al peso_real capturado
        en la propia línea de venta. """
        self.ensure_one()
        delivery_move = self._get_delivery_move()
        if delivery_move:
            return delivery_move.peso_real
        return self.peso_real

    def _get_delivery_move(self):
        """ Movimiento de salida al cliente validado más reciente de la línea
        (ver `_get_peso_real_delivered`). """
        self.ensure_one()
        return self.move_ids.filtered(
            lambda m: m.state == "done" and m.location_dest_usage == "customer"
        ).sorted("date", reverse=True)[:1]

    @api.depends_context("duran_cambio_producto_label")
    def _compute_display_name(self):
        if not self.env.context.get("duran_cambio_producto_label"):
            return super()._compute_display_name()
        # Registros sin orden/producto (ej. un sale.order.line nuevo, todavía
        # sin guardar) no tienen forma de armar la etiqueta "#N · producto";
        # se les deja el comportamiento estándar de Odoo en vez de arriesgar
        # un formato roto como "#0 · False".
        generic = self.filtered(lambda l: not l.order_id or not l.product_id)
        if generic:
            super(SaleOrderLine, generic)._compute_display_name()
        for line in self - generic:
            content_lines = line.order_id.order_line.filtered(lambda l: not l.display_type)
            row = content_lines.ids.index(line.id) + 1 if line.id in content_lines.ids else 0
            label = f"#{row} · {line.product_id.display_name}"
            if line.es_peso_variable:
                label += f" · {line._get_peso_real_delivered():.3f} kg"
            line.display_name = label

    @api.model_create_multi
    def create(self, vals_list):
        expanded_vals_list = []
        for vals in vals_list:
            expanded_vals_list.extend(self._expand_peso_variable_vals(vals))
        return super().create(expanded_vals_list)

    def write(self, vals):
        res = super().write(vals)
        if "product_uom_qty" in vals or "product_id" in vals:
            for line in self:
                if line.es_peso_variable and line.product_uom_qty > 1:
                    line._split_peso_variable_line()
        return res

    @api.model
    def _expand_peso_variable_vals(self, vals):
        """ Un producto de peso variable nunca debe tener más de 1 unidad por
        línea (cada rollo = 1 línea). Si se intenta crear una línea con
        cantidad > 1, se reparte en varias líneas de cantidad 1. """
        product_id = vals.get("product_id")
        qty = vals.get("product_uom_qty")
        if not product_id or not qty or qty <= 1:
            return [vals]
        product = self.env["product.product"].browse(product_id)
        if not product.es_peso_variable:
            return [vals]
        return [dict(vals, product_uom_qty=split_qty) for split_qty in self._split_peso_variable_qty(qty)]

    def _split_peso_variable_line(self):
        self.ensure_one()
        qtys = self._split_peso_variable_qty(self.product_uom_qty)
        self.product_uom_qty = qtys[0]
        for split_qty in qtys[1:]:
            # `order_id` tiene copy=False en sale.order.line (para no arrastrar
            # el pedido original al duplicar una orden completa), así que hay
            # que pasarlo explícito para que la línea nueva quede en esta orden.
            self.copy({"order_id": self.order_id.id, "product_uom_qty": split_qty, "peso_real": 0.0})

    @api.model
    def _split_peso_variable_qty(self, qty):
        precision = self.env["decimal.precision"].precision_get("Product Unit of Measure")
        full_lines = int(float_round(qty, precision_digits=0, rounding_method="DOWN"))
        remainder = qty - full_lines
        qtys = [1.0] * full_lines
        if not float_is_zero(remainder, precision_digits=precision):
            qtys.append(remainder)
        return qtys or [qty]
