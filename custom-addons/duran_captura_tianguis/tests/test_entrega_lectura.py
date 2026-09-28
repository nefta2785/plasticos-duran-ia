""" Paso 3 (modo Entrega): rutas de lectura de clientes con entregas pendientes
y de lo pendiente de entregar a un cliente. """
from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import HttpCase, tagged

from .common import GRUPO_CAPTURA, CapturaDatosPrueba, CapturaHttpMixin

RUTA_CLIENTES = "/captura/api/entrega/clientes"
RUTA_PENDIENTE = "/captura/api/entrega/pendiente"


@tagged("post_install", "-at_install")
class TestEntregaLectura(CapturaDatosPrueba, CapturaHttpMixin, HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._sin_gastar_folios()
        cls._crear_datos_captura()
        env = cls.env
        cls.mama = cls._usuario("entrega_mama", GRUPO_CAPTURA)
        cls.otro_vendedor = cls._usuario("entrega_otro_vendedor", "sales_team.group_sale_salesman")
        cls.sin_grupo = cls._usuario("entrega_sin_grupo", "sales_team.group_sale_salesman")
        cls.almacen = env["stock.warehouse"].search([("company_id", "=", env.company.id)], limit=1)

        cls.zona_b = env["res.partner.category"].create({"name": "Zona prueba B"})
        zona_a = cls.zona_con_clientes
        cls.direccion = env["res.partner"].create({
            "name": "Puesto del cliente prueba", "parent_id": cls.cliente.id, "type": "delivery",
        })
        cls.dos_zonas = cls._cliente("Cliente prueba dos zonas", zona_a | cls.zona_b)
        cls.sin_pendientes = cls._cliente("Cliente prueba sin pendientes", zona_a)
        cls.otra_zona = cls._cliente("Cliente prueba otra zona", cls.zona_b)

        cls.rollo = cls._plantilla(
            "Rollo almacenable prueba", es_peso_variable=True, precio_por_kg=50.0, is_storable=True,
        ).product_variant_id
        cls.sin_stock = cls._plantilla("Almacenable sin stock prueba", is_storable=True).product_variant_id
        # Existencia para UN solo rollo: de los dos pedidos, uno queda reservado.
        env["stock.quant"]._update_available_quantity(cls.rollo, cls.almacen.lot_stock_id, 1)

        # Pendientes del cliente: la orden más antigua es de otro vendedor y sin zona.
        cls.o1 = cls._confirmada(cls.cliente, [(cls.normal, 2), (cls.rollo, 2)], vendedor=cls.otro_vendedor)
        cls.o2 = cls._confirmada(
            cls.cliente, [(cls.normal, 3, 12.0), (cls.sin_stock, 4)],
            partner_shipping_id=cls.direccion.id,
        )
        # Lo que NO debe aparecer.
        cls.entregada = cls._confirmada(cls.cliente, [(cls.normal, 1)])
        cls.entrega_validada = cls._validar(cls.entregada.picking_ids)
        cls.cancelada = cls._confirmada(cls.cliente, [(cls.normal, 1)])
        cls.cancelada._action_cancel()
        cls.devolucion_cliente = cls._devolver(cls.entrega_validada)
        cls._validar(cls.devolucion_cliente)
        cls.devolucion_de_devolucion = cls._devolver(cls.devolucion_cliente)
        cls.a_proveedor = cls._salida_sin_venta(cls.cliente, env.ref("stock.stock_location_suppliers"))
        cls.salida_manual = cls._salida_sin_venta(cls.cliente, env.ref("stock.stock_location_customers"))
        cls._confirmada(cls.sin_pendientes, [(cls.normal, 1)]).picking_ids.action_cancel()
        cls._validar(cls._confirmada(cls.sin_pendientes, [(cls.normal, 1)]).picking_ids)

        cls.o_dos_zonas = cls._confirmada(cls.dos_zonas, [(cls.normal, 1)], vendedor=cls.otro_vendedor)
        cls.o_otra_zona = cls._confirmada(cls.otra_zona, [(cls.sin_stock, 1)])

    # === Ayudantes para armar los datos === #

    @classmethod
    def _devolver(cls, picking):
        asistente = cls.env["stock.return.picking"].with_context(
            active_id=picking.id, active_model="stock.picking",
        ).create({})
        asistente.product_return_moves.quantity = 1
        return asistente._create_return()

    @classmethod
    def _salida_sin_venta(cls, cliente, destino):
        picking = cls.env["stock.picking"].create({
            "picking_type_id": cls.almacen.out_type_id.id,
            "partner_id": cliente.id,
            "location_id": cls.almacen.lot_stock_id.id,
            "location_dest_id": destino.id,
            "move_ids": [Command.create({
                "product_id": cls.normal.id, "product_uom_qty": 1,
                "location_id": cls.almacen.lot_stock_id.id, "location_dest_id": destino.id,
            })],
        })
        picking.action_confirm()
        return picking

    # === Ayudantes para las rutas === #

    def setUp(self):
        super().setUp()
        self._entrar(self.mama)

    def _clientes(self, zona):
        return [c["id"] for c in self._resultado(RUTA_CLIENTES, {"zona_id": zona.id})]

    def _pendiente(self, cliente, zona=None):
        return self._resultado(RUTA_PENDIENTE, {
            "cliente_id": cliente.id, "zona_id": (zona or self.zona_con_clientes).id,
        })

    def _error(self, ruta, params):
        respuesta = self._jsonrpc(ruta, params)
        self.assertNotIn("result", respuesta)
        return respuesta["error"]["data"]

    def _producto(self, pendiente, producto):
        return next(p for p in pendiente["productos"] if p["id"] == producto.id)

    # === Clientes de la zona === #

    def test_clientes_con_entregas_pendientes(self):
        self.assertEqual(
            self._clientes(self.zona_con_clientes), [self.cliente.id, self.dos_zonas.id],
            "Solo clientes de la zona con pendientes; sin pendientes y de otra zona, no",
        )

    def test_cliente_en_dos_zonas_aparece_en_ambas(self):
        self.assertIn(self.dos_zonas.id, self._clientes(self.zona_con_clientes))
        self.assertEqual(self._clientes(self.zona_b), [self.dos_zonas.id, self.otra_zona.id])

    def test_zona_vacia_y_zona_sin_pendientes(self):
        self.assertEqual(self._clientes(self.zona_vacia), [])
        zona_sin_pendientes = self.env["res.partner.category"].create({"name": "Zona prueba sin pendientes"})
        self.sin_pendientes.category_id = [Command.link(zona_sin_pendientes.id)]
        self.assertEqual(self._clientes(zona_sin_pendientes), [])

    def test_cliente_solo_con_devoluciones_y_salidas_sin_venta_no_aparece(self):
        """ Con la entrega de venta pendiente ya validada, al cliente solo le
        quedan pendientes una devolución, una devolución a proveedor y una
        salida sin orden de venta: ya no aparece. """
        for orden in (self.o1, self.o2):
            self._validar(orden.picking_ids)
        self.assertNotIn(self.devolucion_de_devolucion.state, ("done", "cancel"))
        self.assertTrue(self.devolucion_de_devolucion.return_id)
        self.assertEqual(self.a_proveedor.picking_type_code, "outgoing")
        self.assertNotEqual(self.salida_manual.state, "done")
        self.assertEqual(self._clientes(self.zona_con_clientes), [self.dos_zonas.id])

    def test_zona_inexistente(self):
        self.assertEqual(self._error(RUTA_CLIENTES, {"zona_id": 999999999})["message"], "La zona ya no existe.")

    # === Lo pendiente del cliente === #

    def test_todas_las_entregas_pendientes_del_cliente_y_nada_mas(self):
        pendiente = self._pendiente(self.cliente)
        self.assertEqual(pendiente["cliente"], {"id": self.cliente.id, "nombre": self.cliente.name})
        movimientos = {m["move_id"] for p in pendiente["productos"] for m in p["movimientos"]}
        esperados = (self.o1 | self.o2).picking_ids.move_ids
        self.assertEqual(movimientos, set(esperados.ids))

    def test_orden_de_otro_vendedor_y_sin_zona_si_aparece(self):
        self.assertEqual((self.o1.user_id, self.o1.zona_id.id), (self.otro_vendedor, False))
        with self.assertRaises(AccessError, msg="Con sus permisos no puede leer la orden de otro vendedor"):
            self.o1.with_user(self.mama).read(["name"])
        normal = self._producto(self._pendiente(self.cliente), self.normal)
        self.assertEqual(normal["movimientos"][0]["precio"], 10.0, "Precio leído de la orden de otro vendedor")

    def test_agrupado_por_producto_de_la_orden_mas_antigua_a_la_mas_nueva(self):
        pendiente = self._pendiente(self.cliente)
        self.assertEqual(
            [p["id"] for p in pendiente["productos"]], [self.normal.id, self.rollo.id, self.sin_stock.id],
        )
        normal = self._producto(pendiente, self.normal)
        self.assertEqual(
            [(m["move_id"], m["cantidad"]) for m in normal["movimientos"]],
            [(self.o1.picking_ids.move_ids.filtered(lambda m: m.product_id == self.normal).id, 2.0),
             (self.o2.picking_ids.move_ids.filtered(lambda m: m.product_id == self.normal).id, 3.0)],
        )
        self.assertEqual(normal["cantidad"], 5.0)

    def test_rollos_uno_por_uno(self):
        rollo = self._producto(self._pendiente(self.cliente), self.rollo)
        movimientos_rollo = self.o1.picking_ids.move_ids.filtered(lambda m: m.product_id == self.rollo)
        self.assertEqual(len(movimientos_rollo), 2)
        self.assertEqual([m["move_id"] for m in rollo["movimientos"]], movimientos_rollo.sorted("id").ids)
        self.assertEqual([m["cantidad"] for m in rollo["movimientos"]], [1.0, 1.0])
        self.assertEqual((rollo["cantidad"], rollo["es_peso_variable"], rollo["unidad"]), (2.0, True, "c/u"))

    def test_marca_sin_existencia_en_sistema(self):
        pendiente = self._pendiente(self.cliente)
        normal = self._producto(pendiente, self.normal)
        self.assertEqual((normal["sin_existencia"], normal["cantidad_reservada"]), (False, 5.0))
        self.assertEqual([m["sin_existencia"] for m in normal["movimientos"]], [False, False])

        rollo = self._producto(pendiente, self.rollo)
        self.assertEqual(sorted(m["sin_existencia"] for m in rollo["movimientos"]), [False, True],
                         "Hay existencia para un solo rollo")
        self.assertEqual((rollo["sin_existencia"], rollo["cantidad_reservada"]), (True, 1.0))

        sin_stock = self._producto(pendiente, self.sin_stock)
        self.assertEqual((sin_stock["sin_existencia"], sin_stock["cantidad_reservada"]), (True, 0.0))

    def test_precios(self):
        """ Peso variable: precio por kg VIGENTE. Los demás: el de su línea de
        venta (si difiere entre órdenes, el grupo muestra ambos). """
        self.rollo.product_tmpl_id.precio_por_kg = 55.0
        self.normal.product_tmpl_id.list_price = 99.0
        pendiente = self._pendiente(self.cliente)

        rollo = self._producto(pendiente, self.rollo)
        self.assertEqual((rollo["precio"], rollo["precio_texto"]), (55.0, "$55/kg"))
        self.assertEqual([m["precio"] for m in rollo["movimientos"]], [55.0, 55.0])

        normal = self._producto(pendiente, self.normal)
        self.assertEqual([m["precio"] for m in normal["movimientos"]], [10.0, 12.0])
        self.assertEqual((normal["precio"], normal["precio_texto"]), (None, "$10 c/u / $12 c/u"))

        sin_stock = self._producto(pendiente, self.sin_stock)
        self.assertEqual((sin_stock["precio"], sin_stock["precio_texto"]), (10.0, "$10 c/u"))

    def test_cliente_en_dos_zonas_desde_cualquiera(self):
        for zona in (self.zona_con_clientes, self.zona_b):
            with self.subTest(zona=zona.name):
                pendiente = self._pendiente(self.dos_zonas, zona)
                self.assertEqual(
                    [m["move_id"] for p in pendiente["productos"] for m in p["movimientos"]],
                    self.o_dos_zonas.picking_ids.move_ids.ids,
                )

    def test_cliente_sin_pendientes_devuelve_lista_vacia(self):
        self.assertEqual(self._pendiente(self.sin_pendientes)["productos"], [])

    # === Lo que la usuaria de captura NO puede leer === #

    def test_no_lee_clientes_de_otra_zona_ni_fuera_de_zonas(self):
        fuera = self.env["res.partner"].create({"name": "Cliente prueba sin zona"})
        self._confirmada(fuera, [(self.normal, 1)])
        casos = [
            (self.otra_zona, self.zona_con_clientes, "Cliente prueba otra zona ya no está en la zona Zona prueba con clientes."),
            (fuera, self.zona_con_clientes, "Cliente prueba sin zona ya no está en la zona Zona prueba con clientes."),
            (self.direccion, self.zona_con_clientes, None),
        ]
        for cliente, zona, mensaje in casos:
            with self.subTest(cliente=cliente.name):
                error = self._error(RUTA_PENDIENTE, {"cliente_id": cliente.id, "zona_id": zona.id})
                self.assertEqual(error["name"], "odoo.exceptions.UserError")
                if mensaje:
                    self.assertEqual(error["message"], mensaje)

    def test_datos_inexistentes(self):
        self.assertEqual(
            self._error(RUTA_PENDIENTE, {"cliente_id": 999999999, "zona_id": self.zona_con_clientes.id})["message"],
            "El cliente ya no existe.",
        )
        self.assertEqual(
            self._error(RUTA_PENDIENTE, {"cliente_id": self.cliente.id, "zona_id": 999999999})["message"],
            "La zona ya no existe.",
        )

    def test_sin_grupo_y_sin_sesion(self):
        casos = (
            (RUTA_CLIENTES, {"zona_id": self.zona_con_clientes.id}),
            (RUTA_PENDIENTE, {"cliente_id": self.cliente.id, "zona_id": self.zona_con_clientes.id}),
        )
        self._entrar(self.sin_grupo)
        for ruta, params in casos:
            with self.subTest(ruta=ruta, usuario="sin grupo"):
                self.assertEqual(self._error(ruta, params)["name"], "odoo.exceptions.AccessError")
        self.authenticate(None, None)
        for ruta, params in casos:
            with self.subTest(ruta=ruta, usuario="sin sesión"):
                respuesta = self._jsonrpc(ruta, params)
                self.assertNotIn("result", respuesta)
                self.assertEqual(respuesta["error"]["code"], 100)
