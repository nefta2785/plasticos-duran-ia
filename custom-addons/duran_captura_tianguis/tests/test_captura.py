import itertools
import re
import uuid
from datetime import timedelta

from odoo import Command, fields
from odoo.addons.base.models import ir_sequence
from odoo.exceptions import UserError
from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged

GRUPO_CAPTURA = "duran_captura_tianguis.group_captura_tianguis"
RUTAS_API = (
    "/captura/api/zonas", "/captura/api/clientes", "/captura/api/catalogo",
    "/captura/api/habituales", "/captura/api/enviar",
)


class CapturaDatosPrueba:
    """ Crea todo lo que las pruebas necesitan, sin depender de los datos que
    ya existan en la base. Todo se revierte al terminar cada clase. """

    _numero_orden = 0

    @classmethod
    def _sin_gastar_folios(cls):
        """ Los folios de órdenes y entregas salen de secuencias de PostgreSQL
        (`_select_nextval`), que NO se revierten al terminar la prueba. Mientras
        dure la clase, se sustituye por un contador falso: las órdenes que se
        confirman en las pruebas no gastan folios reales de duranDEV. """
        contador = itertools.count(900001)
        cls.classPatch(ir_sequence, "_select_nextval", lambda cr, nombre: (next(contador),))

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
        cls._sin_gastar_folios()

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

    # === Enviar === #

    def _params_envio(self, lineas, token=None, cliente=None, zona=None):
        return {
            "cliente_id": (cliente or self.cliente).id,
            "zona_id": (zona or self.zona_con_clientes).id,
            "lineas": [{"producto_id": producto.id, "cantidad": cantidad} for producto, cantidad in lineas],
            "token": token or uuid.uuid4().hex,
        }

    def _enviar(self, lineas, **kwargs):
        return self._resultado("/captura/api/enviar", self._params_envio(lineas, **kwargs))

    def test_enviar_crea_y_confirma_la_orden(self):
        self._entrar(self.usuario_captura)
        token = uuid.uuid4().hex
        envio = self._enviar(
            [(self.normal, 2), (self.por_kilo, 3), (self.pv_con_precio, 3)], token=token,
        )
        self.assertFalse(envio["ya_existia"])
        self.assertEqual(envio["productos"], 8)
        self.assertEqual(envio["cliente"], self.cliente.name)

        self.env.invalidate_all()
        orden = self.env["sale.order"].browse(envio["id"])
        self.assertEqual(orden.name, envio["nombre"])
        self.assertEqual(orden.state, "sale", "la orden debe quedar confirmada")
        self.assertEqual(orden.partner_id, self.cliente)
        self.assertEqual(orden.zona_id, self.zona_con_clientes)
        self.assertEqual(orden.user_id, self.usuario_captura)
        self.assertEqual(orden.captura_token, token)
        cantidades = {}
        for linea in orden.order_line:
            cantidades.setdefault(linea.product_id, []).append(linea.product_uom_qty)
        # Peso variable: duran_peso_variable parte la línea en 1 rollo por línea.
        self.assertEqual(cantidades, {self.normal: [2.0], self.por_kilo: [3.0], self.pv_con_precio: [1.0, 1.0, 1.0]})
        self.assertEqual(orden.order_line.tax_ids, self.env["account.tax"], "sin impuestos")
        # Confirmar crea la entrega de inmediato, con los mismos productos.
        self.assertEqual(len(orden.picking_ids), 1)
        self.assertEqual(sum(orden.picking_ids.move_ids.mapped("product_uom_qty")), 8)
        # Folios del contador falso (_sin_gastar_folios), no de duranDEV.
        self.assertRegex(orden.name, r"9\d{5}$")
        self.assertRegex(orden.picking_ids.name, r"9\d{5}$")
        # Quien captura ("solo sus documentos") sí ve la orden que creó.
        self.assertIn(orden, self.env["sale.order"].with_user(self.usuario_captura).search([]))

    def test_enviar_siempre_crea_una_orden_nueva(self):
        existente = self._orden(self.cliente, [(self.normal, 1)], estado="draft")
        self._entrar(self.usuario_captura)
        primera = self._enviar([(self.normal, 1)])
        segunda = self._enviar([(self.normal, 1)])
        self.assertEqual(len({existente.id, primera["id"], segunda["id"]}), 3)
        self.env.invalidate_all()
        self.assertEqual(len(existente.order_line), 1, "no se suma a la orden existente")
        self.assertEqual(existente.state, "draft")

    def test_mismo_token_no_duplica(self):
        self._entrar(self.usuario_captura)
        token = uuid.uuid4().hex
        primera = self._enviar([(self.normal, 2)], token=token)
        segunda = self._enviar([(self.normal, 2)], token=token)
        self.assertEqual(segunda["id"], primera["id"])
        self.assertEqual((primera["ya_existia"], segunda["ya_existia"]), (False, True))
        self.assertEqual(self.env["sale.order"].search_count([("captura_token", "=", token)]), 1)

    def test_vendedor_es_quien_captura_aunque_el_cliente_tenga_vendedor(self):
        self.cliente.user_id = self.usuario_sin_grupo
        self._entrar(self.usuario_captura)
        envio = self._enviar([(self.normal, 1)])
        self.env.invalidate_all()
        self.assertEqual(self.env["sale.order"].browse(envio["id"]).user_id, self.usuario_captura)

    def test_enviar_error_legible_y_sin_orden(self):
        antes = self.env["sale.order"].search_count([("partner_id", "=", self.cliente.id)])
        self._entrar(self.usuario_captura)
        respuesta = self._jsonrpc(
            "/captura/api/enviar", self._params_envio([(self.normal, 1), (self.pv_sin_precio, 1)]),
        )
        self.assertNotIn("result", respuesta)
        self.assertEqual(respuesta["error"]["data"]["name"], "odoo.exceptions.UserError")
        self.assertIn(self.pv_sin_precio.name, respuesta["error"]["data"]["message"])
        self.env.invalidate_all()
        self.assertEqual(self.env["sale.order"].search_count([("partner_id", "=", self.cliente.id)]), antes)

    # === Rutas JSON sin grupo / sin sesión === #

    def _params_ruta(self, ruta):
        if ruta.endswith("clientes"):
            return {"zona_id": self.zona_con_clientes.id}
        if ruta.endswith("habituales"):
            return {"cliente_id": self.cliente.id}
        if ruta.endswith("enviar"):
            return self._params_envio([(self.normal, 1)])
        return {}

    def test_api_sin_grupo_o_sin_sesion_no_crea_ordenes(self):
        antes = self.env["sale.order"].search_count([("partner_id", "=", self.cliente.id)])
        self._entrar(self.usuario_sin_grupo)
        self._jsonrpc("/captura/api/enviar", self._params_envio([(self.normal, 1)]))
        self.authenticate(None, None)
        self._jsonrpc("/captura/api/enviar", self._params_envio([(self.normal, 1)]))
        self.env.invalidate_all()
        self.assertEqual(self.env["sale.order"].search_count([("partner_id", "=", self.cliente.id)]), antes)

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


