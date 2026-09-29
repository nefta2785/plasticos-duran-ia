from odoo import fields, models


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
