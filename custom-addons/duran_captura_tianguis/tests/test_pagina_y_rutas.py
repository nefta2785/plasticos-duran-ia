""" Pasos 2 a 4: la página /captura y las rutas de lectura (zonas, clientes, catálogo). """
import json
import re
import struct

from odoo import Command
from odoo.tests import HttpCase, tagged

from .common import GRUPO_CAPTURA, RUTAS_API, CapturaDatosPrueba, CapturaHttpMixin


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
        for contenedor in (
            'id="contenido"', 'id="btn-regresar"', 'id="btn-inicio"', 'id="operacion"', 'id="barra-pedido"', 'id="btn-pedido"',
            'id="falta-paso"', 'id="modal-titulo"',
        ):
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
                    for ruta in RUTAS_API:
                        self.assertIn(ruta, response.text)

    # === App instalable: manifiesto, íconos y service worker === #

    def test_pagina_enlaza_manifiesto_e_iconos(self):
        self._entrar(self.usuario_captura)
        pagina = self.url_open("/captura").text
        self.assertRegex(
            pagina, r'<link rel="manifest" href="/duran_captura_tianguis/static/captura\.webmanifest\?v=\d+"',
        )
        self.assertIn('rel="icon"', pagina)
        self.assertIn('rel="apple-touch-icon"', pagina)
        self.assertIn("/captura/sw.js", self.url_open("/duran_captura_tianguis/static/src/captura.js").text)

    def test_manifiesto_e_iconos_sin_sesion(self):
        """ Chrome descarga el manifiesto sin cookies: debe ser público. """
        self._entrar(self.usuario_captura)
        ruta_manifiesto = re.search(r'rel="manifest" href="([^"]+)"', self.url_open("/captura").text).group(1)
        self.authenticate(None, None)
        response = self.url_open(ruta_manifiesto, allow_redirects=False)
        self.assertEqual(response.status_code, 200)
        manifiesto = json.loads(response.text)
        self.assertEqual(
            {campo: manifiesto[campo] for campo in (
                "name", "short_name", "start_url", "scope", "display", "theme_color", "background_color",
            )},
            {
                "name": "Captura tianguis", "short_name": "Captura", "start_url": "/captura",
                "scope": "/captura", "display": "standalone",
                "theme_color": "#0b3d91", "background_color": "#0b3d91",
            },
        )
        self.assertEqual(
            {(icono["sizes"], icono["purpose"]) for icono in manifiesto["icons"]},
            {("192x192", "any"), ("512x512", "any"), ("512x512", "maskable")},
        )
        for icono in manifiesto["icons"]:
            with self.subTest(icono=icono["src"]):
                response = self.url_open(icono["src"], allow_redirects=False)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers["Content-Type"], "image/png")
                ancho, alto = struct.unpack(">II", response.content[16:24])  # cabecera IHDR del PNG
                self.assertEqual(f"{ancho}x{alto}", icono["sizes"])

    def test_service_worker_sin_sesion_y_sin_cache(self):
        self.authenticate(None, None)
        response = self.url_open("/captura/sw.js", allow_redirects=False)
        self.assertEqual(response.status_code, 200)
        self.assertIn("javascript", response.headers["Content-Type"])
        # Su alcance máximo sería /captura/ (con diagonal), que no cubre la página /captura.
        self.assertEqual(response.headers["Service-Worker-Allowed"], "/captura")
        self.assertIn('addEventListener("fetch"', response.text)
        self.assertIn("fetch(event.request)", response.text)
        for cache in ("caches", "Cache", ".put(", "addAll(", "match("):
            self.assertNotIn(cache, response.text)

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

    def test_catalogo_por_kg(self):
        """ `por_kg` sale de la unidad estándar kg de Odoo (no de su nombre):
        verdadero en lo que se vende por kg, se pese o no; falso en piezas y en
        los rollos (se pesan, pero se venden por pieza). """
        kg_suelto = self._plantilla(
            "KG suelto prueba", uom_id=self.env.ref("uom.product_uom_kgm").id,
            es_peso_variable=True, precio_por_kg=70.0,
        ).product_variant_id
        self._entrar(self.usuario_captura)
        productos = {p["id"]: p for c in self._resultado("/captura/api/catalogo") for p in c["productos"]}
        casos = {
            self.por_kilo: (True, False, "kg"),
            kg_suelto: (True, True, "kg"),
            self.normal: (False, False, "c/u"),
            self.pv_con_precio: (False, True, "c/u"),
        }
        for producto, esperado in casos.items():
            with self.subTest(producto=producto.name):
                p = productos[producto.id]
                self.assertEqual((p["por_kg"], p["es_peso_variable"], p["unidad"]), esperado)

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

    def _categorias_con_producto(self, nombres, **vals):
        """ Categorías nuevas, cada una con un producto vendible, para que
        salgan en el catálogo. """
        categorias = self.env["product.category"]
        for nombre in nombres:
            categoria = self.env["product.category"].create({"name": nombre, **vals})
            self._plantilla(f"Producto de {nombre}", categ_id=categoria.id)
            categorias |= categoria
        return categorias

    def _orden_en_catalogo(self, categorias):
        self._entrar(self.usuario_captura)
        ids = [c["id"] for c in self._resultado("/captura/api/catalogo")]
        return [i for i in ids if i in categorias.ids], ids

    def test_orden_de_categorias_por_el_campo_de_la_app(self):
        """ Con "Orden en la app", las categorías siguen ese orden (no el
        alfabético) y van antes que todas las que no lo tienen. """
        rollos, asa, basura = self._categorias_con_producto(
            ["Orden prueba Rollos", "Orden prueba Asa", "Orden prueba Basura"],
        )
        rollos.captura_orden, asa.captura_orden, basura.captura_orden = 1, 2, 4
        sin_orden = self._categorias_con_producto(["Orden prueba Zeta sin orden", "Orden prueba Alfa sin orden"])
        orden, todas = self._orden_en_catalogo(rollos | asa | basura | sin_orden)
        self.assertEqual(orden, [rollos.id, asa.id, basura.id, *sin_orden.sorted("complete_name").ids])
        # Todas las que tienen orden (también las reales de la base) van antes que las que no.
        Categoria = self.env["product.category"]
        con_orden = [bool(Categoria.browse(i).captura_orden) for i in todas]
        self.assertEqual(con_orden, sorted(con_orden, reverse=True))
        # El texto del botón sigue siendo el nombre completo de la categoría.
        catalogo = {c["id"]: c["nombre"] for c in self._resultado("/captura/api/catalogo")}
        self.assertEqual(catalogo[asa.id], "Orden prueba Asa")

    def test_sin_orden_queda_el_orden_alfabetico(self):
        """ Sin "Orden en la app" (0 o vacío), el orden alfabético de siempre. """
        categorias = self._categorias_con_producto(
            ["Alfabético prueba C", "Alfabético prueba A", "Alfabético prueba B"],
        )
        categorias[0].captura_orden = 0
        orden, _todas = self._orden_en_catalogo(categorias)
        self.assertEqual(orden, categorias.sorted("complete_name").ids)
        self.assertEqual(
            [self.env["product.category"].browse(i).name for i in orden],
            ["Alfabético prueba A", "Alfabético prueba B", "Alfabético prueba C"],
        )

    def test_orden_visible_en_el_formulario_de_categoria(self):
        arch = self.env["product.category"].get_views(
            [(self.env.ref("product.product_category_form_view").id, "form")],
        )["views"]["form"]["arch"]
        self.assertIn('name="captura_orden"', arch)

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
