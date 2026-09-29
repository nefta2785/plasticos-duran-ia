""" Paso 6 (modo Cobro): arqueo del día en el menú "Resumen de ventas". """
from datetime import timedelta

from lxml import etree

from odoo import fields
from odoo.tests import HttpCase, tagged
from odoo.tools.safe_eval import safe_eval

from .common import GRUPO_CAPTURA
from .test_cobro_confirmar import CobroDatosPrueba

ZONA_HORARIA = "America/Mexico_City"
COLUMNAS = [
    "fecha", "user_id", "partner_id", "zona_id", "tipo", "total_a_cobrar", "monto_recibido", "saldo_pendiente",
]
AGREGADOS = ["monto_recibido:sum", "saldo_pendiente:sum", "__count"]


@tagged("post_install", "-at_install")
class TestCobroArqueo(CobroDatosPrueba, HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.otra = cls._usuario("cobro_arqueo_otra", GRUPO_CAPTURA)
        cls.papa = cls._usuario("cobro_arqueo_papa", "sales_team.group_sale_manager")
        (cls.mama | cls.otra | cls.papa).tz = ZONA_HORARIA
        cls.accion = cls.env.ref("duran_captura_tianguis.captura_cobro_action")
        cls.Cobro = cls.env["duran.captura.cobro"]

    # === Ayudantes === #

    def _busqueda(self):
        return etree.fromstring(self.Cobro.get_views([(False, "search")])["views"]["search"]["arch"])

    def _filtro_hoy(self):
        return safe_eval(self._busqueda().xpath("//filter[@name='hoy']/@domain")[0])

    def _arqueo(self, usuario):
        """ Lo que muestra el menú al abrirlo (hoy, por día y por quién cobró),
        por id de quien cobró. Solo los usuarios de la prueba: la base puede
        tener cobros reales de hoy. """
        grupos = self.Cobro.with_user(usuario).with_context(tz=ZONA_HORARIA).formatted_read_group(
            self._filtro_hoy(), ["fecha:day", "user_id"], AGREGADOS,
        )
        grupos = [g for g in grupos if g["user_id"][0] in (self.mama | self.otra).ids]
        # Un solo grupo por persona: el de hoy.
        self.assertEqual(len(grupos), len({g["user_id"][0] for g in grupos}), grupos)
        return {g["user_id"][0]: g for g in grupos}

    def _pagos_en_efectivo(self, usuario, dia):
        return self.env["account.payment"].search([
            ("journal_id", "=", self.efectivo.id), ("create_uid", "=", usuario.id), ("date", "=", dia),
        ])

    def _cobrar(self, usuario, cobros):
        """ `usuario` cobra en la app a un cliente nuevo por cada (tipo, monto):
        $100 de saldo anterior y $300 entregados. """
        self._entrar(usuario)
        for tipo, monto in cobros:
            cliente = self._cliente(f"Cliente prueba arqueo {usuario.login} {tipo} {monto}", self.zona_con_clientes)
            self._facturada(cliente, 100.0, fecha=self.hace_10_dias)
            self._entregada(cliente, [(self.pieza, 3, 100.0)])
            self._confirmar(cliente=cliente, tipo=tipo, monto=monto)

    def _cobro_de_ayer(self, usuario):
        """ Un cobro de ayer en la bitácora: no entra en el arqueo de hoy. """
        return self.Cobro.create({
            "token": "a" * 32, "fecha": fields.Datetime.now() - timedelta(days=1), "user_id": usuario.id,
            "partner_id": self.cliente.id, "zona_id": self.zona_con_clientes.id, "tipo": "todo",
            "total_a_cobrar": 999.0, "monto_recibido": 999.0, "saldo_pendiente": 0.0,
        })

    # === Pruebas === #

    def test_menu_abre_hoy_por_dia_y_por_quien_cobro(self):
        contexto = safe_eval(self.accion.context)
        self.assertTrue(contexto["search_default_hoy"])
        # El número es el orden de las agrupaciones: primero el día, luego quién cobró.
        self.assertEqual((contexto["search_default_agrupar_dia"], contexto["search_default_agrupar_usuario"]), (1, 2))
        busqueda = self._busqueda()
        agrupar = {
            nombre: safe_eval(busqueda.xpath(f"//filter[@name='{nombre}']/@context")[0])["group_by"]
            for nombre in ("agrupar_dia", "agrupar_usuario")
        }
        self.assertEqual(agrupar, {"agrupar_dia": "fecha:day", "agrupar_usuario": "user_id"})
        self.assertEqual(self._filtro_hoy(), [("fecha", ">=", "today"), ("fecha", "<", "today +1d")])

    def test_columnas_y_sumas(self):
        for usuario in (self.papa, self.mama):
            with self.subTest(usuario=usuario.login):
                vista = self.Cobro.with_user(usuario).get_views([(False, "list")])["views"]["list"]["arch"]
                visibles = [
                    campo.get("name") for campo in etree.fromstring(vista).xpath("//field")
                    if not campo.get("column_invisible") and campo.get("optional") != "hide"
                ]
                self.assertEqual(visibles, COLUMNAS)
                sumas = {campo.get("name") for campo in etree.fromstring(vista).xpath("//field[@sum]")}
                self.assertLessEqual({"monto_recibido", "saldo_pendiente"}, sumas)
        descripcion = self.Cobro.fields_get(["fecha", "monto_recibido", "saldo_pendiente"], ["type", "aggregator"])
        self.assertEqual(descripcion["fecha"]["type"], "datetime", "fecha y hora")
        self.assertEqual(
            (descripcion["monto_recibido"]["aggregator"], descripcion["saldo_pendiente"]["aggregator"]), ("sum", "sum"),
        )

    def test_suma_del_dia_igual_a_los_pagos_en_efectivo_de_quien_cobro(self):
        """ Cada grupo (hoy, quién cobró) suma el efectivo recibido y lo que
        quedó pendiente; el efectivo = la suma de los pagos en el diario de
        efectivo creados por esa persona hoy. Un cobro de ayer y un pago hecho
        desde Odoo por otra persona no cuentan. """
        self._cobrar(self.mama, [("todo", None), ("parte", 120.5), ("nada", None), ("parte", 0.01)])
        self._cobrar(self.otra, [("parte", 75), ("todo", None)])
        self._cobro_de_ayer(self.mama)
        factura = self._facturada(self.otro_cliente, 50.0)
        self.env["account.payment.register"].with_context(
            active_model="account.move", active_ids=factura.ids,
        ).create({"journal_id": self.efectivo.id, "amount": 50.0})._create_payments()

        hoy = fields.Date.context_today(self.Cobro.with_context(tz=ZONA_HORARIA))
        grupos = self._arqueo(self.papa)
        self.assertEqual(set(grupos), {self.mama.id, self.otra.id})
        esperado = {self.mama.id: (4, 520.51, 1079.49), self.otra.id: (2, 475.0, 325.0)}
        for usuario_id, grupo in grupos.items():
            usuario = self.env["res.users"].browse(usuario_id)
            with self.subTest(usuario=usuario.login):
                pagos = self._pagos_en_efectivo(usuario, hoy)
                self.assertAlmostEqual(grupo["monto_recibido:sum"], sum(pagos.mapped("amount")), places=2)
                self.assertEqual(
                    (grupo["__count"], round(grupo["monto_recibido:sum"], 2), round(grupo["saldo_pendiente:sum"], 2)),
                    esperado[usuario.id],
                )

    def test_mama_solo_ve_sus_cobros_en_el_arqueo(self):
        self._cobrar(self.mama, [("parte", 40)])
        self._cobrar(self.otra, [("todo", None)])
        grupos = self.Cobro.with_user(self.mama).with_context(tz=ZONA_HORARIA).formatted_read_group(
            self._filtro_hoy(), ["fecha:day", "user_id"], AGREGADOS,
        )
        self.assertEqual(
            [(g["user_id"][0], g["__count"], g["monto_recibido:sum"]) for g in grupos], [(self.mama.id, 1, 40.0)],
        )
        self.assertEqual(set(self._arqueo(self.papa)), {self.mama.id, self.otra.id}, "el gerente de Ventas ve a las dos")
        menu = self.env.ref("duran_captura_tianguis.captura_cobro_menu")
        for usuario in (self.mama, self.papa):
            self.assertIn(menu.id, self.env["ir.ui.menu"].with_user(usuario)._visible_menu_ids())
