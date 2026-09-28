import re
from collections import defaultdict
from datetime import timedelta

from markupsafe import Markup

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_round, format_amount

# "Lo de siempre": órdenes confirmadas de los últimos DIAS_HABITUALES días,
# como máximo MAX_HABITUALES productos.
DIAS_HABITUALES = 90
MAX_HABITUALES = 8

# Token que genera la pantalla para cada pedido: 32 caracteres hexadecimales.
FORMATO_TOKEN = re.compile(r"^[0-9a-f]{32}$")

# Modo Entrega: el peso de un rollo llega tal cual se tecleó ("1.250", "1,250",
# "1250"), en kg y con máximo 3 decimales. Los límites son parámetros del
# sistema (data/ir_config_parameter.xml).
FORMATO_PESO = re.compile(r"^(\d+)(?:[.,](\d+))?$")
DECIMALES_PESO = 3
PARAMETROS_PESO = {
    "bloqueo_max": "duran_captura_tianguis.peso_bloqueo_max",
    "advertencia_min": "duran_captura_tianguis.peso_advertencia_min",
    "advertencia_max": "duran_captura_tianguis.peso_advertencia_max",
}
# Sin punto decimal y de este valor en adelante, se sugiere que faltó el punto
# ("1250" -> "¿Quisiste decir 1.250 kg?").
PESO_SIN_PUNTO_SOSPECHOSO = 100


