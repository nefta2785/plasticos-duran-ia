""" /captura como inicio de los usuarios de tianguis: después del login, botón
"Salir" y app "Captura" en el menú de Odoo. """
from urllib.parse import urlparse

from odoo import http
from odoo.tests import HttpCase, tagged
from odoo.tests.common import HOST, Opener, get_db_name

from .common import GRUPO_CAPTURA, CapturaDatosPrueba

GERENTE = "sales_team.group_sale_manager"
DESTINOS = (None, "/odoo", "/odoo/discuss", "/odoo/action-sale.action_orders", "/captura")


@tagged("post_install", "-at_install")
class TestInicioCaptura(CapturaDatosPrueba, HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tianguis = cls._usuario("inicio_tianguis", GRUPO_CAPTURA)
        cls.gerente = cls._usuario("inicio_gerente", f"{GRUPO_CAPTURA},{GERENTE}")
        cls.admin = cls._usuario("inicio_admin", f"{GRUPO_CAPTURA},base.group_system")
        cls.permisos = cls._usuario("inicio_permisos", f"{GRUPO_CAPTURA},base.group_erp_manager")
        cls.vendedor = cls._usuario("inicio_vendedor", "sales_team.group_sale_salesman")
        cls.menu = cls.env.ref("duran_captura_tianguis.captura_menu_root")

    # === Ayudantes === #

    def _sin_sesion(self):
        """ Sesión nueva sin usuario, como un celular que abre el login
        (igual que web/tests/test_login.py). """
        self.session = http.root.session_store.new()
        self.session.update(http.get_default_session(), db=get_db_name())
        self.opener = Opener(self)
        self.opener.cookies.set("session_id", self.session.sid, domain=HOST, path="/")

    def _login(self, usuario, destino=None):
        """ Inicia sesión con el formulario de Odoo y devuelve a dónde manda. """
        self._sin_sesion()
        datos = {"login": usuario.login, "password": usuario.login, "csrf_token": http.Request.csrf_token(self)}
        if destino:
            datos["redirect"] = destino
        respuesta = self.url_open("/web/login", data=datos, allow_redirects=False)
        self.assertEqual(respuesta.status_code, 303, respuesta.text[:300])
        return urlparse(respuesta.headers["Location"]).path

    def _pagina(self, usuario):
        self.authenticate(usuario.login, usuario.login)
        respuesta = self.url_open("/captura")
        self.assertEqual(respuesta.status_code, 200)
        return respuesta.text

    # === Después del login === #

    def test_tianguis_siempre_llega_a_captura(self):
        for destino in DESTINOS:
            with self.subTest(destino=destino):
                self.assertEqual(self._login(self.tianguis, destino), "/captura")

    def test_gerente_y_administradores_entran_a_odoo_como_siempre(self):
        for usuario in (self.gerente, self.admin, self.permisos):
            for destino in DESTINOS:
                with self.subTest(usuario=usuario.login, destino=destino):
                    esperado = urlparse(destino or "/odoo").path
                    self.assertEqual(self._login(usuario, destino), esperado)

    def test_sin_grupo_captura_no_cambia(self):
        self.assertEqual(self._login(self.vendedor), "/odoo")

    # === Botón "Salir" === #

    def test_boton_salir_lo_decide_el_servidor(self):
        self.assertNotIn("data-salir", self._pagina(self.tianguis))
        for usuario in (self.gerente, self.admin, self.permisos):
            with self.subTest(usuario=usuario.login):
                self.assertIn('data-salir="1"', self._pagina(usuario))

    # === App "Captura" en el menú de Odoo === #

    def test_app_captura_en_el_menu(self):
        accion = self.menu.action
        self.assertEqual((accion.type, accion.url, accion.target), ("ir.actions.act_url", "/captura", "self"))
        self.assertFalse(self.menu.parent_id, "es una app del menú principal")
        Menu = self.env["ir.ui.menu"]
        for usuario in (self.tianguis, self.gerente, self.admin):
            with self.subTest(usuario=usuario.login):
                visibles = Menu.with_user(usuario)._visible_menu_ids()
                self.assertIn(self.menu.id, visibles)
                # No es la primera app: /odoo sin acción abre la primera, y los
                # gerentes y administradores deben seguir entrando a Odoo normal.
                primera = Menu.with_user(usuario).search([("parent_id", "=", False)]).filtered(
                    lambda m: m.id in visibles
                )[:1]
                self.assertNotEqual(primera, self.menu)
        self.assertNotIn(self.menu.id, Menu.with_user(self.vendedor)._visible_menu_ids())

    # === Celular perdido === #

    def test_cambiar_la_contrasena_cierra_las_sesiones(self):
        """ Lo que dice docs/guia-operacion.md: cambiar la contraseña desde
        Odoo cierra las sesiones abiertas del usuario. """
        self.authenticate(self.tianguis.login, self.tianguis.login)
        self.assertEqual(self.url_open("/captura", allow_redirects=False).status_code, 200)
        self.tianguis.password = "otra-contrasena-de-prueba"
        self.env.flush_all()
        respuesta = self.url_open("/captura", allow_redirects=False)
        self.assertEqual(respuesta.status_code, 303)
        self.assertEqual(urlparse(respuesta.headers["Location"]).path, "/web/login")
