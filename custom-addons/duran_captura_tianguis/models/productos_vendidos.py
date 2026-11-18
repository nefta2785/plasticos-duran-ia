from odoo import fields, models, tools
from odoo.tools import SQL

from .captura import ZONA_HORARIA_OPERACION

# Para el id estable de cada renglón (producto y día): días desde esta fecha.
DIA_BASE = "2020-01-01"
DIAS_POR_PRODUCTO = 100000


class DuranProductosVendidos(models.Model):
    """ Productos vendidos (Ventas › Órdenes › Productos vendidos): vista SQL
    de solo lectura, un renglón por producto y día, con lo entregado al cliente
    y lo devuelto. Sin importes en pesos.

    - El día es el de calendario en México en que se validó el movimiento
      (`stock.move.date`), con la misma regla que "Pendiente de cobro".
    - Vendido: salida validada al cliente de una venta, que no es devolución
      (misma regla que las entregas de `duran.pendiente.cobro`). Incluye el
      rollo nuevo de un Cambio de producto.
    - Devuelto: devolución validada desde el cliente de un movimiento de venta
      (botón Devolver o asistente Cambio de producto). La "devolución de una
      devolución" no cuenta ni como vendido ni como devuelto.
    - Unidades y kg:
        * peso variable (de cualquier unidad): unidades = rollos, kg = peso real;
        * todo lo demás, sin importar su unidad de medida: unidades = cantidad,
          sin kg (las Bolsas de asa tienen unidad kg pero se venden por pieza;
          las cantidades siempre son enteras).
      Así el total de Unidades es el total de productos vendidos y el de kg
      solo lleva peso real. """
    _name = "duran.productos.vendidos"
    _description = "Productos vendidos"
    _auto = False
    _order = "dia desc, product_id"
    _rec_name = "product_id"

    dia = fields.Date(string="Día", readonly=True)
    es_hoy = fields.Boolean(string="Es hoy", readonly=True)
    product_id = fields.Many2one("product.product", string="Producto", readonly=True)
    unidad_producto_id = fields.Many2one("uom.uom", string="Unidad", readonly=True)
    es_peso_variable = fields.Boolean(string="Es peso variable", readonly=True)
    # Qué columnas aplican al producto (las otras se ven vacías en la lista).
    usa_unidades = fields.Boolean(readonly=True)
    usa_kg = fields.Boolean(readonly=True)
    vendido_unidades = fields.Float(string="Vendido (unidades)", digits="Product Unit", readonly=True)
    vendido_kg = fields.Float(string="Vendido (kg)", digits=(16, 3), readonly=True)
    devuelto_unidades = fields.Float(string="Devuelto (unidades)", digits="Product Unit", readonly=True)
    devuelto_kg = fields.Float(string="Devuelto (kg)", digits=(16, 3), readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(SQL("CREATE VIEW %s AS (%s)", SQL.identifier(self._table), self._consulta()))

    def _consulta(self):
        return SQL(
            """
            WITH movimientos AS (
                SELECT sm.product_id,
                       (sm.date AT TIME ZONE 'UTC' AT TIME ZONE %(tz)s)::date AS dia,
                       (destino.usage = 'customer') AS es_venta,
                       sm.cantidad_entregada, sm.peso_real
                  FROM stock_move sm
                  JOIN stock_picking sp ON sp.id = sm.picking_id
                  JOIN stock_picking_type spt ON spt.id = sp.picking_type_id
                  JOIN stock_location origen ON origen.id = sm.location_id
                  JOIN stock_location destino ON destino.id = sm.location_dest_id
                 WHERE sm.state = 'done'
                   AND sm.sale_line_id IS NOT NULL
                   AND (
                       -- Entrega al cliente (como las entregas de Pendiente de cobro).
                       (spt.code = 'outgoing' AND destino.usage = 'customer'
                        AND sp.sale_id IS NOT NULL AND sp.return_id IS NULL)
                       -- Devolución del cliente (como duran_peso_variable).
                       OR (sm.origin_returned_move_id IS NOT NULL
                           AND origen.usage = 'customer' AND destino.usage <> 'customer')
                   )
            ),
            clasificados AS (
                SELECT m.product_id, m.dia, m.es_venta,
                       COALESCE(pt.es_peso_variable, FALSE) AS es_peso_variable,
                       pt.uom_id, m.cantidad_entregada, m.peso_real
                  FROM movimientos m
                  JOIN product_product pp ON pp.id = m.product_id
                  JOIN product_template pt ON pt.id = pp.product_tmpl_id
            ),
            valores AS (
                -- Unidades: siempre la cantidad (un rollo = 1). kg: solo el peso
                -- real del peso variable; la unidad de medida no cuenta.
                SELECT product_id, dia, es_venta, es_peso_variable, uom_id,
                       cantidad_entregada AS unidades,
                       CASE WHEN es_peso_variable THEN COALESCE(peso_real, 0) END AS kg
                  FROM clasificados
            )
            SELECT v.product_id::bigint * %(por_producto)s + (v.dia - DATE %(base)s) AS id,
                   v.dia,
                   (v.dia = (now() AT TIME ZONE %(tz)s)::date) AS es_hoy,
                   v.product_id,
                   v.uom_id AS unidad_producto_id,
                   v.es_peso_variable,
                   TRUE AS usa_unidades,
                   v.es_peso_variable AS usa_kg,
                   SUM(v.unidades) FILTER (WHERE v.es_venta) AS vendido_unidades,
                   SUM(v.kg) FILTER (WHERE v.es_venta) AS vendido_kg,
                   SUM(v.unidades) FILTER (WHERE NOT v.es_venta) AS devuelto_unidades,
                   SUM(v.kg) FILTER (WHERE NOT v.es_venta) AS devuelto_kg
              FROM valores v
             GROUP BY v.product_id, v.dia, v.uom_id, v.es_peso_variable
            """,
            tz=ZONA_HORARIA_OPERACION, por_producto=DIAS_POR_PRODUCTO, base=DIA_BASE,
        )
