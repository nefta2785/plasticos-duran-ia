""" Paso 1 (modo Cobro): bitácora de cobros en tianguis (duran.captura.cobro). """
import uuid

import psycopg2
from lxml import etree

from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger

from .common import GRUPO_CAPTURA, CapturaDatosPrueba

CAMPOS_DOCUMENTOS = ("invoice_ids", "payment_id", "linea_ids")


@tagged("post_install", "-at_install")
class TestBitacoraCobros(CapturaDatosPrueba, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._sin_gastar_folios()
        cls._crear_datos_captura()
        cls.mama = cls._usuario("cobro_bitacora_mama", GRUPO_CAPTURA)
        cls.otra = cls._usuario("cobro_bitacora_otra", GRUPO_CAPTURA)
        cls.vendedor = cls._usuario("cobro_bitacora_vendedor", "sales_team.group_sale_salesman")
        cls.gerente = cls._usuario("cobro_bitacora_gerente", "sales_team.group_sale_manager")
        cls.Cobro = cls.env["duran.captura.cobro"]

        # Factura y pago de una orden de OTRO vendedor: quien cobra no puede leerlos.
        orden = cls._confirmada(cls.cliente, [(cls.normal, 2)], vendedor=cls.vendedor)
        cls._validar(orden.picking_ids)
        cls.factura = orden._create_invoices()
        cls.factura.action_post()
        anterior = cls._confirmada(cls.cliente, [(cls.normal, 1)], vendedor=cls.vendedor)
        cls._validar(anterior.picking_ids)
        cls.anterior = anterior._create_invoices()
        cls.anterior.action_post()
        efectivo = cls.env["account.journal"].search([
            ("type", "=", "cash"), ("company_id", "=", cls.env.company.id),
        ], limit=1)
        cls.pago = cls.env["account.payment.register"].with_context(
            active_model="account.move", active_ids=cls.factura.ids,
        ).create({"journal_id": efectivo.id, "amount": 5.0})._create_payments()

    def _registrar(self, usuario, token=None, **vals):
        return self.Cobro.with_user(usuario).create({
            "token": token or uuid.uuid4().hex,
            "partner_id": self.cliente.id,
            "zona_id": self.zona_con_clientes.id,
            "tipo": "parte",
            "total_entregado": 20.0,
            "saldo_anterior": 0.0,
            "creditos": 0.0,
            "total_a_cobrar": 20.0,
            "monto_recibido": 5.0,
            "saldo_pendiente": 15.0,
            "linea_ids": [
                Command.create({
                    "move_id": self.factura.id, "tipo": "nueva",
                    "saldo_antes": 20.0, "aplicado": 5.0, "saldo_despues": 15.0,
                }),
                Command.create({
                    "move_id": self.anterior.id, "tipo": "anterior",
                    "saldo_antes": 10.0, "aplicado": 0.0, "saldo_despues": 10.0,
                }),
            ],
            "payment_id": self.pago.id,
            **vals,
        })

    def test_quien_captura_registra_su_cobro(self):
        """ Aunque las facturas y el pago sean de otro vendedor (que quien
        cobra no puede leer), el registro se guarda. """
        with self.assertRaises(AccessError):
            self.factura.with_user(self.mama).check_access("read")
        cobro = self._registrar(self.mama)
        self.assertEqual(cobro.user_id, self.mama, "Cobró = quien captura, sin mandarlo desde la pantalla")
        self.assertEqual(cobro.company_id, self.env.company)
        self.assertEqual(cobro.currency_id, self.env.company.currency_id)
        self.assertTrue(cobro.fecha)
        self.assertEqual(
            (cobro.tipo, cobro.total_a_cobrar, cobro.monto_recibido, cobro.saldo_pendiente),
            ("parte", 20.0, 5.0, 15.0),
        )
        self.assertEqual(cobro.linea_ids.move_id, self.factura | self.anterior)
        self.assertEqual(cobro.linea_ids.mapped("aplicado"), [5.0, 0.0])
        self.assertEqual(cobro.invoice_ids, self.factura, "Facturas = solo las creadas en este cobro")
        self.assertEqual(cobro.payment_id, self.pago)
        self.assertIn(self.cliente.name, cobro.display_name)

    def test_token_unico_en_la_base(self):
        """ Aunque dos confirmaciones con el mismo token llegaran al mismo
        tiempo, la base de datos no deja registrar el cobro dos veces. """
        token = uuid.uuid4().hex
        self._registrar(self.mama, token=token)
        with self.assertRaises(psycopg2.errors.UniqueViolation), mute_logger("odoo.sql_db"):
            with self.env.cr.savepoint():
                self._registrar(self.mama, token=token)

    def test_token_con_formato_invalido(self):
        for token in ("abc", "X" * 32, uuid.uuid4().hex.upper(), uuid.uuid4().hex + "0"):
            with self.subTest(token=token), self.assertRaises(ValidationError):
                with self.env.cr.savepoint():
                    self._registrar(self.mama, token=token)

    def test_tipo_obligatorio_y_valido(self):
        with self.assertRaises(Exception), mute_logger("odoo.sql_db"):
            with self.env.cr.savepoint():
                self._registrar(self.mama, tipo=False)
        with self.assertRaises(ValueError):
            with self.env.cr.savepoint():
                self._registrar(self.mama, tipo="fiado")

    def test_quien_captura_no_modifica_ni_borra(self):
        cobro = self._registrar(self.mama)
        with self.assertRaises(AccessError):
            cobro.with_user(self.mama).write({"monto_recibido": 1.0})
        with self.assertRaises(AccessError):
            cobro.linea_ids[0].with_user(self.mama).write({"aplicado": 20.0})
        with self.assertRaises(AccessError):
            cobro.linea_ids.with_user(self.mama).unlink()
        with self.assertRaises(AccessError):
            cobro.with_user(self.mama).unlink()

    def test_quien_captura_solo_ve_los_suyos(self):
        mio = self._registrar(self.mama)
        ajeno = self._registrar(self.otra)
        encontrados = self.Cobro.with_user(self.mama).search([("id", "in", (mio | ajeno).ids)])
        self.assertEqual(encontrados, mio)
        with self.assertRaises(AccessError):
            ajeno.with_user(self.mama).read(["monto_recibido"])
        lineas = self.env["duran.captura.cobro.linea"].with_user(self.mama).search([
            ("cobro_id", "in", (mio | ajeno).ids),
        ])
        self.assertEqual(lineas, mio.linea_ids)

    def test_no_registra_a_nombre_de_otra_persona(self):
        """ La regla de "solo los propios" también aplica al crear. """
        with self.assertRaises(AccessError):
            with self.env.cr.savepoint():
                self._registrar(self.mama, user_id=self.otra.id)

    def test_vendedor_sin_grupo_no_ve_la_bitacora(self):
        self._registrar(self.mama)
        with self.assertRaises(AccessError):
            self.Cobro.with_user(self.vendedor).search([])
        with self.assertRaises(AccessError):
            with self.env.cr.savepoint():
                self._registrar(self.vendedor)

    def test_gerente_ve_todos_pero_no_los_modifica(self):
        cobros = self._registrar(self.mama) | self._registrar(self.otra)
        Cobro = self.Cobro.with_user(self.gerente)
        self.assertEqual(Cobro.search([("id", "in", cobros.ids)]), cobros)
        self.assertEqual(len(cobros.with_user(self.gerente).linea_ids), 4)
        with self.assertRaises(AccessError):
            cobros.with_user(self.gerente).write({"monto_recibido": 1.0})
        with self.assertRaises(AccessError):
            cobros.with_user(self.gerente).unlink()

    def test_vistas_y_menu(self):
        menu = self.env.ref("duran_captura_tianguis.captura_cobro_menu")
        for usuario in (self.gerente, self.mama):
            with self.subTest(usuario=usuario.login):
                vistas = self.Cobro.with_user(usuario).get_views(
                    [(False, "list"), (False, "form"), (False, "search")]
                )
                self.assertEqual(set(vistas["views"]), {"list", "form", "search"})
                self.assertIn("'group_by': 'user_id'", vistas["views"]["search"]["arch"])
                self.assertIn(menu.id, self.env["ir.ui.menu"].with_user(usuario)._visible_menu_ids())
                # Facturas y pago: solo el gerente (en la lista, solo las facturas).
                esperados = {"list": {"invoice_ids"}, "form": set(CAMPOS_DOCUMENTOS)}
                for vista, campos in esperados.items():
                    arch = vistas["views"][vista]["arch"]
                    presentes = {campo for campo in CAMPOS_DOCUMENTOS if f'name="{campo}"' in arch}
                    self.assertEqual(presentes, campos if usuario == self.gerente else set(), vista)
        self.assertNotIn(menu.id, self.env["ir.ui.menu"].with_user(self.vendedor)._visible_menu_ids())

    def test_quien_cobra_abre_su_cobro_sin_error(self):
        """ Las vistas no le muestran facturas ni pago (no puede leerlos): los
        campos que sí ve se leen sin error. """
        cobro = self._registrar(self.mama).with_user(self.mama)
        for vista in ("list", "form"):
            with self.subTest(vista=vista):
                arch = etree.fromstring(cobro.get_views([(False, vista)])["views"][vista]["arch"])
                campos = set(arch.xpath("//field/@name")) & set(self.Cobro._fields)
                self.assertTrue(campos)
                self.assertFalse(set(CAMPOS_DOCUMENTOS) & campos)
                cobro.web_read({campo: {} for campo in campos})
        leido = self._registrar(self.mama).with_user(self.gerente).web_read({
            "invoice_ids": {"fields": {"display_name": {}}},
            "payment_id": {"fields": {"display_name": {}}},
            "linea_ids": {"fields": {"move_id": {"fields": {"display_name": {}}}, "aplicado": {}}},
        })[0]
        self.assertEqual(leido["payment_id"]["id"], self.pago.id)
        self.assertEqual([f["id"] for f in leido["invoice_ids"]], self.factura.ids)
        self.assertEqual(len(leido["linea_ids"]), 2)
