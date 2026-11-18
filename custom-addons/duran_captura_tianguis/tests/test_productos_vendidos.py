""" Productos vendidos (Ventas › Órdenes › Productos vendidos): vista SQL
`duran.productos.vendidos`, un renglón por producto y día con lo vendido y lo
devuelto, en unidades y kg. Sin importes en pesos. """
from datetime import date, datetime, time, timedelta

import pytz
from lxml import etree

from odoo import Command, fields
from odoo.exceptions import AccessError
from odoo.tests import HttpCase, tagged
from odoo.tools.safe_eval import safe_eval

from ..models.productos_vendidos import DIA_BASE, DIAS_POR_PRODUCTO
from .common import GRUPO_CAPTURA
from .test_cobro_confirmar import CobroDatosPrueba

ZONA_HORARIA = "America/Mexico_City"
COLUMNAS = ["dia", "product_id", "vendido_unidades", "vendido_kg", "devuelto_unidades", "devuelto_kg"]
CANTIDADES = COLUMNAS[2:]


@tagged("post_install", "-at_install")
class TestProductosVendidos(CobroDatosPrueba, HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.papa = cls._usuario("productos_vendidos_papa", "sales_team.group_sale_manager")
        cls.admin = cls._usuario("productos_vendidos_admin", "base.group_system,sales_team.group_sale_manager")
        cls.vendedor = cls._usuario("productos_vendidos_vendedor", "sales_team.group_sale_salesman")
        cls.accion = env.ref("duran_captura_tianguis.productos_vendidos_action")
        cls.menu = env.ref("duran_captura_tianguis.productos_vendidos_menu")
        kg = env.ref("uom.product_uom_kgm").id
        facturable = {"invoice_policy": "delivery", "taxes_id": [Command.clear()]}
        # Unidad kg sin peso variable (como las Bolsas de asa): se vende por pieza.
        cls.bolsa_asa = cls._plantilla("Bolsa asa productos vendidos", uom_id=kg, **facturable).product_variant_id
        # Peso variable con unidad kg (como "Hoja polipapel (KG suelto)"): se trata como rollo.
        cls.rollo_kg = cls._plantilla(
            "Rollo kg productos vendidos", uom_id=kg, es_peso_variable=True, precio_por_kg=70.0, **facturable,
        ).product_variant_id
        cls.almacenable = cls._plantilla(
            "Almacenable productos vendidos", is_storable=True, **facturable,
        ).product_variant_id
        cls.productos = cls.pieza | cls.otra_pieza | cls.rollo | cls.bolsa_asa | cls.rollo_kg | cls.almacenable
        cls.almacen = env["stock.warehouse"].search([("company_id", "=", env.company.id)], limit=1)
        cls.hoy = fields.Date.context_today(env["res.partner"].with_context(tz=ZONA_HORARIA))
        cls.ayer = cls.hoy - timedelta(days=1)

    # === Ayudantes === #

    def _movimientos(self, orden):
        return orden.picking_ids.move_ids.filtered(lambda m: m.state == "done").sorted("id")

    def _a_utc(self, dia, hora, minuto=0):
        local = pytz.timezone(ZONA_HORARIA).localize(datetime.combine(dia, time(hora, minuto)))
        return local.astimezone(pytz.utc).replace(tzinfo=None)

    def _renglones(self, filtro=None):
        """ Renglones que ve el gerente con `filtro`, solo de los productos de
        la prueba (la base puede tener datos reales). """
        self.env.flush_all()
        self.env.invalidate_all()
        dominio = self._filtro(filtro) if filtro else []
        return self.env["duran.productos.vendidos"].with_user(self.papa).search(
            dominio + [("product_id", "in", self.productos.ids)],
        )

    def _filas(self, filtro=None):
        return sorted(
            (r.dia, r.product_id.name, *(round(r[c], 3) for c in CANTIDADES), r.usa_unidades, r.usa_kg)
            for r in self._renglones(filtro)
        )

    def _devolver(self, picking, cantidades):
        """ Devolución con el botón Devolver de Odoo. `cantidades`:
        {movimiento original: (cantidad, peso o None)}. """
        asistente = self.env["stock.return.picking"].with_context(
            active_id=picking.id, active_model="stock.picking",
        ).create({})
        for linea in asistente.product_return_moves:
            linea.quantity = cantidades.get(linea.move_id, (0, None))[0]
        devolucion = asistente._create_return()
        for movimiento in devolucion.move_ids:
            peso = cantidades[movimiento.origin_returned_move_id][1]
            movimiento.write({"quantity": movimiento.product_uom_qty, "picked": True})
            if peso is not None:
                movimiento.peso_real = peso
        devolucion.button_validate()
        self.assertEqual(devolucion.state, "done")
        return devolucion

    def _busqueda(self):
        return etree.fromstring(self.env["duran.productos.vendidos"].get_views(
            [(self.accion.search_view_id.id, "search")],
        )["views"]["search"]["arch"])

    def _filtro(self, nombre):
        return safe_eval(self._busqueda().xpath(f"//filter[@name='{nombre}']/@domain")[0])

    def _transferencia(self, tipo, origen, destino, producto, cantidad):
        picking = self.env["stock.picking"].create({
            "picking_type_id": tipo.id, "location_id": origen.id, "location_dest_id": destino.id,
            "move_ids": [Command.create({
                "product_id": producto.id, "product_uom_qty": cantidad,
                "location_id": origen.id, "location_dest_id": destino.id,
            })],
        })
        picking.action_confirm()
        return self._validar(picking)

    # === Casos === #

    def test_pieza_entregada_hoy(self):
        self._entregada(self.cliente, [(self.pieza, 2, 10.0)])
        self.assertEqual(self._filas(), [(self.hoy, self.pieza.name, 2.0, 0.0, 0.0, 0.0, True, False)])
        self.assertTrue(self._renglones().es_hoy)

    def test_rollos_peso_variable(self):
        """ Cada rollo es 1 unidad; los kg son la suma de su peso real. Dos
        clientes: un solo renglón por producto y día. """
        self._entregada(self.cliente, [(self.rollo, 2)], pesos=(1.25, 1.5))
        self._entregada(self.otro_cliente, [(self.rollo, 1)], pesos=(0.75,))
        self.assertEqual(self._filas(), [(self.hoy, self.rollo.name, 3.0, 3.5, 0.0, 0.0, True, True)])

    def test_devolucion_con_boton_devolver(self):
        """ Lo devuelto con el botón Devolver, con su peso; una devolución sin
        peso capturado cuenta 0 kg. """
        orden = self._entregada(self.cliente, [(self.pieza, 3, 10.0), (self.rollo, 2)], pesos=(1.5, 1.2))
        movimientos = self._movimientos(orden)
        pieza = movimientos.filtered(lambda m: m.product_id == self.pieza)
        rollo_1, rollo_2 = movimientos.filtered(lambda m: m.product_id == self.rollo)
        self._devolver(orden.picking_ids, {pieza: (1, None), rollo_1: (1, 0.8)})
        self._devolver(orden.picking_ids.filtered(lambda p: not p.return_id), {rollo_2: (1, None)})
        self.assertEqual(self._filas(), sorted([
            (self.hoy, self.pieza.name, 3.0, 0.0, 1.0, 0.0, True, False),
            (self.hoy, self.rollo.name, 2.0, 2.7, 2.0, 0.8, True, True),
        ]))

    def test_cambio_de_producto(self):
        """ El rollo nuevo es Vendido y el devuelto es Devuelto, el mismo día. """
        orden = self._entregada(self.cliente, [(self.rollo, 1)], pesos=(1.5,))
        orden._create_invoices().action_post()
        asistente = self.env["duran.cambio.producto"].with_context(active_id=orden.id).create({
            "sale_line_id": orden.order_line.id, "peso_devuelto": 0.5, "peso_nuevo": 1.8, "cobra_ahora": False,
        })
        asistente.action_confirm()
        self.assertEqual(self._filas(), [(self.hoy, self.rollo.name, 2.0, 3.3, 1.0, 0.5, True, True)])

    def test_unidad_kg_cuenta_en_unidades_y_totales(self):
        """ Sin peso variable, la unidad de medida no cuenta: un producto con
        unidad kg (Bolsa de asa) va en unidades, sin kg, en Vendido y en
        Devuelto. Peso variable con unidad kg: se trata como rollo (unidades =
        rollos, kg = peso real). El total de unidades suma todo; el de kg, solo
        el peso real. """
        orden = self._entregada(
            self.cliente, [(self.bolsa_asa, 3, 70.0), (self.pieza, 2, 10.0), (self.rollo, 2)], pesos=(1.5, 1.2),
        )
        self._entregada(self.otro_cliente, [(self.rollo_kg, 1)], pesos=(1.4,))
        movimientos = self._movimientos(orden)
        bolsa = movimientos.filtered(lambda m: m.product_id == self.bolsa_asa)
        rollo_1 = movimientos.filtered(lambda m: m.product_id == self.rollo)[0]
        self._devolver(orden.picking_ids, {bolsa: (2, None), rollo_1: (1, 0.8)})
        self.assertEqual(self._filas(), sorted([
            (self.hoy, self.bolsa_asa.name, 3.0, 0.0, 2.0, 0.0, True, False),
            (self.hoy, self.pieza.name, 2.0, 0.0, 0.0, 0.0, True, False),
            (self.hoy, self.rollo.name, 2.0, 2.7, 1.0, 0.8, True, True),
            (self.hoy, self.rollo_kg.name, 1.0, 1.4, 0.0, 0.0, True, True),
        ]))
        # El kg de la bolsa queda vacío (no 0) en la base: la columna no aplica.
        renglon_bolsa = self._renglones().filtered(lambda r: r.product_id == self.bolsa_asa)
        self.env.cr.execute(
            "SELECT vendido_kg, devuelto_kg FROM duran_productos_vendidos WHERE id = %s", [renglon_bolsa.id],
        )
        self.assertEqual(self.env.cr.fetchone(), (None, None))
        # Total al pie (sin agrupar): unidades vendidas = 3 + 2 + 2 + 1, devueltas
        # = 2 + 1; kg solo peso real: 1.5 + 1.2 + 1.4 vendidos, 0.8 devueltos.
        Vista = self.env["duran.productos.vendidos"].with_user(self.papa)
        [totales] = Vista._read_group(
            [("product_id", "in", self.productos.ids)], [],
            ["vendido_unidades:sum", "vendido_kg:sum", "devuelto_unidades:sum", "devuelto_kg:sum"],
        )
        self.assertEqual(tuple(round(t, 3) for t in totales), (8.0, 4.1, 3.0, 0.8))

    def test_dia_es_el_de_mexico(self):
        """ Las 23:30 de hoy en México (ya mañana en UTC) son hoy; las 23:30 de
        ayer (ya hoy en UTC) son ayer. """
        noche = self._entregada(self.cliente, [(self.pieza, 1, 10.0)])
        anoche = self._entregada(self.cliente, [(self.pieza, 3, 10.0)])
        self._movimientos(noche).date = self._a_utc(self.hoy, 23, 30)
        self._movimientos(anoche).date = self._a_utc(self.ayer, 23, 30)
        self.assertEqual(self._movimientos(noche).date.date(), self.hoy + timedelta(days=1), "en UTC ya es mañana")
        self.assertEqual(self._filas(), [
            (self.ayer, self.pieza.name, 3.0, 0.0, 0.0, 0.0, True, False),
            (self.hoy, self.pieza.name, 1.0, 0.0, 0.0, 0.0, True, False),
        ])
        self.assertEqual(self._renglones("hoy").mapped("dia"), [self.hoy])

    def test_lo_que_no_cuenta(self):
        """ No cuentan: pedidos sin entregar o cancelados, compras, traslados
        internos, ajustes de inventario, entradas del cliente sin venta ni la
        devolución de una devolución (como Pendiente de cobro). """
        self._confirmada(self.cliente, [(self.otra_pieza, 5)])
        self._confirmada(self.cliente, [(self.otra_pieza, 4)])._action_cancel()
        stock = self.almacen.lot_stock_id
        proveedor = self.env.ref("stock.stock_location_suppliers")
        cliente = self.env.ref("stock.stock_location_customers")
        self._transferencia(self.almacen.in_type_id, proveedor, stock, self.almacenable, 10)
        self._transferencia(self.almacen.int_type_id, stock, stock, self.almacenable, 2)
        self._transferencia(self.almacen.in_type_id, cliente, stock, self.almacenable, 1)
        self.env["stock.quant"].with_context(inventory_mode=True).create({
            "product_id": self.almacenable.id, "location_id": stock.id, "inventory_quantity": 20,
        }).action_apply_inventory()
        # Entregada, devuelta y vuelta a entregar: solo cuentan la entrega y la devolución.
        orden = self._entregada(self.cliente, [(self.pieza, 1, 10.0)])
        devolucion = self._devolver(orden.picking_ids, {self._movimientos(orden): (1, None)})
        otra_vez = self._devolver(devolucion, {devolucion.move_ids: (1, None)})
        self.assertEqual(otra_vez.move_ids.location_dest_id.usage, "customer")
        self.assertTrue(otra_vez.move_ids.sale_line_id)
        self.assertEqual(self._filas(), [(self.hoy, self.pieza.name, 1.0, 0.0, 1.0, 0.0, True, False)])

    def test_varios_dias_y_agrupado(self):
        """ Un renglón por producto y día, con id estable; los grupos por día y
        por producto suman. """
        for dias, cantidad in ((2, 2), (1, 3), (0, 1)):
            orden = self._entregada(self.cliente, [(self.pieza, cantidad, 10.0)])
            self._movimientos(orden).date = self._a_utc(self.hoy - timedelta(days=dias), 12)
        self._entregada(self.cliente, [(self.rollo, 1)], pesos=(1.2,))
        hace_2 = self.hoy - timedelta(days=2)
        self.assertEqual(self._filas(), sorted([
            (hace_2, self.pieza.name, 2.0, 0.0, 0.0, 0.0, True, False),
            (self.ayer, self.pieza.name, 3.0, 0.0, 0.0, 0.0, True, False),
            (self.hoy, self.pieza.name, 1.0, 0.0, 0.0, 0.0, True, False),
            (self.hoy, self.rollo.name, 1.0, 1.2, 0.0, 0.0, True, True),
        ]))
        renglones = self._renglones()
        self.assertEqual(
            {r.id for r in renglones},
            {r.product_id.id * DIAS_POR_PRODUCTO + (r.dia - date.fromisoformat(DIA_BASE)).days for r in renglones},
        )
        self.assertEqual(renglones.mapped("dia"), sorted(renglones.mapped("dia"), reverse=True), "más reciente primero")
        Vista = self.env["duran.productos.vendidos"].with_user(self.papa)
        dominio = [("product_id", "in", self.productos.ids)]
        self.assertEqual(
            dict(Vista._read_group(dominio, ["dia:day"], ["vendido_unidades:sum"])),
            {hace_2: 2.0, self.ayer: 3.0, self.hoy: 2.0},
        )
        self.assertEqual(
            {p: (u, round(k, 3)) for p, u, k in Vista._read_group(
                dominio, ["product_id"], ["vendido_unidades:sum", "vendido_kg:sum"],
            )},
            {self.pieza: (6.0, 0.0), self.rollo: (1.0, 1.2)},
        )

    def test_lista_buscador_y_orden(self):
        Vista = self.env["duran.productos.vendidos"]
        arch = etree.fromstring(Vista.with_user(self.papa).get_views(
            [(self.accion.view_id.id, "list")],
        )["views"]["list"]["arch"])
        visibles = [c.get("name") for c in arch.xpath("//field") if not c.get("column_invisible")]
        self.assertEqual(visibles, COLUMNAS)
        self.assertEqual({c: arch.xpath(f"//field[@name='{c}']/@sum") for c in CANTIDADES},
                         {c: ["Total"] for c in CANTIDADES})
        self.assertEqual(arch.get("js_class"), "duran_lista_recarga")
        self.assertEqual(arch.get("default_order"), "dia desc, product_id")
        # Totales también en los grupos; ningún importe en pesos.
        campos = Vista.fields_get(attributes=["type", "aggregator"])
        self.assertEqual({c: campos[c]["aggregator"] for c in CANTIDADES}, {c: "sum" for c in CANTIDADES})
        self.assertFalse([c for c, d in campos.items() if d["type"] == "monetary"])
        # Abre en hoy, sin agrupar.
        contexto = safe_eval(self.accion.context)
        self.assertEqual(contexto, {"search_default_hoy": 1})
        self.assertFalse(self.accion.domain)
        busqueda = self._busqueda()
        self.assertEqual(self._filtro("hoy"), [("es_hoy", "=", True)])
        self.assertEqual(
            {f.get("name"): safe_eval(f.get("context"))["group_by"] for f in busqueda.xpath("//filter[@context]")},
            {"agrupar_dia": "dia:day", "agrupar_producto": "product_id"},
        )
        # "Hoy" deja fuera lo de ayer.
        orden = self._entregada(self.cliente, [(self.pieza, 1, 10.0)])
        self._movimientos(orden).date = self._a_utc(self.ayer, 12)
        self._entregada(self.cliente, [(self.rollo, 1)], pesos=(1.0,))
        self.assertEqual(self._renglones("hoy").product_id, self.rollo)
        self.assertEqual(len(self._renglones()), 2)

    def test_menu_y_acceso_solo_gerente(self):
        Menu = self.env["ir.ui.menu"]
        resumen = self.env.ref("duran_captura_tianguis.captura_cobro_menu")
        self.assertEqual(self.menu.parent_id, self.env.ref("sale.sale_order_menu"))
        hermanos = Menu.with_user(self.papa).search([("parent_id", "=", self.menu.parent_id.id)])
        self.assertEqual(hermanos.ids.index(self.menu.id), hermanos.ids.index(resumen.id) + 1,
                         "va justo después de Resumen de ventas")
        self.assertEqual(self.accion.group_ids, self.env.ref("sales_team.group_sale_manager"))
        self._entregada(self.cliente, [(self.pieza, 1, 10.0)])
        for usuario in (self.papa, self.admin):
            with self.subTest(usuario=usuario.login):
                self.assertIn(self.menu.id, Menu.with_user(usuario)._visible_menu_ids())
                self.assertTrue(self._renglones())
                Vista = self.env["duran.productos.vendidos"].with_user(usuario)
                self.assertEqual([Vista.has_access(o) for o in ("write", "create", "unlink")], [False] * 3)
        for usuario in (self.mama, self.vendedor):
            with self.subTest(usuario=usuario.login):
                self.assertNotIn(self.menu.id, Menu.with_user(usuario)._visible_menu_ids())
                with self.assertRaises(AccessError):
                    self.env["duran.productos.vendidos"].with_user(usuario).search([])
        self.assertTrue(self.mama.has_group(GRUPO_CAPTURA))