@tagged("post_install", "-at_install")
class TestEnviarPedidoValidaciones(CapturaDatosPrueba, TransactionCase):
    """ Cada caso inválido falla con un mensaje claro y no deja ninguna orden. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._crear_datos_captura()
        cls._sin_gastar_folios()
        cls.usuario_captura = new_test_user(
            cls.env, login="captura_envio_prueba", groups=GRUPO_CAPTURA,
            context={"no_reset_password": True},
        )
        cls.otra_zona = cls.env["res.partner.category"].create({"name": "Otra zona prueba"})

    def _enviar(self, lineas=None, token=None, cliente_id=None, zona_id=None):
        if lineas is None:
            lineas = [{"producto_id": self.normal.id, "cantidad": 1}]
        return self.env["duran.captura"].with_user(self.usuario_captura).enviar_pedido(
            cliente_id or self.cliente.id,
            zona_id or self.zona_con_clientes.id,
            lineas,
            uuid.uuid4().hex if token is None else token,
        )

    def _id_borrado(self, modelo, vals):
        registro = self.env[modelo].create(vals)
        registro_id = registro.id
        registro.unlink()
        return registro_id

    def assertRechaza(self, mensaje, **kwargs):
        antes = self.env["sale.order"].search_count([])
        with self.assertRaisesRegex(UserError, mensaje):
            with self.env.cr.savepoint():
                self._enviar(**kwargs)
        self.assertEqual(self.env["sale.order"].search_count([]), antes, "no debe quedar ninguna orden")

    def test_caso_valido_de_referencia(self):
        self.assertEqual(self.env["sale.order"].browse(self._enviar()["id"]).state, "sale")

    def test_cantidades_enteras_mayores_a_cero(self):
        for cantidad in (1.5, 0, -1, True, "2", None):
            with self.subTest(cantidad=cantidad):
                self.assertRechaza(
                    "números enteros mayores a cero",
                    lineas=[{"producto_id": self.normal.id, "cantidad": cantidad}],
                )

    def test_producto_invalido(self):
        for lineas in ([{"producto_id": "x", "cantidad": 1}], [{"cantidad": 1}], ["no es un dict"]):
            with self.subTest(lineas=lineas):
                self.assertRechaza("producto inválido", lineas=lineas)

    def test_pedido_vacio(self):
        for lineas in ([], "nada"):
            with self.subTest(lineas=lineas):
                self.assertRechaza("El pedido está vacío", lineas=lineas)

    def test_token_invalido(self):
        for token in ("", "abc", str(uuid.uuid4()), "X" * 32, 12345):
            with self.subTest(token=token):
                self.assertRechaza("No se pudo identificar el pedido", token=token)

    def test_zona_y_cliente(self):
        self.assertRechaza("La zona ya no existe", zona_id=self._id_borrado("res.partner.category", {"name": "Zona prueba x"}))
        self.assertRechaza("El cliente ya no existe", cliente_id=self._id_borrado("res.partner", {"name": "Cliente prueba x"}))
        self.assertRechaza("ya no está en la zona", zona_id=self.otra_zona.id)

    def test_productos_que_no_estan_a_la_venta(self):
        borrado = self._id_borrado("product.product", {"name": "Producto prueba borrado"})
        for producto_id in (self.pv_precio_cero.id, self.pv_sin_precio.id, self.no_vendible.id, self.archivado.id, borrado):
            with self.subTest(producto_id=producto_id):
                self.assertRechaza(
                    "ya no están a la venta",
                    lineas=[{"producto_id": self.normal.id, "cantidad": 1}, {"producto_id": producto_id, "cantidad": 1}],
                )

    def test_producto_repetido_se_suma(self):
        envio = self._enviar(lineas=[
            {"producto_id": self.normal.id, "cantidad": 2}, {"producto_id": self.normal.id, "cantidad": 3},
        ])
        orden = self.env["sale.order"].browse(envio["id"])
        self.assertEqual(orden.order_line.mapped("product_uom_qty"), [5.0])
