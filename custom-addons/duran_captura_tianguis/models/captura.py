from odoo import _, api, models
from odoo.exceptions import UserError
from odoo.tools import format_amount


class DuranCaptura(models.AbstractModel):
    """ Datos de solo lectura para la pantalla /captura. Todo se lee con los
    permisos del usuario que captura (sin sudo). """
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
        """ Variantes activas y vendibles agrupadas por categoría. Se excluyen
        las de peso variable sin precio por kg, porque se venderían en $0. """
        productos = self.env["product.product"].search([
            ("sale_ok", "=", True),
            ("product_tmpl_id.active", "=", True),
            "|", ("es_peso_variable", "=", False), ("precio_por_kg", ">", 0),
        ])
        productos = productos.sorted(
            lambda p: (p.categ_id.complete_name or "", p.name.lower(), p.id)
        )
        currency = self.env.company.currency_id
        categorias = {}
        for producto in productos:
            categoria = categorias.setdefault(producto.categ_id.id, {
                "id": producto.categ_id.id,
                "nombre": producto.categ_id.complete_name,
                "productos": [],
            })
            categoria["productos"].append(self._get_producto_vals(producto, currency))
        return list(categorias.values())

    @api.model
    def _get_producto_vals(self, producto, currency):
        if producto.es_peso_variable:
            precio = producto.precio_por_kg
            unidad_precio = "kg"
        else:
            precio = producto.lst_price
            unidad_precio = producto.uom_id.name
        variante = producto.product_template_attribute_value_ids._get_combination_name()
        return {
            "id": producto.id,
            "nombre": f"{producto.name} {variante}" if variante else producto.name,
            "uom": producto.uom_id.name,
            "es_peso_variable": producto.es_peso_variable,
            "precio": precio,
            "precio_texto": "%s/%s" % (
                format_amount(self.env, precio, currency, trailing_zeroes=False),
                unidad_precio,
            ),
        }
