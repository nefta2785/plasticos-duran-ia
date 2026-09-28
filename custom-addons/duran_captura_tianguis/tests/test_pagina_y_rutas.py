""" Pasos 2 a 4: la página /captura y las rutas de lectura (zonas, clientes, catálogo). """
import re

from odoo import Command
from odoo.tests import HttpCase, tagged

from .common import GRUPO_CAPTURA, RUTAS_API, RUTAS_PEDIDO, CapturaDatosPrueba, CapturaHttpMixin


@tagged("post_install", "-at_install")
class TestPaginaYRutas(CapturaDatosPrueba, CapturaHttpMixin, HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.usuario_captura = cls._usuario("captura_prueba", GRUPO_CAPTURA)
        cls.usuario_sin_grupo = cls._usuario("sin_grupo_prueba", "sales_team.group_sale_salesman")
        cls.usuario_portal = cls._usuario("portal_prueba", "base.group_portal")
        cls._crear_datos_captura()
        cls._sin_gastar_folios()

    # === Página /captura === #

    def test_pagina_sin_sesion_redirige_al_login(self):
        self.authenticate(None, None)
        response = self.url_open("/captura", allow_redirects=False)
        self.assertIn(response.status_code, (302, 303))
        self.assertIn("/web/login", response.headers["Location"])

    def test_pagina_sin_grupo_da_403(self):
        for usuario in (self.usuario_sin_grupo, self.usuario_portal):
            with self.subTest(usuario=usuario.login):
                self._entrar(usuario)
                self.assertEqual(self.url_open("/captura").status_code, 403)

    def test_pagina_con_grupo_da_200(self):
        self._entrar(self.usuario_captura)
        response = self.url_open("/captura")
        self.assertEqual(response.status_code, 200)
        for contenedor in ('id="contenido"', 'id="btn-regresar"', 'id="barra-pedido"', 'id="btn-pedido"'):
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
                    for ruta in RUTAS_PEDIDO:
                        self.assertIn(ruta, response.text)

    # === Zonas y clientes === #

    def test_zonas_son_las_etiquetas_de_contacto(self):
        self._entrar(self.usuario_captura)
        zonas = self._resultado("/captura/api/zonas")
        esperadas = self.env["res.partner.category"].search([])
        self.assertEqual(
            {z["id"]: z["nombre"] for z in zonas},
            {zona.id: zona.display_name for zona in esperadas},
        )

    def test_zona_hija_muestra_su_nombre_completo(self):
        padre = self.env["res.partner.category"].create({"name": "Zona padre prueba"})
        hija = self.env["res.partner.category"].create({"name": "Zona hija prueba", "parent_id": padre.id})
        self._entrar(self.usuario_captura)
        zonas = {z["id"]: z["nombre"] for z in self._resultado("/captura/api/zonas")}
        self.assertEqual(zonas[hija.id], "Zona padre prueba / Zona hija prueba")

    def test_clientes_de_zona(self):
        self._entrar(self.usuario_captura)
        clientes = self._resultado("/captura/api/clientes", {"zona_id": self.zona_con_clientes.id})
        self.assertEqual(clientes, [{"id": self.cliente.id, "nombre": self.cliente.name}])

    def test_cliente_con_varias_zonas_aparece_en_cada_una(self):
        zona_a, zona_b = self.env["res.partner.category"].create([
            {"name": "Zona prueba A"}, {"name": "Zona prueba B"},
        ])
        cliente = self.env["res.partner"].create({
            "name": "Cliente dos zonas prueba", "category_id": [Command.set([zona_a.id, zona_b.id])],
        })
        self._entrar(self.usuario_captura)
        for zona in (zona_a, zona_b):
            with self.subTest(zona=zona.name):
                clientes = self._resultado("/captura/api/clientes", {"zona_id": zona.id})
                self.assertEqual([c["id"] for c in clientes], [cliente.id])

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

    # === Catálogo === #

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

        # Nombre + atributo.
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

    def test_categoria_hija_muestra_su_nombre_completo(self):
        hija = self.env["product.category"].create({"name": "Subcategoría prueba", "parent_id": self.categoria.id})
        producto = self._plantilla("En subcategoría prueba", categ_id=hija.id).product_variant_id
        self._entrar(self.usuario_captura)
        catalogo = self._resultado("/captura/api/catalogo")
        categoria = next(c for c in catalogo if c["id"] == hija.id)
        self.assertEqual(categoria["nombre"], "Categoría prueba captura / Subcategoría prueba")
        self.assertEqual([p["id"] for p in categoria["productos"]], [producto.id])

    # === Rutas JSON sin grupo / sin sesión === #

    def test_api_sin_grupo_da_access_error(self):
        for usuario in (self.usuario_sin_grupo, self.usuario_portal):
            self._entrar(usuario)
            for ruta in RUTAS_API:
                with self.subTest(usuario=usuario.login, ruta=ruta):
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
