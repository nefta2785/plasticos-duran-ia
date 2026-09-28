""" Paso 4 (modo Entrega): vista previa del total y revisión de lo que se entrega. """
from unittest.mock import patch

from odoo import Command
from odoo.sql_db import Cursor
from odoo.tests import HttpCase, tagged
from odoo.tools import SQL

from .common import GRUPO_CAPTURA, CapturaDatosPrueba, CapturaHttpMixin

RUTA = "/captura/api/entrega/vista_previa"


@tagged("post_install", "-at_install")
class TestEntregaVistaPrevia(CapturaDatosPrueba, CapturaHttpMixin, HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._sin_gastar_folios()
        cls._crear_datos_captura()
        env = cls.env
        cls.mama = cls._usuario("vista_previa_mama", GRUPO_CAPTURA)
        cls.otro_vendedor = cls._usuario("vista_previa_otro", "sales_team.group_sale_salesman")
        cls.sin_grupo = cls._usuario("vista_previa_sin_grupo", "sales_team.group_sale_salesman")
        cls.direccion = env["res.partner"].create({
            # "other": si fuera "delivery", Odoo la usaría en todas las órdenes del cliente.
            "name": "Puesto prueba vista previa", "parent_id": cls.cliente.id, "type": "other",
        })
        cls.otro_cliente = cls._cliente("Cliente prueba de otra zona", env["res.partner.category"].create({
            "name": "Zona prueba otra",
        }))
        sin_impuestos = {"taxes_id": [Command.clear()]}
        cls.rollo_a = cls._plantilla(
            "Rollo A prueba", es_peso_variable=True, precio_por_kg=85.5, **sin_impuestos,
        ).product_variant_id
        cls.rollo_b = cls._plantilla(
            "Rollo B prueba", es_peso_variable=True, precio_por_kg=43.0, **sin_impuestos,
        ).product_variant_id
        cls.pieza = cls._plantilla("Pieza prueba", **sin_impuestos).product_variant_id
        cls.kilo = cls._plantilla(
            "Kilo prueba", uom_id=env.ref("uom.product_uom_kgm").id, **sin_impuestos,
        ).product_variant_id

        # La más antigua es de otro vendedor; o3 va a otra dirección de entrega
        # (Odoo la factura aparte).
        cls.o1 = cls._confirmada(cls.cliente, [(cls.rollo_a, 2), (cls.pieza, 3, 12.345)], vendedor=cls.otro_vendedor)
        cls.o2 = cls._confirmada(cls.cliente, [(cls.rollo_b, 2), (cls.pieza, 2, 7.777), (cls.kilo, 5, 33.333)])
        cls.o3 = cls._confirmada(
            cls.cliente, [(cls.rollo_a, 1), (cls.pieza, 1, 12.345)], partner_shipping_id=cls.direccion.id,
        )
        cls.ajena = cls._confirmada(cls.otro_cliente, [(cls.rollo_a, 1), (cls.pieza, 1)])
        cls.ya_entregada = cls._confirmada(cls.cliente, [(cls.rollo_a, 1)])
        cls._validar(cls.ya_entregada.picking_ids)

    def setUp(self):
        super().setUp()
        self._entrar(self.mama)

    # === Ayudantes === #

    def _movimientos(self, orden, producto):
        return orden.picking_ids.move_ids.filtered(lambda m: m.product_id == producto).sorted("id")

    def _params(self, rollos=(), productos=(), cliente=None, zona=None):
        return {
            "cliente_id": (cliente or self.cliente).id,
            "zona_id": (zona or self.zona_con_clientes).id,
            "rollos": [{"move_id": movimiento.id, "peso": peso} for movimiento, peso in rollos],
            "productos": [{"producto_id": producto.id, "cantidad": cantidad} for producto, cantidad in productos],
        }

    def _vista_previa(self, **kwargs):
        return self._resultado(RUTA, self._params(**kwargs))

    def _error(self, params):
        respuesta = self._jsonrpc(RUTA, params)
        self.assertNotIn("result", respuesta)
        return respuesta["error"]["data"]

    def _entrega_mezclada(self):
        """ Rollos de 3 órdenes (uno de o2 no se entrega), 4 piezas repartidas
        entre o1 (3) y o2 (1), 4 de 5 kg; la pieza de o3 no se entrega. """
        a1, a2 = self._movimientos(self.o1, self.rollo_a)
        b1, _b2 = self._movimientos(self.o2, self.rollo_b)
        a3 = self._movimientos(self.o3, self.rollo_a)
        return {
            "rollos": [(a1, "1.237"), (a2, "0,913"), (b1, "2.071"), (a3, "1.111")],
            "productos": [(self.pieza, 4), (self.kilo, 4)],
        }

    def _validar_como_la_confirmacion(self, rollos, cantidades):
        """ Lo que hará la confirmación (paso 5): cada rollo con su peso, cada
        movimiento con su cantidad y lo demás cancelado, sin backorder. """
        pickings = self.env["stock.picking"].union(*(m.picking_id for m, _peso in rollos), *(m.picking_id for m in cantidades))
        for movimiento in pickings.move_ids:
            movimiento.write({"quantity": 0, "picked": False})
        for movimiento, peso in rollos:
            movimiento.write({"quantity": 1, "picked": True, "peso_real": float(peso.replace(",", "."))})
        for movimiento, cantidad in cantidades.items():
            movimiento.write({"quantity": cantidad, "picked": True})
        for picking in pickings:
            picking.with_context(skip_backorder=True, picking_ids_not_to_backorder=picking.ids).button_validate()
            self.assertEqual(picking.state, "done")

    # === Total contra la factura real === #

    def test_total_coincide_con_la_factura(self):
        """ Rollos y productos normales mezclados, de 3 órdenes (dos facturas,
        porque o3 va a otra dirección), con importes de más de 2 decimales. El
        precio por kg sube después de pedir: cuenta el vigente al entregar. """
        self.rollo_a.product_tmpl_id.precio_por_kg = 86.25
        entrega = self._entrega_mezclada()
        vista = self._vista_previa(**entrega)
        self.assertTrue(vista["puede_confirmar"])

        crudo = (1.237 + 0.913 + 1.111) * 86.25 + 2.071 * 43 + 3 * 12.345 + 7.777 + 4 * 33.333
        self.assertNotAlmostEqual(crudo, round(crudo, 2), places=6, msg="Debe haber algo que redondear")

        (p1,) = self._movimientos(self.o1, self.pieza)
        (p2,) = self._movimientos(self.o2, self.pieza)
        (k2,) = self._movimientos(self.o2, self.kilo)
        self._validar_como_la_confirmacion(entrega["rollos"], {p1: 3, p2: 1, k2: 4})
        facturas = (self.o1 | self.o2 | self.o3)._create_invoices()
        self.assertEqual(len(facturas), 2)
        self.assertAlmostEqual(vista["total"], sum(facturas.mapped("amount_total")), places=6)
        self.assertEqual(vista["total_texto"], self._formato(vista["total"]))
        self.assertRegex(vista["total_texto"], r"^\$[\d,.]*[.,]\d{2}$", "El total siempre con centavos")

        # Cada línea, igual que el total de su línea de factura.
        lineas_factura = facturas.invoice_line_ids
        for rollo in vista["rollos"]:
            linea = lineas_factura.filtered(lambda l: rollo["move_id"] in l.sale_line_ids.move_ids.ids)
            self.assertAlmostEqual(rollo["importe"], linea.price_total, places=6)
        for producto in vista["productos"]:
            lineas = lineas_factura.filtered(lambda l: l.product_id.id == producto["id"])
            self.assertAlmostEqual(producto["importe"], sum(lineas.mapped("price_total")), places=6)
        rollos_factura = facturas.invoice_line_ids.filtered("es_peso_variable")
        self.assertEqual(sorted(rollos_factura.mapped("peso_real")), [0.913, 1.111, 1.237, 2.071])

    def test_total_con_impuestos_coincide_con_la_factura(self):
        iva = self.env["account.tax"].create({
            "name": "IVA prueba 16%", "amount": 16.0, "amount_type": "percent", "type_tax_use": "sale",
        })
        cliente = self._cliente("Cliente prueba con IVA", self.zona_con_clientes)
        orden = self._confirmada(cliente, [(self.rollo_b, 1), (self.pieza, 3, 12.345)])
        orden.order_line.tax_ids = iva
        rollos = [(self._movimientos(orden, self.rollo_b), "1.357")]
        vista = self._vista_previa(rollos=rollos, productos=[(self.pieza, 2)], cliente=cliente)

        self._validar_como_la_confirmacion(rollos, {self._movimientos(orden, self.pieza): 2})
        factura = orden._create_invoices()
        self.assertGreater(factura.amount_tax, 0)
        self.assertAlmostEqual(vista["total"], factura.amount_total, places=6)

    def _formato(self, importe):
        return self.env["duran.captura"]._formato_precio(importe, self.env.company.currency_id, centavos=True)

    def test_detalle_por_linea(self):
        vista = self._vista_previa(**self._entrega_mezclada())
        self.assertEqual(vista["cliente"], {"id": self.cliente.id, "nombre": self.cliente.name})
        self.assertEqual(
            [(r["producto_id"], r["peso"], r["precio"]) for r in vista["rollos"]],
            [(self.rollo_a.id, 1.237, 85.5), (self.rollo_a.id, 0.913, 85.5),
             (self.rollo_b.id, 2.071, 43.0), (self.rollo_a.id, 1.111, 85.5)],
            "De la orden más antigua a la más nueva; la coma decimal se acepta",
        )
        self.assertAlmostEqual(vista["rollos"][0]["importe"], 1.237 * 85.5, delta=0.011)
        self.assertEqual(
            [(p["id"], p["cantidad"], p["unidad"]) for p in vista["productos"]],
            [(self.pieza.id, 4, "c/u"), (self.kilo.id, 4, "kg")],
        )
        self.assertAlmostEqual(vista["productos"][0]["importe"], 3 * 12.345 + 7.777, delta=0.011)

    def test_sin_nada_que_entregar(self):
        vista = self._vista_previa()
        self.assertEqual((vista["rollos"], vista["productos"], vista["total"], vista["puede_confirmar"]), ([], [], 0.0, True))

    # === No escribe nada === #

    def test_no_escribe_nada_en_la_base(self):
        movimientos = (self.o1 | self.o2 | self.o3).picking_ids.move_ids
        campos = ["quantity", "picked", "peso_real", "precio_por_kg", "state"]
        antes = movimientos.read(campos)
        facturas_antes = self.env["account.move"].search_count([])
        self.env.flush_all()
        escrituras = []
        execute = Cursor.execute

        def espiar(cr, query, params=None, log_exceptions=True):
            texto = (query.code if isinstance(query, SQL) else str(query)).lstrip().upper()
            if texto.startswith(("INSERT", "UPDATE", "DELETE")):
                escrituras.append(texto[:100])
            return execute(cr, query, params, log_exceptions)

        with patch.object(Cursor, "execute", espiar):
            vista = self._vista_previa(**self._entrega_mezclada())
        self.assertTrue(vista["puede_confirmar"])
        self.assertEqual(escrituras, [])
        movimientos.invalidate_recordset()
        self.assertEqual(movimientos.read(campos), antes)
        self.assertEqual(self.env["account.move"].search_count([]), facturas_antes)
        self.assertFalse(self.env["duran.captura.entrega"].search([]))

    # === Validaciones que rechazan === #

    def test_rollos_invalidos(self):
        a1, _a2 = self._movimientos(self.o1, self.rollo_a)
        (pieza,) = self._movimientos(self.o1, self.pieza)
        casos = {
            "de otro cliente": ([(self._movimientos(self.ajena, self.rollo_a), "1")], "ya no está pendiente"),
            "ya entregado": ([(self.ya_entregada.picking_ids.move_ids, "1")], "ya no está pendiente"),
            "no es de peso variable": ([(pieza, "1")], "ya no está pendiente"),
            "no existe": (None, "ya no está pendiente"),
            "repetido": ([(a1, "1"), (a1, "1.1")], "dos veces"),
        }
        for nombre, (rollos, mensaje) in casos.items():
            with self.subTest(caso=nombre):
                params = self._params(rollos=rollos or [])
                if rollos is None:
                    params["rollos"] = [{"move_id": 999999999, "peso": "1"}]
                self.assertIn(mensaje, self._error(params)["message"])
        for rollos in ("x", [5], [{"move_id": a1.id}], [{"move_id": str(a1.id), "peso": "1"}],
                       [{"move_id": True, "peso": "1"}]):
            with self.subTest(rollos=rollos):
                params = self._params()
                params["rollos"] = rollos
                self.assertEqual(self._error(params)["name"], "odoo.exceptions.UserError")

    def test_productos_invalidos(self):
        casos = [
            ([(self.pieza, 1.5)], "enteros"),
            ([(self.pieza, 0)], "enteros"),
            ([(self.pieza, -1)], "enteros"),
            ([(self.pieza, True)], "enteros"),
            ([(self.pieza, "2")], "enteros"),
            ([(self.rollo_a, 1)], "ya no está pendiente"),
            ([(self.normal, 1)], "ya no está pendiente"),
            ([(self.pieza, 1), (self.pieza, 1)], "dos veces"),
            ([(self.pieza, 7)], "solo hay 6 pendientes"),
        ]
        for productos, mensaje in casos:
            with self.subTest(productos=[(p.name, c) for p, c in productos]):
                self.assertIn(mensaje, self._error(self._params(productos=productos))["message"])
        params = self._params()
        params["productos"] = [{"producto_id": "x", "cantidad": 1}]
        self.assertIn("producto inválido", self._error(params)["message"])
        self.assertTrue(self._vista_previa(productos=[(self.pieza, 6)])["puede_confirmar"], "Todo lo pendiente sí")

    def test_cliente_de_otra_zona(self):
        params = self._params(
            rollos=[(self._movimientos(self.ajena, self.rollo_a), "1")], cliente=self.otro_cliente,
        )
        self.assertIn("ya no está en la zona", self._error(params)["message"])

    # === Peso: bloqueos, advertencias y sugerencia === #

    def _revision(self, peso):
        (movimiento,) = self._movimientos(self.o2, self.rollo_b)[:1]
        vista = self._vista_previa(rollos=[(movimiento, peso)])
        (rollo,) = vista["rollos"]
        return rollo, vista

    def test_pesos_bloqueados(self):
        casos = {
            "abc": "Escribe el peso en kg, por ejemplo 1.250.",
            "": "Escribe el peso en kg, por ejemplo 1.250.",
            "1.2.5": "Escribe el peso en kg, por ejemplo 1.250.",
            "-1": "Escribe el peso en kg, por ejemplo 1.250.",
            ".5": "Escribe el peso en kg, por ejemplo 1.250.",
            "1.2345": "El peso lleva máximo 3 decimales.",
            "0": "El peso debe ser mayor a 0 kg.",
            "0,000": "El peso debe ser mayor a 0 kg.",
            "15.001": "Un rollo no puede pesar más de 15 kg.",
            "99": "Un rollo no puede pesar más de 15 kg.",
        }
        for peso, mensaje in casos.items():
            with self.subTest(peso=peso):
                rollo, vista = self._revision(peso)
                self.assertEqual(rollo["bloqueo"], mensaje)
                self.assertEqual((vista["puede_confirmar"], vista["total"], rollo["importe"]), (False, None, None))
        rollo, _vista = self._revision(1.25)
        self.assertEqual(rollo["bloqueo"], "Escribe el peso en kg, por ejemplo 1.250.", "El peso llega como texto")

    def test_pesos_con_advertencia_y_sin_ella(self):
        casos = {
            "0.499": ["Pesa menos de 0.5 kg: revisa que esté bien."],
            "0.5": [],
            "1,250": [],
            " 1.250 ": [],
            "8": [],
            "8.001": ["Pesa más de 8 kg: revisa que esté bien."],
            "15": ["Pesa más de 8 kg: revisa que esté bien."],
        }
        for peso, advertencias in casos.items():
            with self.subTest(peso=peso):
                rollo, vista = self._revision(peso)
                self.assertEqual((rollo["bloqueo"], rollo["advertencias"], rollo["sugerencia"]), (None, advertencias, None))
                self.assertTrue(vista["puede_confirmar"], "Una advertencia no impide confirmar")
                self.assertIsNotNone(vista["total"])

    def test_sugerencia_cuando_falta_el_punto(self):
        rollo, _vista = self._revision("1250")
        self.assertEqual(rollo["sugerencia"], 1.25)
        self.assertEqual(rollo["advertencias"], ["¿Quisiste decir 1.250 kg?"])
        self.assertEqual(rollo["bloqueo"], "Un rollo no puede pesar más de 15 kg.")
        rollo, _vista = self._revision("150")
        self.assertEqual((rollo["sugerencia"], rollo["advertencias"]), (0.15, ["¿Quisiste decir 0.150 kg?"]))
        for peso in ("99", "1250.0", "125,0"):
            with self.subTest(peso=peso):
                self.assertIsNone(self._revision(peso)[0]["sugerencia"], "Solo sin punto y de 100 en adelante")

    def test_limites_configurables(self):
        parametros = self.env["ir.config_parameter"]
        parametros.set_param("duran_captura_tianguis.peso_bloqueo_max", "20")
        parametros.set_param("duran_captura_tianguis.peso_advertencia_min", "1")
        parametros.set_param("duran_captura_tianguis.peso_advertencia_max", "3")
        self.assertEqual(self._revision("16")[0]["advertencias"], ["Pesa más de 3 kg: revisa que esté bien."])
        self.assertEqual(self._revision("0.9")[0]["advertencias"], ["Pesa menos de 1 kg: revisa que esté bien."])
        self.assertEqual(self._revision("2")[0]["advertencias"], [])
        self.assertEqual(self._revision("20.5")[0]["bloqueo"], "Un rollo no puede pesar más de 20 kg.")

        parametros.search([("key", "=", "duran_captura_tianguis.peso_advertencia_max")]).unlink()
        (movimiento,) = self._movimientos(self.o2, self.rollo_b)[:1]
        self.assertIn(
            "duran_captura_tianguis.peso_advertencia_max",
            self._error(self._params(rollos=[(movimiento, "1")]))["message"],
        )

    # === Acceso === #

    def test_sin_grupo_y_sin_sesion(self):
        params = self._params(**self._entrega_mezclada())
        self._entrar(self.sin_grupo)
        self.assertEqual(self._error(params)["name"], "odoo.exceptions.AccessError")
        self.authenticate(None, None)
        respuesta = self._jsonrpc(RUTA, params)
        self.assertNotIn("result", respuesta)
        self.assertEqual(respuesta["error"]["code"], 100)
