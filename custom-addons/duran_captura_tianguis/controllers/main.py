from werkzeug.exceptions import Forbidden

from odoo import http
from odoo.http import request

GRUPO_CAPTURA = "duran_captura_tianguis.group_captura_tianguis"


class CapturaTianguis(http.Controller):

    def _check_grupo_captura(self):
        """ `auth='user'` ya exige sesión iniciada; además solo los usuarios
        del grupo "Captura tianguis" pueden usar la pantalla. """
        if not request.env.user.has_group(GRUPO_CAPTURA):
            raise Forbidden()

    @http.route("/captura", type="http", auth="user", methods=["GET"])
    def captura(self, **kwargs):
        self._check_grupo_captura()
        return request.render("duran_captura_tianguis.captura_page", {
            "user": request.env.user,
        })
