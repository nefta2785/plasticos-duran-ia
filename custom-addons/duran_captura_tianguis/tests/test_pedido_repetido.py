""" Aviso de pedido repetido: al enviar, si el cliente ya tiene en el día
operativo un pedido igual (mismos productos y cantidades), el servidor lo
devuelve como posible duplicado sin crear nada; con `es_otro` lo crea. Un
reintento con el mismo token nunca avisa. """
import uuid
from datetime import datetime

import pytz

from odoo.exceptions import AccessError, UserError
from odoo.tests import HttpCase, tagged

from .common import GRUPO_CAPTURA, CapturaDatosPrueba, CapturaHttpMixin

CDMX = pytz.timezone("America/Mexico_City")
# Día operativo de las pruebas: el 10 de marzo de 2030 (lejos de los datos reales).
DIA = 10


def utc(dia, hora, minuto=0):
    """ Hora local de marzo de 2030 -> UTC sin zona horaria (como se guarda). """
    return CDMX.localize(datetime(2030, 3, dia, hora, minuto)).astimezone(pytz.utc).replace(tzinfo=None)


@tagged("post_install", "-at_install")
class TestPedidoRepetido(CapturaDatosPrueba, CapturaHttpMixin, HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._sin_gastar_folios()
        cls._crear_datos_captura()
        env = cls.env
        cls.mama = cls._usuario("repetido_mama", GRUPO_CAPTURA)
        cls.papa = cls._usuario("repetido_papa", GRUPO_CAPTURA)
        (cls.mama | cls.papa).tz = "America/Mexico_City"
        cls.papa.name = "Raúl prueba"
        cls.ahora = utc(DIA, 12)
        cls.classPatch(type(env["duran.captura"]), "_ahora", lambda self: cls.ahora)
        cls.otro_cliente = cls._cliente("Otro cliente prueba repetido", cls.zona_con_clientes)
        cls.Captura = env["duran.captura"].with_user(cls.mama)

    def _anterior(self, lineas, cuando=None, cliente=None, vendedor=None, **vals):
        """ Pedido ya confirmado (con su entrega), a las 10:42 de hoy si no se dice otra hora. """
        orden = self._confirmada(
            cliente or self.cliente, lineas, vendedor=vendedor or self.mama,
            zona_id=self.zona_con_clientes.id, **vals,
        )
        orden.date_order = cuando or utc(DIA, 10, 42)
        return orden

    def _enviar_como(self, lineas, usuario=None, token=None, cliente=None, **kwargs):
        captura = self.Captura if usuario is None else self.env["duran.captura"].with_user(usuario)
        return captura.enviar_pedido(
            (cliente or self.cliente).id, self.zona_con_clientes.id,
            [{"producto_id": producto.id, "cantidad": cantidad} for producto, cantidad in lineas],
            token or uuid.uuid4().hex, **kwargs,
        )

    def _ordenes(self, cliente=None):
        return self.env["sale.order"].search_count([("partner_id", "=", (cliente or self.cliente).id)])

    def assertAvisa(self, resultado, orden, estado="pendiente", quien=False):
        hora = pytz.utc.localize(orden.date_order).astimezone(CDMX).strftime("%H:%M")
        self.assertEqual(resultado, {"posible_duplicado": {
            "nombre": orden.name, "hora": hora, "estado": estado, "quien": quien,
        }})

    def assertCrea(self, resultado):
        self.assertNotIn("posible_duplicado", resultado)
        self.assertFalse(resultado["ya_existia"])
        self.assertEqual(self.env["sale.order"].browse(resultado["id"]).state, "sale")

    # === Cuándo avisa === #

    def test_pedido_igual_avisa_y_no_crea_nada(self):
        anterior = self._anterior([(self.normal, 2), (self.por_kilo, 3)])
        antes = self._ordenes()
        resultado = self._enviar_como([(self.normal, 2), (self.por_kilo, 3)])
        self.assertAvisa(resultado, anterior)
        self.assertEqual(resultado["posible_duplicado"]["hora"], "10:42")
        self.assertEqual(self._ordenes(), antes, "no debe crear ninguna orden")

    def test_con_es_otro_si_crea(self):
        self._anterior([(self.normal, 2)])
        antes = self._ordenes()
        self.assertCrea(self._enviar_como([(self.normal, 2)], es_otro=True))
        self.assertEqual(self._ordenes(), antes + 1)

    def test_mismo_token_despues_de_crear_nunca_avisa(self):
        """ Reintento del MISMO envío (sin señal, doble toque): devuelve la
        orden creada, con o sin `es_otro`, aunque ahora haya un pedido igual. """
        self._anterior([(self.normal, 2)])
        token = uuid.uuid4().hex
        creada = self._enviar_como([(self.normal, 2)], token=token, es_otro=True)
        for es_otro in (False, True):
            with self.subTest(es_otro=es_otro):
                otra_vez = self._enviar_como([(self.normal, 2)], token=token, es_otro=es_otro)
                self.assertNotIn("posible_duplicado", otra_vez)
                self.assertEqual((otra_vez["id"], otra_vez["ya_existia"]), (creada["id"], True))
        self.assertEqual(self.env["sale.order"].search_count([("captura_token", "=", token)]), 1)

    def test_mismo_token_tras_el_aviso_si_crea_con_es_otro(self):
        """ El aviso no gasta el token: "Es otro pedido" reenvía con el mismo. """
        self._anterior([(self.normal, 2)])
        token = uuid.uuid4().hex
        self.assertIn("posible_duplicado", self._enviar_como([(self.normal, 2)], token=token))
        creada = self._enviar_como([(self.normal, 2)], token=token, es_otro=True)
        self.assertCrea(creada)
        self.assertEqual(self.env["sale.order"].browse(creada["id"]).captura_token, token)

    def test_mismos_productos_en_otro_orden_o_repetidos_avisa(self):
        anterior = self._anterior([(self.normal, 2), (self.por_kilo, 3), (self.pv_con_precio, 2)])
        casos = {
            "otro orden": [(self.pv_con_precio, 2), (self.por_kilo, 3), (self.normal, 2)],
            "repetidos": [(self.normal, 1), (self.por_kilo, 3), (self.normal, 1), (self.pv_con_precio, 2)],
        }
        for caso, lineas in casos.items():
            with self.subTest(caso=caso):
                self.assertAvisa(self._enviar_como(lineas), anterior)

    def test_anterior_con_producto_en_varias_lineas_avisa(self):
        """ Orden hecha en Odoo con el mismo producto en dos líneas (y los
        rollos de peso variable, una línea por rollo): se suman. """
        anterior = self._anterior([(self.normal, 1), (self.normal, 1), (self.pv_con_precio, 2)])
        self.assertEqual(len(anterior.order_line), 4, "1 + 1 + un rollo por línea")
        self.assertAvisa(self._enviar_como([(self.normal, 2), (self.pv_con_precio, 2)]), anterior)

    def test_cantidad_distinta_o_un_producto_mas_no_avisa(self):
        self._anterior([(self.normal, 2), (self.por_kilo, 3)])
        casos = {
            "cantidad distinta": [(self.normal, 3), (self.por_kilo, 3)],
            "un producto más": [(self.normal, 2), (self.por_kilo, 3), (self.pv_con_precio, 1)],
            "un producto menos": [(self.normal, 2)],
        }
        for caso, lineas in casos.items():
            with self.subTest(caso=caso):
                self.assertCrea(self._enviar_como(lineas))

    def test_si_hay_varios_iguales_avisa_del_mas_reciente(self):
        self._anterior([(self.normal, 2)], cuando=utc(DIA, 9))
        reciente = self._anterior([(self.normal, 2)], cuando=utc(DIA, 11, 5))
        self._anterior([(self.normal, 2)], cuando=utc(DIA, 8))
        resultado = self._enviar_como([(self.normal, 2)])
        self.assertAvisa(resultado, reciente)
        self.assertEqual(resultado["posible_duplicado"]["hora"], "11:05")

    def test_cancelado_o_cotizacion_no_avisa(self):
        cancelada = self._anterior([(self.normal, 2)])
        cancelada._action_cancel()
        cotizacion = self.env["sale.order"].create({
            "partner_id": self.cliente.id, "date_order": utc(DIA, 10),
            "order_line": [(0, 0, {"product_id": self.normal.id, "product_uom_qty": 2})],
        })
        self.assertEqual((cancelada.state, cotizacion.state), ("cancel", "draft"))
        self.assertCrea(self._enviar_como([(self.normal, 2)]))

    def test_corte_del_dia_operativo(self):
        """ El día operativo va de ayer 20:00 a hoy 20:00 (hora local). """
        casos = [
            (utc(DIA - 1, 19, 59), False, "ayer 19:59: es el día operativo de ayer"),
            (utc(DIA - 1, 20, 1), True, "ayer 20:01: ya es el día operativo de hoy"),
            (utc(DIA - 2, 12), False, "anteayer"),
        ]
        for cuando, avisa, caso in casos:
            with self.subTest(caso=caso):
                cliente = self._cliente(f"Cliente corte prueba {caso}", self.zona_con_clientes)
                self._anterior([(self.normal, 2)], cuando=cuando, cliente=cliente)
                resultado = self._enviar_como([(self.normal, 2)], cliente=cliente)
                self.assertEqual("posible_duplicado" in resultado, avisa)

    def test_despues_del_corte_compara_con_el_dia_siguiente(self):
        """ A las 20:01 ya es el día operativo de mañana: el pedido de las
        10:42 de hoy ya no cuenta, pero uno de las 20:00 sí. """
        self._anterior([(self.normal, 2)])
        self.patch(type(self.env["duran.captura"]), "_ahora", lambda captura: utc(DIA, 20, 1))
        self.assertCrea(self._enviar_como([(self.normal, 2)]))
        noche = self._anterior([(self.por_kilo, 1)], cuando=utc(DIA, 20))
        self.assertAvisa(self._enviar_como([(self.por_kilo, 1)]), noche)

    def test_otro_cliente_con_el_mismo_contenido_no_avisa(self):
        self._anterior([(self.normal, 2)], cliente=self.otro_cliente)
        self.assertCrea(self._enviar_como([(self.normal, 2)]))

    def test_pedido_de_una_direccion_del_cliente_avisa(self):
        direccion = self.env["res.partner"].create({
            "name": "Puesto prueba", "parent_id": self.cliente.id, "type": "delivery",
        })
        anterior = self._anterior([(self.normal, 2)], cliente=direccion)
        self.assertAvisa(self._enviar_como([(self.normal, 2)]), anterior)

    def test_extra_igual_avisa(self):
        """ «El cliente quiere algo más» sigue la misma regla, y con
        `es_otro` se crea marcado como extra. """
        anterior = self._anterior([(self.normal, 2)])
        self.assertAvisa(self._enviar_como([(self.normal, 2)], extra=True), anterior)
        creada = self._enviar_como([(self.normal, 2)], extra=True, es_otro=True)
        self.assertCrea(creada)
        self.assertTrue(self.env["sale.order"].browse(creada["id"]).captura_pedido_extra)

    def test_anterior_extra_tambien_cuenta(self):
        anterior = self._anterior([(self.normal, 2)], captura_pedido_extra=True)
        self.assertAvisa(self._enviar_como([(self.normal, 2)]), anterior)

    # === Estado del pedido anterior === #

    def test_entregado_completo_avisa_con_estado_entregado(self):
        anterior = self._anterior([(self.normal, 2)])
        self._validar(anterior.picking_ids)
        self.assertAvisa(self._enviar_como([(self.normal, 2)]), anterior, estado="entregado")

    def test_entregado_con_cantidad_bajada_no_avisa(self):
        """ Pidió 3 y se llevó 2: la entrega baja lo pedido a 2 (como la app,
        `_bajar_cantidad_pedida`). Otro pedido de 3 ya no es igual; uno de 2
        sí. Un producto que no se llevó (bajado a 0) no cuenta. """
        anterior = self._anterior([(self.normal, 3), (self.por_kilo, 1)])
        picking = anterior.picking_ids
        for move in picking.move_ids:
            se_llevo = move.product_id == self.normal
            move.write({"quantity": 2 if se_llevo else 0, "picked": se_llevo})
        picking.with_context(cancel_backorder=True)._action_done()
        self.assertEqual(picking.state, "done")
        self.env["duran.captura"]._bajar_cantidad_pedida(anterior.order_line)
        self.assertEqual(
            {l.product_id: l.product_uom_qty for l in anterior.order_line},
            {self.normal: 2.0, self.por_kilo: 0.0},
        )
        self.assertCrea(self._enviar_como([(self.normal, 3), (self.por_kilo, 1)], cliente=self.cliente))
        self.assertAvisa(self._enviar_como([(self.normal, 2)]), anterior, estado="entregado")

    def test_cobrado_avisa_con_estado_cobrado(self):
        anterior = self._anterior([(self.normal, 2)])
        self._validar(anterior.picking_ids)
        anterior._create_invoices()
        self.assertEqual(anterior.invoice_status, "invoiced")
        self.assertAvisa(self._enviar_como([(self.normal, 2)]), anterior, estado="cobrado")

    # === Pedido de otra persona === #

    def test_pedido_de_otro_vendedor_avisa_con_quien(self):
        """ Quien captura tiene "Ventas: solo sus documentos" y no puede leer
        el pedido de otra persona; aun así se le avisa, con su nombre. """
        anterior = self._anterior([(self.normal, 2)], vendedor=self.papa)
        self.assertFalse(self.mama.has_group("sales_team.group_sale_salesman_all_leads"))
        self.assertTrue(self.mama.has_group("sales_team.group_sale_salesman"))
        with self.assertRaises(AccessError):
            anterior.with_user(self.mama).check_access("read")
        self.assertAvisa(self._enviar_como([(self.normal, 2)]), anterior, quien="Raúl prueba")
        # Para quien lo envió, sin nombre.
        self.assertAvisa(self._enviar_como([(self.normal, 2)], usuario=self.papa), anterior)

    def test_solo_devuelve_folio_hora_estado_y_quien(self):
        self._anterior([(self.normal, 2)], vendedor=self.papa)
        resultado = self._enviar_como([(self.normal, 2)])
        self.assertEqual(list(resultado), ["posible_duplicado"])
        self.assertEqual(set(resultado["posible_duplicado"]), {"nombre", "hora", "estado", "quien"})

    def test_la_busqueda_no_escribe_nada(self):
        anterior = self._anterior([(self.normal, 2)], vendedor=self.papa)
        escrito = anterior.write_date
        self.env.invalidate_all()
        self._enviar_como([(self.normal, 2)])
        self.env.invalidate_all()
        self.assertEqual(anterior.write_date, escrito)

    # === Validaciones === #

    def test_es_otro_de_tipo_invalido(self):
        antes = self._ordenes()
        for es_otro in ("si", 1, 0, None, [], {"a": 1}):
            with self.subTest(es_otro=es_otro):
                with self.assertRaisesRegex(UserError, "No se pudo confirmar el pedido"):
                    with self.env.cr.savepoint():
                        self._enviar_como([(self.normal, 2)], es_otro=es_otro)
        self.assertEqual(self._ordenes(), antes)

    # === Por la ruta (como la pantalla) === #

    def test_por_la_ruta(self):
        anterior = self._anterior([(self.normal, 2)], vendedor=self.papa)
        self._entrar(self.mama)
        params = self._params_envio([(self.normal, 2)])
        aviso = self._resultado("/captura/api/enviar", params)
        self.assertEqual(aviso["posible_duplicado"]["nombre"], anterior.name)
        self.assertEqual(aviso["posible_duplicado"]["quien"], "Raúl prueba")
        creada = self._resultado("/captura/api/enviar", {**params, "es_otro": True})
        self.assertFalse(creada["ya_existia"])
        reintento = self._resultado("/captura/api/enviar", params)  # sin es_otro: mismo token
        self.assertEqual((reintento["id"], reintento["ya_existia"]), (creada["id"], True))

    def test_por_la_ruta_es_otro_invalido(self):
        self._entrar(self.mama)
        respuesta = self._jsonrpc("/captura/api/enviar", {**self._params_envio([(self.normal, 2)]), "es_otro": "si"})
        self.assertEqual(respuesta["error"]["data"]["name"], "odoo.exceptions.UserError")
        self.assertIn("No se pudo confirmar el pedido", respuesta["error"]["data"]["message"])
