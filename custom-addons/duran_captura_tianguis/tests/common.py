""" Datos y ayudantes compartidos por las pruebas de duran_captura_tianguis.

Todas las pruebas crean sus propios usuarios, zonas, clientes y productos, sin
depender de los datos que existan en la base, y todo se revierte al terminar
cada clase de pruebas. """
import itertools
import uuid
from datetime import timedelta

from odoo import Command, fields
from odoo.addons.base.models import ir_sequence
from odoo.tests import new_test_user

GRUPO_CAPTURA = "duran_captura_tianguis.group_captura_tianguis"
RUTAS_PEDIDO = (
    "/captura/api/zonas", "/captura/api/clientes", "/captura/api/catalogo",
    "/captura/api/habituales", "/captura/api/enviar",
)
# Rutas del modo Entrega.
RUTAS_ENTREGA = (
    "/captura/api/entrega/clientes", "/captura/api/entrega/pendiente",
    "/captura/api/entrega/vista_previa", "/captura/api/entrega/confirmar",
)
RUTAS_API = RUTAS_PEDIDO + RUTAS_ENTREGA
# Rutas del modo Cobro. Aún sin pantallas: se suman a RUTAS_API cuando la
# pantalla las use.
RUTAS_COBRO = ("/captura/api/cobro/clientes", "/captura/api/cobro/detalle", "/captura/api/cobro/confirmar")


class CapturaDatosPrueba:
    """ Mezclar con TransactionCase o HttpCase. """

    _numero_orden = 0

    @classmethod
    def _usuario(cls, login, groups):
        # new_test_user pone como contraseña el propio login: solo existe
        # dentro de la prueba y se revierte al terminar.
        return new_test_user(cls.env, login=login, groups=groups, context={"no_reset_password": True})

    @classmethod
    def _sin_gastar_folios(cls):
        """ Los folios de órdenes y entregas salen de secuencias de PostgreSQL
        (`_select_nextval`), que NO se revierten al terminar la prueba. Mientras
        dure la clase se sustituye por un contador falso (folios 9xxxxx): las
        órdenes que se confirman en las pruebas no gastan folios de la base. """
        contador = itertools.count(900001)
        cls.classPatch(ir_sequence, "_select_nextval", lambda cr, nombre: (next(contador),))

    @classmethod
    def _plantilla(cls, name, **vals):
        return cls.env["product.template"].create({
            "name": name, "categ_id": cls.categoria.id, "sale_ok": True, "list_price": 10.0, **vals,
        })

    @classmethod
    def _orden(cls, cliente, lineas, dias_atras=1, estado="sale", vendedor=None):
        """ Orden con fecha `dias_atras` días antes de hoy y en `estado`, SIN
        action_confirm (no gasta folios ni crea entregas): nombre fijo, se crea
        en borrador (crear líneas en una orden ya confirmada lanzaría la
        entrega) y luego solo se cambia su estado. Sirve para armar historial. """
        CapturaDatosPrueba._numero_orden += 1
        orden = cls.env["sale.order"].with_context(skip_procurement=True).create({
            "name": f"PRUEBA-HIST-{CapturaDatosPrueba._numero_orden}",
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
    def _cliente(cls, nombre, zonas):
        return cls.env["res.partner"].create({"name": nombre, "category_id": [Command.set(zonas.ids)]})

    @classmethod
    def _confirmada(cls, cliente, lineas, vendedor=None, **vals):
        """ Orden confirmada (con su entrega), SIN zona, como las creadas desde
        Odoo. Cada línea: (producto, cantidad) o (producto, cantidad, precio). """
        orden = cls.env["sale.order"].create({
            "partner_id": cliente.id,
            "user_id": vendedor.id if vendedor else False,
            "order_line": [
                Command.create({
                    "product_id": linea[0].id, "product_uom_qty": linea[1],
                    **({"price_unit": linea[2]} if len(linea) > 2 else {}),
                })
                for linea in lineas
            ],
            **vals,
        })
        orden.action_confirm()
        return orden

    @classmethod
    def _validar(cls, picking):
        for move in picking.move_ids:
            move.write({"quantity": move.product_uom_qty, "picked": True})
        picking.button_validate()
        assert picking.state == "done", picking.state
        return picking

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


class CapturaHttpMixin:
    """ Ayudantes para llamar a /captura y sus rutas jsonrpc (mezclar con HttpCase). """

    def _entrar(self, usuario):
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

    def _params_envio(self, lineas, token=None, cliente=None, zona=None):
        return {
            "cliente_id": (cliente or self.cliente).id,
            "zona_id": (zona or self.zona_con_clientes).id,
            "lineas": [{"producto_id": producto.id, "cantidad": cantidad} for producto, cantidad in lineas],
            "token": token or uuid.uuid4().hex,
        }

    def _enviar(self, lineas, **kwargs):
        return self._resultado("/captura/api/enviar", self._params_envio(lineas, **kwargs))

    def _params_ruta(self, ruta):
        """ Parámetros válidos para cada ruta de RUTAS_API. """
        if ruta.endswith("clientes"):
            return {"zona_id": self.zona_con_clientes.id}
        if ruta.endswith("cobro/confirmar"):
            return {
                "cliente_id": self.cliente.id, "zona_id": self.zona_con_clientes.id, "tipo": "nada",
                "visto": {"lineas": [], "documentos": [], "borradores": []}, "token": uuid.uuid4().hex,
            }
        if ruta.endswith("entrega/confirmar"):
            return {
                "cliente_id": self.cliente.id, "zona_id": self.zona_con_clientes.id,
                "rollos": [], "productos": [], "movimientos_vistos": [1], "token": uuid.uuid4().hex,
            }
        if ruta.endswith("entrega/vista_previa"):
            return {
                "cliente_id": self.cliente.id, "zona_id": self.zona_con_clientes.id,
                "rollos": [], "productos": [],
            }
        if ruta.endswith(("entrega/pendiente", "cobro/detalle")):
            return {"cliente_id": self.cliente.id, "zona_id": self.zona_con_clientes.id}
        if ruta.endswith("habituales"):
            return {"cliente_id": self.cliente.id}
        if ruta.endswith("enviar"):
            return self._params_envio([(self.normal, 1)])
        return {}
