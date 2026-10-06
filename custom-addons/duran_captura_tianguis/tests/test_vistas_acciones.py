""" Cada acción de ventana del módulo abre vistas de SU modelo y con campos que
ese modelo tiene. Así se detecta, sin abrir el navegador, una acción que cambió
de modelo y sigue apuntando a vistas del otro (en el navegador sale, por
ejemplo, '"stock.move"."estado" field is undefined'). """
from lxml import etree

from odoo.tests import TransactionCase, tagged

MODULO = "duran_captura_tianguis"


@tagged("post_install", "-at_install")
class TestVistasDeAcciones(TransactionCase):

    def _acciones(self):
        datos = self.env["ir.model.data"].search([("module", "=", MODULO), ("model", "=", "ir.actions.act_window")])
        return self.env["ir.actions.act_window"].browse(datos.mapped("res_id"))

    def _vistas(self, accion):
        """ (vista, tipo) que carga el navegador: view_id, las de view_ids y la
        de búsqueda. """
        vistas = [(accion.view_id, accion.view_id.type)] if accion.view_id else []
        vistas += [(v.view_id, v.view_mode) for v in accion.view_ids if v.view_id]
        if accion.search_view_id:
            vistas.append((accion.search_view_id, "search"))
        return vistas

    def test_cada_accion_carga_vistas_de_su_modelo(self):
        acciones = self._acciones()
        self.assertGreaterEqual(len(acciones), 2, "al menos Hoja de carga y Pendiente de cobro")
        for accion in acciones:
            modelo = self.env[accion.res_model]
            for vista, tipo in self._vistas(accion):
                with self.subTest(accion=accion.name, vista=vista.name):
                    self.assertEqual(vista.model, accion.res_model, "la vista es de otro modelo")
                    respuesta = modelo.get_views([(vista.id, tipo)])
                    arch = etree.fromstring(respuesta["views"][tipo]["arch"])
                    campos = respuesta["models"][accion.res_model]["fields"]
                    # Solo los campos de este nivel (no los de subvistas de un x2many).
                    for nodo in arch.xpath("//field[not(ancestor::field)]"):
                        self.assertIn(nodo.get("name"), campos, f"{accion.res_model}.{nodo.get('name')} no existe")
            # Los modos de la acción tienen vista (propia o la de Odoo por defecto).
            for modo in accion.view_mode.split(","):
                with self.subTest(accion=accion.name, modo=modo):
                    self.assertTrue(modelo.get_views([(False, modo)])["views"][modo]["arch"])
