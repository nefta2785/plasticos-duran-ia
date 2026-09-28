import re
from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged

GRUPO_CAPTURA = "duran_captura_tianguis.group_captura_tianguis"
RUTAS_API = (
    "/captura/api/zonas", "/captura/api/clientes", "/captura/api/catalogo", "/captura/api/habituales",
)


class CapturaDatosPrueba:
    """ Crea todo lo que las pruebas necesitan, sin depender de los datos que
    ya existan en la base. Todo se revierte al terminar cada clase. """

    _numero_orden = 0

    @classmethod
    def _plantilla(cls, name, **vals):
        return cls.env["product.template"].create({
            "name": name, "categ_id": cls.categoria.id, "sale_ok": True, "list_price": 10.0, **vals,
        })

    @classmethod
    def _orden(cls, cliente, lineas, dias_atras=1, estado="sale", vendedor=None):
        """ Orden con fecha `dias_atras` días antes de hoy y en `estado`.

        No usa action_confirm: la numeración de órdenes y de entregas usa
        secuencias de PostgreSQL, que NO se revierten al terminar la prueba, y
        confirmar gastaría folios reales de duranDEV. Por lo mismo lleva nombre
        fijo, se crea en borrador (crear líneas en una orden ya confirmada
        lanzaría la entrega) y luego solo se cambia su estado. """
        CapturaDatosPrueba._numero_orden += 1
        orden = cls.env["sale.order"].with_context(skip_procurement=True).create({
            "name": f"PRUEBA-HAB-{CapturaDatosPrueba._numero_orden}",
            "partner_id": cliente.id,
            "user_id": vendedor.id if vendedor else False,
            "order_line": [
                Command.create({"product_id": producto.id, "product_uom_qty": cantidad})
                for producto, cantidad in lineas
            ],
        })
        orden.write({
            "state": estado,
            "date_order": fields.Datetime.now() - timedelta(days=dias_atras),
        })
        return orden

    @classmethod
    def _crear_datos_captura(cls):
        env = cls.env
        cls.zona_con_clientes = env["res.partner.category"].create({"name": "Zona prueba con clientes"})
        cls.zona_vacia = env["res.partner.category"].create({"name": "Zona prueba vacía"})
        cls.cliente = env["res.partner"].create({
            "name": "Cliente prueba captura",
            "category_id": [Command.set(cls.zona_con_clientes.ids)],
        })
        cls.categoria = env["product.category"].create({"name": "Categoría prueba captura"})
        plantilla = cls._plantilla

        cls.normal = plantilla("Normal prueba").product_variant_id
        cls.por_kilo = plantilla(
            "Por kilo prueba", uom_id=env.ref("uom.product_uom_kgm").id,
        ).product_variant_id
        cls.pv_con_precio = plantilla(
            "Peso variable con precio prueba", es_peso_variable=True, precio_por_kg=50.0,
        ).product_variant_id
        cls.pv_precio_cero = plantilla(
            "Peso variable precio cero prueba", es_peso_variable=True, precio_por_kg=0.0,
        ).product_variant_id
        cls.pv_sin_precio = plantilla(
            "Peso variable sin precio prueba", es_peso_variable=True,
        ).product_variant_id
        cls.no_vendible = plantilla("No vendible prueba", sale_ok=False).product_variant_id
        archivado = plantilla("Archivado prueba")
        cls.archivado = archivado.product_variant_id
        archivado.action_archive()

        medida = env["product.attribute"].create({
            "name": "Medida prueba",
            "value_ids": [Command.create({"name": "25x35"}), Command.create({"name": "30x40"})],
        })
        cls.con_variantes = plantilla("Variantes prueba", attribute_line_ids=[Command.create({
            "attribute_id": medida.id,
            "value_ids": [Command.set(medida.value_ids.ids)],
        })]).product_variant_ids


