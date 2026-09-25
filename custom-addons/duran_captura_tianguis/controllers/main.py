from werkzeug.exceptions import Forbidden

from odoo import _, http
from odoo.exceptions import AccessError
from odoo.http import request

GRUPO_CAPTURA = "duran_captura_tianguis.group_captura_tianguis"


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

    @http.route("/captura", type="http", auth="user", methods=["GET"])
    def captura(self, **kwargs):
        if not self._tiene_grupo_captura():
            raise Forbidden()
        return request.render("duran_captura_tianguis.captura_page", {
            "user": request.env.user,
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
