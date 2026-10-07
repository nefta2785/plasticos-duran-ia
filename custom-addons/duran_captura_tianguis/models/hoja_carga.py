import pytz

from odoo import _, api, fields, models, tools
from odoo.exceptions import ConcurrencyError, UserError
from odoo.tools import SQL, float_compare, float_round, formatLang
from odoo.tools.misc import get_lang

from .captura import ZONA_HORARIA_OPERACION


def _hoy():
    """ Día de calendario en México (las marcas empiezan en blanco cada día). """
    return fields.Datetime.now().replace(tzinfo=pytz.utc).astimezone(pytz.timezone(ZONA_HORARIA_OPERACION)).date()


class DuranHojaCargaMarca(models.Model):
    """ "Acomodado" en la Hoja de carga: lo que había de un producto en una zona
    cuando el papá lo marcó, ese día. Las de otros días no se borran: la hoja
    solo mira las de hoy. """
    _name = "duran.hoja.carga.marca"
    _description = "Marca de acomodado en la hoja de carga"
    _order = "fecha desc, id desc"

    product_id = fields.Many2one("product.product", string="Producto", required=True, readonly=True, ondelete="cascade")
    zona_id = fields.Many2one("res.partner.category", string="Zona", readonly=True, ondelete="cascade")
    fecha = fields.Date(string="Fecha", required=True, readonly=True)
    cantidad = fields.Float(string="Cantidad marcada", digits="Product Unit", required=True, readonly=True)
    user_id = fields.Many2one("res.users", string="Usuario", required=True, readonly=True)

    # "Sin zona" (zona vacía) también es una sola marca por producto y día.
    _marca_unica = models.Constraint(
        "UNIQUE NULLS NOT DISTINCT (product_id, zona_id, fecha)",
        "Ese producto ya tiene una marca en esa zona ese día.",
    )


