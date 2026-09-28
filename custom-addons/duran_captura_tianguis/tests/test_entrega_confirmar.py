""" Paso 5 (modo Entrega): confirmación de la entrega. """
import uuid
from unittest.mock import patch

from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import HttpCase, tagged

from .common import GRUPO_CAPTURA, CapturaDatosPrueba, CapturaHttpMixin

RUTA_PENDIENTE = "/captura/api/entrega/pendiente"
RUTA_VISTA_PREVIA = "/captura/api/entrega/vista_previa"
RUTA_CONFIRMAR = "/captura/api/entrega/confirmar"


@tagged("post_install", "-at_install")
class TestEntregaConfirmar(CapturaDatosPrueba, CapturaHttpMixin, HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._sin_gastar_folios()
        cls._crear_datos_captura()
        env = cls.env
        cls.mama = cls._usuario("confirmar_mama", GRUPO_CAPTURA)
        cls.otro_vendedor = cls._usuario("confirmar_otro_vendedor", "sales_team.group_sale_salesman")
        cls.sin_grupo = cls._usuario("confirmar_sin_grupo", "sales_team.group_sale_salesman")
        cls.otro_cliente = cls._cliente("Cliente prueba otra zona", env["res.partner.category"].create({
            "name": "Zona prueba otra",
        }))
        sin_impuestos = {"taxes_id": [Command.clear()]}
        cls.rollo = cls._plantilla(
            "Rollo prueba confirmar", es_peso_variable=True, precio_por_kg=85.5, **sin_impuestos,
        ).product_variant_id
        cls.pieza = cls._plantilla("Pieza prueba confirmar", **sin_impuestos).product_variant_id
        cls.almacenable = cls._plantilla(
            "Almacenable sin stock prueba", is_storable=True, **sin_impuestos,
        ).product_variant_id

    def setUp(self):
        super().setUp()
        self._entrar(self.mama)

    # === Ayudantes === #

    def _movimientos(self, orden, producto=None):
        movimientos = orden.picking_ids.move_ids.sorted("id")
        return movimientos.filtered(lambda m: m.product_id == producto) if producto else movimientos

    def _vistos(self, cliente=None):
        pendiente = self._resultado(RUTA_PENDIENTE, {
            "cliente_id": (cliente or self.cliente).id, "zona_id": self.zona_con_clientes.id,
        })
        return [m["move_id"] for p in pendiente["productos"] for m in p["movimientos"]]

    def _params(self, rollos=(), productos=(), vistos=None, token=None, cliente=None):
        return {
            "cliente_id": (cliente or self.cliente).id,
            "zona_id": self.zona_con_clientes.id,
            "rollos": [{"move_id": movimiento.id, "peso": peso} for movimiento, peso in rollos],
            "productos": [{"producto_id": producto.id, "cantidad": cantidad} for producto, cantidad in productos],
            "movimientos_vistos": self._vistos(cliente) if vistos is None else vistos,
            "token": token or uuid.uuid4().hex,
        }

    def _confirmar(self, **kwargs):
        return self._resultado(RUTA_CONFIRMAR, self._params(**kwargs))

    def _error(self, params):
        respuesta = self._jsonrpc(RUTA_CONFIRMAR, params)
        self.assertNotIn("result", respuesta)
        return respuesta["error"]["data"]

    def _foto(self, ordenes):
        """ Estado de entregas, movimientos, líneas y bitácora, para comprobar
        que un rechazo o una falla no dejan nada. """
        # Los mensajes de seguimiento de Odoo se crean al guardar (precommit).
        self.env.flush_all()
        self.env.cr.precommit.run()
        self.env.invalidate_all()
        movimientos = ordenes.picking_ids.move_ids
        return {
            "entregas": ordenes.picking_ids.mapped("state"),
            "movimientos": movimientos.read(["state", "quantity", "picked", "peso_real", "precio_por_kg"]),
            "lineas": ordenes.order_line.mapped("product_uom_qty"),
            "mensajes": len(ordenes.picking_ids.message_ids) + len(ordenes.message_ids),
            "bitacora": self.env["duran.captura.entrega"].search_count([]),
        }

    def _actividades(self, ordenes):
        Actividad = self.env["mail.activity"]
        return (
            Actividad.search_count([("res_model", "=", "sale.order"), ("res_id", "in", ordenes.ids)])
            + Actividad.search_count([("res_model", "=", "stock.picking"), ("res_id", "in", ordenes.picking_ids.ids)])
        )

    def _nota(self, picking):
        notas = picking.message_ids.filtered(lambda m: "captura del tianguis" in (m.body or ""))
        self.assertEqual(len(notas), 1)
        return notas.body

    # === Entrega completa: peso, precio congelado y factura === #

    def test_entrega_completa_llega_a_la_factura_con_el_total_de_la_vista_previa(self):
        orden = self._confirmada(self.cliente, [(self.rollo, 2), (self.pieza, 3, 12.345)], vendedor=self.otro_vendedor)
        r1, r2 = self._movimientos(orden, self.rollo)
        self.rollo.product_tmpl_id.precio_por_kg = 86.25  # sube después de pedir: cuenta el de hoy
        entrega = {"rollos": [(r1, "1.237"), (r2, "0,913")], "productos": [(self.pieza, 3)]}
        vista = self._resultado(RUTA_VISTA_PREVIA, {
            k: v for k, v in self._params(**entrega).items() if k not in ("movimientos_vistos", "token")
        })

        token = uuid.uuid4().hex
        resultado = self._confirmar(**entrega, token=token)
        self.assertEqual(resultado["total"], vista["total"])
        self.assertEqual(resultado["total_texto"], vista["total_texto"])
        self.assertEqual(
            resultado["entregas"],
            [{"folio": orden.picking_ids.name, "orden": orden.name, "estado": "validada"}],
        )
        self.assertFalse(resultado["ya_existia"])
        self.assertEqual(orden.picking_ids.state, "done")
        self.assertEqual((r1 | r2).mapped("peso_real"), [1.237, 0.913])
        self.assertEqual((r1 | r2).mapped("precio_por_kg"), [86.25, 86.25], "Precio congelado al validar")
        self.assertEqual(orden.amount_total, resultado["total"], "La orden muestra el monto de la vista previa")

        self.rollo.product_tmpl_id.precio_por_kg = 99.0  # sube otra vez antes de facturar
        self.assertEqual(orden.amount_total, resultado["total"], "El precio congelado no cambia")
        factura = orden._create_invoices()
        self.assertEqual(factura.amount_total, resultado["total"])
        rollos = factura.invoice_line_ids.filtered("es_peso_variable")
        self.assertEqual(rollos.mapped("peso_real"), [1.237, 0.913])
        self.assertEqual(rollos.mapped("precio_por_kg"), [86.25, 86.25])

        registro = self.env["duran.captura.entrega"].browse(resultado["id"])
        self.assertEqual(
            (registro.token, registro.user_id, registro.partner_id, registro.zona_id, registro.total),
            (token, self.mama, self.cliente, self.zona_con_clientes, resultado["total"]),
        )
        self.assertEqual(registro.total, orden.amount_total, "Bitácora = orden = vista previa = factura")
        self.assertEqual((registro.picking_ids, registro.order_ids), (orden.picking_ids, orden))
        self.assertEqual(
            [(l.product_id, l.cantidad, l.peso_real, l.precio_unitario) for l in registro.linea_ids],
            [(self.rollo, 1, 1.237, 86.25), (self.rollo, 1, 0.913, 86.25), (self.pieza, 3, 0.0, 12.345)],
        )
        # Cada renglón, igual que su línea de factura (redondeada por separado,
        # como en la factura: pueden no sumar el total por un centavo).
        for linea in registro.linea_ids:
            linea_factura = factura.invoice_line_ids.filtered(lambda l: linea.sale_line_id in l.sale_line_ids)
            self.assertAlmostEqual(linea.importe, linea_factura.price_total, places=6)
        self.assertEqual(self._actividades(orden), 0)
        self.assertFalse(orden.picking_ids.message_ids.filtered(lambda m: "captura del tianguis" in (m.body or "")),
                         "Entrega completa y con existencia: sin nota")

    # === Parcial, nada entregado, sin existencia === #

    def test_entrega_parcial_cancela_lo_demas_sin_backorder(self):
        orden = self._confirmada(self.cliente, [(self.rollo, 2), (self.pieza, 3, 10.0)], vendedor=self.otro_vendedor)
        r1, r2 = self._movimientos(orden, self.rollo)
        (pieza,) = self._movimientos(orden, self.pieza)
        mensajes_antes = orden.message_ids
        # El precio de lista sube después de pedir: al bajar la cantidad, la
        # línea NO se vuelve a tarifar (sigue a $10, como en el total mostrado).
        self.pieza.product_tmpl_id.list_price = 15.0

        self._confirmar(rollos=[(r1, "1.5")], productos=[(self.pieza, 2)])
        self.assertEqual(len(orden.picking_ids), 1, "Sin backorder")
        self.assertEqual(orden.picking_ids.state, "done")
        self.assertEqual((r1.state, r2.state, pieza.state, pieza.quantity), ("done", "cancel", "done", 2.0))

        lineas = orden.order_line.sorted("id")
        self.assertEqual(lineas.mapped("product_uom_qty"), [1.0, 0.0, 2.0], "Cantidad pedida = entregada")
        self.assertEqual(lineas[2].price_unit, 10.0)
        nuevos = orden.message_ids - mensajes_antes
        self.assertEqual(nuevos.author_id, self.mama.partner_id, "Registro en el historial a su nombre")
        cuerpos = " ".join(nuevos.mapped("body"))
        self.assertIn("3.0 -&gt; 2.0", cuerpos, "Pieza: de 3 a 2")
        self.assertIn("1.0 -&gt; 0.0", cuerpos, "Rollo no entregado: de 1 a 0")

        nota = self._nota(orden.picking_ids)
        self.assertIn("entregado 0 de 1", nota)
        self.assertIn("entregado 2 de 3", nota)
        self.assertEqual(self._actividades(orden), 0, "Sin actividades")

        factura = orden._create_invoices()
        factura.action_post()
        self.assertEqual(factura.amount_total, 1.5 * 85.5 + 2 * 10.0)
        self.assertEqual(orden.invoice_status, "invoiced", "Con la cantidad bajada, la orden queda Facturada")

    def test_orden_sin_nada_entregado_se_cancela_completa(self):
        o1 = self._confirmada(self.cliente, [(self.pieza, 2)])
        o2 = self._confirmada(self.cliente, [(self.rollo, 1), (self.pieza, 1)])
        resultado = self._confirmar(productos=[(self.pieza, 2)])
        self.assertEqual((o1.picking_ids.state, o2.picking_ids.state), ("done", "cancel"))
        self.assertEqual(o2.order_line.mapped("product_uom_qty"), [0.0, 0.0])
        self.assertEqual([e["estado"] for e in resultado["entregas"]], ["validada", "cancelada"])
        self.assertIn("no se llevó nada", self._nota(o2.picking_ids))
        self.assertEqual(self._actividades(o1 | o2), 0)

    def test_cliente_que_no_se_lleva_nada(self):
        orden = self._confirmada(self.cliente, [(self.rollo, 1), (self.pieza, 2)])
        resultado = self._confirmar()
        self.assertEqual((orden.picking_ids.state, resultado["total"]), ("cancel", 0.0))
        self.assertEqual(orden.order_line.mapped("product_uom_qty"), [0.0, 0.0])
        self.assertEqual(self.env["duran.captura.entrega"].browse(resultado["id"]).linea_ids.ids, [])

    def test_producto_sin_existencia(self):
        orden = self._confirmada(self.cliente, [(self.almacenable, 2)])
        self.assertEqual(self.almacenable.qty_available, 0)
        resultado = self._confirmar(productos=[(self.almacenable, 2)])
        self.assertEqual(orden.picking_ids.state, "done")
        self.almacenable.invalidate_recordset()
        self.assertEqual(self.almacenable.qty_available, -2, "Existencias en negativo")
        nota = self._nota(orden.picking_ids)
        self.assertIn("sin existencia en sistema", nota)
        self.assertIn("Almacenable sin stock prueba: 2", nota)
        registro = self.env["duran.captura.entrega"].browse(resultado["id"])
        self.assertEqual(registro.linea_ids.sin_existencia, True)

    # === Reparto entre órdenes === #

    def test_reparto_de_la_orden_mas_antigua_a_la_mas_nueva(self):
        ordenes = [self._confirmada(self.cliente, [(self.pieza, cantidad)]) for cantidad in (3, 2, 4)]
        self._confirmar(productos=[(self.pieza, 6)])
        self.assertEqual([self._movimientos(o).quantity for o in ordenes], [3.0, 2.0, 1.0])
        self.assertEqual([o.picking_ids.state for o in ordenes], ["done", "done", "done"])
        self.assertEqual([o.order_line.product_uom_qty for o in ordenes], [3.0, 2.0, 1.0])
        self.assertIn("entregado 1 de 4", self._nota(ordenes[2].picking_ids))

    # === Lo de siempre === #

    def test_lo_de_siempre_ignora_lineas_en_cero(self):
        orden = self._confirmada(self.cliente, [(self.rollo, 1), (self.pieza, 2)])
        Captura = self.env["duran.captura"].with_user(self.mama)
        self.assertIn(self.pieza.id, [p["id"] for p in Captura.get_habituales(self.cliente.id)])
        self._confirmar(rollos=[(self._movimientos(orden, self.rollo), "1.1")])
        self.assertEqual(orden.order_line.filtered(lambda l: l.product_id == self.pieza).product_uom_qty, 0)
        habituales = [p["id"] for p in Captura.get_habituales(self.cliente.id)]
        self.assertNotIn(self.pieza.id, habituales)
        self.assertIn(self.rollo.id, habituales)

    # === Doble envío, cambios de otra persona y fallas === #

    def test_doble_envio_con_el_mismo_token(self):
        orden = self._confirmada(self.cliente, [(self.pieza, 3)])
        params = self._params(productos=[(self.pieza, 2)])
        bitacora_antes = self.env["duran.captura.entrega"].search_count([])  # la base puede tener entregas reales
        primero = self._resultado(RUTA_CONFIRMAR, params)
        segundo = self._resultado(RUTA_CONFIRMAR, params)
        self.assertTrue(segundo["ya_existia"])
        self.assertEqual({**primero, "ya_existia": True}, segundo)
        self.assertEqual(self.env["duran.captura.entrega"].search_count([]), bitacora_antes + 1)
        self.assertEqual(self.env["duran.captura.entrega"].search_count([("token", "=", params["token"])]), 1)
        self.assertEqual(len(orden.picking_ids), 1)
        self.assertEqual(self._movimientos(orden).quantity, 2.0, "Validada una sola vez")

    def test_entrega_validada_por_otra_persona_se_rechaza_sin_cambios(self):
        o1 = self._confirmada(self.cliente, [(self.pieza, 2)])
        o2 = self._confirmada(self.cliente, [(self.rollo, 1)])
        params = self._params(rollos=[(self._movimientos(o2), "1.2")], productos=[(self.pieza, 2)])
        self._validar(o1.picking_ids)  # alguien más la valida desde Odoo
        antes = self._foto(o1 | o2)
        self.assertIn("cambiaron desde que se cargaron", self._error(params)["message"])
        self.assertEqual(self._foto(o1 | o2), antes)

    def test_entrega_cancelada_o_modificada_por_otra_persona(self):
        o1 = self._confirmada(self.cliente, [(self.pieza, 2)])
        o2 = self._confirmada(self.cliente, [(self.pieza, 1)])
        params = self._params(productos=[(self.pieza, 3)])
        o2.picking_ids.action_cancel()
        self.assertIn("cambiaron", self._error(params)["message"])
        params = self._params(productos=[(self.pieza, 2)])
        o1.order_line = [Command.create({"product_id": self.almacenable.id, "product_uom_qty": 1})]
        self.assertEqual(len(o1.picking_ids.move_ids), 2, "La línea nueva cae en la misma entrega")
        antes = self._foto(o1)
        self.assertIn("cambiaron", self._error(params)["message"])
        self.assertEqual(self._foto(o1), antes)

    def test_entrega_nueva_que_la_pantalla_no_mostro_no_se_toca(self):
        o1 = self._confirmada(self.cliente, [(self.pieza, 2)])
        params = self._params(productos=[(self.pieza, 2)])
        nueva = self._confirmada(self.cliente, [(self.pieza, 5)])
        resultado = self._resultado(RUTA_CONFIRMAR, params)
        self.assertEqual([e["folio"] for e in resultado["entregas"]], [o1.picking_ids.name])
        self.assertEqual((nueva.picking_ids.state, nueva.order_line.product_uom_qty), ("assigned", 5.0))

    def test_falla_a_mitad_del_proceso_no_deja_nada(self):
        o1 = self._confirmada(self.cliente, [(self.rollo, 2), (self.pieza, 3)], vendedor=self.otro_vendedor)
        o2 = self._confirmada(self.cliente, [(self.pieza, 1)])
        r1, _r2 = self._movimientos(o1, self.rollo)
        params = self._params(rollos=[(r1, "1.3")], productos=[(self.pieza, 2)])
        antes = self._foto(o1 | o2)
        Entrega = type(self.env["duran.captura.entrega"])
        # Falla al final: ya se validaron las entregas y se bajaron las cantidades.
        with patch.object(Entrega, "create", side_effect=UserError("Falla forzada")):
            self.assertEqual(self._error(params)["message"], "Falla forzada")
        self.assertEqual(self._foto(o1 | o2), antes)
        # Con la falla corregida, el mismo envío funciona.
        self.assertFalse(self._resultado(RUTA_CONFIRMAR, params)["ya_existia"])

    def test_peso_bloqueado_se_rechaza_aunque_la_pantalla_lo_mande(self):
        orden = self._confirmada(self.cliente, [(self.rollo, 1)])
        antes = self._foto(orden)
        for peso in ("1250", "0", "abc"):
            with self.subTest(peso=peso):
                error = self._error(self._params(rollos=[(self._movimientos(orden), peso)]))
                self.assertIn("Corrige el peso", error["message"])
        self.assertEqual(self._foto(orden), antes)

    def test_revalida_como_la_vista_previa(self):
        orden = self._confirmada(self.cliente, [(self.rollo, 1), (self.pieza, 2)])
        rollo = self._movimientos(orden, self.rollo)
        casos = [
            ({"productos": [(self.pieza, 3)]}, "solo hay 2 pendientes"),
            ({"productos": [(self.pieza, 1.5)]}, "enteros"),
            ({"rollos": [(rollo, "1"), (rollo, "1")]}, "dos veces"),
        ]
        for kwargs, mensaje in casos:
            with self.subTest(kwargs=str(kwargs)):
                self.assertIn(mensaje, self._error(self._params(**kwargs))["message"])
        for token in ("", "abc", uuid.uuid4().hex.upper(), None):
            with self.subTest(token=token):
                params = self._params()
                params["token"] = token
                self.assertIn("No se pudo identificar la entrega", self._error(params)["message"])
        for vistos in ([], "x", [True], [str(rollo.id)]):
            with self.subTest(vistos=vistos):
                self.assertEqual(self._error(self._params(vistos=vistos))["name"], "odoo.exceptions.UserError")

    # === Cambio de producto sobre lo entregado desde la app === #

    def test_cambio_de_producto_sobre_un_rollo_entregado_desde_la_app(self):
        orden = self._confirmada(self.cliente, [(self.rollo, 1)])
        self._confirmar(rollos=[(self._movimientos(orden), "1.5")])
        factura = orden._create_invoices()
        factura.action_post()
        self.assertEqual(factura.amount_total, 1.5 * 85.5)

        asistente = self.env["duran.cambio.producto"].with_context(active_id=orden.id).create({
            "sale_line_id": orden.order_line.id, "peso_devuelto": 0.5, "peso_nuevo": 2.0,
        })
        self.assertTrue(asistente.hay_lineas_elegibles)
        nueva = self.env["account.move"].browse(asistente.action_confirm()["res_id"])
        nota_credito = orden.invoice_ids.filtered(lambda m: m.move_type == "out_refund")
        self.assertEqual(nota_credito.amount_total, 0.5 * 85.5)
        self.assertEqual((nueva.amount_total, nueva.amount_residual), (2.0 * 85.5, 0.0))

    # === Permisos y alcance del sudo === #

    def test_sudo_solo_escribe_la_cantidad_de_las_lineas_de_esta_entrega(self):
        """ (1) solo product_uom_qty (la captura) y peso_real + precio_por_kg
        (duran_peso_variable, al validar un rollo), (2) solo en las líneas de
        los movimientos validados o cancelados en esta entrega, aunque la
        pantalla mande otros datos; los demás campos de esas líneas no
        cambian. """
        o1 = self._confirmada(self.cliente, [(self.rollo, 2), (self.pieza, 3, 12.5)], vendedor=self.otro_vendedor)
        otra = self._confirmada(self.otro_cliente, [(self.pieza, 4)], vendedor=self.otro_vendedor)
        r1, _r2 = self._movimientos(o1, self.rollo)
        params = self._params(rollos=[(r1, "1.2")], productos=[(self.pieza, 2)])
        # Datos de más que la pantalla no debería mandar: se ignoran.
        params["rollos"][0].update({"product_uom_qty": 9, "price_unit": 0, "sale_line_id": otra.order_line.id})
        params["productos"][0].update({"price_unit": 0, "discount": 50, "order_id": otra.id})
        params["sale_line_ids"] = otra.order_line.ids
        params["product_uom_qty"] = 0
        nueva = self._confirmada(self.cliente, [(self.pieza, 5)], vendedor=self.otro_vendedor)
        self.pieza.product_tmpl_id.list_price = 99.0  # no debe re-tarifar al bajar la cantidad
        campos = ["price_unit", "discount", "tax_ids", "name", "product_id", "product_uom_id"]
        pieza_linea = o1.order_line.filtered(lambda l: l.product_id == self.pieza)
        antes = pieza_linea.read(campos)

        escrituras = []
        SaleOrderLine = type(self.env["sale.order.line"])
        write = SaleOrderLine.write

        def espiar(lineas, vals):
            escrituras.append((set(lineas.ids), set(vals), lineas.env.su, lineas.env.uid))
            return write(lineas, vals)

        with patch.object(SaleOrderLine, "write", espiar):
            self._resultado(RUTA_CONFIRMAR, params)

        self.assertTrue(escrituras)
        rollo_validado = r1.sale_line_id
        for ids, campos_escritos, su, uid in escrituras:
            self.assertIn(campos_escritos, ({"product_uom_qty"}, {"peso_real", "precio_por_kg"}))
            if campos_escritos != {"product_uom_qty"}:
                self.assertEqual(ids, set(rollo_validado.ids), "Peso y precio: solo el rollo validado")
            self.assertTrue(ids <= set(o1.order_line.ids))
            self.assertEqual((su, uid), (True, self.mama.id))
        o1.order_line.invalidate_recordset()
        self.assertEqual(pieza_linea.read(campos), antes)
        self.assertEqual((rollo_validado.peso_real, rollo_validado.price_unit), (1.2, 1.2 * 85.5))
        self.assertEqual(o1.order_line.sorted("id").mapped("product_uom_qty"), [1.0, 0.0, 2.0])
        self.assertEqual((otra.order_line.product_uom_qty, otra.picking_ids.state), (4.0, "assigned"))
        self.assertEqual((nueva.order_line.product_uom_qty, nueva.picking_ids.state), (5.0, "assigned"))

    def test_mensaje_del_historial_a_nombre_de_la_mama(self):
        orden = self._confirmada(self.cliente, [(self.pieza, 3)], vendedor=self.otro_vendedor)
        with self.assertRaises(AccessError, msg="Con sus permisos no puede escribir la orden"):
            orden.order_line.with_user(self.mama).write({"product_uom_qty": 2})
        antes = orden.message_ids
        self._confirmar(productos=[(self.pieza, 2)])
        nuevos = orden.message_ids - antes
        cantidad = nuevos.filtered(lambda m: "3.0 -&gt; 2.0" in (m.body or ""))
        self.assertEqual(len(cantidad), 1)
        self.assertEqual((nuevos.author_id, nuevos.create_uid), (self.mama.partner_id, self.mama))

    def test_no_confirma_fuera_de_la_zona_ni_del_filtro(self):
        propia = self._confirmada(self.cliente, [(self.pieza, 1)])
        ajena = self._confirmada(self.otro_cliente, [(self.pieza, 1)])
        entregada = self._confirmada(self.cliente, [(self.pieza, 1)])
        self._validar(entregada.picking_ids)
        antes = self._foto(propia | ajena)
        # Cliente de otra zona.
        params = self._params(cliente=self.otro_cliente, vistos=self._movimientos(ajena).ids)
        self.assertIn("ya no está en la zona", self._error(params)["message"])
        # Movimientos fuera del filtro del cliente: de otro cliente o ya entregados.
        for movimiento in (self._movimientos(ajena), self._movimientos(entregada)):
            with self.subTest(movimiento=movimiento.picking_id.name):
                params = self._params(vistos=self._movimientos(propia).ids + movimiento.ids)
                self.assertIn("cambiaron", self._error(params)["message"])
                params = self._params(rollos=[(movimiento, "1")])
                self.assertEqual(self._error(params)["name"], "odoo.exceptions.UserError")
        self.assertEqual(self._foto(propia | ajena), antes)

    def test_sin_grupo_y_sin_sesion(self):
        orden = self._confirmada(self.cliente, [(self.pieza, 1)])
        params = self._params(productos=[(self.pieza, 1)])
        antes = self._foto(orden)
        self._entrar(self.sin_grupo)
        self.assertEqual(self._error(params)["name"], "odoo.exceptions.AccessError")
        self.authenticate(None, None)
        respuesta = self._jsonrpc(RUTA_CONFIRMAR, params)
        self.assertNotIn("result", respuesta)
        self.assertEqual(respuesta["error"]["code"], 100)
        self.assertEqual(self._foto(orden), antes)
