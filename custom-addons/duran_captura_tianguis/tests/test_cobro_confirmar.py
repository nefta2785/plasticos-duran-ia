""" Paso 3 (modo Cobro): confirmación del cobro con "No pagó hoy". """
import uuid
from datetime import timedelta
from unittest.mock import patch

from odoo import Command, fields
from odoo.exceptions import LockError, UserError
from odoo.tests import HttpCase, tagged

from .common import GRUPO_CAPTURA, CapturaDatosPrueba, CapturaHttpMixin

RUTA_DETALLE = "/captura/api/cobro/detalle"
RUTA_CONFIRMAR = "/captura/api/cobro/confirmar"
AVISO_BORRADOR = "Este cliente tiene una factura en borrador; confírmala o cancélala en Odoo."


class CobroDatosPrueba(CapturaDatosPrueba, CapturaHttpMixin):
    """ Datos y ayudantes de las pruebas de la confirmación del cobro
    (mezclar con HttpCase). """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._sin_gastar_folios()
        cls._crear_datos_captura()
        env = cls.env
        cls.mama = cls._usuario("cobro_confirmar_mama", GRUPO_CAPTURA)
        cls.otro_vendedor = cls._usuario("cobro_confirmar_otro", "sales_team.group_sale_salesman")
        cls.efectivo = env["account.journal"].search([
            ("type", "=", "cash"), ("company_id", "=", env.company.id),
        ], limit=1)
        facturable = {"invoice_policy": "delivery", "taxes_id": [Command.clear()]}
        cls.pieza = cls._plantilla("Pieza cobro confirmar", **facturable).product_variant_id
        cls.otra_pieza = cls._plantilla("Otra pieza cobro confirmar", **facturable).product_variant_id
        cls.rollo = cls._plantilla(
            "Rollo cobro confirmar", es_peso_variable=True, precio_por_kg=50.0, **facturable,
        ).product_variant_id
        cls.direccion = env["res.partner"].create({
            "name": "Puesto prueba cobro confirmar", "parent_id": cls.cliente.id, "type": "other",
        })
        cls.otro_cliente = cls._cliente("Cliente prueba cobro ajeno", cls.zona_con_clientes)
        cls.hace_10_dias = fields.Date.context_today(env["res.partner"]) - timedelta(days=10)

    def setUp(self):
        super().setUp()
        self._entrar(self.mama)

    # === Ayudantes === #

    def _entregada(self, cliente, lineas, pesos=(), vendedor=None, **vals):
        orden = self._confirmada(cliente, lineas, vendedor=vendedor or self.otro_vendedor, **vals)
        rollos = orden.picking_ids.move_ids.filtered("es_peso_variable").sorted("id")
        for movimiento, peso in zip(rollos, pesos):
            movimiento.peso_real = peso
        self._validar(orden.picking_ids)
        return orden

    def _facturada(self, cliente, precio, fecha=None):
        factura = self._entregada(cliente, [(self.pieza, 1, precio)])._create_invoices()
        if fecha:
            factura.write({"invoice_date": fecha, "invoice_date_due": fecha})
        factura.action_post()
        return factura

    def _nota_de_credito(self, cliente, monto):
        nota = self.env["account.move"].create({
            "move_type": "out_refund", "partner_id": cliente.id,
            "invoice_line_ids": [Command.create({
                "name": "Nota prueba", "quantity": 1, "price_unit": monto, "tax_ids": [Command.clear()],
            })],
        })
        nota.action_post()
        return nota

    def _pago_sin_aplicar(self, cliente, monto):
        pago = self.env["account.payment"].create({
            "payment_type": "inbound", "partner_type": "customer", "partner_id": cliente.id,
            "amount": monto, "journal_id": self.efectivo.id,
        })
        pago.action_post()
        return pago

    def _detalle(self, cliente=None):
        return self._resultado(RUTA_DETALLE, {
            "cliente_id": (cliente or self.cliente).id, "zona_id": self.zona_con_clientes.id,
        })

    def _params(self, cliente=None, token=None, visto=None, tipo="nada", monto=None):
        params = {
            "cliente_id": (cliente or self.cliente).id,
            "zona_id": self.zona_con_clientes.id,
            "tipo": tipo,
            "visto": self._detalle(cliente)["visto"] if visto is None else visto,
            "token": token or uuid.uuid4().hex,
        }
        if monto is not None:
            params["monto"] = monto
        return params

    def _confirmar(self, **kwargs):
        resultado = self._resultado(RUTA_CONFIRMAR, self._params(**kwargs))
        self.assertFalse(resultado["cambiaron"], resultado.get("cobro"))
        return resultado

    def _error(self, params):
        respuesta = self._jsonrpc(RUTA_CONFIRMAR, params)
        self.assertNotIn("result", respuesta)
        return respuesta["error"]["data"]

    def _registro(self, resultado):
        return self.env["duran.captura.cobro"].browse(resultado["id"])

    def _receivable(self, movimientos):
        return movimientos.line_ids.filtered(lambda l: l.account_type == "asset_receivable")

    def _foto(self, cliente=None):
        """ Facturas, saldos, conciliaciones, líneas facturadas y bitácora del
        cliente, para comprobar que un rechazo o una falla no dejan nada. """
        cliente = cliente or self.cliente
        self.env.flush_all()
        self.env.invalidate_all()
        facturas = self.env["account.move"].search([("partner_id", "child_of", cliente.id)])
        lineas = self.env["sale.order.line"].search([("order_id.partner_id", "child_of", cliente.id)])
        return {
            "facturas": facturas.read(["state", "amount_residual", "payment_state"]),
            "conciliaciones": self.env["account.partial.reconcile"].search_count([]),
            "facturado": lineas.mapped("qty_invoiced"),
            "cobros": self.env["duran.captura.cobro"].search_count([]),
            "pagos": self.env["account.payment"].search_count([("partner_id", "child_of", cliente.id)]),
        }


