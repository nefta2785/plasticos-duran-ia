""" Paso 2 (modo Entrega): bitácora de entregas en tianguis (duran.captura.entrega). """
import uuid

import psycopg2

from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger

from .common import GRUPO_CAPTURA, CapturaDatosPrueba


@tagged("post_install", "-at_install")
class TestBitacoraEntregas(CapturaDatosPrueba, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._crear_datos_captura()
        cls.mama = cls._usuario("bitacora_mama", GRUPO_CAPTURA)
        cls.otra = cls._usuario("bitacora_otra", GRUPO_CAPTURA)
        cls.vendedor = cls._usuario("bitacora_vendedor", "sales_team.group_sale_salesman")
        cls.gerente = cls._usuario("bitacora_gerente", "sales_team.group_sale_manager")
        cls.Entrega = cls.env["duran.captura.entrega"]

    def _registrar(self, usuario, token=None, **vals):
        return self.Entrega.with_user(usuario).create({
            "token": token or uuid.uuid4().hex,
            "partner_id": self.cliente.id,
            "zona_id": self.zona_con_clientes.id,
            "total": 137.5,
            "linea_ids": [
                Command.create({
                    "product_id": self.pv_con_precio.id, "cantidad": 1, "peso_real": 1.25,
                    "precio_unitario": 50.0, "importe": 62.5,
                }),
                Command.create({
                    "product_id": self.normal.id, "cantidad": 3, "precio_unitario": 25.0,
                    "importe": 75.0, "sin_existencia": True,
                }),
            ],
            **vals,
        })

    def test_quien_captura_registra_su_entrega(self):
        entrega = self._registrar(self.mama)
        self.assertEqual(entrega.user_id, self.mama, "Entregó = quien captura, sin mandarlo desde la pantalla")
        self.assertEqual(entrega.company_id, self.env.company)
        self.assertEqual(entrega.currency_id, self.env.company.currency_id)
        self.assertTrue(entrega.fecha)
        self.assertEqual(entrega.total, 137.5)
        self.assertEqual(entrega.linea_ids.mapped("peso_real"), [1.25, 0.0])
        self.assertEqual(entrega.linea_ids.mapped("sin_existencia"), [False, True])
        self.assertIn(self.cliente.name, entrega.display_name)

    def test_token_unico_en_la_base(self):
        """ Aunque dos confirmaciones con el mismo token llegaran al mismo
        tiempo, la base de datos no deja registrar la entrega dos veces. """
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

    def test_quien_captura_no_modifica_ni_borra(self):
        entrega = self._registrar(self.mama)
        with self.assertRaises(AccessError):
            entrega.with_user(self.mama).write({"total": 1.0})
        with self.assertRaises(AccessError):
            entrega.linea_ids[0].with_user(self.mama).write({"peso_real": 9.0})
        with self.assertRaises(AccessError):
            entrega.linea_ids.with_user(self.mama).unlink()
        with self.assertRaises(AccessError):
            entrega.with_user(self.mama).unlink()

    def test_quien_captura_solo_ve_las_suyas(self):
        mia = self._registrar(self.mama)
        ajena = self._registrar(self.otra)
        Entrega = self.Entrega.with_user(self.mama)
        encontradas = Entrega.search([("id", "in", (mia | ajena).ids)])
        self.assertEqual(encontradas, mia)
        with self.assertRaises(AccessError):
            ajena.with_user(self.mama).read(["total"])
        lineas = self.env["duran.captura.entrega.linea"].with_user(self.mama).search([
            ("entrega_id", "in", (mia | ajena).ids),
        ])
        self.assertEqual(lineas, mia.linea_ids)

    def test_no_registra_a_nombre_de_otra_persona(self):
        """ La regla de "solo las propias" también aplica al crear. """
        with self.assertRaises(AccessError):
            with self.env.cr.savepoint():
                self._registrar(self.mama, user_id=self.otra.id)

    def test_vendedor_sin_grupo_no_ve_la_bitacora(self):
        self._registrar(self.mama)
        with self.assertRaises(AccessError):
            self.Entrega.with_user(self.vendedor).search([])
        with self.assertRaises(AccessError):
            with self.env.cr.savepoint():
                self._registrar(self.vendedor)

    def test_gerente_ve_todas_pero_no_las_modifica(self):
        entregas = self._registrar(self.mama) | self._registrar(self.otra)
        Entrega = self.Entrega.with_user(self.gerente)
        self.assertEqual(Entrega.search([("id", "in", entregas.ids)]), entregas)
        self.assertEqual(len(entregas.with_user(self.gerente).linea_ids), 4)
        with self.assertRaises(AccessError):
            entregas.with_user(self.gerente).write({"total": 1.0})
        with self.assertRaises(AccessError):
            entregas.with_user(self.gerente).unlink()

    def test_vistas_y_menu(self):
        for usuario in (self.gerente, self.mama):
            with self.subTest(usuario=usuario.login):
                vistas = self.Entrega.with_user(usuario).get_views(
                    [(False, "list"), (False, "form"), (False, "search")]
                )
                self.assertEqual(set(vistas["views"]), {"list", "form", "search"})
                self.assertIn("'group_by': 'zona_id'", vistas["views"]["search"]["arch"])
                menus = self.env["ir.ui.menu"].with_user(usuario)._visible_menu_ids()
                self.assertIn(self.env.ref("duran_captura_tianguis.captura_entrega_menu").id, menus)
        menus = self.env["ir.ui.menu"].with_user(self.vendedor)._visible_menu_ids()
        self.assertNotIn(self.env.ref("duran_captura_tianguis.captura_entrega_menu").id, menus)
