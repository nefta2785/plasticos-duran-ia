from odoo import api, fields, models

GRUPO_GERENTE_VENTAS = "sales_team.group_sale_manager"


class StockMove(models.Model):
    _inherit = "stock.move"

    # Para la hoja de carga (Ventas › Órdenes › Hoja de carga): se guardan en
    # el movimiento para poder filtrar y agrupar la lista por ellos.
    zona_id = fields.Many2one(
        related="sale_line_id.order_id.zona_id", store=True, index=True, string="Zona",
    )
    fecha_pedido = fields.Datetime(
        related="sale_line_id.order_id.date_order", store=True, index=True, string="Fecha del pedido",
        help="Fecha en que se confirmó (levantó) el pedido. No cambia si se reprograma la entrega.",
    )
    unidad_producto_id = fields.Many2one(
        related="product_id.uom_id", string="Unidad",
        help="Unidad del producto, en la que se muestra la Demanda de la hoja de carga.",
    )

    # Para el pendiente de cobro (Ventas › Órdenes › Pendiente de cobro): lo
    # entregado, por cliente y pedido, con su importe.
    cliente_id = fields.Many2one(
        related="sale_line_id.order_id.partner_id", store=True, index=True, string="Cliente",
    )
    pedido = fields.Char(related="sale_line_id.order_id.name", store=True, index=True, string="Pedido")
    moneda_id = fields.Many2one(related="company_id.currency_id", string="Moneda")
    cantidad_entregada = fields.Float(
        compute="_compute_entregado", store=True, digits="Product Unit", string="Cantidad",
        # Sin suma en los grupos del pendiente de cobro: mezclaría kg con piezas.
        aggregator=None,
        help="Lo entregado, en la unidad del producto (un rollo = 1 pieza). 0 si no se ha entregado.",
    )
    importe_entregado = fields.Monetary(
        compute="_compute_entregado", store=True, currency_field="moneda_id", string="Pendiente por pagar",
        groups=GRUPO_GERENTE_VENTAS,
        help="Precio de venta de lo entregado, sin impuestos, como lo factura Odoo: en rollos, peso "
        "real × precio por kg congelado; en lo demás, cantidad entregada × precio de la línea. En "
        "ambos casos con el descuento de la línea. 0 si no se ha entregado.",
    )

    @api.depends(
        "state", "quantity", "product_uom", "product_id.uom_id", "product_id.es_peso_variable",
        "peso_real", "precio_por_kg", "company_id.currency_id",
        "sale_line_id.price_unit", "sale_line_id.discount", "sale_line_id.product_uom_id",
    )
    def _compute_entregado(self):
        for move in self:
            linea = move.sale_line_id
            if move.state != "done" or not linea:
                move.cantidad_entregada = 0.0
                move.importe_entregado = 0.0
                continue
            move.cantidad_entregada = move.product_uom._compute_quantity(move.quantity, move.product_id.uom_id)
            if move.product_id.es_peso_variable:
                # Como la factura (duran_peso_variable, _prepare_invoice_line):
                # precio del rollo = peso real × precio por kg congelado.
                base = move.peso_real * move.precio_por_kg
            else:
                base = move.product_uom._compute_quantity(move.quantity, linea.product_uom_id) * linea.price_unit
            move.importe_entregado = move.company_id.currency_id.round(base * (1 - (linea.discount or 0.0) / 100))

