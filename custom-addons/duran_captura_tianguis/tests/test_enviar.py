""" Paso 6: enviar el pedido (orden nueva, con zona y vendedor, confirmada, sin duplicados). """
import uuid

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import HttpCase, TransactionCase, tagged

from .common import GRUPO_CAPTURA, CapturaDatosPrueba, CapturaHttpMixin


@tagged("post_install", "-at_install")
class TestEnviarHttp(CapturaDatosPrueba, CapturaHttpMixin, HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.usuario_captura = cls._usuario("captura_prueba", GRUPO_CAPTURA)
        cls.usuario_sin_grupo = cls._usuario("sin_grupo_prueba", "sales_team.group_sale_salesman")
        cls._crear_datos_captura()
        cls._sin_gastar_folios()

    def _ordenes_del_cliente(self):
        self.env.invalidate_all()
        return self.env["sale.order"].search_count([("partner_id", "=", self.cliente.id)])

    def test_enviar_crea_y_confirma_la_orden(self):
        self._entrar(self.usuario_captura)
        token = uuid.uuid4().hex
        envio = self._enviar(
            [(self.normal, 2), (self.por_kilo, 3), (self.pv_con_precio, 3)], token=token,
        )
        self.assertFalse(envio["ya_existia"])
        self.assertEqual(envio["productos"], 8)
        self.assertEqual(envio["cliente"], self.cliente.name)

        self.env.invalidate_all()
        orden = self.env["sale.order"].browse(envio["id"])
        self.assertEqual(orden.name, envio["nombre"])
        self.assertEqual(orden.state, "sale", "la orden debe quedar confirmada")
        self.assertEqual(orden.partner_id, self.cliente)
        self.assertEqual(orden.zona_id, self.zona_con_clientes)
        self.assertEqual(orden.user_id, self.usuario_captura)
        self.assertEqual(orden.captura_token, token)
        cantidades = {}
        for linea in orden.order_line:
            cantidades.setdefault(linea.product_id, []).append(linea.product_uom_qty)
        # Peso variable: duran_peso_variable parte la línea en 1 rollo por línea.
        self.assertEqual(cantidades, {self.normal: [2.0], self.por_kilo: [3.0], self.pv_con_precio: [1.0, 1.0, 1.0]})
        self.assertEqual(orden.order_line.tax_ids, self.env["account.tax"], "sin impuestos")
        # Confirmar crea la entrega de inmediato, con los mismos productos.
        self.assertEqual(len(orden.picking_ids), 1)
        self.assertEqual(sum(orden.picking_ids.move_ids.mapped("product_uom_qty")), 8)
        # Folios del contador falso (_sin_gastar_folios), no de la base.
        self.assertRegex(orden.name, r"9\d{5}$")
        self.assertRegex(orden.picking_ids.name, r"9\d{5}$")
        # Quien captura ("solo sus documentos") sí ve la orden que creó.
        self.assertIn(orden, self.env["sale.order"].with_user(self.usuario_captura).search([]))

    def test_enviar_siempre_crea_una_orden_nueva(self):
        existente = self._orden(self.cliente, [(self.normal, 1)], estado="draft")
        self._entrar(self.usuario_captura)
        primera = self._enviar([(self.normal, 1)])
        segunda = self._enviar([(self.normal, 1)])
        self.assertEqual(len({existente.id, primera["id"], segunda["id"]}), 3)
        self.env.invalidate_all()
        self.assertEqual(len(existente.order_line), 1, "no se suma a la orden existente")
        self.assertEqual(existente.state, "draft")

    def test_mismo_token_no_duplica(self):
        self._entrar(self.usuario_captura)
        token = uuid.uuid4().hex
        primera = self._enviar([(self.normal, 2)], token=token)
        segunda = self._enviar([(self.normal, 2)], token=token)
        self.assertEqual(segunda["id"], primera["id"])
        self.assertEqual((primera["ya_existia"], segunda["ya_existia"]), (False, True))
        self.assertEqual(self.env["sale.order"].search_count([("captura_token", "=", token)]), 1)

    def test_vendedor_es_quien_captura_aunque_el_cliente_tenga_vendedor(self):
        self.cliente.user_id = self.usuario_sin_grupo
        self._entrar(self.usuario_captura)
        envio = self._enviar([(self.normal, 1)])
        self.env.invalidate_all()
        self.assertEqual(self.env["sale.order"].browse(envio["id"]).user_id, self.usuario_captura)

    def test_cliente_con_dos_zonas_guarda_la_zona_elegida(self):
        otra_zona = self.env["res.partner.category"].create({"name": "Otra zona prueba"})
        self.cliente.category_id = [Command.link(otra_zona.id)]
        self._entrar(self.usuario_captura)
        for zona in (otra_zona, self.zona_con_clientes):
            with self.subTest(zona=zona.name):
                envio = self._enviar([(self.normal, 1)], zona=zona)
                self.env.invalidate_all()
                self.assertEqual(self.env["sale.order"].browse(envio["id"]).zona_id, zona)

    def test_enviar_error_legible_y_sin_orden(self):
        antes = self._ordenes_del_cliente()
        self._entrar(self.usuario_captura)
        respuesta = self._jsonrpc(
            "/captura/api/enviar", self._params_envio([(self.normal, 1), (self.pv_sin_precio, 1)]),
        )
        self.assertNotIn("result", respuesta)
        self.assertEqual(respuesta["error"]["data"]["name"], "odoo.exceptions.UserError")
        self.assertIn(self.pv_sin_precio.name, respuesta["error"]["data"]["message"])
        self.assertEqual(self._ordenes_del_cliente(), antes)

    def test_sin_grupo_o_sin_sesion_no_crea_ordenes(self):
        antes = self._ordenes_del_cliente()
        self._entrar(self.usuario_sin_grupo)
        self._jsonrpc("/captura/api/enviar", self._params_envio([(self.normal, 1)]))
        self.authenticate(None, None)
        self._jsonrpc("/captura/api/enviar", self._params_envio([(self.normal, 1)]))
        self.assertEqual(self._ordenes_del_cliente(), antes)


@tagged("post_install", "-at_install")
class TestEnviarPedidoValidaciones(CapturaDatosPrueba, TransactionCase):
    """ Cada caso inválido falla con un mensaje claro y no deja ninguna orden. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._crear_datos_captura()
        cls._sin_gastar_folios()
        cls.usuario_captura = cls._usuario("captura_envio_prueba", GRUPO_CAPTURA)
        cls.otra_zona = cls.env["res.partner.category"].create({"name": "Otra zona prueba"})

    def _enviar(self, lineas=None, token=None, cliente_id=None, zona_id=None):
        if lineas is None:
            lineas = [{"producto_id": self.normal.id, "cantidad": 1}]
        return self.env["duran.captura"].with_user(self.usuario_captura).enviar_pedido(
            cliente_id or self.cliente.id,
            zona_id or self.zona_con_clientes.id,
            lineas,
            uuid.uuid4().hex if token is None else token,
        )

    def _id_borrado(self, modelo, vals):
        registro = self.env[modelo].create(vals)
        registro_id = registro.id
        registro.unlink()
        return registro_id

    def assertRechaza(self, mensaje, **kwargs):
        antes = self.env["sale.order"].search_count([])
        with self.assertRaisesRegex(UserError, mensaje):
            with self.env.cr.savepoint():
                self._enviar(**kwargs)
        self.assertEqual(self.env["sale.order"].search_count([]), antes, "no debe quedar ninguna orden")

    def test_caso_valido_de_referencia(self):
        self.assertEqual(self.env["sale.order"].browse(self._enviar()["id"]).state, "sale")

    def test_cantidades_enteras_mayores_a_cero(self):
        for cantidad in (1.5, 0, -1, True, "2", None):
            with self.subTest(cantidad=cantidad):
                self.assertRechaza(
                    "números enteros mayores a cero",
                    lineas=[{"producto_id": self.normal.id, "cantidad": cantidad}],
                )

    def test_producto_invalido(self):
        for lineas in ([{"producto_id": "x", "cantidad": 1}], [{"cantidad": 1}], ["no es un dict"]):
            with self.subTest(lineas=lineas):
                self.assertRechaza("producto inválido", lineas=lineas)

    def test_pedido_vacio(self):
        for lineas in ([], "nada"):
            with self.subTest(lineas=lineas):
                self.assertRechaza("El pedido está vacío", lineas=lineas)

    def test_token_invalido(self):
        for token in ("", "abc", str(uuid.uuid4()), "X" * 32, 12345):
            with self.subTest(token=token):
                self.assertRechaza("No se pudo identificar el pedido", token=token)

    def test_zona_y_cliente(self):
        self.assertRechaza("La zona ya no existe", zona_id=self._id_borrado("res.partner.category", {"name": "Zona prueba x"}))
        self.assertRechaza("El cliente ya no existe", cliente_id=self._id_borrado("res.partner", {"name": "Cliente prueba x"}))
        self.assertRechaza("ya no está en la zona", zona_id=self.otra_zona.id)

    def test_productos_que_no_estan_a_la_venta(self):
        borrado = self._id_borrado("product.product", {"name": "Producto prueba borrado"})
        for producto_id in (self.pv_precio_cero.id, self.pv_sin_precio.id, self.no_vendible.id, self.archivado.id, borrado):
            with self.subTest(producto_id=producto_id):
                self.assertRechaza(
                    "ya no están a la venta",
                    lineas=[{"producto_id": self.normal.id, "cantidad": 1}, {"producto_id": producto_id, "cantidad": 1}],
                )

    def test_producto_repetido_se_suma(self):
        envio = self._enviar(lineas=[
            {"producto_id": self.normal.id, "cantidad": 2}, {"producto_id": self.normal.id, "cantidad": 3},
        ])
        orden = self.env["sale.order"].browse(envio["id"])
        self.assertEqual(orden.order_line.mapped("product_uom_qty"), [5.0])
