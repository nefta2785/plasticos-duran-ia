from odoo import fields, models, tools
from odoo.tools import SQL

from .captura import ZONA_HORARIA_OPERACION

# Un renglón de saldo con MÁS de estos días de antigüedad se ve en rojo (7 días
# no; 8 sí). Único lugar donde está el umbral.
DIAS_SALDO_VENCIDO = 7


class DuranPendienteCobro(models.Model):
    """ Pendiente de cobro (Ventas › Órdenes › Pendiente de cobro): vista SQL
    de solo lectura con dos tipos de renglón, por cliente principal.

    - "Entregado hoy": cada movimiento entregado hoy (día de calendario en
      México) y sin facturar, con su importe de venta (`importe_entregado`).
    - "Saldo anterior": lo que ya debía, con la misma regla que el modo Cobro
      (`duran.captura._cobro`): un renglón por cada línea de venta con
      entregado sin facturar de antes de hoy, uno por cada factura publicada
      con saldo y uno por cada saldo a favor (nota de crédito o pago sin
      aplicar, en negativo).

    Así, el total del cliente = lo que la app de Cobro le muestra (salvo que su
    saldo a favor sea mayor: la app muestra $0 y aquí queda en negativo). Todo
    sin impuestos (el negocio opera al 0%). """
    _name = "duran.pendiente.cobro"
    _description = "Pendiente de cobro"
    _auto = False
    _order = "orden_clave, id"
    _rec_name = "pedido"

    tipo = fields.Selection(
        [("hoy", "Entregado hoy"), ("saldo", "Saldo anterior")], string="Tipo", readonly=True,
    )
    company_id = fields.Many2one("res.company", string="Compañía", readonly=True)
    moneda_id = fields.Many2one("res.currency", string="Moneda", readonly=True)
    zona_id = fields.Many2one("res.partner.category", string="Zona", readonly=True)
    cliente_id = fields.Many2one("res.partner", string="Cliente", readonly=True)
    pedido = fields.Char(
        string="Pedido", readonly=True,
        help="Folio de la orden; en facturas y saldos a favor, el folio del documento.",
    )
    product_id = fields.Many2one("product.product", string="Productos", readonly=True)
    es_peso_variable = fields.Boolean(string="Es peso variable", readonly=True)
    # Sin suma en los grupos: mezclaría kg con piezas.
    cantidad = fields.Float(string="Cantidad", digits="Product Unit", readonly=True, aggregator=None)
    unidad_producto_id = fields.Many2one("uom.uom", string="Unidad", readonly=True)
    peso_real = fields.Float(string="Peso del rollo (kg)", digits=(16, 3), readonly=True)
    pendiente_hoy = fields.Monetary(string="Pendiente de hoy", currency_field="moneda_id", readonly=True)
    saldo_anterior = fields.Monetary(string="Saldo anterior", currency_field="moneda_id", readonly=True)
    total = fields.Monetary(string="Total a cobrar", currency_field="moneda_id", readonly=True)
    fecha = fields.Date(
        string="Fecha del saldo", readonly=True,
        help="Fecha de la factura o del documento; en lo entregado sin facturar, el día de su última entrega.",
    )
    # En el encabezado del grupo: el máximo (desde cuándo debe el cliente).
    dias_antiguedad = fields.Integer(string="Días de antigüedad", readonly=True, aggregator="max")
    vencido = fields.Boolean(string="Saldo vencido", readonly=True)
    orden_clave = fields.Char(readonly=True)
    stock_move_id = fields.Many2one("stock.move", string="Movimiento", readonly=True)
    sale_line_id = fields.Many2one("sale.order.line", string="Línea de venta", readonly=True)
    move_line_id = fields.Many2one("account.move.line", string="Apunte", readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(SQL("CREATE VIEW %s AS (%s)", SQL.identifier(self._table), self._consulta()))

    def _consulta(self):
        tz = ZONA_HORARIA_OPERACION
        return SQL(
            """
            WITH parametros AS (
                SELECT (now() AT TIME ZONE %(tz)s)::date AS hoy,
                       (SELECT digits FROM decimal_precision WHERE name = 'Product Unit') AS digitos
            ),
            -- Lo entregado sin facturar: misma regla que duran.captura._lineas_sin_facturar
            -- con cantidad por facturar > 0 (sin devoluciones).
            lineas AS (
                SELECT sol.id, sol.company_id, sol.product_id, sol.product_uom_id, sol.qty_to_invoice,
                       sol.price_unit, sol.discount, so.name AS pedido, so.zona_id, so.date_order,
                       rp.commercial_partner_id AS cliente_id, cur.decimal_places
                  FROM sale_order_line sol
                  JOIN sale_order so ON so.id = sol.order_id
                  JOIN res_partner rp ON rp.id = so.partner_id
                  JOIN res_company co ON co.id = sol.company_id
                  JOIN res_currency cur ON cur.id = co.currency_id
                 CROSS JOIN parametros p
                 WHERE sol.state = 'sale'
                   AND sol.display_type IS NULL
                   AND NOT COALESCE(sol.is_downpayment, FALSE)
                   AND ROUND(sol.qty_to_invoice::numeric, p.digitos) > 0
            ),
            -- Entregas validadas: salida a cliente, ligada a una venta, que no es devolución.
            entregas AS (
                SELECT sm.id, sm.sale_line_id, sm.product_id, sm.quantity, sm.cantidad_entregada,
                       sm.importe_entregado, sm.peso_real,
                       (sm.date AT TIME ZONE 'UTC' AT TIME ZONE %(tz)s)::date AS dia
                  FROM stock_move sm
                  JOIN stock_picking sp ON sp.id = sm.picking_id
                  JOIN stock_picking_type spt ON spt.id = sp.picking_type_id
                  JOIN stock_location sl ON sl.id = sm.location_dest_id
                 WHERE sm.state = 'done'
                   AND spt.code = 'outgoing'
                   AND sl.usage = 'customer'
                   AND sp.sale_id IS NOT NULL
                   AND sp.return_id IS NULL
            ),
            renglones AS (
                -- Entregado hoy.
                SELECT e.id * 3 AS id, 'hoy' AS tipo, l.company_id, l.zona_id, l.cliente_id, l.pedido,
                       e.product_id, e.cantidad_entregada AS cantidad, pt.uom_id AS unidad_producto_id,
                       CASE WHEN pt.es_peso_variable THEN e.peso_real END AS peso_real,
                       e.importe_entregado AS pendiente_hoy, 0.0 AS saldo_anterior, NULL::date AS fecha,
                       e.id AS stock_move_id, l.id AS sale_line_id, NULL::integer AS move_line_id
                  FROM entregas e
                  JOIN lineas l ON l.id = e.sale_line_id
                  JOIN product_product pp ON pp.id = e.product_id
                  JOIN product_template pt ON pt.id = pp.product_tmpl_id
                 CROSS JOIN parametros p
                 WHERE e.dia = p.hoy

                UNION ALL

                -- Entregado sin facturar de antes de hoy: lo que se facturará de la línea
                -- menos lo entregado hoy (que ya va en sus renglones).
                SELECT l.id * 3 + 1, 'saldo', l.company_id, l.zona_id, l.cliente_id, l.pedido,
                       l.product_id, l.qty_to_invoice - COALESCE(h.cantidad, 0), l.product_uom_id,
                       CASE WHEN pt.es_peso_variable THEN ultima.peso_real END,
                       0.0,
                       ROUND((l.qty_to_invoice * l.price_unit * (1 - COALESCE(l.discount, 0) / 100))::numeric,
                             l.decimal_places) - COALESCE(h.importe, 0),
                       COALESCE(ultima.dia, (l.date_order AT TIME ZONE 'UTC' AT TIME ZONE %(tz)s)::date),
                       NULL, l.id, NULL
                  FROM lineas l
                  JOIN product_product pp ON pp.id = l.product_id
                  JOIN product_template pt ON pt.id = pp.product_tmpl_id
                 CROSS JOIN parametros p
                  LEFT JOIN LATERAL (
                      SELECT SUM(e.quantity) AS cantidad, SUM(e.importe_entregado) AS importe
                        FROM entregas e WHERE e.sale_line_id = l.id AND e.dia = p.hoy
                  ) h ON TRUE
                  LEFT JOIN LATERAL (
                      SELECT e.dia, e.peso_real
                        FROM entregas e WHERE e.sale_line_id = l.id AND e.dia < p.hoy
                       ORDER BY e.dia DESC, e.id DESC LIMIT 1
                  ) ultima ON TRUE
                 WHERE ROUND((l.qty_to_invoice - COALESCE(h.cantidad, 0))::numeric, p.digitos) <> 0
                    OR ROUND((l.qty_to_invoice * l.price_unit * (1 - COALESCE(l.discount, 0) / 100))::numeric,
                             l.decimal_places) - COALESCE(h.importe, 0) <> 0

                UNION ALL

                -- Facturas con saldo y saldos a favor: misma regla que
                -- duran.captura._saldos_abiertos (apuntes por cobrar publicados sin conciliar).
                SELECT aml.id * 3 + 2, 'saldo', aml.company_id,
                       (SELECT MIN(so.zona_id)
                          FROM account_move_line il
                          JOIN sale_order_line_invoice_rel r ON r.invoice_line_id = il.id
                          JOIN sale_order_line sol ON sol.id = r.order_line_id
                          JOIN sale_order so ON so.id = sol.order_id
                         WHERE il.move_id = am.id),
                       rp.commercial_partner_id, am.name,
                       NULL, NULL, NULL, NULL,
                       0.0, aml.amount_residual, COALESCE(am.invoice_date, am.date),
                       NULL, NULL, aml.id
                  FROM account_move_line aml
                  JOIN account_account aa ON aa.id = aml.account_id
                  JOIN account_move am ON am.id = aml.move_id
                  JOIN res_partner rp ON rp.id = aml.partner_id
                 WHERE aa.account_type = 'asset_receivable'
                   AND aml.parent_state = 'posted'
                   AND NOT aml.reconciled
                   AND aml.amount_residual <> 0
            )
            SELECT r.id, r.tipo, r.company_id, co.currency_id AS moneda_id, r.cliente_id,
                   -- Zona: la de la orden; si no tiene (o es un saldo sin orden), la del
                   -- cliente si tiene una sola; si no, ninguna (como duran.captura.get_acomodo).
                   COALESCE(r.zona_id, (
                       SELECT MIN(z.category_id) FROM res_partner_res_partner_category_rel z
                        WHERE z.partner_id = r.cliente_id HAVING COUNT(*) = 1
                   )) AS zona_id,
                   r.pedido, r.product_id, COALESCE(pt.es_peso_variable, FALSE) AS es_peso_variable,
                   r.cantidad, r.unidad_producto_id, r.peso_real,
                   r.pendiente_hoy, r.saldo_anterior, r.pendiente_hoy + r.saldo_anterior AS total,
                   r.fecha,
                   CASE WHEN r.tipo = 'saldo' THEN p.hoy - r.fecha END AS dias_antiguedad,
                   (r.tipo = 'saldo' AND p.hoy - r.fecha > %(umbral)s) AS vencido,
                   CASE WHEN r.tipo = 'hoy' THEN '0 ' || COALESCE(r.pedido, '')
                        ELSE '1 ' || TO_CHAR(r.fecha, 'YYYY-MM-DD') || ' ' || COALESCE(r.pedido, '')
                   END AS orden_clave,
                   r.stock_move_id, r.sale_line_id, r.move_line_id
              FROM renglones r
              JOIN res_company co ON co.id = r.company_id
              LEFT JOIN product_product pp ON pp.id = r.product_id
              LEFT JOIN product_template pt ON pt.id = pp.product_tmpl_id
             CROSS JOIN parametros p
            """,
            tz=tz, umbral=DIAS_SALDO_VENCIDO,
        )
