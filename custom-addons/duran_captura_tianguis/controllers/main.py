import os

from werkzeug.exceptions import Forbidden

from odoo import _, http
from odoo.addons.web.controllers.home import Home
from odoo.exceptions import AccessError
from odoo.http import request
from odoo.tools.misc import file_path

GRUPO_CAPTURA = "duran_captura_tianguis.group_captura_tianguis"
GRUPO_GERENTE_VENTAS = "sales_team.group_sale_manager"
ARCHIVOS_ESTATICOS = (
    "duran_captura_tianguis/static/src/captura.css",
    "duran_captura_tianguis/static/src/captura.js",
)


def es_usuario_tianguis(usuario):
    """ Usuario solo de tianguis: con el grupo "Captura tianguis" y sin ser
    gerente de Ventas ni administrador (`_is_admin` incluye a Ajustes, que
    implica "Permisos de acceso"). Su inicio es /captura. """
    usuario = usuario.sudo()
    return (
        usuario.has_group(GRUPO_CAPTURA)
        and not usuario.has_group(GRUPO_GERENTE_VENTAS)
        and not usuario._is_admin()
    )


class CapturaHome(Home):

    def _login_redirect(self, uid, redirect=None):
        """ Después de iniciar sesión, el usuario de tianguis siempre llega a
        /captura, venga de donde venga (p. ej. con ?redirect=/odoo/discuss).
        Con la sesión a medias (segundo factor) se deja lo de Odoo. """
        url = super()._login_redirect(uid, redirect=redirect)
        if request.session.uid and es_usuario_tianguis(request.env["res.users"].browse(uid)):
            return "/captura"
        return url


class CapturaTianguis(http.Controller):
    """ `auth='user'` ya exige sesión iniciada; además solo los usuarios del
    grupo "Captura tianguis" pueden usar la pantalla y sus rutas. """

    def _tiene_grupo_captura(self):
        return request.env.user.has_group(GRUPO_CAPTURA)

    def _captura(self):
        """ Modelo con los datos de la pantalla, tras validar el grupo. En las
        rutas jsonrpc un AccessError llega al navegador como error legible. """
        if not self._tiene_grupo_captura():
            raise AccessError(_("No tienes permiso para usar la pantalla de captura."))
        return request.env["duran.captura"]

    def _version_estaticos(self):
        """ Odoo sirve /static con caché de una semana: se agrega `?v=` con la
        fecha de modificación para que el celular descargue siempre la última
        versión del JS y el CSS. """
        return int(max(os.path.getmtime(file_path(ruta)) for ruta in ARCHIVOS_ESTATICOS))

    @http.route("/captura", type="http", auth="user", methods=["GET"])
    def captura(self, **kwargs):
        if not self._tiene_grupo_captura():
            raise Forbidden()
        return request.render("duran_captura_tianguis.captura_page", {
            "version": self._version_estaticos(),
            # El usuario de tianguis no ve "Salir": no sale a Odoo ni cierra sesión.
            "puede_salir": not es_usuario_tianguis(request.env.user),
        })

    @http.route("/captura/api/zonas", type="jsonrpc", auth="user", methods=["POST"])
    def api_zonas(self):
        return self._captura().get_zonas()

    @http.route("/captura/api/clientes", type="jsonrpc", auth="user", methods=["POST"])
    def api_clientes(self, zona_id):
        return self._captura().get_clientes(zona_id)

    @http.route("/captura/api/catalogo", type="jsonrpc", auth="user", methods=["POST"])
    def api_catalogo(self):
        return self._captura().get_catalogo()

    @http.route("/captura/api/habituales", type="jsonrpc", auth="user", methods=["POST"])
    def api_habituales(self, cliente_id):
        return self._captura().get_habituales(cliente_id)

    @http.route("/captura/api/enviar", type="jsonrpc", auth="user", methods=["POST"])
    def api_enviar(self, cliente_id, zona_id, lineas, token):
        return self._captura().enviar_pedido(cliente_id, zona_id, lineas, token)

    @http.route("/captura/api/entrega/clientes", type="jsonrpc", auth="user", methods=["POST"])
    def api_entrega_clientes(self, zona_id):
        return self._captura().get_clientes_entrega(zona_id)

    @http.route("/captura/api/entrega/pendiente", type="jsonrpc", auth="user", methods=["POST"])
    def api_entrega_pendiente(self, cliente_id, zona_id):
        return self._captura().get_pendientes_entrega(cliente_id, zona_id)

    @http.route("/captura/api/entrega/vista_previa", type="jsonrpc", auth="user", methods=["POST"])
    def api_entrega_vista_previa(self, cliente_id, zona_id, rollos, productos):
        return self._captura().get_vista_previa_entrega(cliente_id, zona_id, rollos, productos)

    @http.route("/captura/api/entrega/confirmar", type="jsonrpc", auth="user", methods=["POST"])
    def api_entrega_confirmar(self, cliente_id, zona_id, rollos, productos, movimientos_vistos, token):
        return self._captura().confirmar_entrega(cliente_id, zona_id, rollos, productos, movimientos_vistos, token)

    @http.route("/captura/api/acomodo", type="jsonrpc", auth="user", methods=["POST"])
    def api_acomodo(self):
        return self._captura().get_acomodo()

    @http.route("/captura/api/cobro/clientes", type="jsonrpc", auth="user", methods=["POST"])
    def api_cobro_clientes(self, zona_id):
        return self._captura().get_clientes_cobro(zona_id)

    @http.route("/captura/api/cobro/detalle", type="jsonrpc", auth="user", methods=["POST"])
    def api_cobro_detalle(self, cliente_id, zona_id):
        return self._captura().get_cobro(cliente_id, zona_id)

    @http.route("/captura/api/cobro/confirmar", type="jsonrpc", auth="user", methods=["POST"])
    def api_cobro_confirmar(self, cliente_id, zona_id, tipo, visto, token, monto=None):
        return self._captura().confirmar_cobro(cliente_id, zona_id, tipo, visto, token, monto)
