""" Al validar una entrega, el peso real y el precio por kg congelado del rollo
pasan a su línea de venta, para que la orden muestre el monto real. """
from unittest.mock import patch

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged

from .common import PesoVariableDatosPrueba


@tagged("post_install", "-at_install")
class TestSincronizarLinea(PesoVariableDatosPrueba, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._crear_datos()
        usuario = lambda login, groups: new_test_user(  # noqa: E731
            cls.env, login=login, groups=groups, context={"no_reset_password": True},
        )
        cls.vendedor = usuario("sinc_vendedor", "sales_team.group_sale_salesman")
        cls.otro_vendedor = usuario("sinc_otro_vendedor", "sales_team.group_sale_salesman")
        cls.almacen = usuario("sinc_almacen", "stock.group_stock_user")

    def _rollos(self, orden):
        return orden.order_line.filtered("es_peso_variable").sorted("id")

    def _validar_como(self, usuario, orden, pesos):
        picking = orden.picking_ids.with_user(usuario)
        for move, peso in zip(picking.move_ids.filtered("es_peso_variable").sorted("id"), pesos):
            move.write({"quantity": 1, "picked": True, "peso_real": peso})
        for move in picking.move_ids.filtered(lambda m: not m.es_peso_variable):
            move.write({"quantity": move.product_uom_qty, "picked": True})
        picking.button_validate()
        self.assertEqual(picking.state, "done")

    def _recalcular_precio(self, lineas):
        """ Fuerza el recálculo del precio (como lo haría cualquier cambio que
        dispare `_compute_price_unit`). """
        lineas.invalidate_recordset(["price_unit"])
        self.env.add_to_compute(lineas._fields["price_unit"], lineas)
        lineas.flush_recordset()

    # === Sincronización === #

    def test_validar_desde_odoo_sincroniza_la_linea(self):
        orden = self._orden([(self.rollo, 2), (self.normal, 2)])
        self.assertEqual(self._rollos(orden).mapped("price_unit"), [0.0, 0.0], "Sin peso, en $0")
        self.assertEqual(orden.amount_total, 60.0)
        self._entregar(orden, pesos=[1.25, 0.8])
        rollos = self._rollos(orden)
        self.assertEqual(rollos.mapped("peso_real"), [1.25, 0.8])
        self.assertEqual(rollos.mapped("precio_por_kg"), [50.0, 50.0])
        self.assertEqual(rollos.mapped("price_unit"), [62.5, 40.0])
        self.assertEqual(orden.amount_total, 62.5 + 40.0 + 60.0)
        factura = self._facturar(orden)
        self.assertEqual(factura.amount_total, orden.amount_total, "La orden muestra lo que se factura")

    def test_la_factura_sale_igual(self):
        """ La factura sigue tomando peso y precio del movimiento: mismo
        resultado que antes de sincronizar la línea. """
        orden = self._orden([(self.rollo, 1)])
        picking = self._entregar(orden, pesos=[1.237])
        self.plantilla_rollo.precio_por_kg = 80.0
        linea_factura = self._facturar(orden).invoice_line_ids
        self.assertEqual(
            (linea_factura.peso_real, linea_factura.precio_por_kg, linea_factura.price_unit),
            (picking.move_ids.peso_real, picking.move_ids.precio_por_kg, 1.237 * 50.0),
        )

    def test_cambiar_el_precio_despues_no_cambia_la_linea(self):
        orden = self._orden([(self.rollo, 1)])
        self._entregar(orden, pesos=[1.25])
        linea = self._rollos(orden)
        self.plantilla_rollo.precio_por_kg = 80.0
        self._recalcular_precio(linea)
        self.assertEqual((linea.precio_por_kg, linea.price_unit), (50.0, 62.5), "Usa el congelado")

        self._facturar(orden).action_post()
        self.plantilla_rollo.precio_por_kg = 90.0
        self._recalcular_precio(linea)
        self.assertEqual(linea.price_unit, 62.5, "Facturada: nunca cambia de precio")

    def test_linea_facturada_sin_precio_congelado_no_cambia(self):
        """ Como las líneas existentes antes de este cambio: facturadas y sin
        precio congelado. Un recálculo ya no las pasa al precio vigente. """
        orden = self._orden([(self.rollo, 1)])
        self._entregar(orden, pesos=[1.25])
        linea = self._rollos(orden)
        linea.write({"precio_por_kg": 0.0})
        self._facturar(orden).action_post()
        self.assertEqual(linea.price_unit, 62.5)
        self.plantilla_rollo.precio_por_kg = 99.0
        self._recalcular_precio(linea)
        self.assertEqual(linea.price_unit, 62.5)

    def test_rollo_sin_entregar_usa_el_precio_vigente(self):
        orden = self._orden([(self.rollo, 1)])
        linea = self._rollos(orden)
        linea.peso_real = 2.0
        self.assertEqual((linea.precio_por_kg, linea.price_unit), (0.0, 100.0))
        self.plantilla_rollo.precio_por_kg = 60.0
        self._recalcular_precio(linea)
        self.assertEqual(linea.price_unit, 120.0)

    def test_devolucion_no_toca_la_linea(self):
        orden = self._orden([(self.rollo, 1)])
        picking = self._entregar(orden, pesos=[1.5])
        linea = self._rollos(orden)
        asistente = self.env["stock.return.picking"].with_context(
            active_id=picking.id, active_model="stock.picking",
        ).create({})
        asistente.product_return_moves.quantity = 1
        devolucion = asistente._create_return()
        devolucion.move_ids.write({"quantity": 1, "picked": True, "peso_real": 0.5})
        devolucion.button_validate()
        self.assertEqual(devolucion.state, "done")
        self.assertEqual((linea.peso_real, linea.precio_por_kg, linea.price_unit), (1.5, 50.0, 75.0))

    def test_nota_de_credito_por_devolucion_sale_igual(self):
        """ Devolución de un rollo facturado: la nota de crédito usa el peso
        devuelto y el precio vigente, como antes. """
        orden = self._orden([(self.rollo, 1)])
        picking = self._entregar(orden, pesos=[1.5])
        self._facturar(orden).action_post()
        self.plantilla_rollo.precio_por_kg = 60.0
        asistente = self.env["stock.return.picking"].with_context(
            active_id=picking.id, active_model="stock.picking",
        ).create({})
        asistente.product_return_moves.quantity = 1
        devolucion = asistente._create_return()
        devolucion.move_ids.write({"quantity": 1, "picked": True, "peso_real": 0.5})
        devolucion.button_validate()
        nota = orden._create_invoices(final=True)
        self.assertEqual(nota.move_type, "out_refund")
        self.assertEqual((nota.invoice_line_ids.peso_real, nota.amount_total), (0.5, 30.0))

    # === Permisos: sudo acotado === #

    def test_sudo_solo_escribe_peso_y_precio_de_las_lineas_validadas(self):
        orden = self._orden([(self.rollo, 2), (self.normal, 1)])
        orden.user_id = self.otro_vendedor
        otra = self._orden([(self.rollo, 1)])
        campos = ["price_unit", "discount", "tax_ids", "name", "product_id", "product_uom_qty"]
        antes_normal = orden.order_line.filtered(lambda l: not l.es_peso_variable).read(campos)
        antes_otra = otra.order_line.read(campos + ["peso_real", "precio_por_kg"])

        escrituras = []
        SaleOrderLine = type(self.env["sale.order.line"])
        write = SaleOrderLine.write

        def espiar(lineas, vals):
            escrituras.append((set(lineas.ids), set(vals), lineas.env.su, lineas.env.uid))
            return write(lineas, vals)

        with patch.object(SaleOrderLine, "write", espiar):
            self._validar_como(self.vendedor, orden, [1.1, 0.9])

        self.assertEqual(len(escrituras), 2, "Una escritura por rollo validado")
        for ids, campos_escritos, su, uid in escrituras:
            self.assertEqual(campos_escritos, {"peso_real", "precio_por_kg"})
            self.assertTrue(ids <= set(self._rollos(orden).ids))
            self.assertEqual((su, uid), (True, self.vendedor.id))
        self.assertEqual(orden.order_line.filtered(lambda l: not l.es_peso_variable).read(campos), antes_normal)
        self.assertEqual(otra.order_line.read(campos + ["peso_real", "precio_por_kg"]), antes_otra)

    def test_vendedor_valida_orden_de_otro_vendedor(self):
        orden = self._orden([(self.rollo, 1)])
        orden.user_id = self.otro_vendedor
        with self.assertRaises(AccessError, msg="Con sus permisos no puede escribir esa orden"):
            orden.order_line.with_user(self.vendedor).write({"peso_real": 1.0})
        mensajes = orden.message_ids
        self._validar_como(self.vendedor, orden, [1.2])
        self.assertEqual(self._rollos(orden).price_unit, 60.0)
        self.env.flush_all()
        self.env.cr.precommit.run()
        # El autor es quien valida en el flujo real (ver la prueba de la
        # captura); aquí el mensaje lo genera el entorno de la prueba al guardar.
        self.assertTrue(orden.message_ids - mensajes, "El cambio de total queda en el historial")

    def test_usuario_solo_de_almacen_valida(self):
        orden = self._orden([(self.rollo, 1)])
        self.assertFalse(self.almacen.has_group("sales_team.group_sale_salesman"))
        self._validar_como(self.almacen, orden, [1.3])
        self.assertEqual((self._rollos(orden).peso_real, self._rollos(orden).price_unit), (1.3, 65.0))

    # === Actualizar el módulo === #

    def test_el_campo_nuevo_no_recalcula_al_actualizar(self):
        """ Odoo solo calcula en registros existentes los campos calculados cuya
        columna es nueva (fields.py, update_db: `return not column`). El precio
        congelado de la línea NO es calculado: agregarlo no dispara recálculos
        de las líneas que ya existen. (Además se comprobó en duranDEV: tras
        actualizar el módulo, líneas y órdenes quedaron idénticas.) """
        campo = self.env["sale.order.line"]._fields["precio_por_kg"]
        self.assertFalse(campo.compute)
        self.assertFalse(campo.related)
