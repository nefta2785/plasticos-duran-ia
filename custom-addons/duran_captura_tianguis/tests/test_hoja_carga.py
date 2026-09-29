""" Hoja de carga (Ventas › Órdenes › Hoja de carga): lo pendiente de entregar
por producto, con la zona y la fecha del pedido guardadas en el movimiento. """
import uuid
from datetime import datetime, time, timedelta

import pytz
from lxml import etree

from odoo import Command, fields
from odoo.tests import HttpCase, tagged
from odoo.tools.safe_eval import safe_eval

from .common import GRUPO_CAPTURA, CapturaDatosPrueba, CapturaHttpMixin

ZONA_HORARIA = "America/Mexico_City"
RUTA_PENDIENTE = "/captura/api/entrega/pendiente"
RUTA_CONFIRMAR = "/captura/api/entrega/confirmar"


@tagged("post_install", "-at_install")
class TestHojaCarga(CapturaDatosPrueba, CapturaHttpMixin, HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._sin_gastar_folios()
        cls._crear_datos_captura()
        env = cls.env
        cls.mama = cls._usuario("hoja_carga_mama", GRUPO_CAPTURA)
        cls.papa = cls._usuario("hoja_carga_papa", "sales_team.group_sale_manager")
        cls.admin = cls._usuario("hoja_carga_admin", "base.group_system,sales_team.group_sale_manager")
        cls.vendedor = cls._usuario("hoja_carga_vendedor", "sales_team.group_sale_salesman")
        (cls.mama | cls.papa | cls.admin).tz = ZONA_HORARIA
        cls.almacen = env["stock.warehouse"].search([("company_id", "=", env.company.id)], limit=1)
        cls.accion = env.ref("duran_captura_tianguis.hoja_carga_action")
        cls.menu = env.ref("duran_captura_tianguis.hoja_carga_menu")
        sin_impuestos = {"taxes_id": [Command.clear()]}
        cls.pieza = cls._plantilla("Pieza hoja de carga", **sin_impuestos).product_variant_id
        cls.almacenable = cls._plantilla(
            "Almacenable hoja de carga", is_storable=True, **sin_impuestos,
        ).product_variant_id
        cls.rollo = cls._plantilla(
            "Rollo hoja de carga", es_peso_variable=True, precio_por_kg=80.0, **sin_impuestos,
        ).product_variant_id
        cls.kilo = cls._plantilla(
            "Kilo hoja de carga", uom_id=env.ref("uom.product_uom_kgm").id, **sin_impuestos,
        ).product_variant_id
        cls.zona_b = env["res.partner.category"].create({"name": "Zona prueba hoja B"})
        cls.cliente_b = cls._cliente("Cliente prueba hoja B", cls.zona_b)

    # === Ayudantes === #

    def _producto(self, nombre, **vals):
        return self._plantilla(nombre, taxes_id=[Command.clear()], **vals).product_variant_id

    def _pedido(self, lineas, cliente=None, zona=None, **vals):
        """ Orden confirmada con zona (como las de la app); `zona=False`: sin
        zona, como las creadas desde Odoo. """
        cliente = cliente or self.cliente
        zona = self.zona_con_clientes if zona is None else zona
        return self._confirmada(cliente, lineas, zona_id=zona.id if zona else False, **vals)

    def _filtro(self, nombre):
        arch = etree.fromstring(self.env["stock.move"].get_views(
            [(self.accion.search_view_id.id, "search")],
        )["views"]["search"]["arch"])
        return safe_eval(arch.xpath(f"//filter[@name='{nombre}']/@domain")[0])

    def _hoja(self, filtro=None, agrupar=("product_id",), usuario=None, productos=None):
        """ Lo que muestra la hoja: la acción, con el filtro de búsqueda
        `filtro`, agrupada como en la lista, con la suma de la Demanda. Solo
        los productos de la prueba (la base puede tener pedidos reales). """
        dominio = safe_eval(self.accion.domain) + (self._filtro(filtro) if filtro else [])
        grupos = self.env["stock.move"].with_user(usuario or self.papa).with_context(
            tz=ZONA_HORARIA,
        ).formatted_read_group(dominio, list(agrupar), ["product_qty:sum"])
        ids = (productos or self._productos_prueba()).ids
        resultado = {}
        for grupo in grupos:
            if "product_id" in agrupar and grupo["product_id"][0] not in ids:
                continue
            clave = tuple(grupo[g][0] if isinstance(grupo[g], (list, tuple)) else grupo[g] for g in agrupar)
            resultado[clave[0] if len(clave) == 1 else clave] = grupo["product_qty:sum"]
        return resultado

    def _productos_prueba(self):
        return self.env["product.product"].search([("name", "ilike", "hoja de carga")])

    def _a_utc(self, dia, hora, minuto):
        local = pytz.timezone(ZONA_HORARIA).localize(datetime.combine(dia, time(hora, minuto)))
        return local.astimezone(pytz.utc).replace(tzinfo=None)

    def _hoy_mexico(self):
        return fields.Date.context_today(self.env["res.partner"].with_context(tz=ZONA_HORARIA))

    def _parcial(self, orden, cantidad, backorder):
        picking = orden.picking_ids
        picking.move_ids.write({"quantity": cantidad, "picked": True})
        picking.with_context(cancel_backorder=not backorder)._action_done()
        return picking

    # === Pendiente === #

    def test_pendiente_en_todos_los_casos(self):
        casos = {}
        # Reservado ("Listo"): lo pedido completo.
        casos["listo"] = (self._producto("Listo hoja de carga"), 2, 2.0)
        # Parcial con backorder: lo que falta queda en otra entrega abierta.
        con_backorder = self._producto("Backorder hoja de carga")
        self._parcial(self._pedido([(con_backorder, 5)]), 2, backorder=True)
        casos["con backorder"] = (con_backorder, None, 3.0)
        # Parcial sin backorder: lo demás se canceló.
        sin_backorder = self._producto("Sin backorder hoja de carga")
        orden_sin_backorder = self._pedido([(sin_backorder, 5)])
        self._parcial(orden_sin_backorder, 2, backorder=False)
        casos["sin backorder"] = (sin_backorder, None, None)
        # Devolución (sin validar y validada): no es carga.
        devuelto = self._producto("Devuelto hoja de carga")
        orden_devuelta = self._pedido([(devuelto, 3)])
        self._validar(orden_devuelta.picking_ids)
        asistente = self.env["stock.return.picking"].with_context(
            active_id=orden_devuelta.picking_ids.id, active_model="stock.picking",
        ).create({})
        asistente.product_return_moves.quantity = 1
        asistente._create_return()
        otra_devolucion = self.env["stock.return.picking"].with_context(
            active_id=orden_devuelta.picking_ids.filtered(lambda p: not p.return_id).id, active_model="stock.picking",
        ).create({})
        otra_devolucion.product_return_moves.quantity = 1
        self._validar(otra_devolucion._create_return())
        casos["devolución"] = (devuelto, None, None)
        # Orden cancelada.
        cancelado = self._producto("Cancelado hoja de carga")
        self._pedido([(cancelado, 4)])._action_cancel()
        casos["orden cancelada"] = (cancelado, None, None)
        # Sin existencia en sistema (almacenable sin stock) y parcialmente disponible.
        sin_existencia = self._producto("Sin existencia hoja de carga", is_storable=True)
        casos["sin existencia"] = (sin_existencia, 3, 3.0)
        parcial = self._producto("Parcial disponible hoja de carga", is_storable=True)
        self.env["stock.quant"]._update_available_quantity(parcial, self.almacen.lot_stock_id, 2)
        casos["parcialmente disponible"] = (parcial, 5, 5.0)

        for producto, cantidad, _esperado in casos.values():
            if cantidad:
                self._pedido([(producto, cantidad)])
        estados = {
            nombre: self.env["stock.move"].search([("product_id", "=", producto.id)]).mapped("state")
            for nombre, (producto, _c, _e) in casos.items()
        }
        self.assertEqual(estados["listo"], ["assigned"])
        self.assertEqual(estados["sin existencia"], ["confirmed"])
        self.assertEqual(estados["parcialmente disponible"], ["partially_available"])

        hoja = self._hoja()
        for nombre, (producto, _cantidad, esperado) in casos.items():
            with self.subTest(caso=nombre):
                self.assertEqual(hoja.get(producto.id), esperado)
        # "Pedido menos entregado" daría pendientes que ya no se van a cargar.
        linea = orden_sin_backorder.order_line
        self.assertEqual(linea.product_uom_qty - linea.qty_delivered, 3.0)
        self.assertEqual(orden_devuelta.order_line.qty_delivered, 2.0)

    def test_bajado_por_el_modo_entrega(self):
        """ La mamá entrega 2 de 5 desde la app: lo demás no se carga. """
        producto = self._producto("Entrega app hoja de carga")
        self._pedido([(producto, 5)])
        self.assertEqual(self._hoja().get(producto.id), 5.0)
        self._entrar(self.mama)
        pendiente = self._resultado(RUTA_PENDIENTE, {
            "cliente_id": self.cliente.id, "zona_id": self.zona_con_clientes.id,
        })
        self._resultado(RUTA_CONFIRMAR, {
            "cliente_id": self.cliente.id, "zona_id": self.zona_con_clientes.id, "rollos": [],
            "productos": [{"producto_id": producto.id, "cantidad": 2}],
            "movimientos_vistos": [m["move_id"] for p in pendiente["productos"] for m in p["movimientos"]],
            "token": uuid.uuid4().hex,
        })
        self.assertIsNone(self._hoja().get(producto.id))

    def test_pedido_nuevo_del_modo_pedido_aparece_al_recargar(self):
        producto = self._producto("Pedido app hoja de carga")
        self._pedido([(producto, 1)])
        self.assertEqual(self._hoja().get(producto.id), 1.0)
        self._entrar(self.mama)
        self._enviar([(producto, 4)])
        self.assertEqual(self._hoja().get(producto.id), 5.0)
        movimiento = self.env["stock.move"].search([("product_id", "=", producto.id)], order="id desc", limit=1)
        self.assertEqual(movimiento.zona_id, self.zona_con_clientes)
        self.assertEqual(movimiento.fecha_pedido, movimiento.sale_line_id.order_id.date_order)

    # === Días === #

    def test_hoy_y_dias_anteriores(self):
        """ Por defecto sale todo lo pendiente, también lo atrasado. "Hoy" y
        "Días anteriores" usan la fecha del pedido, no la de la entrega. """
        hoy = self._hoy_mexico()
        de_hoy = self._producto("Hoy hoja de carga")
        atrasado = self._producto("Atrasado hoja de carga")
        reprogramado = self._producto("Reprogramado hoja de carga")
        self._pedido([(de_hoy, 2)])
        orden_atrasada = self._pedido([(atrasado, 3)])
        orden_atrasada.date_order = self._a_utc(hoy - timedelta(days=1), 10, 0)
        # Pedido de ayer con la entrega programada para hoy.
        orden_reprogramada = self._pedido([(reprogramado, 1)])
        orden_reprogramada.date_order = self._a_utc(hoy - timedelta(days=1), 11, 0)
        orden_reprogramada.picking_ids.move_ids.date = fields.Datetime.now()
        self.env.flush_all()

        productos = de_hoy | atrasado | reprogramado
        self.assertEqual(self._hoja(productos=productos), {de_hoy.id: 2.0, atrasado.id: 3.0, reprogramado.id: 1.0})
        self.assertEqual(self._hoja("hoy", productos=productos), {de_hoy.id: 2.0})
        self.assertEqual(self._hoja("dias_anteriores", productos=productos), {atrasado.id: 3.0, reprogramado.id: 1.0})

    def test_hoy_en_zona_horaria_de_mexico(self):
        hoy = self._hoy_mexico()
        noche = self._producto("Noche hoja de carga")
        madrugada = self._producto("Madrugada hoja de carga")
        anoche = self._producto("Anoche hoja de carga")
        for producto, dia, hora, minuto in (
            (noche, hoy, 23, 30), (madrugada, hoy, 0, 10), (anoche, hoy - timedelta(days=1), 23, 30),
        ):
            self._pedido([(producto, 1)]).date_order = self._a_utc(dia, hora, minuto)
        self.env.flush_all()
        productos = noche | madrugada | anoche
        self.assertEqual(self._hoja("hoy", productos=productos), {noche.id: 1.0, madrugada.id: 1.0})
        self.assertEqual(self._hoja("dias_anteriores", productos=productos), {anoche.id: 1.0})
        # En UTC, las 23:30 de hoy en México ya son mañana.
        movimiento = self.env["stock.move"].search([("product_id", "=", noche.id)])
        self.assertEqual(movimiento.fecha_pedido.date(), hoy + timedelta(days=1))

    # === Zona === #

    def test_agrupar_por_zona_incluye_lo_que_no_tiene_zona(self):
        producto = self._producto("Zonas hoja de carga")
        self._pedido([(producto, 2)])
        self._pedido([(producto, 3)], cliente=self.cliente_b, zona=self.zona_b)
        self._pedido([(producto, 4)], zona=False)
        hoja = self._hoja(agrupar=("zona_id", "product_id"), productos=producto)
        self.assertEqual(hoja, {
            (self.zona_con_clientes.id, producto.id): 2.0,
            (self.zona_b.id, producto.id): 3.0,
            (False, producto.id): 4.0,
        })
        self.assertEqual(self._hoja(productos=producto), {producto.id: 9.0}, "todas las zonas, por defecto")

    # === Unidades === #

    def test_unidades(self):
        """ La Demanda se suma en la unidad del producto: 500 g + 2 kg = 2.5 kg.
        Los rollos, en piezas. """
        gramo = self.env.ref("uom.product_uom_gram")
        self.kilo.product_tmpl_id.uom_ids = [Command.link(gramo.id)]
        orden = self._pedido([(self.kilo, 2)])
        orden.order_line = [Command.create({"product_id": self.kilo.id, "product_uom_qty": 500, "product_uom_id": gramo.id})]
        self._pedido([(self.rollo, 3)])
        hoja = self._hoja(productos=self.kilo | self.rollo)
        self.assertAlmostEqual(hoja[self.kilo.id], 2.5)
        self.assertEqual(hoja[self.rollo.id], 3.0)
        movimientos = self.env["stock.move"].search([("product_id", "in", (self.kilo | self.rollo).ids)])
        self.assertEqual(
            {(m.product_id, m.unidad_producto_id) for m in movimientos},
            {(self.kilo, self.env.ref("uom.product_uom_kgm")), (self.rollo, self.env.ref("uom.product_uom_unit"))},
        )

    # === Vista, acción y menú === #

    def test_lista_de_tres_columnas_agrupada_por_producto(self):
        vista = self.env["stock.move"].with_user(self.papa).get_views(
            [(self.accion.view_id.id, "list")],
        )["views"]["list"]["arch"]
        columnas = [
            (c.get("name"), c.get("string")) for c in etree.fromstring(vista).xpath("//field")
            if not c.get("column_invisible") and c.get("optional") != "hide"
        ]
        self.assertEqual(columnas, [("product_id", None), ("product_qty", "Demanda"), ("unidad_producto_id", "Unidad")])
        self.assertEqual(etree.fromstring(vista).xpath("//field[@name='product_qty']/@sum"), ["Total"])
        contexto = safe_eval(self.accion.context)
        self.assertEqual({k for k in contexto if k.startswith("search_default_")}, {"search_default_agrupar_producto"})

    def test_menu_solo_gerente_y_administrador(self):
        Menu = self.env["ir.ui.menu"]
        self.assertEqual(self.menu.parent_id, self.env.ref("sale.sale_order_menu"))
        for usuario in (self.papa, self.admin):
            with self.subTest(usuario=usuario.login):
                self.assertIn(self.menu.id, Menu.with_user(usuario)._visible_menu_ids())
        for usuario in (self.mama, self.vendedor):
            with self.subTest(usuario=usuario.login):
                self.assertNotIn(self.menu.id, Menu.with_user(usuario)._visible_menu_ids())
