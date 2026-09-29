""" Pendiente de cobro (Ventas › Órdenes › Pendiente de cobro): lo entregado,
un renglón por movimiento, con su importe de venta, por zona y cliente. """
import uuid
from datetime import datetime, time, timedelta

import pytz
from lxml import etree

from odoo import Command, fields
from odoo.exceptions import AccessError
from odoo.tests import HttpCase, tagged
from odoo.tools.safe_eval import safe_eval

from .common import GRUPO_CAPTURA, CapturaDatosPrueba, CapturaHttpMixin

ZONA_HORARIA = "America/Mexico_City"
RUTA_PENDIENTE = "/captura/api/entrega/pendiente"
RUTA_CONFIRMAR = "/captura/api/entrega/confirmar"
COLUMNAS = [
    "cliente_id", "product_id", "cantidad_entregada", "unidad_producto_id", "peso_real", "importe_entregado", "pedido",
]


@tagged("post_install", "-at_install")
class TestPendienteCobro(CapturaDatosPrueba, CapturaHttpMixin, HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._sin_gastar_folios()
        cls._crear_datos_captura()
        env = cls.env
        cls.mama = cls._usuario("pendiente_cobro_mama", GRUPO_CAPTURA)
        cls.papa = cls._usuario("pendiente_cobro_papa", "sales_team.group_sale_manager")
        cls.admin = cls._usuario("pendiente_cobro_admin", "base.group_system,sales_team.group_sale_manager")
        cls.vendedor = cls._usuario("pendiente_cobro_vendedor", "sales_team.group_sale_salesman")
        (cls.mama | cls.papa | cls.admin).tz = ZONA_HORARIA
        cls.accion = env.ref("duran_captura_tianguis.pendiente_cobro_action")
        cls.menu = env.ref("duran_captura_tianguis.pendiente_cobro_menu")
        sin_impuestos = {"taxes_id": [Command.clear()]}
        cls.pieza = cls._plantilla("Pieza pendiente cobro", list_price=10.0, **sin_impuestos).product_variant_id
        cls.kilo = cls._plantilla(
            "Kilo pendiente cobro", uom_id=env.ref("uom.product_uom_kgm").id, **sin_impuestos,
        ).product_variant_id
        cls.rollo = cls._plantilla(
            "Rollo pendiente cobro", es_peso_variable=True, precio_por_kg=80.0, **sin_impuestos,
        ).product_variant_id
        cls.zona_b = env["res.partner.category"].create({"name": "Zona prueba pendiente B"})
        cls.cliente_b = cls._cliente("Cliente prueba pendiente B", cls.zona_b)

    # === Ayudantes === #

    def _entregada(self, lineas, cliente=None, zona=None, pesos=(), **vals):
        """ Orden confirmada y entregada completa. `zona=False`: sin zona. Los
        rollos toman los `pesos` en orden. """
        cliente = cliente or self.cliente
        zona = self.zona_con_clientes if zona is None else zona
        orden = self._confirmada(cliente, lineas, zona_id=zona.id if zona else False, **vals)
        rollos = orden.picking_ids.move_ids.filtered("es_peso_variable").sorted("id")
        for movimiento, peso in zip(rollos, pesos):
            movimiento.peso_real = peso
        self._validar(orden.picking_ids)
        return orden

    def _movimientos(self, orden):
        return orden.picking_ids.move_ids.filtered(lambda m: m.state == "done").sorted("id")

    def _a_utc(self, dia, hora, minuto):
        local = pytz.timezone(ZONA_HORARIA).localize(datetime.combine(dia, time(hora, minuto)))
        return local.astimezone(pytz.utc).replace(tzinfo=None)

    def _hoy_mexico(self):
        return fields.Date.context_today(self.env["res.partner"].with_context(tz=ZONA_HORARIA))

    def _filtro(self, nombre):
        arch = etree.fromstring(self.env["stock.move"].get_views(
            [(self.accion.search_view_id.id, "search")],
        )["views"]["search"]["arch"])
        return safe_eval(arch.xpath(f"//filter[@name='{nombre}']/@domain")[0])

    def _dominio(self, filtro="hoy"):
        return safe_eval(self.accion.domain) + (self._filtro(filtro) if filtro else [])

    def _clientes_prueba(self):
        return self.cliente | self.cliente_b

    def _renglones(self, filtro="hoy"):
        """ Movimientos que muestra el reporte con `filtro`, solo de los
        clientes de la prueba (la base puede tener entregas reales). """
        return self.env["stock.move"].with_user(self.papa).with_context(tz=ZONA_HORARIA).search(
            self._dominio(filtro) + [("cliente_id", "in", self._clientes_prueba().ids)],
        )

    def _grupos(self, agrupar, filtro="hoy"):
        grupos = self.env["stock.move"].with_user(self.papa).with_context(tz=ZONA_HORARIA).formatted_read_group(
            self._dominio(filtro) + [("cliente_id", "in", self._clientes_prueba().ids)],
            list(agrupar), ["importe_entregado:sum", "__count"],
        )
        return {
            tuple(g[a][0] if isinstance(g[a], (list, tuple)) else g[a] for a in agrupar): g["importe_entregado:sum"]
            for g in grupos
        }

    # === Qué entra === #

    def test_solo_lo_entregado_hoy(self):
        hoy = self._hoy_mexico()
        entregada = self._entregada([(self.pieza, 2, 10.0)])
        # Pendiente (sin validar) y orden cancelada: no entran.
        self._confirmada(self.cliente, [(self.pieza, 5, 10.0)], zona_id=self.zona_con_clientes.id)
        cancelada = self._confirmada(self.cliente, [(self.pieza, 4, 10.0)], zona_id=self.zona_con_clientes.id)
        cancelada._action_cancel()
        # Parcial sin backorder: entra lo entregado (2), no lo cancelado (3).
        parcial = self._confirmada(self.cliente, [(self.pieza, 5, 10.0)], zona_id=self.zona_con_clientes.id)
        parcial.picking_ids.move_ids.write({"quantity": 2, "picked": True})
        parcial.picking_ids.with_context(cancel_backorder=True)._action_done()
        # Devolución validada de lo entregado hoy: no entra (no es neto).
        asistente = self.env["stock.return.picking"].with_context(
            active_id=entregada.picking_ids.id, active_model="stock.picking",
        ).create({})
        asistente.product_return_moves.quantity = 1
        self._validar(asistente._create_return())
        # Entregado ayer.
        ayer = self._entregada([(self.pieza, 7, 10.0)])
        self._movimientos(ayer).date = self._a_utc(hoy - timedelta(days=1), 12, 0)

        renglones = self._renglones()
        self.assertEqual(
            sorted((m.sale_line_id.order_id, m.cantidad_entregada, m.importe_entregado) for m in renglones),
            sorted([(entregada, 2.0, 20.0), (parcial, 2.0, 20.0)]),
        )
        self.assertIn(self._movimientos(ayer), self._renglones("ultimos_7_dias"))
        self.assertTrue(all(m.state == "done" and m.location_dest_usage == "customer" for m in renglones))

    def test_hoy_cerca_de_medianoche_en_mexico(self):
        """ "Hoy" es el día en México, no en UTC: las 23:30 de hoy en México ya
        son mañana en UTC, y las 23:30 de ayer ya son hoy en UTC. """
        hoy = self._hoy_mexico()
        noche = self._entregada([(self.pieza, 1, 10.0)])
        madrugada = self._entregada([(self.pieza, 2, 10.0)])
        anoche = self._entregada([(self.pieza, 3, 10.0)])
        self._movimientos(noche).date = self._a_utc(hoy, 23, 30)
        self._movimientos(madrugada).date = self._a_utc(hoy, 0, 10)
        self._movimientos(anoche).date = self._a_utc(hoy - timedelta(days=1), 23, 30)
        self.env.flush_all()
        self.assertEqual(self._movimientos(noche).date.date(), hoy + timedelta(days=1), "en UTC ya es mañana")
        self.assertEqual(self._movimientos(anoche).date.date(), hoy, "en UTC ya es hoy")
        self.assertEqual(
            sorted(self._renglones().sale_line_id.order_id.ids), sorted((noche | madrugada).ids),
        )

    def test_varias_ordenes_del_mismo_cliente_el_mismo_dia(self):
        primera = self._entregada([(self.pieza, 2, 10.0)])
        segunda = self._entregada([(self.pieza, 1, 15.0)])
        self.assertEqual(
            [(m.pedido, m.importe_entregado) for m in self._renglones().sorted(lambda m: (m.pedido, m.id))],
            sorted([(primera.name, 20.0), (segunda.name, 15.0)]),
        )
        self.assertEqual(self._grupos(("cliente_id",)), {(self.cliente.id,): 35.0})

    # === Importe === #

    def test_importe_rollo_producto_normal_y_descuento(self):
        normal = self._entregada([(self.pieza, 3, 10.0)])
        con_descuento = self._entregada([(self.pieza, 3, 10.0)])
        rollo = self._entregada([(self.rollo, 1)], pesos=[1.25])
        rollo_descuento = self._entregada([(self.rollo, 1)], pesos=[1.25])
        for orden in (con_descuento, rollo_descuento):
            orden.order_line.discount = 10.0
        gramos = self.env.ref("uom.product_uom_gram")
        self.kilo.product_tmpl_id.uom_ids = [Command.link(gramos.id)]
        en_gramos = self._confirmada(self.cliente, [], zona_id=self.zona_con_clientes.id)
        en_gramos.order_line = [Command.create({
            "product_id": self.kilo.id, "product_uom_qty": 500, "product_uom_id": gramos.id, "price_unit": 0.1,
        })]
        self._validar(en_gramos.picking_ids)

        casos = {
            "normal": (normal, 3.0, None, 30.0),
            "normal con descuento": (con_descuento, 3.0, None, 27.0),
            "rollo": (rollo, 1.0, 1.25, 100.0),
            "rollo con descuento": (rollo_descuento, 1.0, 1.25, 90.0),
            "vendido en gramos": (en_gramos, 0.5, None, 50.0),
        }
        for nombre, (orden, cantidad, peso, importe) in casos.items():
            with self.subTest(caso=nombre):
                movimiento = self._movimientos(orden)
                self.assertEqual(movimiento.cantidad_entregada, cantidad)
                self.assertEqual(movimiento.peso_real if peso else None, peso)
                self.assertEqual(movimiento.importe_entregado, importe)
                self.assertEqual(movimiento.unidad_producto_id, movimiento.product_id.uom_id)
        # Coincide con lo que factura Odoo.
        for orden in (normal, con_descuento, rollo, rollo_descuento):
            with self.subTest(factura=orden.name):
                self.assertEqual(orden._create_invoices().amount_untaxed, self._movimientos(orden).importe_entregado)

    def test_importe_se_recalcula_si_cambia_precio_o_descuento(self):
        orden = self._entregada([(self.pieza, 2, 10.0)])
        movimiento = self._movimientos(orden)
        self.assertEqual(movimiento.importe_entregado, 20.0)
        orden.order_line.price_unit = 12.5
        self.assertEqual(movimiento.importe_entregado, 25.0)
        orden.order_line.discount = 20.0
        self.assertEqual(movimiento.importe_entregado, 20.0)

    def test_entrega_desde_la_app_con_usuario_de_captura(self):
        """ La mamá (solo grupo Captura) entrega desde la app: el importe se
        calcula aunque ella no pueda leerlo. """
        orden = self._confirmada(self.cliente, [(self.pieza, 3, 10.0)], zona_id=self.zona_con_clientes.id)
        self._entrar(self.mama)
        pendiente = self._resultado(RUTA_PENDIENTE, {"cliente_id": self.cliente.id, "zona_id": self.zona_con_clientes.id})
        self._resultado(RUTA_CONFIRMAR, {
            "cliente_id": self.cliente.id, "zona_id": self.zona_con_clientes.id, "rollos": [],
            "productos": [{"producto_id": self.pieza.id, "cantidad": 2}],
            "movimientos_vistos": [m["move_id"] for p in pendiente["productos"] for m in p["movimientos"]],
            "token": uuid.uuid4().hex,
        })
        movimiento = self._movimientos(orden)
        self.assertEqual((movimiento.cantidad_entregada, movimiento.importe_entregado), (2.0, 20.0))
        self.assertIn(movimiento, self._renglones())

    # === Totales === #

    def test_totales_por_grupo_y_global(self):
        self._entregada([(self.pieza, 2, 10.0)])
        self._entregada([(self.pieza, 1, 5.0)])
        self._entregada([(self.pieza, 3, 10.0)], cliente=self.cliente_b, zona=self.zona_b)
        self._entregada([(self.pieza, 4, 10.0)], zona=False)
        self.assertEqual(self._grupos(("zona_id", "cliente_id")), {
            (self.zona_con_clientes.id, self.cliente.id): 25.0,
            (self.zona_b.id, self.cliente_b.id): 30.0,
            (False, self.cliente.id): 40.0,
        })
        self.assertEqual(self._grupos(("zona_id",)), {
            (self.zona_con_clientes.id,): 25.0, (self.zona_b.id,): 30.0, (False,): 40.0,
        })
        self.assertEqual(sum(self._renglones().mapped("importe_entregado")), 95.0)

    # === Vista, acción, menú y permisos === #

    def test_lista_buscador_y_orden(self):
        arch = etree.fromstring(self.env["stock.move"].with_user(self.papa).get_views(
            [(self.accion.view_id.id, "list")],
        )["views"]["list"]["arch"])
        visibles = [c.get("name") for c in arch.xpath("//field") if not c.get("column_invisible")]
        self.assertEqual(visibles, COLUMNAS)
        self.assertEqual(arch.xpath("//field[@name='importe_entregado']/@sum"), ["Total"])
        self.assertEqual(
            {c: arch.xpath(f"//field[@name='{c}']/@optional") for c in ("peso_real", "pedido")},
            {"peso_real": ["show"], "pedido": ["show"]},
        )
        self.assertEqual(arch.get("default_order"), "pedido, id")
        # En los grupos no se suma la Cantidad (mezclaría kg con piezas); el Peso sí.
        agregados = self.env["stock.move"].fields_get(["cantidad_entregada", "peso_real"], ["aggregator"])
        self.assertEqual(
            {c: agregados[c].get("aggregator") for c in agregados}, {"cantidad_entregada": None, "peso_real": "sum"},
        )
        contexto = safe_eval(self.accion.context)
        self.assertEqual(
            {k: v for k, v in contexto.items() if k.startswith("search_default_")},
            {"search_default_hoy": 1, "search_default_agrupar_zona": 1, "search_default_agrupar_cliente": 2},
        )
        busqueda = etree.fromstring(self.env["stock.move"].get_views(
            [(self.accion.search_view_id.id, "search")],
        )["views"]["search"]["arch"])
        self.assertEqual(
            [f.get("name") for f in busqueda.xpath("/search/field")], ["cliente_id", "product_id", "zona_id", "pedido"],
        )
        self.assertEqual(
            {f.get("name"): safe_eval(f.get("context"))["group_by"] for f in busqueda.xpath("//group/filter")},
            {"agrupar_zona": "zona_id", "agrupar_cliente": "cliente_id", "agrupar_dia": "date:day"},
        )
        self.assertEqual(self._filtro("hoy"), [("date", ">=", "today"), ("date", "<", "today +1d")])

    def test_menu_accion_e_importe_solo_gerente(self):
        Menu = self.env["ir.ui.menu"]
        self.assertEqual(self.menu.parent_id, self.env.ref("sale.sale_order_menu"))
        self.assertEqual(self.accion.group_ids, self.env.ref("sales_team.group_sale_manager"))
        for usuario in (self.papa, self.admin):
            with self.subTest(usuario=usuario.login):
                self.assertIn(self.menu.id, Menu.with_user(usuario)._visible_menu_ids())
        orden = self._entregada([(self.pieza, 1, 10.0)])
        for usuario in (self.mama, self.vendedor):
            with self.subTest(usuario=usuario.login):
                self.assertNotIn(self.menu.id, Menu.with_user(usuario)._visible_menu_ids())
                movimiento = self._movimientos(orden).with_user(usuario)
                with self.assertRaises(AccessError):
                    movimiento.read(["importe_entregado"])
                vista = self.env["stock.move"].with_user(usuario).get_views(
                    [(self.accion.view_id.id, "list")],
                )["views"]["list"]["arch"]
                self.assertNotIn("importe_entregado", vista)
