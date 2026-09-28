""" Precio por kg congelado al validar la entrega (y el Cambio de producto, que
sigue abonando al precio vigente). """
from odoo.tests import Form, TransactionCase, tagged

from .common import PesoVariableDatosPrueba


@tagged("post_install", "-at_install")
class TestPrecioCongelado(PesoVariableDatosPrueba, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._crear_datos()

    def _subir_precio(self, precio):
        self.plantilla_rollo.precio_por_kg = precio

    def test_validar_la_entrega_congela_el_precio(self):
        orden = self._orden([(self.rollo, 2), (self.normal, 1)])
        self.assertEqual(orden.picking_ids.move_ids.mapped("precio_por_kg"), [0.0, 0.0, 0.0])
        picking = self._entregar(orden, pesos=[1.25, 1.0])
        rollos = picking.move_ids.filtered("es_peso_variable")
        self.assertEqual(rollos.mapped("precio_por_kg"), [50.0, 50.0])
        self.assertEqual((picking.move_ids - rollos).precio_por_kg, 0.0, "Solo los rollos llevan precio por kg")

    def test_factura_usa_el_precio_congelado(self):
        """ Se entrega a $50/kg, el precio sube a $80/kg y después se factura:
        se cobra a $50/kg. """
        orden = self._orden([(self.rollo, 1), (self.normal, 2)])
        self._entregar(orden, pesos=[1.25])
        self._subir_precio(80.0)
        factura = self._facturar(orden)
        rollo = self._lineas_producto(factura, self.rollo)
        self.assertEqual((rollo.peso_real, rollo.precio_por_kg, rollo.price_unit), (1.25, 50.0, 62.5))
        self.assertAlmostEqual(factura.amount_total, 62.5 + 60.0)

    def test_corregir_el_peso_en_la_factura_mantiene_el_precio_congelado(self):
        orden = self._orden([(self.rollo, 1)])
        self._entregar(orden, pesos=[1.25])
        self._subir_precio(80.0)
        factura = self._facturar(orden)
        with Form(factura) as formulario:
            with formulario.invoice_line_ids.edit(0) as linea:
                linea.peso_real = 2.0
        self.assertEqual(factura.invoice_line_ids.price_unit, 100.0)

    def test_entrega_anterior_al_cambio_usa_el_precio_vigente(self):
        """ Entregas validadas antes de este cambio no tienen precio congelado:
        se facturan como siempre, al precio vigente del producto. """
        orden = self._orden([(self.rollo, 1)])
        picking = self._entregar(orden, pesos=[1.25])
        picking.move_ids.precio_por_kg = 0.0
        self._subir_precio(80.0)
        rollo = self._facturar(orden).invoice_line_ids
        self.assertEqual((rollo.precio_por_kg, rollo.price_unit), (80.0, 100.0))

    def test_precio_de_la_orden_no_afecta_al_congelado(self):
        """ El precio se congela al ENTREGAR, no al pedir. """
        orden = self._orden([(self.rollo, 1)])
        self._subir_precio(60.0)
        picking = self._entregar(orden, pesos=[2.0])
        self.assertEqual(picking.move_ids.precio_por_kg, 60.0)
        self._subir_precio(90.0)
        self.assertEqual(self._facturar(orden).invoice_line_ids.price_unit, 120.0)

    def _entregado_y_facturado(self, producto, peso=None):
        orden = self._orden([(producto, 1)])
        self._entregar(orden, pesos=[peso] if peso else [])
        factura = self._facturar(orden)
        factura.action_post()
        return orden, factura

    def _cambio(self, orden, **vals):
        asistente = self.env["duran.cambio.producto"].with_context(active_id=orden.id).create({
            "sale_line_id": orden.order_line.id, **vals,
        })
        self.assertTrue(asistente.journal_id, "Se necesita un diario de efectivo para cobrar")
        accion = asistente.action_confirm()
        return self.env["account.move"].browse(accion["res_id"])

    def test_cambio_de_rollo_abona_al_precio_vigente(self):
        """ Rollo entregado y facturado a $50/kg; el precio sube a $60/kg y se
        cambia: el abono de lo devuelto y el rollo nuevo van a $60/kg, como
        indica el diseño del Cambio de producto. """
        orden, factura = self._entregado_y_facturado(self.rollo, peso=1.5)
        self.assertEqual(factura.amount_total, 75.0)
        self._subir_precio(60.0)

        factura_nueva = self._cambio(orden, peso_devuelto=0.5, peso_nuevo=2.0)

        nota = orden.invoice_ids.filtered(lambda m: m.move_type == "out_refund")
        self.assertEqual(len(nota), 1)
        self.assertEqual((nota.invoice_line_ids.peso_real, nota.amount_total), (0.5, 30.0))
        self.assertEqual(factura_nueva.amount_total, 120.0)
        self.assertEqual(factura_nueva.amount_residual, 0.0, "Cobrada completa")
        nueva_entrega = factura_nueva.invoice_line_ids.sale_line_ids.move_ids
        self.assertEqual((nueva_entrega.peso_real, nueva_entrega.precio_por_kg), (2.0, 60.0))
        devolucion = orden.order_line.move_ids.filtered(lambda m: m.origin_returned_move_id)
        self.assertEqual(devolucion.precio_por_kg, 0.0, "La devolución no congela precio")
        linea = orden.order_line
        self.assertEqual((linea.peso_real, linea.precio_por_kg, linea.price_unit), (1.5, 50.0, 75.0),
                         "La línea original conserva lo entregado")
        nueva_linea = factura_nueva.invoice_line_ids.sale_line_ids
        self.assertEqual((nueva_linea.peso_real, nueva_linea.precio_por_kg, nueva_linea.price_unit), (2.0, 60.0, 120.0))

    def test_cambio_de_producto_normal(self):
        orden, _factura = self._entregado_y_facturado(self.normal)
        factura_nueva = self._cambio(orden, peso_devuelto=2.0)
        nota = orden.invoice_ids.filtered(lambda m: m.move_type == "out_refund")
        self.assertEqual(nota.amount_total, 12.0, "2 de 5 kg de una caja de $30")
        self.assertEqual(factura_nueva.amount_total, 30.0)
        self.assertEqual(factura_nueva.amount_residual, 0.0, "Cobrada completa")
