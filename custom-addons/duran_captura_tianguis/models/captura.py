import re
from datetime import timedelta

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import format_amount

# "Lo de siempre": órdenes confirmadas de los últimos DIAS_HABITUALES días,
# como máximo MAX_HABITUALES productos.
DIAS_HABITUALES = 90
MAX_HABITUALES = 8

# Token que genera la pantalla para cada pedido: 32 caracteres hexadecimales.
FORMATO_TOKEN = re.compile(r"^[0-9a-f]{32}$")


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
    def enviar_pedido(self, cliente_id, zona_id, lineas, token):
        """ Crea SIEMPRE una orden nueva para el cliente (nunca suma a una
        existente), marcada con la zona desde la que se eligió y con quien
        captura como vendedor, y la confirma.

        :param lineas: [{"producto_id": int, "cantidad": int >= 1}, ...]
        :param token: identificador del pedido generado por la pantalla. Si ya
            hay una orden con ese token (doble toque, reintento tras perder la
            señal), se devuelve esa orden en lugar de crear otra.

        Todo corre en una sola transacción: si algo falla (incluida la
        confirmación), no queda ninguna orden a medias. """
        token = self._validar_token(token)
        ya_enviada = self.env["sale.order"].search([("captura_token", "=", token)], limit=1)
        if ya_enviada:
            return self._resultado_envio(ya_enviada, ya_existia=True)

        zona = self.env["res.partner.category"].browse(int(zona_id)).exists()
        if not zona:
            raise UserError(_("La zona ya no existe."))
        cliente = self.env["res.partner"].browse(int(cliente_id)).exists()
        if not cliente:
            raise UserError(_("El cliente ya no existe."))
        if zona not in cliente.category_id:
            raise UserError(_(
                "%(cliente)s ya no está en la zona %(zona)s.",
                cliente=cliente.name, zona=zona.display_name,
            ))

        cantidades = self._validar_lineas(lineas)
        productos = self.env["product.product"].search(
            self._dominio_productos_vendibles() + [("id", "in", list(cantidades))]
        )
        no_disponibles = self.env["product.product"].browse(
            [producto_id for producto_id in cantidades if producto_id not in productos.ids]
        ).exists()
        if len(productos) != len(cantidades):
            raise UserError(_(
                "Estos productos ya no están a la venta: %(productos)s. "
                "Quítalos del pedido e intenta de nuevo.",
                productos=", ".join(no_disponibles.mapped("display_name")) or _("(borrados)"),
            ))

        orden = self.env["sale.order"].create({
            "partner_id": cliente.id,
            "zona_id": zona.id,
            "user_id": self.env.user.id,
            "captura_token": token,
            "order_line": [
                Command.create({"product_id": producto_id, "product_uom_qty": cantidad})
                for producto_id, cantidad in cantidades.items()
            ],
        })
        orden.action_confirm()
        return self._resultado_envio(orden, ya_existia=False)

    @api.model
    def _validar_token(self, token):
        if not isinstance(token, str) or not FORMATO_TOKEN.match(token):
            raise UserError(_("No se pudo identificar el pedido. Recarga la página e intenta de nuevo."))
        return token

    @api.model
    def _validar_lineas(self, lineas):
        """ Devuelve {producto_id: cantidad} en el orden recibido. Las
        cantidades son siempre enteras y mayores a cero (no se venden medios
        kilos). """
        if not isinstance(lineas, list) or not lineas:
            raise UserError(_("El pedido está vacío."))
        cantidades = {}
        for linea in lineas:
            producto_id = linea.get("producto_id") if isinstance(linea, dict) else None
            cantidad = linea.get("cantidad") if isinstance(linea, dict) else None
            if not self._es_entero(producto_id):
                raise UserError(_("El pedido trae un producto inválido. Recarga la página."))
            if not self._es_entero(cantidad) or cantidad < 1:
                raise UserError(_("Las cantidades deben ser números enteros mayores a cero."))
            cantidades[producto_id] = cantidades.get(producto_id, 0) + cantidad
        return cantidades

    @staticmethod
    def _es_entero(valor):
        # bool es subclase de int en Python: True no es una cantidad válida.
        return isinstance(valor, int) and not isinstance(valor, bool)

    @api.model
    def _resultado_envio(self, orden, ya_existia):
        return {
            "id": orden.id,
            "nombre": orden.name,
            "cliente": orden.partner_id.name,
            "zona": orden.zona_id.display_name,
            "productos": int(sum(orden.order_line.mapped("product_uom_qty"))),
            "ya_existia": ya_existia,
        }

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