class DuranHojaCarga(models.Model):
    """ Hoja de carga (Ventas › Órdenes › Hoja de carga): vista SQL de solo
    lectura con un renglón por producto y zona y el total pendiente de
    entregar, con la marca de "Acomodado" de hoy.

    Pendiente = misma regla que el modo Entrega (duran.captura,
    `_entregas_pendientes`): entregas de venta a cliente, que no son
    devoluciones, en movimientos sin validar ni cancelar (incluye los "sin
    existencia" y los parcialmente disponibles). Sin filtro de día: también
    sale lo atrasado. El total es `product_qty`, en la unidad del producto (un
    rollo = 1). """
    _name = "duran.hoja.carga"
    _description = "Hoja de carga"
    _auto = False
    _order = "zona_id, product_id"
    _rec_name = "product_id"

    zona_id = fields.Many2one("res.partner.category", string="Zona", readonly=True)
    product_id = fields.Many2one("product.product", string="Producto", readonly=True)
    # Sin suma en los grupos: mezclaría kg con piezas.
    total = fields.Float(string="Total", digits="Product Unit", readonly=True, aggregator=None)
    unidad_producto_id = fields.Many2one("uom.uom", string="Unidad", readonly=True)
    cantidad_marcada = fields.Float(string="Cantidad marcada", digits="Product Unit", readonly=True, aggregator=None)
    estado = fields.Selection(
        [("sin_marcar", "Sin marcar"), ("acomodado", "Acomodado"), ("agregado", "Se agregó")],
        string="Estado", readonly=True,
    )
    # En Python y no en el SQL: los números van con el separador decimal del
    # idioma de quien consulta (es_419: "2,5"), igual que la columna Total.
    aviso = fields.Char(string="Aviso", compute="_compute_aviso")
    # Total y unidad en una columna ("4 pz", "2,5 kg"), para que la lista
    # quepa en el celular.
    cantidad_texto = fields.Char(string="Cantidad", compute="_compute_cantidad_texto")

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(SQL("CREATE VIEW %s AS (%s)", SQL.identifier(self._table), self._consulta()))

    def _consulta(self):
        return SQL(
            """
            WITH parametros AS (
                SELECT (now() AT TIME ZONE %(tz)s)::date AS hoy,
                       (SELECT digits FROM decimal_precision WHERE name = 'Product Unit') AS digitos
            ),
            pendiente AS (
                -- Zona: la de la orden; si no tiene, la del cliente si tiene una sola;
                -- si no, ninguna (como duran.captura.get_acomodo y el Pendiente de cobro).
                SELECT sm.product_id, sm.product_qty,
                       COALESCE(so.zona_id, (
                           SELECT MIN(z.category_id) FROM res_partner_res_partner_category_rel z
                            WHERE z.partner_id = rp.commercial_partner_id HAVING COUNT(*) = 1
                       )) AS zona_id
                  FROM stock_move sm
                  JOIN stock_picking sp ON sp.id = sm.picking_id
                  JOIN stock_picking_type spt ON spt.id = sp.picking_type_id
                  JOIN stock_location sl ON sl.id = sm.location_dest_id
                  JOIN sale_order so ON so.id = sp.sale_id
                  JOIN res_partner rp ON rp.id = so.partner_id
                 WHERE spt.code = 'outgoing'
                   AND sl.usage = 'customer'
                   AND sp.return_id IS NULL
                   AND sm.state NOT IN ('draft', 'done', 'cancel')
            ),
            totales AS (
                SELECT p.product_id, p.zona_id, ROUND(SUM(p.product_qty)::numeric, par.digitos) AS total
                  FROM pendiente p CROSS JOIN parametros par
                 GROUP BY p.product_id, p.zona_id, par.digitos
                HAVING ROUND(SUM(p.product_qty)::numeric, par.digitos) > 0
            )
            SELECT t.product_id::bigint * 1000000 + COALESCE(t.zona_id, 0) AS id,
                   t.zona_id, t.product_id, t.total, pt.uom_id AS unidad_producto_id,
                   m.cantidad AS cantidad_marcada,
                   -- Verde si lo marcado alcanza para lo pendiente (total igual o menor);
                   -- naranja solo si el total pasó de lo marcado. Limitación: si el total
                   -- baja (por entregas) y luego vuelve a subir sin pasar de lo marcado,
                   -- sigue verde aunque el carrito ya tenga menos de lo que se marcó.
                   CASE WHEN m.id IS NULL THEN 'sin_marcar'
                        WHEN t.total > ROUND(m.cantidad::numeric, par.digitos) THEN 'agregado'
                        ELSE 'acomodado'
                   END AS estado
              FROM totales t
              JOIN product_product pp ON pp.id = t.product_id
              JOIN product_template pt ON pt.id = pp.product_tmpl_id
             CROSS JOIN parametros par
              LEFT JOIN duran_hoja_carga_marca m
                     ON m.product_id = t.product_id
                    AND m.zona_id IS NOT DISTINCT FROM t.zona_id
                    AND m.fecha = par.hoy
            """,
            tz=ZONA_HORARIA_OPERACION,
        )

    @api.depends("estado", "total", "cantidad_marcada")
    def _compute_aviso(self):
        for renglon in self:
            if renglon.estado == "acomodado":
                renglon.aviso = _("Acomodado")
            elif renglon.estado == "agregado":
                diferencia = renglon._redondear(renglon.total - renglon.cantidad_marcada)
                if diferencia == 1:
                    renglon.aviso = _("Se agregó 1")
                else:
                    renglon.aviso = _("Se agregaron %(cantidad)s", cantidad=renglon._numero(diferencia))
            else:
                renglon.aviso = False

    @api.depends("total", "unidad_producto_id")
    def _compute_cantidad_texto(self):
        pieza = self.env.ref("uom.product_uom_unit", raise_if_not_found=False)
        for renglon in self:
            # "Unidades" ocupa mucho en el celular: las piezas van como "pz".
            unidad = _("pz") if renglon.unidad_producto_id == pieza else renglon.unidad_producto_id.name
            renglon.cantidad_texto = f"{renglon._numero(renglon.total)} {unidad}".strip()

    def _redondear(self, cantidad):
        return float_round(cantidad, precision_digits=self.env["decimal.precision"].precision_get("Product Unit"))

    def _numero(self, cantidad):
        """ La cantidad con el separador del idioma y sin ceros sobrantes
        (4 -> "4"; 2.50 -> "2,5" en es_419). """
        digitos = self.env["decimal.precision"].precision_get("Product Unit")
        texto = formatLang(self.env, self._redondear(cantidad), digits=digitos, grouping=False)
        punto = get_lang(self.env).decimal_point  # el mismo idioma que usa formatLang
        if punto in texto:
            texto = texto.rstrip("0").rstrip(punto)
        return texto

    def action_acomodado(self):
        """ Marca el renglón con la cantidad que se veía en pantalla
        (`cantidad_vista` en el contexto del botón), no con la de este momento:
        si entró un pedido mientras el papá miraba, al recargar sale "Se agregó".
        Tocar dos veces deja la misma marca. """
        self.ensure_one()
        self.check_access("read")
        cantidad = self.env.context.get("cantidad_vista")
        if isinstance(cantidad, bool) or not isinstance(cantidad, (int, float)) or cantidad <= 0:
            raise UserError(_("No se pudo leer la cantidad del renglón. Recarga la página."))
        hoy = _hoy()
        self._bloquear(hoy)
        Marca = self.env["duran.hoja.carga.marca"]
        marca = self._marca(hoy)
        valores = {"cantidad": cantidad, "user_id": self.env.uid}
        if marca:
            if float_compare(marca.cantidad, cantidad, precision_digits=6) != 0 or marca.user_id != self.env.user:
                marca.write(valores)
        else:
            Marca.create({**valores, "product_id": self.product_id.id, "zona_id": self.zona_id.id, "fecha": hoy})
        return True

    def action_quitar(self):
        """ Quita la marca de hoy del renglón. Tocar dos veces da lo mismo. """
        self.ensure_one()
        self.check_access("read")
        hoy = _hoy()
        self._bloquear(hoy)
        self._marca(hoy).unlink()
        return True

    def _marca(self, hoy):
        return self.env["duran.hoja.carga.marca"].search([
            ("product_id", "=", self.product_id.id), ("zona_id", "=", self.zona_id.id), ("fecha", "=", hoy),
        ])

    def _bloquear(self, hoy):
        """ Dos personas tocando el mismo renglón a la vez: la segunda petición
        se repite desde cero (`ConcurrencyError`, ver
        `odoo.service.model.retrying`) y ya ve la marca de la primera. """
        clave = f"duran_captura_tianguis.hoja_carga:{self.product_id.id}:{self.zona_id.id or 0}:{hoy}"
        self.env.cr.execute("SELECT pg_try_advisory_xact_lock(hashtext(%s))", [clave])
        if not self.env.cr.fetchone()[0]:
            raise ConcurrencyError(_("Alguien más está marcando este producto."))
