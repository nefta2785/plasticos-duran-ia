""" Paso 4 (modo Cobro): "Pagó todo" y "Pagó una parte": un pago en efectivo
aplicado a las facturas abiertas del cliente. """
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import HttpCase, tagged

from .test_cobro_confirmar import RUTA_CONFIRMAR, CobroDatosPrueba


@tagged("post_install", "-at_install")
class TestCobroPago(CobroDatosPrueba, HttpCase):

    def _cliente_100_y_300(self, nombre):
        """ Saldo anterior de $100 (hace 10 días) y $300 entregados hoy. """
        cliente = self._cliente(nombre, self.zona_con_clientes)
        anterior = self._facturada(cliente, 100.0, fecha=self.hace_10_dias)
        orden = self._entregada(cliente, [(self.pieza, 3, 100.0)])
        return cliente, anterior, orden

    def _pago(self, registro):
        return registro.payment_id.sudo()

    # === Estados por factura === #

    def test_estados_por_factura(self):
        casos = [
            # (tipo, monto, anterior: estado y saldo, de hoy: estado y saldo)
            ("todo", None, ("paid", 0.0), ("paid", 0.0)),
            ("parte", 400, ("paid", 0.0), ("paid", 0.0)),
            ("parte", 250, ("paid", 0.0), ("partial", 150.0)),
            ("parte", 50, ("partial", 50.0), ("not_paid", 300.0)),
        ]
        for numero, (tipo, monto, esperado_anterior, esperado_hoy) in enumerate(casos):
            with self.subTest(tipo=tipo, monto=monto):
                cliente, anterior, orden = self._cliente_100_y_300(f"Cliente prueba pago {numero}")
                self.assertEqual(self._detalle(cliente)["total_a_cobrar"], 400.0)
                resultado = self._confirmar(cliente=cliente, tipo=tipo, monto=monto)
                registro = self._registro(resultado)
                hoy = registro.invoice_ids
                self.assertEqual(hoy.invoice_line_ids.sale_line_ids.order_id, orden)
                self.assertEqual((anterior.payment_state, anterior.amount_residual), esperado_anterior)
                self.assertEqual((hoy.payment_state, hoy.amount_residual), esperado_hoy)
                recibido = 400.0 if monto is None else float(monto)
                self.assertEqual(
                    (registro.tipo, registro.total_a_cobrar, registro.monto_recibido, registro.saldo_pendiente),
                    (tipo, 400.0, recibido, 400.0 - recibido),
                )
                self.assertEqual(
                    [(l.move_id, l.tipo, l.saldo_antes, l.aplicado, l.saldo_despues) for l in registro.linea_ids],
                    [
                        (hoy, "nueva", 300.0, 300.0 - esperado_hoy[1], esperado_hoy[1]),
                        (anterior, "anterior", 100.0, 100.0 - esperado_anterior[1], esperado_anterior[1]),
                    ],
                )
                self.assertEqual(self._pago(registro).amount, recibido)
                self.assertEqual(
                    (resultado["monto_recibido"], resultado["saldo_pendiente"]), (recibido, 400.0 - recibido),
                )
                self.assertEqual(cliente.sudo().credit, 400.0 - recibido, "Lo que Odoo dice que debe")

    def test_lo_pendiente_es_saldo_anterior_en_el_siguiente_cobro(self):
        cliente, _anterior, _orden = self._cliente_100_y_300("Cliente prueba pago siguiente")
        hoy = self._registro(self._confirmar(cliente=cliente, tipo="parte", monto=250)).invoice_ids
        siguiente = self._detalle(cliente)
        self.assertEqual(siguiente["entregado"], [])
        self.assertEqual([(d["move_id"], d["saldo"]) for d in siguiente["saldo_anterior"]], [(hoy.id, 150.0)])
        self.assertEqual((siguiente["total_a_cobrar"], siguiente["puede_cobrar"]), (150.0, True))
        # Y se le puede cobrar lo que queda.
        registro = self._registro(self._confirmar(cliente=cliente, tipo="todo"))
        self.assertFalse(registro.invoice_ids)
        self.assertEqual((registro.monto_recibido, registro.saldo_pendiente, hoy.payment_state), (150.0, 0.0, "paid"))

    def test_pago_todo_con_saldo_a_favor(self):
        """ El saldo a favor se aplica primero; se cobra solo lo que falta. """
        anterior = self._facturada(self.cliente, 30.0, fecha=self.hace_10_dias)
        nota = self._nota_de_credito(self.cliente, 7.0)
        self._entregada(self.cliente, [(self.pieza, 2, 10.0)])
        registro = self._registro(self._confirmar(tipo="todo"))
        self.assertEqual((registro.total_a_cobrar, registro.monto_recibido, registro.saldo_pendiente), (43.0, 43.0, 0.0))
        self.assertEqual(self._pago(registro).amount, 43.0)
        self.assertEqual(
            [(l.move_id, l.aplicado, l.saldo_despues) for l in registro.linea_ids],
            [(registro.invoice_ids, 20.0, 0.0), (anterior, 30.0, 0.0), (nota, 7.0, 0.0)],
        )

    # === Montos === #

    def test_montos_invalidos_se_rechazan_sin_crear_nada(self):
        cliente, _anterior, _orden = self._cliente_100_y_300("Cliente prueba pago montos")
        antes = self._foto(cliente)
        casos = [
            (400.01, "es más que el total a cobrar"),
            (1000, "es más que el total a cobrar"),
            (0, "mayor a $0"),
            (-5, "mayor a $0"),
            (12.345, "máximo 2 decimales"),
            ("100", "mayor a $0"),
            (True, "mayor a $0"),
            (None, "mayor a $0"),
        ]
        for monto, mensaje in casos:
            with self.subTest(monto=monto):
                params = self._params(cliente=cliente, tipo="parte")
                params["monto"] = monto
                self.assertIn(mensaje, self._error(params)["message"])
        self.assertEqual(self._foto(cliente), antes)
        # Justo el total, con centavos: sí.
        self._facturada(cliente, 0.5)
        registro = self._registro(self._confirmar(cliente=cliente, tipo="parte", monto=400.5))
        self.assertEqual((registro.monto_recibido, registro.saldo_pendiente), (400.5, 0.0))

    # === Diario de efectivo === #

    def test_debe_haber_exactamente_un_diario_de_efectivo(self):
        self._entregada(self.cliente, [(self.pieza, 1)])
        antes = self._foto()
        otro = self.env["account.journal"].create({"name": "Efectivo 2 prueba", "code": "CPR2", "type": "cash"})
        mensaje = self._error(self._params(tipo="todo"))["message"]
        self.assertIn("exactamente un diario de tipo Efectivo, y hay 2", mensaje)
        self.assertIn("Facturación › Configuración › Contabilidad › Diarios", mensaje, "la ruta real del menú")
        self.assertEqual(self._foto(), antes)
        (self.efectivo | otro).action_archive()
        mensaje = self._error(self._params(tipo="parte", monto=5))["message"]
        self.assertIn("exactamente un diario de tipo Efectivo, y hay 0", mensaje)
        self.assertEqual(self._foto(), antes)
        # "No pagó hoy" no necesita el diario.
        self.assertFalse(self._registro(self._confirmar()).payment_id)

    # === Permiso acotado === #

    def test_pago_solo_en_efectivo_y_sobre_lo_del_cliente(self):
        anterior = self._facturada(self.cliente, 30.0, fecha=self.hace_10_dias)
        self._entregada(self.cliente, [(self.pieza, 2, 10.0)])
        factura_ajena = self._facturada(self.otro_cliente, 9.0)
        banco = self.env["account.journal"].search([("type", "=", "bank")], limit=1)
        antes_ajeno = self._foto(self.otro_cliente)
        del antes_ajeno["conciliaciones"], antes_ajeno["cobros"]

        params = self._params(tipo="parte", monto=35)
        # Datos de más que la pantalla no debería mandar: se ignoran.
        params.update({
            "journal_id": banco.id, "diario_id": banco.id, "line_ids": self._receivable(factura_ajena).ids,
            "factura_ids": factura_ajena.ids, "partner_id": self.otro_cliente.id,
        })
        llamadas = []
        Asistente = type(self.env["account.payment.register"])
        create_payments = Asistente._create_payments

        def espiar(asistente):
            llamadas.append({
                "diario": asistente.journal_id.id, "lineas": set(asistente.line_ids.ids),
                "monto": asistente.amount, "agrupar": asistente.group_payment,
                "diferencia": asistente.payment_difference_handling,
                "su": asistente.env.su, "uid": asistente.env.uid,
            })
            return create_payments(asistente)

        with patch.object(Asistente, "_create_payments", espiar):
            registro = self._registro(self._resultado(RUTA_CONFIRMAR, params))

        hoy = registro.invoice_ids
        self.assertEqual(llamadas, [{
            "diario": self.efectivo.id, "lineas": set(self._receivable(anterior | hoy).ids), "monto": 35.0,
            "agrupar": True, "diferencia": "open", "su": True, "uid": self.mama.id,
        }])
        pago = self._pago(registro)
        self.assertEqual((pago.journal_id, pago.partner_id, pago.payment_type), (self.efectivo, self.cliente, "inbound"))
        self.assertEqual(
            self._receivable(pago.move_id).matched_debit_ids.debit_move_id, self._receivable(anterior | hoy),
        )
        self.assertEqual((anterior.payment_state, hoy.amount_residual), ("paid", 15.0))
        despues_ajeno = self._foto(self.otro_cliente)
        del despues_ajeno["conciliaciones"], despues_ajeno["cobros"]
        self.assertEqual(despues_ajeno, antes_ajeno, "Lo del otro cliente, intacto")

    def test_creado_por_fecha_y_referencia_del_pago(self):
        self._entregada(self.cliente, [(self.pieza, 1)])
        registro = self._registro(self._confirmar(tipo="todo"))
        pago = self._pago(registro)
        self.assertEqual(pago.create_uid, self.mama)
        self.assertEqual(pago.date, fields.Date.context_today(pago))
        self.assertEqual(pago.memo, f"Cobro en tianguis #{registro.id}")
        self.assertEqual(pago.move_id.ref, pago.memo)
        self.assertEqual(pago.state, "paid")

    # === Cambios desde Odoo, doble toque y fallas === #

    def test_pago_registrado_desde_odoo_entre_lectura_y_confirmacion(self):
        anterior = self._facturada(self.cliente, 30.0)
        self._entregada(self.cliente, [(self.pieza, 1)])
        for tipo, monto in (("todo", None), ("parte", 5)):
            with self.subTest(tipo=tipo):
                params = self._params(tipo=tipo, monto=monto)
                self._pagar_desde_odoo(anterior, 1.0)
                antes = self._foto()
                resultado = self._resultado(RUTA_CONFIRMAR, params)
                self.assertTrue(resultado["cambiaron"])
                self.assertEqual(resultado["cobro"], self._detalle())
                self.assertEqual(self._foto(), antes)

    def _pagar_desde_odoo(self, factura, monto):
        self.env["account.payment.register"].with_context(
            active_model="account.move", active_ids=factura.ids,
        ).create({"journal_id": self.efectivo.id, "amount": monto})._create_payments()

    def test_doble_toque_un_solo_pago(self):
        self._entregada(self.cliente, [(self.pieza, 1)])
        params = self._params(tipo="parte", monto=4)
        primero = self._resultado(RUTA_CONFIRMAR, params)
        segundo = self._resultado(RUTA_CONFIRMAR, params)
        self.assertTrue(segundo["ya_existia"])
        self.assertEqual({**primero, "ya_existia": True}, segundo)
        self.assertEqual(self._foto()["pagos"], 1)

    def test_falla_despues_de_crear_el_pago_no_deja_nada(self):
        self._facturada(self.cliente, 30.0, fecha=self.hace_10_dias)
        self._nota_de_credito(self.cliente, 7.0)
        self._entregada(self.cliente, [(self.pieza, 2, 10.0)])
        params = self._params(tipo="parte", monto=25)
        antes = self._foto()
        Cobro = type(self.env["duran.captura.cobro"])
        # Falla al registrar la bitácora: ya se facturó, se aplicó el saldo a favor y se creó el pago.
        with patch.object(Cobro, "create", side_effect=UserError("Falla forzada")):
            self.assertEqual(self._error(params)["message"], "Falla forzada")
        self.assertEqual(self._foto(), antes)
        # Con la falla corregida, el mismo envío funciona.
        self.assertEqual(self._registro(self._resultado(RUTA_CONFIRMAR, params)).monto_recibido, 25.0)

    # === Arqueo === #

    def test_arqueo_del_dia(self):
        """ El efectivo recibido de la bitácora del día = los pagos en el diario
        de efectivo creados por quien cobra ese día. Un pago hecho por otra
        persona no cuenta. """
        for numero, (tipo, monto) in enumerate((("todo", None), ("parte", 120.5), ("nada", None), ("parte", 0.01))):
            cliente, _anterior, _orden = self._cliente_100_y_300(f"Cliente prueba arqueo {numero}")
            self._confirmar(cliente=cliente, tipo=tipo, monto=monto)
        self._pagar_desde_odoo(self._facturada(self.cliente, 50.0), 50.0)  # lo cobró otra persona

        hoy = fields.Date.context_today(self.env["res.partner"])
        cobros = self.env["duran.captura.cobro"].search([("user_id", "=", self.mama.id)]).filtered(
            lambda c: fields.Datetime.context_timestamp(c, c.fecha).date() == hoy
        )
        pagos = self.env["account.payment"].search([
            ("journal_id", "=", self.efectivo.id), ("create_uid", "=", self.mama.id), ("date", "=", hoy),
        ])
        self.assertEqual(len(cobros), 4)
        self.assertEqual(len(pagos), 3)
        self.assertAlmostEqual(sum(cobros.mapped("monto_recibido")), 400.0 + 120.5 + 0.01, places=2)
        self.assertAlmostEqual(sum(cobros.mapped("monto_recibido")), sum(pagos.mapped("amount")), places=2)
        self.assertEqual(pagos, cobros.payment_id)