@tagged("post_install", "-at_install")
class TestZonaEnOrden(TransactionCase):

    def test_zona_id_es_many2one_a_etiquetas_de_contacto(self):
        field = self.env["sale.order"]._fields.get("zona_id")
        self.assertTrue(field, "sale.order debe tener zona_id")
        self.assertEqual(field.type, "many2one")
        self.assertEqual(field.comodel_name, "res.partner.category")

    def test_agrupar_ordenes_por_zona(self):
        zona_a, zona_b = self.env["res.partner.category"].create([
            {"name": "Zona prueba A"}, {"name": "Zona prueba B"},
        ])
        cliente = self.env["res.partner"].create({"name": "Cliente prueba zona"})
        # Nombre explícito: así no se consume un folio real de la secuencia
        # de órdenes (los folios de PostgreSQL no se revierten con rollback).
        ordenes = self.env["sale.order"].create([
            {"name": "PRUEBA-ZONA-1", "partner_id": cliente.id, "zona_id": zona_a.id},
            {"name": "PRUEBA-ZONA-2", "partner_id": cliente.id, "zona_id": zona_a.id},
            {"name": "PRUEBA-ZONA-3", "partner_id": cliente.id, "zona_id": zona_b.id},
        ])
        grupos = self.env["sale.order"]._read_group(
            [("id", "in", ordenes.ids)], groupby=["zona_id"], aggregates=["__count"],
        )
        self.assertEqual(dict(grupos), {zona_a: 2, zona_b: 1})

    def test_vistas_muestran_zona(self):
        SaleOrder = self.env["sale.order"]
        busqueda = SaleOrder.get_view(self.env.ref("sale.view_sales_order_filter").id, "search")["arch"]
        self.assertIn('<field name="zona_id"', busqueda)
        self.assertIn("'group_by': 'zona_id'", busqueda)
        lista = SaleOrder.get_view(self.env.ref("sale.view_order_tree").id, "list")["arch"]
        self.assertIn('name="zona_id"', lista)
        formulario = SaleOrder.get_view(self.env.ref("sale.view_order_form").id, "form")["arch"]
        self.assertIn('name="zona_id"', formulario)