class DuranCaptura(models.AbstractModel):
    """ Datos para la pantalla /captura. Todo se lee con los permisos del
    usuario que captura; las únicas excepciones (con sudo) son el historial de
    "Lo de siempre" (ver `get_habituales`), los precios de las líneas de venta
    de las entregas pendientes (ver `get_pendientes_entrega` y
    `_importes_entrega`) y los límites de peso (parámetros del sistema). """
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
        clientes = self._clientes_de_zona(self._zona(zona_id))
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
                # Líneas bajadas a 0 al entregar (el cliente no se lo llevó).
                ("product_uom_qty", ">", 0),
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

        zona = self._zona(zona_id)
        cliente = self._cliente_en_zona(cliente_id, zona)

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

    # === Modo Entrega === #

    @api.model
    def get_clientes_entrega(self, zona_id):
        """ Clientes de la zona (misma regla que `get_clientes`) que tienen al
        menos una entrega de venta pendiente, sin importar el vendedor ni la
        zona de la orden. """
        clientes = self._clientes_de_zona(self._zona(zona_id))
        if not clientes:
            return []
        entregas = self._entregas_pendientes(clientes)
        # Un cliente tiene pendientes si el contacto de alguna entrega es él
        # mismo o uno de sus contactos hijos (p. ej. una dirección de entrega).
        con_pendientes = set()
        for contacto in entregas.partner_id:
            while contacto:
                con_pendientes.add(contacto.id)
                contacto = contacto.parent_id
        return [
            {"id": cliente.id, "nombre": cliente.name}
            for cliente in clientes if cliente.id in con_pendientes
        ]

    @api.model
    def get_pendientes_entrega(self, cliente_id, zona_id):
        """ Todo lo pendiente de entregar al cliente, de todas sus entregas de
        venta pendientes, agrupado por producto. Los productos salen en el orden
        en que aparecen de la orden más antigua (creada primero) a la más nueva.

        Cada producto trae sus movimientos en ese mismo orden: en peso variable
        cada movimiento es un rollo (cantidad 1); en los demás, la cantidad de
        cada orden. `sin_existencia` indica lo que Odoo no tiene reservado.

        Precio: `precio_por_kg` vigente en peso variable; en los demás, el de la
        línea de venta. Esos precios se leen con sudo porque con "Ventas: solo
        sus documentos" el usuario no puede leer líneas de órdenes de otros
        vendedores; el sudo se limita a las líneas de los movimientos que ya se
        filtraron aquí (cliente de la zona, entrega de venta pendiente). """
        cliente = self._cliente_en_zona(cliente_id, self._zona(zona_id))
        movimientos = self._movimientos_pendientes(cliente)
        precio_linea = {linea.id: linea.price_unit for linea in movimientos.sale_line_id.sudo()}

        currency = self.env.company.currency_id
        uom_unidad = self.env.ref("uom.product_uom_unit", raise_if_not_found=False)
        productos = {}
        for movimiento in movimientos:
            producto = movimiento.product_id
            if producto.es_peso_variable:
                precio = producto.precio_por_kg
            else:
                precio = precio_linea.get(movimiento.sale_line_id.id)
            reservada = self._cantidad_reservada(movimiento)
            grupo = productos.setdefault(producto.id, {
                **self._get_producto_vals(producto, currency, uom_unidad),
                "movimientos": [],
            })
            grupo["movimientos"].append({
                "move_id": movimiento.id,
                "cantidad": movimiento.product_uom_qty,
                "reservada": reservada,
                "sin_existencia": movimiento.product_uom.compare(reservada, movimiento.product_uom_qty) < 0,
                "precio": precio,
            })

        resultado = []
        for grupo in productos.values():
            detalle = grupo["movimientos"]
            grupo["cantidad"] = sum(m["cantidad"] for m in detalle)
            grupo["cantidad_reservada"] = sum(m["reservada"] for m in detalle)
            grupo["sin_existencia"] = any(m["sin_existencia"] for m in detalle)
            if not grupo["es_peso_variable"]:
                self._precio_de_lineas(grupo, currency, uom_unidad)
            resultado.append(grupo)
        return {"cliente": {"id": cliente.id, "nombre": cliente.name}, "productos": resultado}

    @api.model
    def get_vista_previa_entrega(self, cliente_id, zona_id, rollos, productos):
        """ Vista previa de lo que se va a entregar al cliente: importe por
        línea, total y revisión del peso de cada rollo. No escribe nada.

        :param rollos: [{"move_id": int, "peso": "1.250"}, ...] el peso tal cual
            se tecleó (punto o coma decimal).
        :param productos: [{"producto_id": int, "cantidad": int >= 1}, ...] para
            los productos que no son de peso variable.

        Datos inválidos (movimientos que no son de este cliente o ya no están
        pendientes, cantidades no enteras o mayores a lo pendiente) lanzan un
        error. Los pesos fuera de límites no: cada rollo trae su `bloqueo`
        (impide confirmar) y sus `advertencias` (piden confirmar), y
        `puede_confirmar` dice si hay algún bloqueo. Con algún bloqueo el total
        va vacío. """
        entrega = self._preparar_entrega(cliente_id, zona_id, rollos, productos)
        puede_confirmar = not any(rollo["bloqueo"] for rollo in entrega["rollos"])
        importes, total = self._importes_entrega(entrega) if puede_confirmar else ({}, None)
        currency = self.env.company.currency_id
        uom_unidad = self.env.ref("uom.product_uom_unit", raise_if_not_found=False)

        def importe(lineas_venta):
            if not puede_confirmar:
                return None
            return currency.round(sum(importes.get(linea.id, 0.0) for linea in lineas_venta))

        return {
            "cliente": {"id": entrega["cliente"].id, "nombre": entrega["cliente"].name},
            "rollos": [
                {
                    "move_id": rollo["move"].id,
                    "producto_id": rollo["move"].product_id.id,
                    "nombre": self._get_producto_vals(rollo["move"].product_id, currency, uom_unidad)["nombre"],
                    "peso": rollo["peso"],
                    "precio": rollo["move"].product_id.precio_por_kg,
                    "importe": importe(rollo["move"].sale_line_id) if not rollo["bloqueo"] else None,
                    "bloqueo": rollo["bloqueo"],
                    "advertencias": rollo["advertencias"],
                    "sugerencia": rollo["sugerencia"],
                }
                for rollo in entrega["rollos"]
            ],
            "productos": [
                {
                    **{
                        clave: valor
                        for clave, valor in self._get_producto_vals(linea["producto"], currency, uom_unidad).items()
                        if clave in ("id", "nombre", "unidad")
                    },
                    "cantidad": linea["cantidad"],
                    "importe": importe(self.env["sale.order.line"].union(
                        *(movimiento.sale_line_id for movimiento, _cantidad in linea["asignacion"])
                    )),
                }
                for linea in entrega["productos"]
            ],
            "total": total,
            "total_texto": self._formato_precio(total, currency, centavos=True) if puede_confirmar else None,
            "puede_confirmar": puede_confirmar,
        }

    @api.model
    def _preparar_entrega(self, cliente_id, zona_id, rollos, productos, movimientos_vistos=None):
        """ Valida lo que se va a entregar (mismas reglas para la vista previa
        y para la confirmación) y lo ordena de la orden más antigua a la más
        nueva. La cantidad de un producto se reparte entre sus movimientos
        pendientes empezando por la orden más antigua.

        Con `movimientos_vistos` (confirmación) solo se consideran los
        movimientos que mostró la pantalla, y se rechaza si desde entonces
        alguno dejó de estar pendiente o si en sus entregas apareció otro. """
        cliente = self._cliente_en_zona(cliente_id, self._zona(zona_id))
        pendientes = self._movimientos_pendientes(cliente)
        if movimientos_vistos is not None:
            pendientes = self._validar_movimientos_vistos(movimientos_vistos, pendientes)
        orden = {movimiento.id: posicion for posicion, movimiento in enumerate(pendientes)}
        limites = self._limites_peso()

        rollos_entregados = []
        for movimiento, texto in self._validar_rollos(rollos, pendientes):
            rollos_entregados.append({"move": movimiento, **self._revisar_peso(texto, limites)})
        rollos_entregados.sort(key=lambda rollo: orden[rollo["move"].id])

        productos_entregados = []
        for producto, cantidad in self._validar_productos(productos, pendientes).items():
            restante = cantidad
            asignacion = []
            for movimiento in pendientes.filtered(lambda m: m.product_id == producto):
                if movimiento.product_uom.compare(restante, 0.0) <= 0:
                    break
                parte = min(restante, movimiento.product_uom_qty)
                asignacion.append((movimiento, parte))
                restante -= parte
            productos_entregados.append({"producto": producto, "cantidad": cantidad, "asignacion": asignacion})
        productos_entregados.sort(key=lambda linea: orden[linea["asignacion"][0][0].id])
        return {
            "cliente": cliente,
            "movimientos": pendientes,
            "rollos": rollos_entregados,
            "productos": productos_entregados,
        }

    @api.model
    def _validar_movimientos_vistos(self, movimientos_vistos, pendientes):
        """ Los movimientos que mostró la pantalla, que deben seguir pendientes
        y ser todos los pendientes de sus entregas. """
        if (
            not isinstance(movimientos_vistos, list)
            or not movimientos_vistos
            or not all(self._es_entero(move_id) for move_id in movimientos_vistos)
        ):
            raise UserError(_("La entrega trae datos inválidos. Recarga la página."))
        vistos = pendientes.filtered(lambda m: m.id in set(movimientos_vistos))
        nuevos = pendientes.filtered(lambda m: m.picking_id in vistos.picking_id) - vistos
        if len(vistos) != len(set(movimientos_vistos)) or nuevos:
            raise UserError(_(
                "Las entregas de este cliente cambiaron desde que se cargaron (alguien más las "
                "validó, canceló o modificó). Regresa y vuelve a abrir al cliente."
            ))
        return vistos

    @api.model
    def confirmar_entrega(self, cliente_id, zona_id, rollos, productos, movimientos_vistos, token):
        """ Confirma la entrega al cliente en una sola transacción: valida sus
        entregas con los pesos y cantidades entregados, cancela lo no entregado
        sin backorder, baja la cantidad pedida de las líneas de venta a lo
        entregado y registra la bitácora. Si algo falla, no queda nada.

        Mismos parámetros que `get_vista_previa_entrega`, más:
        :param movimientos_vistos: ids de TODOS los movimientos que mostró la
            pantalla (ruta de pendientes); solo esas entregas se tocan.
        :param token: identificador de esta entrega generado por la pantalla.
            Si ya hay una entrega registrada con ese token (doble toque,
            reintento sin señal), se devuelve esa en lugar de repetirla. """
        token = self._validar_token(token, _("la entrega"))
        ya_registrada = self.env["duran.captura.entrega"].search([("token", "=", token)], limit=1)
        if ya_registrada:
            return self._resultado_entrega(ya_registrada, ya_existia=True)

        entrega = self._preparar_entrega(cliente_id, zona_id, rollos, productos, movimientos_vistos)
        bloqueados = [rollo for rollo in entrega["rollos"] if rollo["bloqueo"]]
        if bloqueados:
            raise UserError(_(
                "Corrige el peso de estos rollos antes de confirmar: %(rollos)s",
                rollos="; ".join(
                    f"{rollo['move'].product_id.display_name}: {rollo['bloqueo']}" for rollo in bloqueados
                ),
            ))
        importes, total = self._importes_entrega(entrega)

        movimientos = entrega["movimientos"]
        pedida = {movimiento: movimiento.product_uom_qty for movimiento in movimientos}
        sin_existencia = {
            movimiento for movimiento in movimientos
            if movimiento.product_uom.compare(self._cantidad_reservada(movimiento), movimiento.product_uom_qty) < 0
        }
        entregada = defaultdict(float)
        pesos = {}
        for rollo in entrega["rollos"]:
            entregada[rollo["move"]] = rollo["move"].product_uom_qty
            pesos[rollo["move"]] = rollo["peso"]
        for producto in entrega["productos"]:
            for movimiento, cantidad in producto["asignacion"]:
                entregada[movimiento] += cantidad

        # 1) Cantidades: lo no entregado en 0 y sin marcar (se cancela al validar).
        no_entregados = movimientos.filtered(lambda m: m not in entregada)
        no_entregados.write({"quantity": 0, "picked": False})
        for movimiento, cantidad in entregada.items():
            valores = {"quantity": cantidad, "picked": True}
            if movimiento in pesos:
                valores["peso_real"] = pesos[movimiento]
            movimiento.write(valores)

        # 2) Validar sin backorder (como el botón nativo "Sin backorder" del
        #    asistente de backorder, pero sin su actividad), o cancelar la
        #    entrega completa si no se entregó nada de ella.
        entregas = movimientos.picking_id
        for picking in entregas:
            if any(movimiento in entregada for movimiento in movimientos & picking.move_ids):
                picking.with_context(
                    skip_backorder=True, picking_ids_not_to_backorder=picking.ids,
                ).button_validate()
                if picking.state != "done":
                    raise UserError(_("La entrega %(folio)s no se pudo validar.", folio=picking.name))
            else:
                picking.action_cancel()
                if picking.state != "cancel":
                    raise UserError(_("La entrega %(folio)s no se pudo cancelar.", folio=picking.name))
            self._nota_entrega(picking, movimientos & picking.move_ids, pedida, entregada, sin_existencia)

        # 3) La cantidad pedida baja a lo entregado.
        self._bajar_cantidad_pedida(movimientos.sale_line_id)

        # 4) Bitácora.
        registro = self.env["duran.captura.entrega"].create({
            "token": token,
            "partner_id": entrega["cliente"].id,
            "zona_id": int(zona_id),
            "picking_ids": [Command.set(entregas.ids)],
            "total": total,
            "linea_ids": self._lineas_bitacora(entrega, importes, sin_existencia),
        })
        return self._resultado_entrega(registro, ya_existia=False)

    @api.model
    def _cantidad_reservada(self, movimiento):
        return movimiento.quantity if movimiento.state in ("assigned", "partially_available") else 0.0

    @api.model
    def _nota_entrega(self, picking, movimientos, pedida, entregada, sin_existencia):
        """ Nota (sin actividad) en la entrega cuando se entregó menos de lo
        pedido o algo sin existencia en sistema. """
        menos = [m for m in movimientos if m.product_uom.compare(entregada.get(m, 0.0), pedida[m]) < 0]
        sin_stock = [m for m in movimientos if m in sin_existencia and m in entregada]
        if not menos and not sin_stock:
            return
        cuerpo = Markup("<p>%s</p>") % _("Entrega registrada desde la captura del tianguis.")
        if picking.state == "cancel":
            cuerpo += Markup("<p>%s</p>") % _("El cliente no se llevó nada: se canceló la entrega completa.")
        elif menos:
            cuerpo += Markup("<p>%s</p><ul>") % _("Se entregó menos de lo pedido; lo demás se canceló, sin backorder:")
            for movimiento in menos:
                cuerpo += Markup("<li>%s</li>") % _(
                    "%(producto)s: entregado %(entregado)s de %(pedido)s",
                    producto=movimiento.product_id.display_name,
                    entregado=f"{entregada.get(movimiento, 0.0):g}", pedido=f"{pedida[movimiento]:g}",
                )
            cuerpo += Markup("</ul>")
        if sin_stock:
            cuerpo += Markup("<p>%s</p><ul>") % _(
                "Se entregó sin existencia en sistema (el inventario queda en negativo):"
            )
            for movimiento in sin_stock:
                cuerpo += Markup("<li>%s</li>") % _(
                    "%(producto)s: %(cantidad)s",
                    producto=movimiento.product_id.display_name, cantidad=f"{entregada[movimiento]:g}",
                )
            cuerpo += Markup("</ul>")
        picking.message_post(body=cuerpo, subtype_xmlid="mail.mt_note")

    @api.model
    def _bajar_cantidad_pedida(self, lineas):
        """ Baja la cantidad pedida de las líneas de venta a lo entregado,
        cuando ya no les queda nada pendiente. Odoo deja el cambio en el
        historial de la orden ("The ordered quantity has been updated").

        Con sudo porque las órdenes pueden ser de otro vendedor ("Ventas: solo
        sus documentos" no deja escribirlas). El sudo SOLO escribe
        `product_uom_qty` y SOLO en estas líneas, que son las de los
        movimientos que se acaban de validar o cancelar en esta entrega; sudo
        conserva al usuario, así que el mensaje del historial queda a su
        nombre.

        Al cambiar la cantidad Odoo recalcularía el precio y el descuento de
        las líneas cuyo precio no se editó a mano (lista de precios): se
        protegen para que sigan siendo los de la orden, que son los que usó el
        total que se mostró. """
        Linea = self.env["sale.order.line"]
        campos_precio = [
            Linea._fields[campo]
            for campo in ("pricelist_item_id", "price_unit", "technical_price_unit", "discount")
        ]
        por_cantidad = defaultdict(lambda: Linea.sudo())
        for linea in lineas.sudo():
            if linea.move_ids.filtered(lambda m: m.state not in ("done", "cancel")):
                continue  # aún tiene algo pendiente en otra entrega
            if linea.product_uom_id.compare(linea.product_uom_qty, linea.qty_delivered) > 0:
                por_cantidad[linea.qty_delivered] |= linea
        for cantidad, lineas_cantidad in por_cantidad.items():
            with self.env.protecting(campos_precio, lineas_cantidad):
                lineas_cantidad.write({"product_uom_qty": cantidad})

    @api.model
    def _lineas_bitacora(self, entrega, importes, sin_existencia):
        """ Un renglón por rollo y por línea de venta de los demás productos. """
        lineas = []
        for rollo in entrega["rollos"]:
            movimiento = rollo["move"]
            lineas.append(Command.create({
                "product_id": movimiento.product_id.id,
                "sale_line_id": movimiento.sale_line_id.id,
                "move_id": movimiento.id,
                "cantidad": movimiento.product_uom_qty,
                "peso_real": rollo["peso"],
                "precio_unitario": movimiento.precio_por_kg,
                "importe": importes.get(movimiento.sale_line_id.id, 0.0),
                "sin_existencia": movimiento in sin_existencia,
            }))
        for producto in entrega["productos"]:
            por_linea = defaultdict(list)
            for movimiento, cantidad in producto["asignacion"]:
                por_linea[movimiento.sale_line_id].append((movimiento, cantidad))
            for linea, partes in por_linea.items():
                lineas.append(Command.create({
                    "product_id": producto["producto"].id,
                    "sale_line_id": linea.id,
                    "move_id": partes[0][0].id if len(partes) == 1 else False,
                    "cantidad": sum(cantidad for _movimiento, cantidad in partes),
                    "precio_unitario": linea.sudo().price_unit,
                    "importe": importes.get(linea.id, 0.0),
                    "sin_existencia": any(movimiento in sin_existencia for movimiento, _cantidad in partes),
                }))
        return lineas

    @api.model
    def _resultado_entrega(self, registro, ya_existia):
        currency = registro.currency_id
        return {
            "id": registro.id,
            "cliente": registro.partner_id.name,
            "total": registro.total,
            "total_texto": self._formato_precio(registro.total, currency, centavos=True),
            "entregas": [
                {
                    "folio": picking.name,
                    "orden": picking.origin,
                    "estado": "validada" if picking.state == "done" else "cancelada",
                }
                for picking in registro.picking_ids.sorted("id")
            ],
            "ya_existia": ya_existia,
        }

    @api.model
    def _validar_rollos(self, rollos, pendientes):
        """ [(movimiento, peso tecleado), ...]: cada rollo una sola vez, de peso
        variable y pendiente de entregar a este cliente. """
        if not isinstance(rollos, list):
            raise UserError(_("La entrega trae datos inválidos. Recarga la página."))
        resultado = []
        vistos = set()
        for rollo in rollos:
            move_id = rollo.get("move_id") if isinstance(rollo, dict) else None
            if not self._es_entero(move_id) or "peso" not in rollo:
                raise UserError(_("La entrega trae un rollo inválido. Recarga la página."))
            if move_id in vistos:
                raise UserError(_("El mismo rollo viene dos veces en la entrega."))
            vistos.add(move_id)
            movimiento = pendientes.filtered(lambda m: m.id == move_id and m.product_id.es_peso_variable)
            if not movimiento:
                raise UserError(_(
                    "Uno de los rollos ya no está pendiente de entregar a este cliente. "
                    "Recarga la lista e intenta de nuevo."
                ))
            resultado.append((movimiento, rollo["peso"]))
        return resultado

    @api.model
    def _validar_productos(self, productos, pendientes):
        """ {producto: cantidad} de los productos que no son de peso variable:
        cantidades enteras, mayores a cero y sin pasar de lo pendiente. """
        if not isinstance(productos, list):
            raise UserError(_("La entrega trae datos inválidos. Recarga la página."))
        cantidades = {}
        for linea in productos:
            producto_id = linea.get("producto_id") if isinstance(linea, dict) else None
            cantidad = linea.get("cantidad") if isinstance(linea, dict) else None
            if not self._es_entero(producto_id):
                raise UserError(_("La entrega trae un producto inválido. Recarga la página."))
            if not self._es_entero(cantidad) or cantidad < 1:
                raise UserError(_("Las cantidades deben ser números enteros mayores a cero."))
            movimientos = pendientes.filtered(
                lambda m: m.product_id.id == producto_id and not m.product_id.es_peso_variable
            )
            if not movimientos:
                raise UserError(_(
                    "Uno de los productos ya no está pendiente de entregar a este cliente. "
                    "Recarga la lista e intenta de nuevo."
                ))
            producto = movimientos.product_id
            if producto in cantidades:
                raise UserError(_("%(producto)s viene dos veces en la entrega.", producto=producto.display_name))
            pendiente = sum(movimientos.mapped("product_uom_qty"))
            if movimientos[0].product_uom.compare(cantidad, pendiente) > 0:
                raise UserError(_(
                    "De %(producto)s solo hay %(pendiente)s pendientes. Si quiere más, levanta un "
                    "pedido nuevo.",
                    producto=producto.display_name, pendiente=f"{pendiente:g}",
                ))
            cantidades[producto] = cantidad
        return cantidades

    @api.model
    def _limites_peso(self):
        """ Límites de peso en kg, de los parámetros del sistema. Solo el
        administrador puede leer parámetros del sistema, por eso el sudo (solo
        estas tres claves). """
        parametros = self.env["ir.config_parameter"].sudo()
        limites = {}
        for nombre, clave in PARAMETROS_PESO.items():
            try:
                valor = float(parametros.get_param(clave) or "")
            except ValueError:
                valor = 0.0
            if valor <= 0:
                raise UserError(_(
                    "Falta configurar el parámetro del sistema %(clave)s (un número de kg mayor a 0).",
                    clave=clave,
                ))
            limites[nombre] = valor
        return limites

    @api.model
    def _revisar_peso(self, texto, limites):
        """ Revisa el peso tecleado de un rollo. Devuelve el peso en kg (o None
        si no se entiende), el `bloqueo` (texto, o None) y las `advertencias`.
        Si no trae punto decimal y es de 100 o más, se sugiere que faltó el
        punto: `sugerencia` = peso / 1000. """
        revision = {"peso": None, "bloqueo": None, "advertencias": [], "sugerencia": None}
        encontrado = FORMATO_PESO.match(texto.strip()) if isinstance(texto, str) else None
        if not encontrado:
            revision["bloqueo"] = _("Escribe el peso en kg, por ejemplo 1.250.")
            return revision
        enteros, decimales = encontrado.groups()
        if decimales and len(decimales) > DECIMALES_PESO:
            revision["bloqueo"] = _("El peso lleva máximo 3 decimales.")
            return revision
        peso = float_round(float(f"{enteros}.{decimales or 0}"), precision_digits=DECIMALES_PESO)
        revision["peso"] = peso
        if decimales is None and peso >= PESO_SIN_PUNTO_SOSPECHOSO:
            sugerencia = float_round(peso / 1000, precision_digits=DECIMALES_PESO)
            revision["sugerencia"] = sugerencia
            revision["advertencias"].append(_("¿Quisiste decir %(peso)s kg?", peso=f"{sugerencia:.3f}"))
        if peso <= 0:
            revision["bloqueo"] = _("El peso debe ser mayor a 0 kg.")
        elif peso > limites["bloqueo_max"]:
            revision["bloqueo"] = _(
                "Un rollo no puede pesar más de %(maximo)s kg.", maximo=f"{limites['bloqueo_max']:g}",
            )
        elif peso < limites["advertencia_min"]:
            revision["advertencias"].append(_(
                "Pesa menos de %(minimo)s kg: revisa que esté bien.", minimo=f"{limites['advertencia_min']:g}",
            ))
        elif peso > limites["advertencia_max"]:
            revision["advertencias"].append(_(
                "Pesa más de %(maximo)s kg: revisa que esté bien.", maximo=f"{limites['advertencia_max']:g}",
            ))
        return revision

    @api.model
    def _importes_entrega(self, entrega):
        """ ({id de línea de venta: importe}, total) de lo que se entrega,
        calculado como lo hará la factura: una línea de factura por línea de venta (rollo:
        cantidad 1 a peso × precio por kg vigente, que es el que se congela al
        validar; demás productos: la cantidad entregada al precio de su línea
        de venta, con su descuento e impuestos) y el motor de impuestos de Odoo
        con el redondeo de la compañía.

        Las órdenes se agrupan en facturas como lo hace Odoo al facturarlas
        juntas: por las claves de `_get_invoice_grouping_keys` sobre los
        valores de `_prepare_invoice` (que solo lee).

        Igual que en la factura, el importe de cada línea se redondea por
        separado (su subtotal) y el total se redondea una vez por factura; por
        eso la suma de las líneas puede diferir del total por centavos.

        Los precios, descuentos, impuestos y datos de facturación de las líneas
        y órdenes de venta se leen con sudo (pueden ser de otro vendedor); solo
        los de los movimientos que ya pasaron `_preparar_entrega`. """
        cantidades = defaultdict(float)
        precios = {}
        for rollo in entrega["rollos"]:
            linea = rollo["move"].sale_line_id
            cantidades[linea] += rollo["move"].product_uom_qty
            precios[linea] = rollo["peso"] * rollo["move"].product_id.precio_por_kg
        for producto in entrega["productos"]:
            for movimiento, cantidad in producto["asignacion"]:
                cantidades[movimiento.sale_line_id] += cantidad
        AccountTax = self.env["account.tax"]
        claves_factura = self.env["sale.order"]._get_invoice_grouping_keys()
        valores_factura = {}  # orden -> valores de su factura
        facturas = defaultdict(list)
        for linea, cantidad in cantidades.items():
            if not linea:
                continue  # movimiento agregado a mano, sin línea de venta: no se factura
            linea_sudo = linea.sudo()
            orden = linea_sudo.order_id
            datos_linea = dict(
                id=linea.id,
                product_id=linea_sudo.product_id,
                tax_ids=linea_sudo.tax_ids,
                price_unit=precios.get(linea, linea_sudo.price_unit),
                quantity=cantidad,
                discount=linea_sudo.discount,
                currency_id=orden.currency_id,
                partner_id=orden.partner_id,
            )
            if orden not in valores_factura:
                valores_factura[orden] = orden._prepare_invoice()
            facturas[tuple(valores_factura[orden].get(clave) for clave in claves_factura)].append(datos_linea)
        importes = {}
        total = 0.0
        for lineas_factura in facturas.values():
            company = self.env["sale.order.line"].browse(lineas_factura[0]["id"]).sudo().company_id
            currency = lineas_factura[0]["currency_id"]
            for datos_linea in lineas_factura:
                # Como account.move.line._compute_totals: cada línea sola.
                sola = AccountTax._prepare_base_line_for_taxes_computation(None, **datos_linea)
                AccountTax._add_tax_details_in_base_line(sola, company)
                AccountTax._round_base_lines_tax_details([sola], company)
                importes[datos_linea["id"]] = sola["tax_details"]["total_included_currency"]
            # Como account.move._compute_tax_totals: la factura completa.
            base_lines = [
                AccountTax._prepare_base_line_for_taxes_computation(None, **datos_linea)
                for datos_linea in lineas_factura
            ]
            AccountTax._add_tax_details_in_base_lines(base_lines, company)
            AccountTax._round_base_lines_tax_details(base_lines, company)
            total += AccountTax._get_tax_totals_summary(base_lines, currency, company)["total_amount_currency"]
        return importes, self.env.company.currency_id.round(total)

    @api.model
    def _movimientos_pendientes(self, cliente):
        """ Movimientos pendientes de las entregas de venta pendientes del
        cliente, de la orden más antigua (creada primero) a la más nueva. """
        return self._entregas_pendientes(cliente).move_ids.filtered(
            lambda m: m.state not in ("done", "cancel")
            and m.product_uom.compare(m.product_uom_qty, 0.0) > 0
        ).sorted(lambda m: (m.picking_id.sale_id.id, m.sale_line_id.id or 0, m.id))

    @api.model
    def _precio_de_lineas(self, grupo, currency, uom_unidad):
        """ Precio del grupo según sus líneas de venta: si todas tienen el mismo
        precio, ese; si difieren (el precio cambió entre órdenes), `precio` queda
        vacío y el texto muestra cada precio. """
        producto = self.env["product.product"].browse(grupo["id"])
        sufijo = self._sufijo_precio(producto, uom_unidad)
        precios = sorted({m["precio"] for m in grupo["movimientos"] if m["precio"] is not None})
        grupo["precio"] = precios[0] if len(precios) == 1 else None
        grupo["precio_texto"] = " / ".join(self._formato_precio(p, currency) + sufijo for p in precios)

    @api.model
    def _entregas_pendientes(self, clientes):
        """ Entregas de venta pendientes de los clientes (o de sus direcciones):
        de tipo salida, ligadas a una orden de venta, con destino a cliente, que
        no son devoluciones y sin validar ni cancelar. Deja fuera "Devolución a
        proveedor" (destino proveedor, sin orden de venta) y las devoluciones de
        clientes (destino interno, y son devoluciones). """
        return self.env["stock.picking"].search([
            ("partner_id", "child_of", clientes.ids),
            ("picking_type_code", "=", "outgoing"),
            ("location_dest_id.usage", "=", "customer"),
            ("sale_id", "!=", False),
            ("return_id", "=", False),
            ("state", "not in", ("done", "cancel")),
        ])

    # === Validaciones comunes === #

    @api.model
    def _zona(self, zona_id):
        zona = self.env["res.partner.category"].browse(int(zona_id)).exists()
        if not zona:
            raise UserError(_("La zona ya no existe."))
        return zona

    @api.model
    def _clientes_de_zona(self, zona):
        return self.env["res.partner"].search([("category_id", "in", zona.ids)], order="name, id")

    @api.model
    def _cliente_en_zona(self, cliente_id, zona):
        cliente = self.env["res.partner"].browse(int(cliente_id)).exists()
        if not cliente:
            raise UserError(_("El cliente ya no existe."))
        if zona not in cliente.category_id:
            raise UserError(_(
                "%(cliente)s ya no está en la zona %(zona)s.",
                cliente=cliente.name, zona=zona.display_name,
            ))
        return cliente

    @api.model
    def _validar_token(self, token, que=None):
        if not isinstance(token, str) or not FORMATO_TOKEN.match(token):
            raise UserError(_(
                "No se pudo identificar %(que)s. Recarga la página e intenta de nuevo.",
                que=que or _("el pedido"),
            ))
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
        unidad = "c/u" if producto.uom_id == uom_unidad else producto.uom_id.name
        precio = producto.precio_por_kg if producto.es_peso_variable else producto.lst_price
        sufijo_precio = self._sufijo_precio(producto, uom_unidad)
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
    def _sufijo_precio(self, producto, uom_unidad):
        if producto.es_peso_variable:
            return "/kg"
        if producto.uom_id == uom_unidad:
            return " c/u"
        return f"/{producto.uom_id.name}"

    @api.model
    def _formato_precio(self, precio, currency, centavos=False):
        """ "$85" en lugar de "$ 85": más corto en la pantalla del celular. Con
        `centavos`, siempre con sus decimales ("$211.40"), para importes. """
        texto = format_amount(self.env, precio, currency, trailing_zeroes=centavos)
        return texto.replace(f"{currency.symbol}\N{NO-BREAK SPACE}", currency.symbol, 1)
