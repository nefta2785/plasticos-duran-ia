""" Datos y ayudantes compartidos por las pruebas de duran_peso_variable.

Cada clase crea su propio cliente y productos (sin impuestos, sin control de
existencias) y todo se revierte al terminar. """
import itertools

from odoo import Command
from odoo.addons.base.models import ir_sequence


class PesoVariableDatosPrueba:
    """ Mezclar con TransactionCase. """

    @classmethod
    def _sin_gastar_folios(cls):
        """ Los folios de órdenes, entregas y facturas salen de secuencias de
        PostgreSQL (`_select_nextval`), que NO se revierten al terminar la
        prueba. Mientras dure la clase se sustituye por un contador falso
        (folios 9xxxxx). """
        contador = itertools.count(900001)
        cls.classPatch(ir_sequence, "_select_nextval", lambda cr, nombre: (next(contador),))

    @classmethod
    def _crear_datos(cls):
        cls._sin_gastar_folios()
        cls.cliente = cls.env["res.partner"].create({"name": "Cliente prueba peso variable"})
        categoria = cls.env["product.category"].create({"name": "Categoría prueba peso variable"})
        comunes = {
            "categ_id": categoria.id, "sale_ok": True, "invoice_policy": "delivery",
            "taxes_id": [Command.clear()], "is_storable": False,
        }
        cls.plantilla_rollo = cls.env["product.template"].create({
            "name": "Rollo prueba peso variable", "es_peso_variable": True, "precio_por_kg": 50.0,
            **comunes,
        })
        cls.rollo = cls.plantilla_rollo.product_variant_id
        cls.normal = cls.env["product.template"].create({
            "name": "Caja prueba peso fijo", "list_price": 30.0, "peso_referencia": 5.0, **comunes,
        }).product_variant_id

    def _orden(self, lineas):
        orden = self.env["sale.order"].create({
            "partner_id": self.cliente.id,
            "order_line": [
                Command.create({"product_id": producto.id, "product_uom_qty": cantidad})
                for producto, cantidad in lineas
            ],
        })
        orden.action_confirm()
        return orden

    def _entregar(self, orden, pesos=()):
        """ Valida la entrega de la orden completa: cada rollo con su peso (en
        el orden de las líneas) y lo demás con la cantidad pedida. """
        picking = orden.picking_ids.filtered(lambda p: p.state not in ("done", "cancel"))
        self.assertEqual(len(picking), 1)
        pesos = list(pesos)
        for move in picking.move_ids.sorted(lambda m: m.sale_line_id.id):
            vals = {"quantity": move.product_uom_qty, "picked": True}
            if move.es_peso_variable:
                vals["peso_real"] = pesos.pop(0)
            move.write(vals)
        self.assertIs(picking.button_validate(), True)
        self.assertEqual(picking.state, "done")
        return picking

    def _facturar(self, orden):
        factura = orden._create_invoices()
        self.assertEqual(len(factura), 1)
        return factura

    def _lineas_producto(self, factura, producto):
        return factura.invoice_line_ids.filtered(lambda l: l.product_id == producto)