@tagged("post_install", "-at_install")
class TestCobroConfirmar(CobroDatosPrueba, HttpCase):

    # === Facturar y publicar === #

    def test_total_igual_a_entrega_vista_previa_bitacora_y_detalle(self):
        """ Entregado desde la app (rollo y pieza): la factura del cobro =
        vista previa de la entrega = bitácora de entregas = detalle del cobro. """
        orden = self._confirmada(self.cliente, [(self.rollo, 1), (self.pieza, 3, 12.345)], vendedor=self.otro_vendedor)
        rollo = orden.picking_ids.move_ids.filtered("es_peso_variable")
        pendiente = self._resultado("/captura/api/entrega/pendiente", {
            "cliente_id": self.cliente.id, "zona_id": self.zona_con_clientes.id,
        })
        entrega = {
            "cliente_id": self.cliente.id, "zona_id": self.zona_con_clientes.id,
            "rollos": [{"move_id": rollo.id, "peso": "1.237"}],
            "productos": [{"producto_id": self.pieza.id, "cantidad": 3}],
        }
        vista = self._resultado("/captura/api/entrega/vista_previa", entrega)
        entregado = self._resultado("/captura/api/entrega/confirmar", {
            **entrega, "token": uuid.uuid4().hex,
            "movimientos_vistos": [m["move_id"] for p in pendiente["productos"] for m in p["movimientos"]],
        })
        bitacora_entrega = self.env["duran.captura.entrega"].browse(entregado["id"])

        detalle = self._detalle()
        resultado = self._confirmar()
        registro = self._registro(resultado)
        factura = registro.invoice_ids
        self.assertEqual(len(factura), 1)
        self.assertEqual(factura.state, "posted")
        self.assertEqual(
            [factura.amount_total, vista["total"], bitacora_entrega.total, detalle["total_entregado"]],
            [registro.total_entregado] * 4,
        )
        self.assertAlmostEqual(factura.amount_total, 1.237 * 50.0 + 3 * 12.345, places=2)
        self.assertEqual(factura.invoice_line_ids.filtered("es_peso_variable").peso_real, 1.237)
        self.assertEqual(
            (registro.tipo, registro.total_a_cobrar, registro.monto_recibido, registro.saldo_pendiente),
            ("nada", detalle["total_a_cobrar"], 0.0, factura.amount_total),
        )
        self.assertEqual((factura.payment_state, factura.amount_residual), ("not_paid", factura.amount_total))
        self.assertEqual(
            [(l.move_id, l.tipo, l.saldo_antes, l.aplicado, l.saldo_despues) for l in registro.linea_ids],
            [(factura, "nueva", factura.amount_total, 0.0, factura.amount_total)],
        )
        self.assertEqual(
            {k: resultado[k] for k in ("tipo", "total_a_cobrar", "saldo_pendiente", "facturas", "ya_existia")},
            {"tipo": "nada", "total_a_cobrar": factura.amount_total, "saldo_pendiente": factura.amount_total,
             "facturas": [{"folio": factura.name, "total": factura.amount_total}], "ya_existia": False},
        )
        self.assertEqual(orden.invoice_status, "invoiced")
        self.assertEqual(self._detalle()["entregado"], [], "Ya no queda nada sin facturar")

    def test_agrupacion_como_odoo(self):
        """ Dos órdenes a la misma dirección: una factura; una tercera a otra
        dirección: otra factura. Un solo cobro. """
        o1 = self._entregada(self.cliente, [(self.pieza, 1, 10.0)])
        o2 = self._entregada(self.cliente, [(self.pieza, 2, 10.0)], vendedor=self.env.user)
        o3 = self._entregada(self.cliente, [(self.pieza, 1, 7.0)], partner_shipping_id=self.direccion.id)
        registro = self._registro(self._confirmar())
        facturas = registro.invoice_ids
        self.assertEqual(len(facturas), 2)
        self.assertEqual(
            sorted((f.amount_total, sorted(f.invoice_line_ids.sale_line_ids.order_id.ids)) for f in facturas),
            [(7.0, o3.ids), (30.0, sorted((o1 | o2).ids))],
        )
        self.assertEqual((registro.total_entregado, registro.saldo_pendiente), (37.0, 37.0))
        self.assertEqual(set(facturas.mapped("state")), {"posted"})

    def test_sin_el_permiso_acotado_la_factura_saldria_vacia(self):
        """ Odoo no deja facturar a quien no puede modificar la orden (de otro
        vendedor): devuelve una factura vacía, sin error. La ruta debe
        producir la factura completa. """
        orden = self._entregada(self.cliente, [(self.rollo, 1), (self.pieza, 2, 10.0)], pesos=[1.5])
        self.assertFalse(orden.with_user(self.mama)._create_invoices(), "La trampa de Odoo")
        self.assertEqual(orden.invoice_ids, self.env["account.move"])
        factura = self._registro(self._confirmar()).invoice_ids
        self.assertEqual(factura.invoice_line_ids.sale_line_ids, orden.order_line)
        self.assertEqual(factura.amount_total, 1.5 * 50.0 + 20.0)

    def test_devoluciones_sin_nota_de_credito_no_se_facturan(self):
        """ final=False: en la MISMA orden, la devolución de algo ya facturado
        sigue pendiente de su nota de crédito (en Odoo) y solo se factura lo
        entregado sin facturar. """
        orden = self._entregada(self.cliente, [(self.pieza, 2, 10.0), (self.otra_pieza, 1, 7.0)])
        devuelta, pendiente = orden.order_line.sorted("id")
        # Se facturó solo la pieza (se quitó la otra de la factura) y luego se devolvió una.
        factura = orden._create_invoices()
        factura.invoice_line_ids.filtered(lambda l: pendiente in l.sale_line_ids).unlink()
        factura.action_post()
        asistente = self.env["stock.return.picking"].with_context(
            active_id=orden.picking_ids.id, active_model="stock.picking",
        ).create({})
        asistente.product_return_moves.filtered(lambda l: l.product_id == self.pieza).quantity = 1
        self._validar(asistente._create_return())
        self.assertEqual((devuelta.qty_to_invoice, pendiente.qty_to_invoice), (-1.0, 1.0))

        registro = self._registro(self._confirmar())
        self.assertEqual(registro.invoice_ids.invoice_line_ids.sale_line_ids, pendiente)
        self.assertEqual((registro.invoice_ids.move_type, registro.invoice_ids.amount_total), ("out_invoice", 7.0))
        self.assertEqual(devuelta.qty_to_invoice, -1.0, "Sigue pendiente de su nota de crédito")
        self.assertEqual(len(self._detalle()["devoluciones"]), 1)

    # === Bloqueo === #

    def test_bloquea_ordenes_y_facturas_del_cliente(self):
        orden = self._entregada(self.cliente, [(self.pieza, 1)])
        anterior = self._facturada(self.cliente, 30.0)
        nota = self._nota_de_credito(self.cliente, 5.0)
        self._entregada(self.otro_cliente, [(self.pieza, 1)])
        params = self._params()
        bloqueados = []
        Base = type(self.env["base"])
        lock_for_update = Base.lock_for_update

        def espiar(registros, *args, **kwargs):
            bloqueados.append((registros._name, set(registros.ids)))
            return lock_for_update(registros, *args, **kwargs)

        with patch.object(Base, "lock_for_update", espiar):
            self._resultado(RUTA_CONFIRMAR, params)
        self.assertEqual(bloqueados, [
            ("sale.order", set(orden.ids)),
            ("sale.order.line", set(orden.order_line.ids)),
            ("account.move", set((anterior | nota).ids)),
            ("account.move.line", set(self._receivable(anterior | nota).ids)),
        ])

    def test_si_alguien_mas_los_tiene_bloqueados(self):
        self._entregada(self.cliente, [(self.pieza, 1)])
        params = self._params()
        antes = self._foto()
        Base = type(self.env["base"])
        with patch.object(Base, "lock_for_update", side_effect=LockError("Cannot grab a lock on records")):
            self.assertIn("intenta de nuevo", self._error(params)["message"])
        self.assertEqual(self._foto(), antes)

    # === Permiso acotado === #

    def test_permiso_acotado_solo_sobre_lo_del_cliente(self):
        """ Con sudo solo se factura lo del cliente, se publican esas facturas
        y se concilian sus documentos, aunque la pantalla mande ids ajenos; con
        el usuario de quien cobra. """
        propia = self._entregada(self.cliente, [(self.pieza, 2, 10.0)])
        anterior = self._facturada(self.cliente, 15.0, fecha=self.hace_10_dias)
        nota = self._nota_de_credito(self.cliente, 5.0)
        ajena = self._entregada(self.otro_cliente, [(self.pieza, 1)])
        factura_ajena = self._facturada(self.otro_cliente, 9.0)
        nota_ajena = self._nota_de_credito(self.otro_cliente, 3.0)
        antes_ajeno = self._foto(self.otro_cliente)
        del antes_ajeno["conciliaciones"], antes_ajeno["cobros"]

        params = self._params()
        # Datos de más que la pantalla no debería mandar: se ignoran.
        params.update({
            "orden_ids": ajena.ids, "factura_ids": factura_ajena.ids, "partner_id": self.otro_cliente.id,
            "move_ids": (factura_ajena | nota_ajena).ids,
        })

        llamadas = []
        SaleOrder = type(self.env["sale.order"])
        AccountMove = type(self.env["account.move"])
        AccountMoveLine = type(self.env["account.move.line"])
        originales = {
            "facturar": SaleOrder._create_invoices, "publicar": AccountMove.action_post,
            "conciliar": AccountMoveLine.reconcile,
        }

        def espia(nombre):
            def espiar(registros, *args, **kwargs):
                resultado = originales[nombre](registros, *args, **kwargs)
                # Solo ids: los registros de la petición no sobreviven a su cursor.
                llamadas.append((nombre, registros._name, registros.ids, registros.env.su, registros.env.uid))
                return resultado
            return espiar

        with patch.object(SaleOrder, "_create_invoices", espia("facturar")), \
                patch.object(AccountMove, "action_post", espia("publicar")), \
                patch.object(AccountMoveLine, "reconcile", espia("conciliar")):
            registro = self._registro(self._resultado(RUTA_CONFIRMAR, params))

        self.assertEqual([nombre for nombre, *_resto in llamadas], ["facturar", "publicar", "conciliar"])
        for _nombre, _modelo, _ids, su, uid in llamadas:
            self.assertEqual((su, uid), (True, self.mama.id))
        facturadas, publicadas, conciliadas = (self.env[modelo].browse(ids) for _n, modelo, ids, *_r in llamadas)
        self.assertEqual(facturadas, propia)
        self.assertEqual(publicadas, registro.invoice_ids)
        self.assertEqual(publicadas.invoice_line_ids.sale_line_ids, propia.order_line)
        self.assertEqual(conciliadas, self._receivable(publicadas | anterior | nota))
        self.assertEqual(set(conciliadas.partner_id.ids), {self.cliente.id})

        despues_ajeno = self._foto(self.otro_cliente)
        del despues_ajeno["conciliaciones"], despues_ajeno["cobros"]
        self.assertEqual(despues_ajeno, antes_ajeno, "Lo del otro cliente, intacto")

    def test_ids_ajenos_en_lo_visto_no_tocan_nada(self):
        self._entregada(self.cliente, [(self.pieza, 1)])
        ajena = self._entregada(self.otro_cliente, [(self.pieza, 1)])
        factura_ajena = self._facturada(self.otro_cliente, 9.0)
        visto = self._detalle()["visto"]
        visto["lineas"].append([ajena.order_line.id, 1.0])
        visto["documentos"].append([factura_ajena.id, 9.0])
        antes = (self._foto(), self._foto(self.otro_cliente))
        resultado = self._resultado(RUTA_CONFIRMAR, self._params(visto=visto))
        self.assertTrue(resultado["cambiaron"])
        self.assertEqual(resultado["cobro"]["visto"], self._detalle()["visto"])
        self.assertEqual((self._foto(), self._foto(self.otro_cliente)), antes)

    def test_creado_por_y_autor_en_el_historial(self):
        orden = self._entregada(self.cliente, [(self.pieza, 1)])
        factura = self._registro(self._confirmar()).invoice_ids
        self.env.flush_all()
        self.env.cr.precommit.run()
        self.assertEqual(factura.create_uid, self.mama)
        self.assertEqual(factura.invoice_user_id, self.otro_vendedor, "El vendedor sigue siendo el de la orden")
        self.assertTrue(factura.message_ids)
        self.assertEqual(factura.message_ids.author_id, self.mama.partner_id)
        self.assertEqual(factura.message_ids.create_uid, self.mama)
        self.assertEqual(orden.invoice_ids, factura)

    # === Saldo a favor === #

    def test_saldo_a_favor_se_aplica_a_las_facturas_abiertas(self):
        """ Saldo anterior 30 (el más antiguo) + entregado 20 - a favor 11
        (nota de 7 y pago de 4) = 39. El saldo a favor se aplica primero a la
        factura más antigua. """
        anterior = self._facturada(self.cliente, 30.0, fecha=self.hace_10_dias)
        nota = self._nota_de_credito(self.cliente, 7.0)
        pago = self._pago_sin_aplicar(self.cliente, 4.0)
        self._entregada(self.cliente, [(self.pieza, 2, 10.0)])
        detalle = self._detalle()
        self.assertEqual(detalle["total_a_cobrar"], 39.0)

        registro = self._registro(self._confirmar())
        nueva = registro.invoice_ids
        self.assertEqual(
            [(l.move_id, l.tipo, l.saldo_antes, l.aplicado, l.saldo_despues) for l in registro.linea_ids],
            [
                (nueva, "nueva", 20.0, 0.0, 20.0),
                (anterior, "anterior", 30.0, 11.0, 19.0),
                (nota, "credito", 7.0, 7.0, 0.0),
                (pago.move_id, "credito", 4.0, 4.0, 0.0),
            ],
        )
        self.assertEqual(
            (registro.saldo_anterior, registro.creditos, registro.total_a_cobrar, registro.saldo_pendiente),
            (30.0, 11.0, 39.0, 39.0),
        )
        self.assertEqual((anterior.amount_residual, anterior.payment_state), (19.0, "partial"))
        self.assertEqual((nota.amount_residual, nota.payment_state), (0.0, "paid"))
        self.assertEqual(self.cliente.sudo().credit, 39.0, "Lo que Odoo dice que debe")
        self.assertEqual(self._detalle()["total_a_cobrar"], 39.0, "El siguiente cobro parte de aquí")
        self.assertEqual(self._detalle()["creditos"], [])

    def test_saldo_a_favor_mayor_que_la_deuda(self):
        anterior = self._facturada(self.cliente, 30.0, fecha=self.hace_10_dias)
        nota = self._nota_de_credito(self.cliente, 60.0)
        self._entregada(self.cliente, [(self.pieza, 2, 10.0)])
        registro = self._registro(self._confirmar())
        self.assertEqual((registro.total_a_cobrar, registro.saldo_pendiente), (0.0, 0.0))
        # Odoo marca "Revertida" (no "Pagada") la factura cubierta solo con notas de crédito.
        self.assertEqual((registro.invoice_ids.amount_residual, registro.invoice_ids.payment_state), (0.0, "reversed"))
        self.assertEqual((anterior.amount_residual, anterior.payment_state), (0.0, "reversed"))
        self.assertEqual(nota.amount_residual, 10.0, "Le quedan 10 a favor")
        self.assertEqual(self._detalle()["saldo_a_favor"], 10.0)

    def test_solo_saldo_anterior_no_crea_facturas(self):
        anterior = self._facturada(self.cliente, 30.0)
        registro = self._registro(self._confirmar())
        self.assertFalse(registro.invoice_ids)
        self.assertEqual(
            [(l.move_id, l.tipo, l.aplicado) for l in registro.linea_ids], [(anterior, "anterior", 0.0)],
        )
        self.assertEqual(registro.saldo_pendiente, 30.0)

    # === Doble toque, cambios desde Odoo, rechazos y fallas === #

    def test_doble_toque_un_solo_cobro(self):
        orden = self._entregada(self.cliente, [(self.pieza, 1)])
        params = self._params()
        cobros_antes = self.env["duran.captura.cobro"].search_count([])
        primero = self._resultado(RUTA_CONFIRMAR, params)
        segundo = self._resultado(RUTA_CONFIRMAR, params)
        self.assertTrue(segundo["ya_existia"])
        self.assertEqual({**primero, "ya_existia": True}, segundo)
        self.assertEqual(self.env["duran.captura.cobro"].search_count([]), cobros_antes + 1)
        self.assertEqual(len(orden.invoice_ids), 1)

    def test_factura_hecha_desde_odoo_entre_lectura_y_confirmacion(self):
        orden = self._entregada(self.cliente, [(self.pieza, 1)])
        otra = self._entregada(self.cliente, [(self.pieza, 2)])
        params = self._params()
        orden._create_invoices().action_post()  # alguien la factura desde Odoo
        antes = self._foto()
        resultado = self._resultado(RUTA_CONFIRMAR, params)
        self.assertTrue(resultado["cambiaron"])
        self.assertEqual(resultado["cobro"], self._detalle())
        self.assertEqual(self._foto(), antes)
        self.assertEqual(otra.invoice_status, "to invoice", "No facturó lo demás")
        # Con lo nuevo, sí.
        self._confirmar()

    def test_factura_en_borrador_hecha_desde_odoo_entre_lectura_y_confirmacion(self):
        orden = self._entregada(self.cliente, [(self.pieza, 1)])
        params = self._params()
        orden._create_invoices()
        antes = self._foto()
        resultado = self._resultado(RUTA_CONFIRMAR, params)
        self.assertTrue(resultado["cambiaron"])
        self.assertEqual(resultado["cobro"]["avisos"], [AVISO_BORRADOR])
        self.assertEqual(self._foto(), antes)

    def test_pago_registrado_desde_odoo_entre_lectura_y_confirmacion(self):
        anterior = self._facturada(self.cliente, 30.0)
        self._entregada(self.cliente, [(self.pieza, 1)])
        params = self._params()
        self.env["account.payment.register"].with_context(
            active_model="account.move", active_ids=anterior.ids,
        ).create({"journal_id": self.efectivo.id, "amount": 10.0})._create_payments()
        antes = self._foto()
        resultado = self._resultado(RUTA_CONFIRMAR, params)
        self.assertTrue(resultado["cambiaron"])
        self.assertEqual(resultado["cobro"]["total_saldo_anterior"], 20.0)
        self.assertEqual(self._foto(), antes)

    def test_borrador_del_cliente_se_rechaza_sin_crear_nada(self):
        borrador = self._entregada(self.cliente, [(self.pieza, 1)])._create_invoices()
        self._entregada(self.cliente, [(self.pieza, 2)])
        params = self._params()
        self.assertEqual(params["visto"]["borradores"], borrador.ids)
        antes = self._foto()
        self.assertEqual(self._error(params)["message"], AVISO_BORRADOR)
        self.assertEqual(self._foto(), antes)
        self.assertEqual(borrador.state, "draft")

    def test_falla_a_mitad_del_proceso_no_deja_nada(self):
        self._facturada(self.cliente, 30.0, fecha=self.hace_10_dias)
        self._nota_de_credito(self.cliente, 7.0)
        self._entregada(self.cliente, [(self.pieza, 2, 10.0)])
        params = self._params()
        antes = self._foto()
        Cobro = type(self.env["duran.captura.cobro"])
        # Falla al final: ya se facturó, se publicó y se aplicó el saldo a favor.
        with patch.object(Cobro, "create", side_effect=UserError("Falla forzada")):
            self.assertEqual(self._error(params)["message"], "Falla forzada")
        self.assertEqual(self._foto(), antes)
        # Con la falla corregida, el mismo envío funciona.
        self.assertFalse(self._resultado(RUTA_CONFIRMAR, params)["ya_existia"])

    def test_nada_que_cobrar(self):
        self._confirmada(self.cliente, [(self.pieza, 1)])  # sin entregar
        antes = self._foto()
        self.assertEqual(self._error(self._params())["message"], "Este cliente no tiene nada que cobrar.")
        self.assertEqual(self._foto(), antes)

    def test_tipo_de_pago_invalido(self):
        self._entregada(self.cliente, [(self.pieza, 1)])
        antes = self._foto()
        for tipo in ("fiado", "", None, 1):
            with self.subTest(tipo=tipo):
                self.assertIn("datos inválidos", self._error(self._params(tipo=tipo))["message"])
        self.assertEqual(self._foto(), antes)

    def test_datos_invalidos(self):
        self._entregada(self.cliente, [(self.pieza, 1)])
        antes = self._foto()
        for visto in (
            None, [], {"lineas": []}, {"lineas": [[1]], "documentos": [], "borradores": []},
            {"lineas": [["1", 1.0]], "documentos": [], "borradores": []},
            {"lineas": [], "documentos": [[1, True]], "borradores": []},
            {"lineas": [], "documentos": [], "borradores": ["x"]},
        ):
            with self.subTest(visto=visto):
                params = {**self._params(), "visto": visto}
                self.assertIn("datos inválidos", self._error(params)["message"])
        self.assertIn("No se pudo identificar el cobro", self._error({**self._params(), "token": "abc"})["message"])
        self.assertEqual(self._foto(), antes)

    def test_cliente_de_otra_zona(self):
        otra_zona = self._cliente("Cliente prueba cobro otra zona", self.env["res.partner.category"].create({
            "name": "Zona prueba cobro confirmar otra",
        }))
        self._entregada(otra_zona, [(self.pieza, 1)])
        params = {**self._params(), "cliente_id": otra_zona.id}
        antes = self._foto(otra_zona)
        self.assertIn("ya no está en la zona", self._error(params)["message"])
        self.assertEqual(self._foto(otra_zona), antes)

    # === Cambio de producto === #

    def test_cambio_de_producto_sobre_un_rollo_cobrado_con_no_pago_hoy(self):
        orden = self._entregada(self.cliente, [(self.rollo, 1)], pesos=[1.5])
        factura = self._registro(self._confirmar()).invoice_ids
        self.assertEqual((factura.amount_total, factura.payment_state), (75.0, "not_paid"))

        asistente = self.env["duran.cambio.producto"].with_context(active_id=orden.id).create({
            "sale_line_id": orden.order_line.id, "peso_devuelto": 0.5, "peso_nuevo": 2.0,
        })
        self.assertTrue(asistente.hay_lineas_elegibles)
        nueva = self.env["account.move"].browse(asistente.action_confirm()["res_id"])
        nota_credito = orden.invoice_ids.filtered(lambda m: m.move_type == "out_refund")
        self.assertEqual(nota_credito.amount_total, 0.5 * 50.0)
        self.assertEqual((nueva.amount_total, nueva.amount_residual), (2.0 * 50.0, 0.0))
        self.assertEqual(factura.amount_residual, 75.0, "La factura del cobro sigue pendiente")
