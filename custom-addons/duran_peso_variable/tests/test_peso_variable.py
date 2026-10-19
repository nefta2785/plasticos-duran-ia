""" Comportamiento base del peso variable: un rollo por línea y factura por peso real. """
from odoo import Command
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


@tagged("post_install", "-at_install")
class TestPesoVariableFueraDeEntregas(PesoVariableDatosPrueba, TransactionCase):
    """ La regla de 1 rollo por movimiento solo aplica a las entregas al
    cliente: los demás movimientos de rollos pueden llevar varios. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._crear_datos()
        cls.proveedor = cls.env["res.partner"].create({"name": "Proveedor prueba peso variable"})
        cls.almacen = cls.env["stock.warehouse"].search([("company_id", "=", cls.env.company.id)], limit=1)
        # Los ajustes de inventario y las transferencias internas necesitan
        # un rollo con control de existencias.
        cls.rollo_almacenable = cls.env["product.template"].create({
            "name": "Rollo almacenable prueba peso variable", "es_peso_variable": True,
            "precio_por_kg": 50.0, "is_storable": True,
        }).product_variant_id

    def _validar(self, picking, cantidad):
        picking.move_ids.write({"quantity": cantidad, "picked": True})
        self.assertIs(picking.button_validate(), True)
        self.assertEqual(picking.state, "done")

    def _recibir_compra(self, cantidad):
        if "purchase.order" not in self.env:
            self.skipTest("El módulo purchase no está instalado en esta base.")
        compra = self.env["purchase.order"].create({
            "partner_id": self.proveedor.id,
            "order_line": [Command.create({"product_id": self.rollo.id, "product_qty": cantidad})],
        })
        compra.button_confirm()
        recepcion = compra.picking_ids
        self.assertEqual(len(recepcion), 1)
        self.assertEqual(recepcion.move_ids.product_uom_qty, cantidad)
        self._validar(recepcion, cantidad)
        return recepcion

    def test_compra_de_2_rollos(self):
        self._recibir_compra(2)

    def test_ajuste_de_inventario_de_3_rollos(self):
        ubicacion = self.almacen.lot_stock_id
        self.env["stock.quant"].with_context(inventory_mode=True).create({
            "product_id": self.rollo_almacenable.id, "location_id": ubicacion.id, "inventory_quantity": 3,
        }).action_apply_inventory()
        self.assertEqual(self.env["stock.quant"]._get_available_quantity(self.rollo_almacenable, ubicacion), 3)

    def test_transferencia_interna_de_2_rollos(self):
        origen = self.almacen.lot_stock_id
        destino = self.env["stock.location"].create({"name": "Anaquel prueba", "location_id": origen.id})
        self.env["stock.quant"]._update_available_quantity(self.rollo_almacenable, origen, 2)
        transferencia = self.env["stock.picking"].create({
            "picking_type_id": self.almacen.int_type_id.id,
            "location_id": origen.id,
            "location_dest_id": destino.id,
            "move_ids": [Command.create({
                "product_id": self.rollo_almacenable.id, "product_uom_qty": 2,
                "location_id": origen.id, "location_dest_id": destino.id,
            })],
        })
        transferencia.action_confirm()
        transferencia.action_assign()
        self._validar(transferencia, 2)
        self.assertEqual(self.env["stock.quant"]._get_available_quantity(self.rollo_almacenable, destino), 2)

    def test_devolucion_a_proveedor_de_2_rollos(self):
        recepcion = self._recibir_compra(2)
        asistente = self.env["stock.return.picking"].with_context(
            active_id=recepcion.id, active_model="stock.picking",
        ).create({})
        asistente.product_return_moves.quantity = 2
        devolucion = asistente._create_return()
        self.assertEqual(devolucion.location_dest_id.usage, "supplier")
        self._validar(devolucion, 2)
