""" Paso 1 y 2: la zona en la orden de venta, el grupo y la integridad de la base. """
import uuid

import psycopg2

from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger

from .common import GRUPO_CAPTURA, CapturaDatosPrueba


@tagged("post_install", "-at_install")
class TestZonaEnOrden(CapturaDatosPrueba, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._crear_datos_captura()
        cls._sin_gastar_folios()

    def test_zona_id_es_many2one_a_etiquetas_de_contacto(self):
        field = self.env["sale.order"]._fields.get("zona_id")
        self.assertTrue(field, "sale.order debe tener zona_id")
        self.assertEqual(field.type, "many2one")
        self.assertEqual(field.comodel_name, "res.partner.category")

    def test_agrupar_ordenes_por_zona(self):
        zona_a, zona_b = self.env["res.partner.category"].create([
            {"name": "Zona prueba A"}, {"name": "Zona prueba B"},
        ])
        ordenes = self._orden(self.cliente, [(self.normal, 1)])
        ordenes |= self._orden(self.cliente, [(self.normal, 1)])
        ordenes |= self._orden(self.cliente, [(self.normal, 1)])
        ordenes[:2].zona_id = zona_a
        ordenes[2].zona_id = zona_b
        grupos = self.env["sale.order"]._read_group(
            [("id", "in", ordenes.ids)], groupby=["zona_id"], aggregates=["__count"],
        )
        self.assertEqual(dict(grupos), {zona_a: 2, zona_b: 1})

    def test_vistas_muestran_zona(self):
        SaleOrder = self.env["sale.order"]
        busqueda = SaleOrder.get_view(self.env.ref("sale.view_sales_order_filter").id, "search")["arch"]
        self.assertIn('<field name="zona_id"', busqueda)
        self.assertIn("'group_by': 'zona_id'", busqueda)
        lista = SaleOrder.get_view(self.env.ref("sale.view_order_tree").id, "list")["arch"]
        self.assertIn('name="zona_id"', lista)
        formulario = SaleOrder.get_view(self.env.ref("sale.view_order_form").id, "form")["arch"]
        self.assertIn('name="zona_id"', formulario)

    def test_no_se_puede_borrar_una_zona_usada_en_ordenes(self):
        zona = self.env["res.partner.category"].create({"name": "Zona prueba usada"})
        self._orden(self.cliente, [(self.normal, 1)]).zona_id = zona
        with self.assertRaises(psycopg2.errors.ForeignKeyViolation), mute_logger("odoo.sql_db"):
            with self.env.cr.savepoint():
                zona.unlink()

    def test_token_unico_en_la_base(self):
        """ Aunque dos envíos con el mismo token llegaran al mismo tiempo, la
        base de datos no deja crear la segunda orden. """
        token = uuid.uuid4().hex
        self._orden(self.cliente, [(self.normal, 1)]).captura_token = token
        otra = self._orden(self.cliente, [(self.normal, 1)])
        with self.assertRaises(psycopg2.errors.UniqueViolation), mute_logger("odoo.sql_db"):
            with self.env.cr.savepoint():
                otra.captura_token = token
                otra.flush_recordset()

    def test_duplicar_una_orden_no_copia_token_ni_zona(self):
        orden = self._orden(self.cliente, [(self.normal, 1)])
        orden.write({"captura_token": uuid.uuid4().hex, "zona_id": self.zona_con_clientes.id})
        copia = orden.copy()
        self.assertFalse(copia.captura_token)
        self.assertFalse(copia.zona_id)


@tagged("post_install", "-at_install")
class TestGrupoCaptura(TransactionCase):

    def test_grupo_incluye_ventas_solo_sus_documentos(self):
        grupo = self.env.ref(GRUPO_CAPTURA)
        self.assertIn(self.env.ref("sales_team.group_sale_salesman"), grupo.all_implied_ids)
        # Solo sus documentos: no incluye "Ventas: todos los documentos".
        self.assertNotIn(self.env.ref("sales_team.group_sale_salesman_all_leads"), grupo.all_implied_ids)

    def test_grupo_tiene_su_propio_selector_en_ventas(self):
        grupo = self.env.ref(GRUPO_CAPTURA)
        self.assertEqual(grupo.privilege_id.name, "Captura tianguis")
        self.assertEqual(grupo.privilege_id.category_id, self.env.ref("base.module_category_sales"))
