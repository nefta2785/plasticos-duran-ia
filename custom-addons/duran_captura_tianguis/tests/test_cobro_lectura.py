""" Paso 2 (modo Cobro): rutas de lectura de clientes con algo por cobrar y de
lo que hay que cobrarle a un cliente. """
from datetime import timedelta
from unittest.mock import patch

from odoo import Command, fields
from odoo.exceptions import AccessError
from odoo.sql_db import Cursor
from odoo.tests import HttpCase, tagged
from odoo.tools import SQL

from .common import GRUPO_CAPTURA, CapturaDatosPrueba, CapturaHttpMixin

RUTA_CLIENTES = "/captura/api/cobro/clientes"
RUTA_DETALLE = "/captura/api/cobro/detalle"
AVISO_BORRADOR = "Este cliente tiene una factura en borrador; confírmala o cancélala en Odoo."


@tagged("post_install", "-at_install")
class TestCobroLectura(CapturaDatosPrueba, CapturaHttpMixin, HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._sin_gastar_folios()
        cls._crear_datos_captura()
        env = cls.env
        cls.mama = cls._usuario("cobro_lectura_mama", GRUPO_CAPTURA)
        cls.otro_vendedor = cls._usuario("cobro_lectura_otro", "sales_team.group_sale_salesman")
        cls.efectivo = env["account.journal"].search([
            ("type", "=", "cash"), ("company_id", "=", env.company.id),
        ], limit=1)
        hoy = fields.Date.context_today(env["res.partner"])

        # Facturan lo entregado, sin impuestos (no dependen de la configuración de la base).
        facturable = {"invoice_policy": "delivery", "taxes_id": [Command.clear()]}
        cls.pieza = cls._plantilla("Pieza cobro prueba", **facturable).product_variant_id
        cls.rollo = cls._plantilla(
            "Rollo cobro prueba", es_peso_variable=True, precio_por_kg=50.0, **facturable,
        ).product_variant_id

        zona_a = cls.zona_con_clientes
        cls.zona_b = env["res.partner.category"].create({"name": "Zona prueba cobro B"})
        cls.direccion = env["res.partner"].create({
            # "other": si fuera "delivery", Odoo la usaría en todas las órdenes del cliente.
            "name": "Puesto prueba cobro", "parent_id": cls.cliente.id, "type": "other",
        })
        cls.solo_saldo = cls._cliente("Cliente prueba cobro solo saldo", zona_a)
        cls.con_borrador = cls._cliente("Cliente prueba cobro con borrador", zona_a)
        cls.al_corriente = cls._cliente("Cliente prueba cobro al corriente", zona_a)
        cls.sin_entregar = cls._cliente("Cliente prueba cobro sin entregar", zona_a)
        cls.dos_zonas = cls._cliente("Cliente prueba cobro dos zonas", zona_a | cls.zona_b)
        cls.otra_zona = cls._cliente("Cliente prueba cobro otra zona", cls.zona_b)

        # === El cliente principal === #
        # Entregado sin facturar: o1 (de otro vendedor) y o2 (a otra dirección:
        # Odoo lo factura aparte).
        cls.o1 = cls._confirmada(cls.cliente, [(cls.rollo, 1), (cls.pieza, 2)], vendedor=cls.otro_vendedor)
        cls._entregar(cls.o1, pesos=[1.25])
        cls.o2 = cls._confirmada(cls.cliente, [(cls.pieza, 1, 12.5)], partner_shipping_id=cls.direccion.id)
        cls._entregar(cls.o2)
        # Saldo anterior: la factura de o4 se crea primero pero es más reciente
        # que la de o3 (el pago se aplica por fecha, no por orden de creación).
        cls.o4 = cls._confirmada(cls.cliente, [(cls.pieza, 1)])
        cls._entregar(cls.o4)
        cls.factura_o4 = cls._facturar(cls.o4, fecha=hoy - timedelta(days=5))
        cls.o3 = cls._confirmada(cls.cliente, [(cls.pieza, 3, 12.0)], vendedor=cls.otro_vendedor)
        cls._entregar(cls.o3)
        # Ajuste hecho a mano en Odoo (+5) y un pago parcial de 10: saldo 31.
        cls.factura_o3 = cls._facturar(cls.o3, fecha=hoy - timedelta(days=10), ajuste=5.0)
        cls._pagar(cls.factura_o3, 10.0)
        # Saldo a favor: nota de crédito de 7 y pago de 4 sin aplicar.
        cls.nota = cls._nota_de_credito(cls.cliente, 7.0)
        cls.pago_suelto = cls._pago_sin_aplicar(cls.cliente, 4.0)
        # Pedido sin entregar: no se cobra.
        cls._confirmada(cls.cliente, [(cls.pieza, 1)])
        # Factura pagada y después devolución de una pieza, sin nota de crédito.
        cls.o6 = cls._confirmada(cls.cliente, [(cls.pieza, 2)])
        cls._entregar(cls.o6)
        cls._pagar(cls._facturar(cls.o6), 20.0)
        cls._validar(cls._devolver(cls.o6.picking_ids))

        # === Los demás clientes === #
        cls.factura_solo_saldo = cls._facturar(cls._entregar(cls._confirmada(cls.solo_saldo, [(cls.pieza, 1, 15.0)])))
        con_borrador = cls._entregar(cls._confirmada(cls.con_borrador, [(cls.pieza, 1)]))
        cls.borrador = con_borrador._create_invoices()
        cls._entregar(cls._confirmada(cls.con_borrador, [(cls.pieza, 2)]))
        # Al corriente: pagó de más, solo tiene saldo a favor.
        cls._pagar(cls._facturar(cls._entregar(cls._confirmada(cls.al_corriente, [(cls.pieza, 1)]))), 10.0)
        cls._pago_sin_aplicar(cls.al_corriente, 3.0)
        cls._confirmada(cls.sin_entregar, [(cls.pieza, 1)])
        cls._entregar(cls._confirmada(cls.dos_zonas, [(cls.pieza, 1)], vendedor=cls.otro_vendedor))
        cls._entregar(cls._confirmada(cls.otra_zona, [(cls.pieza, 1)]))

    def setUp(self):
        super().setUp()
        self._entrar(self.mama)

    # === Ayudantes para armar los datos === #

    @classmethod
    def _entregar(cls, orden, pesos=()):
        rollos = orden.picking_ids.move_ids.filtered("es_peso_variable").sorted("id")
        for movimiento, peso in zip(rollos, pesos):
            movimiento.peso_real = peso
        cls._validar(orden.picking_ids)
        return orden

    @classmethod
    def _facturar(cls, orden, fecha=None, ajuste=0.0):
        factura = orden._create_invoices()
        if fecha:
            # Como una factura hecha ese día (sin plazo de pago, vence el mismo día).
            factura.write({"invoice_date": fecha, "invoice_date_due": fecha})
        if ajuste:
            factura.invoice_line_ids = [Command.create({
                "name": "Ajuste a mano prueba", "quantity": 1, "price_unit": ajuste, "tax_ids": [Command.clear()],
            })]
        factura.action_post()
        return factura

    @classmethod
    def _pagar(cls, factura, monto):
        return cls.env["account.payment.register"].with_context(
            active_model="account.move", active_ids=factura.ids,
        ).create({"journal_id": cls.efectivo.id, "amount": monto})._create_payments()

    @classmethod
    def _nota_de_credito(cls, cliente, monto):
        nota = cls.env["account.move"].create({
            "move_type": "out_refund",
            "partner_id": cliente.id,
            "invoice_line_ids": [Command.create({
                "name": "Nota prueba", "quantity": 1, "price_unit": monto, "tax_ids": [Command.clear()],
            })],
        })
        nota.action_post()
        return nota

    @classmethod
    def _pago_sin_aplicar(cls, cliente, monto):
        pago = cls.env["account.payment"].create({
            "payment_type": "inbound", "partner_type": "customer", "partner_id": cliente.id,
            "amount": monto, "journal_id": cls.efectivo.id,
        })
        pago.action_post()
        return pago

    @classmethod
    def _devolver(cls, picking):
        asistente = cls.env["stock.return.picking"].with_context(
            active_id=picking.id, active_model="stock.picking",
        ).create({})
        asistente.product_return_moves.quantity = 1
        return asistente._create_return()

    def _detalle(self, cliente, zona=None):
        return self._resultado(RUTA_DETALLE, {
            "cliente_id": cliente.id, "zona_id": (zona or self.zona_con_clientes).id,
        })

    def _formato(self, importe, centavos=False):
        return self.env["duran.captura"]._formato_precio(importe, self.env.company.currency_id, centavos=centavos)

    def _nombres(self, *clientes):
        return [c.name for c in sorted(clientes, key=lambda c: (c.name, c.id))]

    # === Clientes con algo por cobrar === #

    def test_clientes_con_algo_por_cobrar(self):
        """ Entregado sin facturar, saldo pendiente o factura en borrador; no
        los que solo tienen pedidos sin entregar o saldo a favor. """
        clientes = self._resultado(RUTA_CLIENTES, {"zona_id": self.zona_con_clientes.id})
        self.assertEqual(
            [c["nombre"] for c in clientes],
            self._nombres(self.cliente, self.solo_saldo, self.con_borrador, self.dos_zonas),
        )
        self.assertEqual(clientes[0], {"id": self.cliente.id, "nombre": self.cliente.name})

    def test_clientes_de_otra_zona(self):
        clientes = self._resultado(RUTA_CLIENTES, {"zona_id": self.zona_b.id})
        self.assertEqual([c["nombre"] for c in clientes], self._nombres(self.dos_zonas, self.otra_zona))

    def test_zona_sin_clientes(self):
        self.assertEqual(self._resultado(RUTA_CLIENTES, {"zona_id": self.zona_vacia.id}), [])

    def test_cliente_por_su_direccion(self):
        """ Un cliente cuya única entrega sin facturar es de una de sus direcciones. """
        cliente = self._cliente("Cliente prueba cobro por dirección", self.zona_con_clientes)
        direccion = self.env["res.partner"].create({"name": "Dirección prueba", "parent_id": cliente.id})
        self._entregar(self._confirmada(direccion, [(self.pieza, 1)]))
        clientes = self._resultado(RUTA_CLIENTES, {"zona_id": self.zona_con_clientes.id})
        self.assertIn(cliente.id, [c["id"] for c in clientes])
        self.assertEqual(len(self._detalle(cliente)["entregado"]), 1)

    # === Lo que hay que cobrarle === #

    def test_detalle_del_cobro(self):
        # El precio por kg sube después de entregar: cuenta el congelado.
        self.rollo.product_tmpl_id.precio_por_kg = 80.0
        cobro = self._detalle(self.cliente)
        self.assertEqual(cobro["cliente"], {"id": self.cliente.id, "nombre": self.cliente.name})
        self.assertEqual(
            [(e["orden"], e["id"], e["cantidad"], e["peso"], e["precio_texto"], e["importe"]) for e in cobro["entregado"]],
            [
                (self.o1.name, self.rollo.id, 1.0, 1.25, self._formato(50.0) + "/kg", 62.5),
                (self.o1.name, self.pieza.id, 2.0, None, self._formato(10.0) + " c/u", 20.0),
                (self.o2.name, self.pieza.id, 1.0, None, self._formato(12.5) + " c/u", 12.5),
            ],
        )
        self.assertEqual((cobro["total_entregado"], cobro["total_entregado_texto"]), (95.0, self._formato(95.0, centavos=True)))
        self.assertEqual(
            [(d["move_id"], d["saldo"]) for d in cobro["saldo_anterior"]],
            [(self.factura_o3.id, 31.0), (self.factura_o4.id, 10.0)],
            "De la más antigua a la más nueva; con el ajuste a mano y el pago parcial",
        )
        self.assertEqual(cobro["saldo_anterior"][0]["total"], 41.0)
        self.assertEqual(cobro["saldo_anterior"][0]["folio"], self.factura_o3.name)
        self.assertEqual(cobro["total_saldo_anterior"], 41.0)
        self.assertEqual(
            [(d["move_id"], d["saldo"]) for d in cobro["creditos"]],
            [(self.nota.id, 7.0), (self.pago_suelto.move_id.id, 4.0)],
        )
        self.assertEqual(cobro["total_creditos"], 11.0)
        self.assertEqual(
            (cobro["total_a_cobrar"], cobro["total_a_cobrar_texto"], cobro["saldo_a_favor"]),
            (125.0, self._formato(125.0, centavos=True), 0.0),
            "95 entregado + 41 saldo - 11 a favor",
        )
        self.assertEqual(cobro["borradores"], [])
        self.assertTrue(cobro["puede_cobrar"])

    def test_orden_del_saldo_anterior_como_lo_aplica_odoo(self):
        """ El saldo anterior sale en el orden en que Odoo le aplicaría un
        pago: por vencimiento y, si vencen el mismo día, el menor primero. Se
        comprueba contra Odoo: un pago de 20 paga completa la primera. """
        cliente = self._cliente("Cliente prueba cobro orden", self.zona_con_clientes)
        grande = self._facturar(self._entregar(self._confirmada(cliente, [(self.pieza, 1, 30.0)])))
        chica = self._facturar(self._entregar(self._confirmada(cliente, [(self.pieza, 1, 20.0)])))
        vieja = self._facturar(
            self._entregar(self._confirmada(cliente, [(self.pieza, 1, 50.0)])),
            fecha=fields.Date.context_today(self.env["res.partner"]) - timedelta(days=3),
        )
        cobro = self._detalle(cliente)
        self.assertEqual([d["move_id"] for d in cobro["saldo_anterior"]], (vieja | chica | grande).ids)

        pago = self._pago_sin_aplicar(cliente, 70.0)
        receivable = lambda m: m.line_ids.filtered(lambda l: l.account_type == "asset_receivable")  # noqa: E731
        (receivable(pago.move_id) | receivable(vieja | chica | grande)).reconcile()
        self.assertEqual(
            (vieja | chica | grande).mapped("payment_state"), ["paid", "paid", "not_paid"],
            "Odoo aplica el pago en el mismo orden",
        )

    def test_devolucion_sin_nota_de_credito_solo_avisa(self):
        cobro = self._detalle(self.cliente)
        self.assertEqual(
            [(d["orden"], d["nombre"], d["cantidad"]) for d in cobro["devoluciones"]],
            [(self.o6.name, self.pieza.name, 1.0)],
        )
        self.assertNotIn(self.o6.name, [e["orden"] for e in cobro["entregado"]])
        self.assertEqual(len(cobro["avisos"]), 1)
        self.assertIn(self.o6.name, cobro["avisos"][0])
        self.assertIn("nota de crédito", cobro["avisos"][0])

    def test_total_entregado_coincide_con_las_facturas(self):
        """ Lo entregado sin facturar, igual que las facturas que hará Odoo
        (dos: o2 va a otra dirección), línea por línea. """
        cobro = self._detalle(self.cliente)
        facturas = (self.o1 | self.o2)._create_invoices()
        self.assertEqual(len(facturas), 2)
        self.assertAlmostEqual(cobro["total_entregado"], sum(facturas.mapped("amount_total")), places=6)
        for renglon in cobro["entregado"]:
            linea = facturas.invoice_line_ids.filtered(lambda l: renglon["linea_id"] in l.sale_line_ids.ids)
            self.assertAlmostEqual(renglon["importe"], linea.price_total, places=6)
            self.assertEqual(renglon["cantidad"], linea.quantity)

    def test_saldo_igual_al_de_odoo(self):
        """ Saldo anterior menos saldo a favor = lo que el cliente le debe a la
        empresa según Odoo ("Por cobrar" del contacto). """
        cobro = self._detalle(self.cliente)
        self.assertAlmostEqual(
            cobro["total_saldo_anterior"] - cobro["total_creditos"], self.cliente.sudo().credit, places=6,
        )

    def test_lee_lo_de_otro_vendedor(self):
        """ Con "Ventas: solo sus documentos" quien cobra no puede leer las
        órdenes ni las facturas de otro vendedor; la ruta sí las incluye. """
        with self.assertRaises(AccessError):
            self.o1.order_line.with_user(self.mama).check_access("read")
        with self.assertRaises(AccessError):
            self.factura_o3.with_user(self.mama).check_access("read")
        cobro = self._detalle(self.cliente)
        self.assertIn(self.o1.name, [e["orden"] for e in cobro["entregado"]])
        self.assertIn(self.factura_o3.id, [d["move_id"] for d in cobro["saldo_anterior"]])
        cobro = self._detalle(self.dos_zonas, zona=self.zona_b)
        self.assertEqual(cobro["total_a_cobrar"], 10.0)

    def test_solo_saldo_sin_entregas(self):
        cobro = self._detalle(self.solo_saldo)
        self.assertEqual(cobro["entregado"], [])
        self.assertEqual([d["move_id"] for d in cobro["saldo_anterior"]], self.factura_solo_saldo.ids)
        self.assertEqual((cobro["total_a_cobrar"], cobro["puede_cobrar"]), (15.0, True))

    def test_factura_en_borrador_no_permite_cobrar(self):
        """ La factura en borrador ya cuenta como facturada en Odoo: su entrega
        no aparece como sin facturar, y mientras exista no se puede cobrar. """
        cobro = self._detalle(self.con_borrador)
        self.assertEqual([b["move_id"] for b in cobro["borradores"]], self.borrador.ids)
        self.assertEqual(cobro["avisos"], [AVISO_BORRADOR])
        self.assertFalse(cobro["puede_cobrar"])
        self.assertEqual([e["cantidad"] for e in cobro["entregado"]], [2.0], "Solo la orden sin factura")
        self.assertEqual(self.borrador.state, "draft", "No la toca")

    def test_nota_de_credito_en_borrador_tambien_bloquea(self):
        nota = self.env["account.move"].create({
            "move_type": "out_refund", "partner_id": self.solo_saldo.id,
            "invoice_line_ids": [Command.create({"name": "Nota borrador", "quantity": 1, "price_unit": 1.0})],
        })
        cobro = self._detalle(self.solo_saldo)
        self.assertEqual([b["move_id"] for b in cobro["borradores"]], nota.ids)
        self.assertFalse(cobro["puede_cobrar"])

    def test_saldo_a_favor_mayor_que_la_deuda(self):
        """ Si el saldo a favor cubre todo, no hay nada que cobrar y se dice
        cuánto le queda a favor. """
        self._nota_de_credito(self.solo_saldo, 25.0)
        cobro = self._detalle(self.solo_saldo)
        self.assertEqual((cobro["total_a_cobrar"], cobro["saldo_a_favor"]), (0.0, 10.0))
        self.assertEqual(cobro["total_a_cobrar_texto"], self._formato(0.0, centavos=True))
        self.assertRegex(cobro["total_a_cobrar_texto"], r"^\$0[.,]00$")

    def test_cliente_sin_nada_que_cobrar(self):
        cobro = self._detalle(self.sin_entregar)
        self.assertEqual(
            (cobro["entregado"], cobro["saldo_anterior"], cobro["total_a_cobrar"], cobro["puede_cobrar"]),
            ([], [], 0.0, False),
        )

    # === Rechazos === #

    def test_cliente_de_otra_zona(self):
        respuesta = self._jsonrpc(RUTA_DETALLE, {"cliente_id": self.otra_zona.id, "zona_id": self.zona_con_clientes.id})
        self.assertIn("ya no está en la zona", respuesta["error"]["data"]["message"])

    def test_cliente_o_zona_inexistentes(self):
        for params, mensaje in (
            ({"cliente_id": 999999999, "zona_id": self.zona_con_clientes.id}, "El cliente ya no existe."),
            ({"cliente_id": self.cliente.id, "zona_id": 999999999}, "La zona ya no existe."),
        ):
            with self.subTest(mensaje=mensaje):
                self.assertEqual(self._jsonrpc(RUTA_DETALLE, params)["error"]["data"]["message"], mensaje)
        respuesta = self._jsonrpc(RUTA_CLIENTES, {"zona_id": 999999999})
        self.assertEqual(respuesta["error"]["data"]["message"], "La zona ya no existe.")

    # === No escribe nada === #

    def test_no_escribe_nada_en_la_base(self):
        self.env.flush_all()
        escrituras = []
        execute = Cursor.execute

        def espiar(cr, query, params=None, log_exceptions=True):
            texto = (query.code if isinstance(query, SQL) else str(query)).lstrip().upper()
            if texto.startswith(("INSERT", "UPDATE", "DELETE")):
                escrituras.append(texto[:100])
            return execute(cr, query, params, log_exceptions)

        with patch.object(Cursor, "execute", espiar):
            self._resultado(RUTA_CLIENTES, {"zona_id": self.zona_con_clientes.id})
            for cliente in (self.cliente, self.con_borrador, self.solo_saldo):
                self._detalle(cliente)
        self.assertEqual(escrituras, [])
