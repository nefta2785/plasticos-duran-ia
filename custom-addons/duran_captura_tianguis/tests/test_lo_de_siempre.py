""" Paso 5: "Lo de siempre" (órdenes confirmadas de 90 días, máximo 8, por frecuencia). """
from odoo import sql_db
from odoo.exceptions import UserError
from odoo.tests import HttpCase, TransactionCase, tagged

from .common import GRUPO_CAPTURA, CapturaDatosPrueba, CapturaHttpMixin


@tagged("post_install", "-at_install")
class TestLoDeSiempre(CapturaDatosPrueba, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._crear_datos_captura()
        # Quien captura tiene "Ventas: solo sus documentos" (incluido en el
        # grupo); las órdenes del historial son de OTRO vendedor.
        cls.usuario_captura = cls._usuario("captura_habituales_prueba", GRUPO_CAPTURA)
        cls.otro_vendedor = cls._usuario("otro_vendedor_prueba", "sales_team.group_sale_salesman")
        cls.cliente_habitual = cls.env["res.partner"].create({"name": "Cliente habitual prueba"})
        cls.p = [cls._plantilla(f"Habitual prueba {i}").product_variant_id for i in range(10)]

    def _captura(self):
        return self.env["duran.captura"].with_user(self.usuario_captura)

    def _habituales(self, cliente):
        return [producto["id"] for producto in self._captura().get_habituales(cliente.id)]

    def _orden_de_otro(self, lineas, cliente=None, **kwargs):
        return self._orden(cliente or self.cliente_habitual, lineas, vendedor=self.otro_vendedor, **kwargs)

    def test_orden_por_frecuencia_cantidad_y_fecha(self):
        a, b, c, d, e, f, g = self.p[:7]
        self._orden_de_otro([(a, 1), (b, 5), (e, 2)], dias_atras=1)
        self._orden_de_otro([(a, 1), (b, 5)], dias_atras=2)
        self._orden_de_otro([(a, 1), (c, 1)], dias_atras=3)
        self._orden_de_otro([(d, 3)], dias_atras=4)
        self._orden_de_otro([(g, 1)], dias_atras=5)
        self._orden_de_otro([(f, 1)], dias_atras=10)
        # a: 3 órdenes; b: 2 órdenes; el resto 1 orden, desempatados por
        # cantidad total (d 3 > e 2 > c, g, f 1) y luego por fecha más reciente
        # (c hace 3 días > g hace 5 > f hace 10).
        self.assertEqual(self._habituales(self.cliente_habitual), [x.id for x in (a, b, d, e, c, g, f)])

    def test_maximo_8_productos(self):
        self._orden_de_otro([(producto, 1) for producto in self.p])
        habituales = self._habituales(self.cliente_habitual)
        self.assertEqual(len(habituales), 8)
        self.assertEqual(habituales, [p.id for p in self.p[:8]])

    def test_solo_cuentan_ordenes_confirmadas_recientes_del_cliente(self):
        valido, viejo, borrador, cancelado, de_otro_cliente, de_contacto = self.p[:6]
        self._orden_de_otro([(valido, 1)], dias_atras=89)
        self._orden_de_otro([(viejo, 1)], dias_atras=91)
        self._orden_de_otro([(borrador, 1)], estado="draft")
        self._orden_de_otro([(cancelado, 1)], estado="cancel")
        otro_cliente = self.env["res.partner"].create({"name": "Otro cliente prueba"})
        self._orden_de_otro([(de_otro_cliente, 1)], cliente=otro_cliente)
        # Las órdenes a nombre de un contacto del cliente también cuentan.
        contacto = self.env["res.partner"].create({
            "name": "Contacto prueba", "parent_id": self.cliente_habitual.id,
        })
        self._orden_de_otro([(de_contacto, 1)], cliente=contacto)
        self.assertCountEqual(self._habituales(self.cliente_habitual), [valido.id, de_contacto.id])

    def test_solo_productos_del_catalogo(self):
        valido = self.p[0]
        self._orden_de_otro([
            (valido, 1), (self.pv_precio_cero, 1), (self.pv_sin_precio, 1),
            (self.no_vendible, 1), (self.archivado, 1),
        ])
        self.assertEqual(self._habituales(self.cliente_habitual), [valido.id])

    def test_sin_historial_lista_vacia(self):
        self.assertEqual(self._habituales(self.cliente_habitual), [])

    def test_ve_historial_de_ordenes_de_otro_vendedor(self):
        orden = self._orden_de_otro([(self.p[0], 1)])
        SaleOrder = self.env["sale.order"].with_user(self.usuario_captura)
        self.assertFalse(SaleOrder.search([("id", "=", orden.id)]), "con solo sus documentos no ve la orden")
        self.assertEqual(self._habituales(self.cliente_habitual), [self.p[0].id])

    def test_mismos_datos_que_el_catalogo(self):
        self._orden_de_otro([(self.pv_con_precio, 1), (self.normal, 1)])
        catalogo = {p["id"]: p for c in self._captura().get_catalogo() for p in c["productos"]}
        for producto in self._captura().get_habituales(self.cliente_habitual.id):
            self.assertEqual(producto, catalogo[producto["id"]])

    def test_cliente_inexistente(self):
        borrado = self.env["res.partner"].create({"name": "Cliente prueba borrado"})
        cliente_id = borrado.id
        borrado.unlink()
        with self.assertRaisesRegex(UserError, "El cliente ya no existe."):
            self._captura().get_habituales(cliente_id)

    def test_consultas_no_crecen_con_el_historial(self):
        """ El costo depende de cuántos productos se muestran, no de cuántas
        órdenes tiene el cliente: 3 órdenes o 40 cuestan lo mismo. """
        poco = self.env["res.partner"].create({"name": "Cliente poco historial prueba"})
        mucho = self.env["res.partner"].create({"name": "Cliente mucho historial prueba"})
        for _i in range(3):
            self._orden_de_otro([(producto, 1) for producto in self.p], cliente=poco)
        for _i in range(40):
            self._orden_de_otro([(producto, 1) for producto in self.p], cliente=mucho)

        def consultas(cliente):
            self._habituales(cliente)  # calienta cachés de permisos
            self.env.invalidate_all()
            antes = sql_db.sql_counter
            self._habituales(cliente)
            return sql_db.sql_counter - antes

        con_poco, con_mucho = consultas(poco), consultas(mucho)
        self.assertLessEqual(con_mucho, con_poco + 2, f"3 órdenes: {con_poco} consultas; 40 órdenes: {con_mucho}")
        self.assertLess(con_mucho, 40)


@tagged("post_install", "-at_install")
class TestLoDeSiempreHttp(CapturaDatosPrueba, CapturaHttpMixin, HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.usuario_captura = cls._usuario("captura_prueba", GRUPO_CAPTURA)
        cls._crear_datos_captura()
        cls._sin_gastar_folios()

    def test_habituales(self):
        self._orden(self.cliente, [(self.normal, 2), (self.por_kilo, 1)])
        self._orden(self.cliente, [(self.normal, 1)])
        self._entrar(self.usuario_captura)
        habituales = self._resultado("/captura/api/habituales", {"cliente_id": self.cliente.id})
        self.assertEqual([p["id"] for p in habituales], [self.normal.id, self.por_kilo.id])

    def test_habituales_cliente_inexistente_da_error_legible(self):
        self._entrar(self.usuario_captura)
        borrado = self.env["res.partner"].create({"name": "Cliente prueba borrado"})
        cliente_id = borrado.id
        borrado.unlink()
        respuesta = self._jsonrpc("/captura/api/habituales", {"cliente_id": cliente_id})
        self.assertNotIn("result", respuesta)
        self.assertEqual(respuesta["error"]["data"]["name"], "odoo.exceptions.UserError")
        self.assertEqual(respuesta["error"]["data"]["message"], "El cliente ya no existe.")

    def test_lo_enviado_aparece_despues_en_lo_de_siempre(self):
        """ De punta a punta: un pedido enviado desde la pantalla alimenta el
        "Lo de siempre" de ese cliente la siguiente vez. """
        self._entrar(self.usuario_captura)
        self.assertEqual(self._resultado("/captura/api/habituales", {"cliente_id": self.cliente.id}), [])
        self._enviar([(self.por_kilo, 1), (self.normal, 1)])
        self._enviar([(self.normal, 1)])
        habituales = self._resultado("/captura/api/habituales", {"cliente_id": self.cliente.id})
        self.assertEqual([p["id"] for p in habituales], [self.normal.id, self.por_kilo.id])
