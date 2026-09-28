import os

from werkzeug.exceptions import Forbidden

from odoo import _, http
from odoo.exceptions import AccessError
from odoo.http import request
from odoo.tools.misc import file_path

GRUPO_CAPTURA = "duran_captura_tianguis.group_captura_tianguis"
ARCHIVOS_ESTATICOS = (
    "duran_captura_tianguis/static/src/captura.css",
    "duran_captura_tianguis/static/src/captura.js",
)


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
