""" Pendiente de cobro (Ventas › Órdenes › Pendiente de cobro): vista SQL
`duran.pendiente.cobro` con lo entregado hoy y el saldo anterior de cada
cliente, por zona y cliente. El total de cada cliente debe ser el que muestra
la app de Cobro. """
from datetime import datetime, time, timedelta

import pytz
from lxml import etree

from odoo import Command, fields
from odoo.exceptions import AccessError
from odoo.tests import HttpCase, tagged
from odoo.tools.safe_eval import safe_eval

from ..models.pendiente_cobro import DIAS_SALDO_VENCIDO
from .common import GRUPO_CAPTURA
from .test_cobro_confirmar import CobroDatosPrueba

ZONA_HORARIA = "America/Mexico_City"
COLUMNAS = [
    "zona_id", "cliente_id", "pedido", "product_id", "cantidad", "unidad_producto_id", "peso_real",
    "pendiente_hoy", "saldo_anterior", "total", "fecha", "dias_antiguedad",
]


@tagged("post_install", "-at_install")
class TestPendienteCobro(CobroDatosPrueba, HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.papa = cls._usuario("pendiente_cobro_papa", "sales_team.group_sale_manager")
        cls.admin = cls._usuario("pendiente_cobro_admin", "base.group_system,sales_team.group_sale_manager")
        cls.vendedor = cls._usuario("pendiente_cobro_vendedor", "sales_team.group_sale_salesman")
        cls.accion = env.ref("duran_captura_tianguis.pendiente_cobro_action")
        cls.menu = env.ref("duran_captura_tianguis.pendiente_cobro_menu")
        facturable = {"invoice_policy": "delivery", "taxes_id": [Command.clear()]}
        cls.kilo = cls._plantilla(
            "Kilo pendiente cobro", uom_id=env.ref("uom.product_uom_kgm").id, **facturable,
        ).product_variant_id
        cls.zona_b = env["res.partner.category"].create({"name": "Zona prueba pendiente B"})
        cls.hoy = fields.Date.context_today(env["res.partner"].with_context(tz=ZONA_HORARIA))

    # === Ayudantes === #

    def _nuevo_cliente(self, nombre, zonas=None):
        return self._cliente(nombre, zonas or self.zona_con_clientes)

    def _movimientos(self, orden):
        return orden.picking_ids.move_ids.filtered(lambda m: m.state == "done").sorted("id")

    def _a_utc(self, dia, hora, minuto=0):
        local = pytz.timezone(ZONA_HORARIA).localize(datetime.combine(dia, time(hora, minuto)))
        return local.astimezone(pytz.utc).replace(tzinfo=None)

    def _entregada_el(self, dia, cliente, lineas, **kwargs):
        orden = self._entregada(cliente, lineas, **kwargs)
        self._movimientos(orden).date = self._a_utc(dia, 12)
        return orden

    def _renglones(self, clientes, filtro=None):
        """ Renglones que ve el gerente con `filtro`, solo de `clientes` (la
        base puede tener datos reales). """
        self.env.flush_all()
        self.env.invalidate_all()
        dominio = self._filtro(filtro) if filtro else []
        return self.env["duran.pendiente.cobro"].with_user(self.papa).search(
            dominio + [("cliente_id", "in", clientes.ids)],
        )

    def _filas(self, clientes, filtro=None):
        return [
            (r.tipo, r.pedido, r.cantidad, r.pendiente_hoy, r.saldo_anterior, r.total, r.fecha or None,
             r.dias_antiguedad if r.tipo == "saldo" else None)
            for r in self._renglones(clientes, filtro)
        ]

    def _total(self, cliente):
        return round(sum(self._renglones(cliente).mapped("total")), 2)

    def _busqueda(self):
        return etree.fromstring(self.env["duran.pendiente.cobro"].get_views(
            [(self.accion.search_view_id.id, "search")],
        )["views"]["search"]["arch"])

    def _filtro(self, nombre):
        return safe_eval(self._busqueda().xpath(f"//filter[@name='{nombre}']/@domain")[0])

    def _grupos(self, clientes, agrupar):
        self.env.flush_all()
        grupos = self.env["duran.pendiente.cobro"].with_user(self.papa).formatted_read_group(
            [("cliente_id", "in", clientes.ids)], list(agrupar),
            ["pendiente_hoy:sum", "saldo_anterior:sum", "total:sum"],
        )
        return {
            tuple(g[a][0] if isinstance(g[a], (list, tuple)) else g[a] for a in agrupar):
                (g["pendiente_hoy:sum"], g["saldo_anterior:sum"], g["total:sum"])
            for g in grupos
        }

    # === Casos === #

    def test_entrega_hoy_sin_deuda(self):
        cliente = self._nuevo_cliente("Cliente pendiente solo hoy")
        orden = self._entregada(cliente, [(self.pieza, 2, 10.0)], zona_id=self.zona_con_clientes.id)
        self.assertEqual(self._filas(cliente), [("hoy", orden.name, 2.0, 20.0, 0.0, 20.0, None, None)])
        renglon = self._renglones(cliente)
        self.assertEqual((renglon.zona_id, renglon.stock_move_id), (self.zona_con_clientes, self._movimientos(orden)))
        self.assertFalse(renglon.vencido)
        self.assertFalse(self._renglones(cliente, "solo_saldo"))
        self.assertEqual(self._total(cliente), self._detalle(cliente)["total_a_cobrar"])

    def test_deuda_sin_entrega_hoy(self):
        """ Aparece aunque hoy no tenga entrega; su zona sale de la orden
        facturada. """
        cliente = self._nuevo_cliente("Cliente pendiente solo deuda", self.zona_con_clientes | self.zona_b)
        factura = self._facturada(cliente, 100.0, fecha=self.hoy - timedelta(days=3))
        factura.invoice_line_ids.sale_line_ids.order_id.zona_id = self.zona_b
        self.assertEqual(
            self._filas(cliente), [("saldo", factura.name, 0.0, 0.0, 100.0, 100.0, self.hoy - timedelta(days=3), 3)],
        )
        self.assertEqual(self._renglones(cliente).zona_id, self.zona_b)
        self.assertEqual(self._renglones(cliente, "solo_saldo"), self._renglones(cliente))
        self.assertEqual(self._total(cliente), self._detalle(cliente)["total_a_cobrar"])

    def test_pago_parcial_hoy(self):
        """ Lo entregado hoy se factura al cobrar: sale de "Entregado hoy" y lo
        que no pagó queda como saldo de la factura de hoy (0 días). """
        cliente = self._nuevo_cliente("Cliente pendiente pago parcial")
        anterior = self._facturada(cliente, 100.0, fecha=self.hace_10_dias)
        orden = self._entregada(cliente, [(self.pieza, 3, 100.0)], zona_id=self.zona_con_clientes.id)
        self.assertEqual(self._filas(cliente), [
            ("hoy", orden.name, 3.0, 300.0, 0.0, 300.0, None, None),
            ("saldo", anterior.name, 0.0, 0.0, 100.0, 100.0, self.hace_10_dias, 10),
        ])
        self.assertEqual(self._total(cliente), self._detalle(cliente)["total_a_cobrar"])
        registro = self._registro(self._confirmar(cliente=cliente, tipo="parte", monto=250))
        hoy = registro.invoice_ids
        self.assertEqual(self._filas(cliente), [("saldo", hoy.name, 0.0, 0.0, 150.0, 150.0, self.hoy, 0)])
        self.assertEqual(self._total(cliente), self._detalle(cliente)["total_a_cobrar"])
        self.assertEqual(self._total(cliente), registro.saldo_pendiente)

    def test_entrega_anterior_sin_cobrar(self):
        """ Lo entregado otro día y no cobrado (sin facturar) es saldo, con la
        fecha de su entrega. Una línea entregada en partes: lo de hoy en su
        renglón y lo de antes como saldo. """
        cliente = self._nuevo_cliente("Cliente pendiente entrega anterior")
        hace_3 = self.hoy - timedelta(days=3)
        antes = self._entregada_el(hace_3, cliente, [(self.pieza, 2, 10.0)], zona_id=self.zona_con_clientes.id)
        partes = self._confirmada(
            cliente, [(self.pieza, 5, 10.0)], vendedor=self.otro_vendedor, zona_id=self.zona_con_clientes.id,
        )
        primera_entrega = partes.picking_ids
        primera_entrega.move_ids.write({"quantity": 2, "picked": True})
        primera_entrega._action_done()  # deja los otros 3 en una entrega pendiente
        backorder = partes.picking_ids - primera_entrega
        self._movimientos(partes).date = self._a_utc(hace_3, 12)
        self._validar(backorder)
        self.assertEqual(
            sorted(self._filas(cliente), key=lambda f: (f[0], f[1], f[2])),
            sorted([
                ("hoy", partes.name, 3.0, 30.0, 0.0, 30.0, None, None),
                ("saldo", antes.name, 2.0, 0.0, 20.0, 20.0, hace_3, 3),
                ("saldo", partes.name, 2.0, 0.0, 20.0, 20.0, hace_3, 3),
            ], key=lambda f: (f[0], f[1], f[2])),
        )
        self.assertEqual(self._total(cliente), 70.0)
        self.assertEqual(self._total(cliente), self._detalle(cliente)["total_a_cobrar"])

    def test_saldo_a_favor(self):
        cliente = self._nuevo_cliente("Cliente pendiente saldo a favor")
        factura = self._facturada(cliente, 30.0, fecha=self.hace_10_dias)
        nota = self._nota_de_credito(cliente, 7.0)
        pago = self._pago_sin_aplicar(cliente, 4.0)
        self.assertEqual(
            sorted((r.pedido, r.saldo_anterior, r.zona_id) for r in self._renglones(cliente)),
            sorted([
                (factura.name, 30.0, self.zona_con_clientes),
                (nota.name, -7.0, self.zona_con_clientes),
                (pago.move_id.name, -4.0, self.zona_con_clientes),
            ]),
        )
        self.assertEqual(self._total(cliente), 19.0)
        self.assertEqual(self._total(cliente), self._detalle(cliente)["total_a_cobrar"])
        # Cliente con dos zonas y saldo sin orden: sin zona.
        dos_zonas = self._nuevo_cliente("Cliente pendiente dos zonas", self.zona_con_clientes | self.zona_b)
        self._nota_de_credito(dos_zonas, 5.0)
        self.assertFalse(self._renglones(dos_zonas).zona_id)

    def test_cliente_con_direccion_hija(self):
        """ Lo de sus direcciones va al cliente principal: un solo grupo. """
        cliente = self._nuevo_cliente("Cliente pendiente con dirección")
        direccion = self.env["res.partner"].create({
            "name": "Puesto pendiente cobro", "parent_id": cliente.id, "type": "other",
        })
        self._entregada(direccion, [(self.pieza, 2, 10.0)], zona_id=self.zona_con_clientes.id)
        self._facturada(direccion, 50.0, fecha=self.hace_10_dias)
        self._entregada(cliente, [(self.pieza, 1, 5.0)], zona_id=self.zona_con_clientes.id)
        self.assertEqual(self._renglones(cliente | direccion).cliente_id, cliente)
        self.assertEqual(self._grupos(cliente | direccion, ("cliente_id",)), {(cliente.id,): (25.0, 50.0, 75.0)})
        self.assertEqual(self._total(cliente), self._detalle(cliente)["total_a_cobrar"])

    def test_total_coincide_con_la_app_de_cobro(self):
        """ Todo junto: rollo, descuento, kilos con centavos, entrega anterior,
        factura con pago parcial, nota de crédito y una devolución de hoy. """
        cliente = self._nuevo_cliente("Cliente pendiente todo junto")
        zona = {"zona_id": self.zona_con_clientes.id}
        self._entregada(cliente, [(self.rollo, 1)], pesos=[1.237], **zona)
        con_descuento = self._entregada(cliente, [(self.pieza, 3, 12.5)], **zona)
        con_descuento.order_line.discount = 10.0
        self._entregada(cliente, [(self.kilo, 1.5, 33.33)], **zona)
        self._entregada_el(self.hoy - timedelta(days=2), cliente, [(self.otra_pieza, 4, 7.25)], **zona)
        factura = self._facturada(cliente, 80.0, fecha=self.hace_10_dias)
        self.env["account.payment.register"].with_context(
            active_model="account.move", active_ids=factura.ids,
        ).create({"amount": 30.0, "journal_id": self.efectivo.id})._create_payments()
        self._nota_de_credito(cliente, 3.5)
        devuelta = self._entregada(cliente, [(self.pieza, 2, 10.0)], **zona)
        asistente = self.env["stock.return.picking"].with_context(
            active_id=devuelta.picking_ids.id, active_model="stock.picking",
        ).create({})
        asistente.product_return_moves.quantity = 1
        self._validar(asistente._create_return())
        detalle = self._detalle(cliente)
        self.assertEqual(self._total(cliente), detalle["total_a_cobrar"])
        renglones = self._renglones(cliente)
        self.assertEqual(
            round(sum(renglones.mapped("pendiente_hoy")) + sum(renglones.mapped("saldo_anterior")), 2),
            detalle["total_a_cobrar"],
        )

    def test_hoy_es_el_dia_en_mexico(self):
        """ Las 23:30 de hoy en México (ya mañana en UTC) son hoy; las 23:30 de
        ayer (ya hoy en UTC) son saldo de ayer. """
        cliente = self._nuevo_cliente("Cliente pendiente medianoche")
        noche = self._entregada(cliente, [(self.pieza, 1, 10.0)], zona_id=self.zona_con_clientes.id)
        anoche = self._entregada(cliente, [(self.pieza, 3, 10.0)], zona_id=self.zona_con_clientes.id)
        self._movimientos(noche).date = self._a_utc(self.hoy, 23, 30)
        self._movimientos(anoche).date = self._a_utc(self.hoy - timedelta(days=1), 23, 30)
        self.assertEqual(self._movimientos(noche).date.date(), self.hoy + timedelta(days=1), "en UTC ya es mañana")
        self.assertEqual(
            sorted((r.tipo, r.pedido, r.fecha or None) for r in self._renglones(cliente)),
            sorted([("hoy", noche.name, None), ("saldo", anoche.name, self.hoy - timedelta(days=1))]),
        )

    def test_rojo_con_mas_de_7_dias(self):
        cliente = self._nuevo_cliente("Cliente pendiente antigüedad")
        siete = self._facturada(cliente, 10.0, fecha=self.hoy - timedelta(days=DIAS_SALDO_VENCIDO))
        ocho = self._facturada(cliente, 20.0, fecha=self.hoy - timedelta(days=DIAS_SALDO_VENCIDO + 1))
        viejo = self._entregada_el(self.hoy - timedelta(days=30), cliente, [(self.pieza, 1, 5.0)])
        hoy = self._entregada(cliente, [(self.pieza, 1, 5.0)])
        self._movimientos(hoy).date = self._a_utc(self.hoy, 0, 5)
        self.assertEqual(DIAS_SALDO_VENCIDO, 7)
        self.assertEqual(
            sorted((r.pedido, r.dias_antiguedad if r.tipo == "saldo" else None, r.vencido)
                   for r in self._renglones(cliente)),
            sorted([(siete.name, 7, False), (ocho.name, 8, True), (viejo.name, 30, True), (hoy.name, None, False)]),
        )
        arch = etree.fromstring(self.env["duran.pendiente.cobro"].with_user(self.papa).get_views(
            [(self.accion.view_id.id, "list")],
        )["views"]["list"]["arch"])
        self.assertEqual(arch.get("decoration-danger"), "vencido")

    def test_zona_de_respaldo_en_lo_entregado_hoy(self):
        """ Orden de hoy sin zona y cliente con una sola zona: esa zona, y el
        cliente queda en un solo grupo con sus saldos. Con dos zonas: sin zona. """
        cliente = self._nuevo_cliente("Cliente pendiente orden sin zona", self.zona_b)
        self._entregada(cliente, [(self.pieza, 2, 10.0)])
        self._facturada(cliente, 15.0, fecha=self.hace_10_dias)
        self._nota_de_credito(cliente, 4.0)
        renglones = self._renglones(cliente)
        self.assertEqual(sorted(renglones.mapped("tipo")), ["hoy", "saldo", "saldo"])
        self.assertEqual(renglones.zona_id, self.zona_b)
        self.assertEqual(self._grupos(cliente, ("zona_id", "cliente_id")), {(self.zona_b.id, cliente.id): (20.0, 11.0, 31.0)})
        # Días de antigüedad en el encabezado del grupo: el máximo.
        self.env.flush_all()
        grupo = self.env["duran.pendiente.cobro"].with_user(self.papa).formatted_read_group(
            [("cliente_id", "=", cliente.id)], ["cliente_id"], ["dias_antiguedad:max"],
        )
        self.assertEqual(grupo[0]["dias_antiguedad:max"], 10)
        # La orden con zona manda sobre la del cliente.
        con_zona = self._entregada(cliente, [(self.pieza, 1, 5.0)], zona_id=self.zona_con_clientes.id)
        self.assertEqual(
            self._renglones(cliente).filtered(lambda r: r.pedido == con_zona.name).zona_id, self.zona_con_clientes,
        )
        # Cliente con dos zonas y orden sin zona: sin zona.
        dos_zonas = self._nuevo_cliente("Cliente pendiente dos zonas hoy", self.zona_con_clientes | self.zona_b)
        self._entregada(dos_zonas, [(self.pieza, 1, 10.0)])
        self.assertEqual(self._renglones(dos_zonas).mapped("tipo"), ["hoy"])
        self.assertFalse(self._renglones(dos_zonas).zona_id)

    def test_totales_por_zona_y_cliente(self):
        uno = self._nuevo_cliente("Cliente pendiente total uno")
        dos = self._nuevo_cliente("Cliente pendiente total dos", self.zona_b)
        self._entregada(uno, [(self.pieza, 2, 10.0)], zona_id=self.zona_con_clientes.id)
        self._facturada(uno, 15.0, fecha=self.hace_10_dias)
        self._entregada(dos, [(self.pieza, 3, 10.0)], zona_id=self.zona_b.id)
        self._nota_de_credito(dos, 4.0)
        self.assertEqual(self._grupos(uno | dos, ("zona_id", "cliente_id")), {
            (self.zona_con_clientes.id, uno.id): (20.0, 15.0, 35.0),
            (self.zona_b.id, dos.id): (30.0, -4.0, 26.0),
        })
        self.assertEqual(self._grupos(uno | dos, ("zona_id",)), {
            (self.zona_con_clientes.id,): (20.0, 15.0, 35.0), (self.zona_b.id,): (30.0, -4.0, 26.0),
        })

    # === Importe del movimiento (stock.move.importe_entregado) === #

    def test_importe_rollo_producto_normal_y_descuento(self):
        normal = self._entregada(self.cliente, [(self.pieza, 3, 10.0)])
        con_descuento = self._entregada(self.cliente, [(self.pieza, 3, 10.0)])
        rollo = self._entregada(self.cliente, [(self.rollo, 1)], pesos=[1.25])
        rollo_descuento = self._entregada(self.cliente, [(self.rollo, 1)], pesos=[1.25])
        for orden in (con_descuento, rollo_descuento):
            orden.order_line.discount = 10.0
        casos = {
            "normal": (normal, 3.0, 30.0),
            "normal con descuento": (con_descuento, 3.0, 27.0),
            "rollo": (rollo, 1.0, 62.5),
            "rollo con descuento": (rollo_descuento, 1.0, 56.25),
        }
        for nombre, (orden, cantidad, importe) in casos.items():
            with self.subTest(caso=nombre):
                movimiento = self._movimientos(orden)
                self.assertEqual((movimiento.cantidad_entregada, movimiento.importe_entregado), (cantidad, importe))
                self.assertEqual(orden._create_invoices().amount_untaxed, importe, "como lo factura Odoo")

    def test_importe_se_recalcula_si_cambia_precio_o_descuento(self):
        orden = self._entregada(self.cliente, [(self.pieza, 2, 10.0)])
        movimiento = self._movimientos(orden)
        self.assertEqual(movimiento.importe_entregado, 20.0)
        orden.order_line.price_unit = 12.5
        self.assertEqual(movimiento.importe_entregado, 25.0)
        orden.order_line.discount = 20.0
        self.assertEqual(movimiento.importe_entregado, 20.0)

    # === Vista, acción, menú y permisos === #

    def test_lista_buscador_y_orden(self):
        Pendiente = self.env["duran.pendiente.cobro"]
        arch = etree.fromstring(Pendiente.with_user(self.papa).get_views(
            [(self.accion.view_id.id, "list")],
        )["views"]["list"]["arch"])
        visibles = [c.get("name") for c in arch.xpath("//field") if not c.get("column_invisible")]
        self.assertEqual(visibles, COLUMNAS)
        self.assertEqual(
            {c: arch.xpath(f"//field[@name='{c}']/@sum") for c in ("pendiente_hoy", "saldo_anterior", "total")},
            {"pendiente_hoy": ["Total"], "saldo_anterior": ["Total"], "total": ["Total"]},
        )
        self.assertEqual(arch.xpath("//field[@name='pedido']/@optional"), ["show"])
        self.assertEqual(arch.get("default_order"), "orden_clave, id")
        # En los grupos: Cantidad sin suma (mezclaría kg con piezas); Días, el máximo.
        agregados = Pendiente.fields_get(["cantidad", "dias_antiguedad"], ["aggregator"])
        self.assertEqual({c: agregados[c].get("aggregator") for c in agregados}, {"cantidad": None, "dias_antiguedad": "max"})
        contexto = safe_eval(self.accion.context)
        self.assertEqual(
            {k: v for k, v in contexto.items() if k.startswith("search_default_")},
            {"search_default_agrupar_zona": 1, "search_default_agrupar_cliente": 2},
        )
        self.assertFalse(self.accion.domain)
        # Sin filtro "Hoy": solo "Solo con saldo anterior".
        busqueda = self._busqueda()
        self.assertEqual(
            [f.get("name") for f in busqueda.xpath("//filter[@domain]")], ["solo_saldo"],
        )
        self.assertFalse(busqueda.xpath("//filter[@name='hoy']"))
        self.assertEqual(self._filtro("solo_saldo"), [("tipo", "=", "saldo")])
        # Orden: lo de hoy por pedido; después los saldos del más antiguo al más reciente.
        cliente = self._nuevo_cliente("Cliente pendiente orden")
        reciente = self._facturada(cliente, 1.0, fecha=self.hoy - timedelta(days=2))
        antigua = self._facturada(cliente, 1.0, fecha=self.hoy - timedelta(days=9))
        primera = self._entregada(cliente, [(self.pieza, 1, 1.0)])
        segunda = self._entregada(cliente, [(self.pieza, 1, 1.0)])
        self.assertEqual(
            self._renglones(cliente).mapped("pedido"),
            sorted([primera.name, segunda.name]) + [antigua.name, reciente.name],
        )

    def test_menu_y_acceso_solo_gerente(self):
        Menu = self.env["ir.ui.menu"]
        self.assertEqual(self.menu.parent_id, self.env.ref("sale.sale_order_menu"))
        self.assertEqual(self.accion.group_ids, self.env.ref("sales_team.group_sale_manager"))
        self._entregada(self.cliente, [(self.pieza, 1, 10.0)])
        for usuario in (self.papa, self.admin):
            with self.subTest(usuario=usuario.login):
                self.assertIn(self.menu.id, Menu.with_user(usuario)._visible_menu_ids())
                self.assertTrue(self._renglones(self.cliente))
        for usuario in (self.mama, self.vendedor):
            with self.subTest(usuario=usuario.login):
                self.assertNotIn(self.menu.id, Menu.with_user(usuario)._visible_menu_ids())
                with self.assertRaises(AccessError):
                    self.env["duran.pendiente.cobro"].with_user(usuario).search([])
        self.assertTrue(self.mama.has_group(GRUPO_CAPTURA))
