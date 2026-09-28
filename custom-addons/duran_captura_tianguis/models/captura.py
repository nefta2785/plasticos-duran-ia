from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import format_amount

# "Lo de siempre": órdenes confirmadas de los últimos DIAS_HABITUALES días,
# como máximo MAX_HABITUALES productos.
DIAS_HABITUALES = 90
MAX_HABITUALES = 8


class DuranCaptura(models.AbstractModel):
    """ Datos de solo lectura para la pantalla /captura. Todo se lee con los
    permisos del usuario que captura; la única excepción (con sudo) es el
    historial de "Lo de siempre", ver `get_habituales`. """
    _name = "duran.captura"
    _description = "Captura de pedidos en tianguis"

    @api.model
    def get_zonas(self):
        """ Las zonas son las etiquetas de contacto tal cual existen. """
        zonas = self.env["res.partner.category"].search([])
        return [{"id": zona.id, "nombre": zona.display_name} for zona in zonas]

    @api.model
    def get_clientes(self, zona_id):
        """ Clientes que tienen la zona entre sus etiquetas. Una zona sin
        clientes devuelve una lista vacía. """
        zona = self.env["res.partner.category"].browse(int(zona_id)).exists()
        if not zona:
            raise UserError(_("La zona ya no existe."))
        clientes = self.env["res.partner"].search(
            [("category_id", "in", zona.ids)], order="name, id",
        )
        return [{"id": cliente.id, "nombre": cliente.name} for cliente in clientes]

    @api.model
    def get_catalogo(self):
        """ Variantes activas y vendibles agrupadas por categoría. """
        productos = self.env["product.product"].search(self._dominio_productos_vendibles())
        productos = productos.sorted(
            lambda p: (p.categ_id.complete_name or "", p.name.lower(), p.id)
        )
        currency = self.env.company.currency_id
        uom_unidad = self.env.ref("uom.product_uom_unit", raise_if_not_found=False)
        categorias = {}
        for producto in productos:
            categoria = categorias.setdefault(producto.categ_id.id, {
                "id": producto.categ_id.id,
                "nombre": producto.categ_id.complete_name,
                "productos": [],
            })
            categoria["productos"].append(self._get_producto_vals(producto, currency, uom_unidad))
        return list(categorias.values())

    @api.model
    def get_habituales(self, cliente_id):
        """ "Lo de siempre": los productos que más pide el cliente según sus
        órdenes confirmadas de los últimos 90 días, como máximo 8.

        Orden: en cuántas órdenes distintas aparece (frecuencia); a igual
        frecuencia, mayor cantidad total; luego, pedido más reciente.
        Solo se devuelven productos que también están en el catálogo. Sin
        historial devuelve una lista vacía.

        El historial se lee con sudo: con "Ventas: solo sus documentos" el
        usuario solo vería las órdenes donde él es el vendedor, y el historial
        real incluye órdenes de otros vendedores. El sudo se limita a este
        cliente (que el usuario sí puede leer) y solo expone qué productos
        pidió, nunca las órdenes. """
        cliente = self.env["res.partner"].browse(int(cliente_id)).exists()
        if not cliente:
            raise UserError(_("El cliente ya no existe."))
        cliente.check_access("read")

        desde = fields.Datetime.now() - timedelta(days=DIAS_HABITUALES)
        grupos = self.env["sale.order.line"].sudo()._read_group(
            [
                ("order_id.partner_id", "child_of", cliente.id),
                ("state", "=", "sale"),
                ("order_id.date_order", ">=", desde),
                ("display_type", "=", False),
                ("product_id", "!=", False),
            ],
            groupby=["product_id", "order_id"],
            aggregates=["product_uom_qty:sum"],
        )
        historial = {}  # id de producto -> [órdenes, cantidad total, fecha más reciente]
        for producto, orden, cantidad in grupos:
            datos = historial.setdefault(producto.id, [0, 0.0, orden.date_order])
            datos[0] += 1
            datos[1] += cantidad
            datos[2] = max(datos[2], orden.date_order)

        # De vuelta a los permisos del usuario: mismo filtro que el catálogo.
        productos = self.env["product.product"].search(
            self._dominio_productos_vendibles() + [("id", "in", list(historial))]
        )
        productos = productos.sorted(lambda p: (
            -historial[p.id][0], -historial[p.id][1], -historial[p.id][2].timestamp(), p.id,
        ))[:MAX_HABITUALES]
        currency = self.env.company.currency_id
        uom_unidad = self.env.ref("uom.product_uom_unit", raise_if_not_found=False)
        return [self._get_producto_vals(producto, currency, uom_unidad) for producto in productos]

    @api.model
    def _dominio_productos_vendibles(self):
        """ Variantes activas y vendibles. Se excluyen las de peso variable sin
        precio por kg, porque se venderían en $0. """
        return [
            ("sale_ok", "=", True),
            ("product_tmpl_id.active", "=", True),
            "|", ("es_peso_variable", "=", False), ("precio_por_kg", ">", 0),
        ]

    @api.model
    def _get_producto_vals(self, producto, currency, uom_unidad):
        # Las piezas se muestran como "c/u" ("2 c/u", "$325 c/u"); el resto con
        # el nombre de su unidad ("3 kg", "$70/kg").
        es_pieza = producto.uom_id == uom_unidad
        unidad = "c/u" if es_pieza else producto.uom_id.name
        if producto.es_peso_variable:
            precio = producto.precio_por_kg
            sufijo_precio = "/kg"
        else:
            precio = producto.lst_price
            sufijo_precio = " c/u" if es_pieza else f"/{unidad}"
        variante = producto.product_template_attribute_value_ids._get_combination_name()
        return {
            "id": producto.id,
            "nombre": f"{producto.name} {variante}" if variante else producto.name,
            "unidad": unidad,
            "es_peso_variable": producto.es_peso_variable,
            "precio": precio,
            "precio_texto": self._formato_precio(precio, currency) + sufijo_precio,
        }

    @api.model
    def _formato_precio(self, precio, currency):
        """ "$85" en lugar de "$ 85": más corto en la pantalla del celular. """
        texto = format_amount(self.env, precio, currency, trailing_zeroes=False)
        return texto.replace(f"{currency.symbol}\N{NO-BREAK SPACE}", currency.symbol, 1)