@tagged("post_install", "-at_install")
class TestCapturaHttp(CapturaDatosPrueba, HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.usuario_captura = new_test_user(
            cls.env, login="captura_prueba", groups=GRUPO_CAPTURA,
            context={"no_reset_password": True},
        )
        cls.usuario_sin_grupo = new_test_user(
            cls.env, login="sin_grupo_prueba", groups="sales_team.group_sale_salesman",
            context={"no_reset_password": True},
        )
        cls._crear_datos_captura()

    def _entrar(self, usuario):
        # new_test_user asigna como contraseña el login (solo existe en la prueba).
        self.authenticate(usuario.login, usuario.login)

    def _jsonrpc(self, ruta, params=None):
        response = self.url_open(ruta, json={
            "jsonrpc": "2.0", "method": "call", "id": 0, "params": params or {},
        })
        self.assertEqual(response.status_code, 200)
        return response.json()

    def _resultado(self, ruta, params=None):
        respuesta = self._jsonrpc(ruta, params)
        self.assertNotIn("error", respuesta, respuesta.get("error"))
        return respuesta["result"]

    # === Página /captura === #

    def test_pagina_sin_sesion_redirige_al_login(self):
        self.authenticate(None, None)
        response = self.url_open("/captura", allow_redirects=False)
        self.assertIn(response.status_code, (302, 303))
        self.assertIn("/web/login", response.headers["Location"])

    def test_pagina_sin_grupo_da_403(self):
        self._entrar(self.usuario_sin_grupo)
        response = self.url_open("/captura")
        self.assertEqual(response.status_code, 403)

    def test_pagina_con_grupo_da_200(self):
        self._entrar(self.usuario_captura)
        response = self.url_open("/captura")
        self.assertEqual(response.status_code, 200)
        for contenedor in ('id="contenido"', 'id="btn-regresar"', 'id="barra-pedido"'):
            self.assertIn(contenedor, response.text)

    def test_pagina_carga_js_y_css(self):
        self._entrar(self.usuario_captura)
        pagina = self.url_open("/captura").text
        self.assertIn('name="viewport"', pagina)
        tipos = {"css": "text/css", "js": "javascript"}
        for extension, tipo in tipos.items():
            with self.subTest(archivo=extension):
                encontrado = re.search(
                    rf'"(/duran_captura_tianguis/static/src/captura\.{extension}\?v=\d+)"', pagina,
                )
                self.assertTrue(encontrado, f"la página no enlaza captura.{extension} con ?v=")
                response = self.url_open(encontrado.group(1))
                self.assertEqual(response.status_code, 200)
                self.assertIn(tipo, response.headers["Content-Type"])
                if extension == "js":
                    self.assertIn("/captura/api/catalogo", response.text)

    # === Rutas JSON con el grupo === #

    def test_zonas_son_las_etiquetas_de_contacto(self):
        self._entrar(self.usuario_captura)
        zonas = self._resultado("/captura/api/zonas")
        esperadas = self.env["res.partner.category"].search([])
        self.assertEqual({z["id"] for z in zonas}, set(esperadas.ids))
        self.assertEqual(
            {z["id"]: z["nombre"] for z in zonas},
            {zona.id: zona.display_name for zona in esperadas},
        )

    def test_clientes_de_zona(self):
        self._entrar(self.usuario_captura)
        clientes = self._resultado("/captura/api/clientes", {"zona_id": self.zona_con_clientes.id})
        self.assertEqual(clientes, [{"id": self.cliente.id, "nombre": self.cliente.name}])

    def test_zona_sin_clientes_devuelve_lista_vacia(self):
        self._entrar(self.usuario_captura)
        clientes = self._resultado("/captura/api/clientes", {"zona_id": self.zona_vacia.id})
        self.assertEqual(clientes, [])

    def test_zona_inexistente_da_error_legible(self):
        self._entrar(self.usuario_captura)
        zona_borrada = self.env["res.partner.category"].create({"name": "Zona prueba borrada"})
        zona_id = zona_borrada.id
        zona_borrada.unlink()
        respuesta = self._jsonrpc("/captura/api/clientes", {"zona_id": zona_id})
        self.assertNotIn("result", respuesta)
        self.assertEqual(respuesta["error"]["data"]["name"], "odoo.exceptions.UserError")
        self.assertEqual(respuesta["error"]["data"]["message"], "La zona ya no existe.")

    def test_catalogo(self):
        self._entrar(self.usuario_captura)
        catalogo = self._resultado("/captura/api/catalogo")
        productos = {p["id"]: p for categoria in catalogo for p in categoria["productos"]}

        # Regla general: ningún producto de peso variable sin precio por kg.
        for producto in productos.values():
            if producto["es_peso_variable"]:
                self.assertGreater(producto["precio"], 0, producto)

        # Agrupado por categoría, solo lo activo y vendible.
        mi_categoria = next(c for c in catalogo if c["id"] == self.categoria.id)
        self.assertEqual(mi_categoria["nombre"], self.categoria.complete_name)
        self.assertEqual(
            {p["id"] for p in mi_categoria["productos"]},
            {self.normal.id, self.por_kilo.id, self.pv_con_precio.id, *self.con_variantes.ids},
        )
        for excluido in (self.pv_precio_cero, self.pv_sin_precio, self.no_vendible, self.archivado):
            self.assertNotIn(excluido.id, productos, excluido.name)

        # Nombre + atributo, unidad y precio.
        self.assertEqual(
            sorted(productos[v.id]["nombre"] for v in self.con_variantes),
            ["Variantes prueba 25x35", "Variantes prueba 30x40"],
        )
        # Precios: "$50/kg" para peso variable, "c/u" para piezas y "/<unidad>"
        # para el resto. La ruta responde en el idioma del usuario que captura.
        simbolo = self.env.company.currency_id.symbol
        kg = self.por_kilo.uom_id.with_context(lang=self.usuario_captura.lang).name
        pv = productos[self.pv_con_precio.id]
        self.assertEqual((pv["precio"], pv["precio_texto"], pv["unidad"]), (50.0, f"{simbolo}50/kg", "c/u"))
        normal = productos[self.normal.id]
        self.assertEqual((normal["precio"], normal["precio_texto"], normal["unidad"]), (10.0, f"{simbolo}10 c/u", "c/u"))
        por_kilo = productos[self.por_kilo.id]
        self.assertEqual((por_kilo["precio_texto"], por_kilo["unidad"]), (f"{simbolo}10/{kg}", kg))

    def test_habituales(self):
        self._orden(self.cliente, [(self.normal, 2), (self.por_kilo, 1)])
        self._orden(self.cliente, [(self.normal, 1)])
        self._entrar(self.usuario_captura)
        habituales = self._resultado("/captura/api/habituales", {"cliente_id": self.cliente.id})
        self.assertEqual([p["id"] for p in habituales], [self.normal.id, self.por_kilo.id])

    def test_habituales_cliente_inexistente_da_error_legible(self):
        self._entrar(self.usuario_captura)
        borrado = self.env["res.partner"].create({"name": "Cliente prueba borrado"})
        cliente_id = borrado.id
        borrado.unlink()
        respuesta = self._jsonrpc("/captura/api/habituales", {"cliente_id": cliente_id})
        self.assertNotIn("result", respuesta)
        self.assertEqual(respuesta["error"]["data"]["name"], "odoo.exceptions.UserError")
        self.assertEqual(respuesta["error"]["data"]["message"], "El cliente ya no existe.")

    # === Rutas JSON sin grupo / sin sesión === #

    def _params_ruta(self, ruta):
        if ruta.endswith("clientes"):
            return {"zona_id": self.zona_con_clientes.id}
        if ruta.endswith("habituales"):
            return {"cliente_id": self.cliente.id}
        return {}

    def test_api_sin_grupo_da_access_error(self):
        self._entrar(self.usuario_sin_grupo)
        for ruta in RUTAS_API:
            with self.subTest(ruta=ruta):
                respuesta = self._jsonrpc(ruta, self._params_ruta(ruta))
                self.assertNotIn("result", respuesta)
                self.assertEqual(respuesta["error"]["data"]["name"], "odoo.exceptions.AccessError")

    def test_api_sin_sesion_da_sesion_expirada(self):
        self.authenticate(None, None)
        for ruta in RUTAS_API:
            with self.subTest(ruta=ruta):
                respuesta = self._jsonrpc(ruta, self._params_ruta(ruta))
                self.assertNotIn("result", respuesta)
                self.assertEqual(respuesta["error"]["code"], 100)


@tagged("post_install", "-at_install")
class TestLoDeSiempre(CapturaDatosPrueba, TransactionCase):
    """ Cálculo de "Lo de siempre": órdenes confirmadas de los últimos 90
    días, máximo 8 productos, por frecuencia. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._crear_datos_captura()
        # Quien captura tiene "Ventas: solo sus documentos" (implícito en el
        # grupo); las órdenes del historial son de OTRO vendedor.
        cls.usuario_captura = new_test_user(
            cls.env, login="captura_habituales_prueba", groups=GRUPO_CAPTURA,
            context={"no_reset_password": True},
        )
        cls.otro_vendedor = new_test_user(
            cls.env, login="otro_vendedor_prueba", groups="sales_team.group_sale_salesman",
            context={"no_reset_password": True},
        )
        cls.cliente_habitual = cls.env["res.partner"].create({"name": "Cliente habitual prueba"})
        cls.p = [cls._plantilla(f"Habitual prueba {i}").product_variant_id for i in range(10)]

    def _habituales(self, cliente):
        captura = self.env["duran.captura"].with_user(self.usuario_captura)
        return [producto["id"] for producto in captura.get_habituales(cliente.id)]

    def _orden_de_otro(self, lineas, **kwargs):
        return self._orden(self.cliente_habitual, lineas, vendedor=self.otro_vendedor, **kwargs)

    def test_orden_por_frecuencia_cantidad_y_fecha(self):
        a, b, c, d, e, f, g = self.p[:7]
        self._orden_de_otro([(a, 1), (b, 5), (e, 2)], dias_atras=1)
        self._orden_de_otro([(a, 1), (b, 5)], dias_atras=2)
        self._orden_de_otro([(a, 1), (c, 1)], dias_atras=3)
        self._orden_de_otro([(d, 3)], dias_atras=4)
        self._orden_de_otro([(g, 1)], dias_atras=5)
        self._orden_de_otro([(f, 1)], dias_atras=10)
        # a: 3 órdenes; b: 2 órdenes; el resto 1 orden, desempatados por
        # cantidad total (d 3 > e 2 > c, g, f 1) y luego por fecha más reciente
        # (c hace 3 días > g hace 5 > f hace 10).
        self.assertEqual(self._habituales(self.cliente_habitual), [x.id for x in (a, b, d, e, c, g, f)])

    def test_maximo_8_productos(self):
        self._orden_de_otro([(producto, 1) for producto in self.p])
        habituales = self._habituales(self.cliente_habitual)
        self.assertEqual(len(habituales), 8)
        self.assertEqual(habituales, [p.id for p in self.p[:8]])

    def test_solo_cuentan_ordenes_confirmadas_recientes_del_cliente(self):
        valido, viejo, borrador, cancelado, de_otro_cliente, de_contacto = self.p[:6]
        self._orden_de_otro([(valido, 1)], dias_atras=89)
        self._orden_de_otro([(viejo, 1)], dias_atras=91)
        self._orden_de_otro([(borrador, 1)], estado="draft")
        self._orden_de_otro([(cancelado, 1)], estado="cancel")
        otro_cliente = self.env["res.partner"].create({"name": "Otro cliente prueba"})
        self._orden(otro_cliente, [(de_otro_cliente, 1)], vendedor=self.otro_vendedor)
        # Las órdenes a nombre de un contacto del cliente también cuentan.
        contacto = self.env["res.partner"].create({
            "name": "Contacto prueba", "parent_id": self.cliente_habitual.id,
        })
        self._orden(contacto, [(de_contacto, 1)], vendedor=self.otro_vendedor)
        self.assertCountEqual(self._habituales(self.cliente_habitual), [valido.id, de_contacto.id])

    def test_solo_productos_del_catalogo(self):
        valido = self.p[0]
        self._orden_de_otro([
            (valido, 1), (self.pv_precio_cero, 1), (self.pv_sin_precio, 1),
            (self.no_vendible, 1), (self.archivado, 1),
        ])
        self.assertEqual(self._habituales(self.cliente_habitual), [valido.id])

    def test_sin_historial_lista_vacia(self):
        self.assertEqual(self._habituales(self.cliente_habitual), [])

    def test_ve_historial_de_ordenes_de_otro_vendedor(self):
        orden = self._orden_de_otro([(self.p[0], 1)])
        SaleOrder = self.env["sale.order"].with_user(self.usuario_captura)
        self.assertFalse(SaleOrder.search([("id", "=", orden.id)]), "con solo sus documentos no ve la orden")
        self.assertEqual(self._habituales(self.cliente_habitual), [self.p[0].id])

    def test_mismos_datos_que_el_catalogo(self):
        self._orden_de_otro([(self.pv_con_precio, 1), (self.normal, 1)])
        captura = self.env["duran.captura"].with_user(self.usuario_captura)
        catalogo = {p["id"]: p for c in captura.get_catalogo() for p in c["productos"]}
        for producto in captura.get_habituales(self.cliente_habitual.id):
            self.assertEqual(producto, catalogo[producto["id"]])

    def test_cliente_inexistente(self):
        borrado = self.env["res.partner"].create({"name": "Cliente prueba borrado"})
        cliente_id = borrado.id
        borrado.unlink()
        with self.assertRaisesRegex(UserError, "El cliente ya no existe."):
            self.env["duran.captura"].with_user(self.usuario_captura).get_habituales(cliente_id)
