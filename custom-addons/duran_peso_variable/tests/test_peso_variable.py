""" Comportamiento base del peso variable: un rollo por línea y factura por peso real. """
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged

from .common import PesoVariableDatosPrueba


@tagged("post_install", "-at_install")
class TestPesoVariable(PesoVariableDatosPrueba, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._crear_datos()

    def test_un_rollo_por_linea(self):
        orden = self._orden([(self.rollo, 3), (self.normal, 4)])
        rollos = orden.order_line.filtered(lambda l: l.product_id == self.rollo)
        self.assertEqual(rollos.mapped("product_uom_qty"), [1.0, 1.0, 1.0])
        self.assertEqual(len(orden.picking_ids.move_ids.filtered("es_peso_variable")), 3)

    def test_movimiento_de_rollo_no_pasa_de_1(self):
        orden = self._orden([(self.rollo, 1)])
        with self.assertRaises(ValidationError):
            orden.picking_ids.move_ids.quantity = 2

    def test_factura_por_peso_real_de_la_entrega(self):
        orden = self._orden([(self.rollo, 2), (self.normal, 3)])
        self._entregar(orden, pesos=[1.25, 0.8])
        factura = self._facturar(orden)
        rollos = self._lineas_producto(factura, self.rollo)
        self.assertEqual(sorted(rollos.mapped("peso_real")), [0.8, 1.25])
        self.assertEqual(sorted(rollos.mapped("price_unit")), [40.0, 62.5])
        self.assertEqual(self._lineas_producto(factura, self.normal).price_subtotal, 90.0)
        self.assertAlmostEqual(factura.amount_total, 192.5)

    def test_devolucion_no_arrastra_el_peso_de_la_entrega(self):
        orden = self._orden([(self.rollo, 1)])
        picking = self._entregar(orden, pesos=[1.5])
        asistente = self.env["stock.return.picking"].with_context(
            active_id=picking.id, active_model="stock.picking",
        ).create({})
        asistente.product_return_moves.quantity = 1
        devolucion = asistente._create_return()
        self.assertEqual(devolucion.move_ids.peso_real, 0.0)
