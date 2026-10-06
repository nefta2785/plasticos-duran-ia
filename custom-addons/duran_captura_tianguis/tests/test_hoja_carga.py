""" Hoja de carga (Ventas › Órdenes › Hoja de carga): vista SQL
`duran.hoja.carga` con lo pendiente de entregar por producto y zona, y la
marca de "Acomodado" de hoy (`duran.hoja.carga.marca`). """
import uuid
from datetime import timedelta

from lxml import etree
from psycopg2 import IntegrityError

from odoo import Command, fields
from odoo.exceptions import AccessError
from odoo.tests import HttpCase, tagged
from odoo.tools import mute_logger
from odoo.tools.safe_eval import safe_eval

from ..models.hoja_carga import _hoy
from .common import GRUPO_CAPTURA, CapturaDatosPrueba, CapturaHttpMixin

RUTA_PENDIENTE = "/captura/api/entrega/pendiente"
RUTA_CONFIRMAR = "/captura/api/entrega/confirmar"


@tagged("post_install", "-at_install")
class TestHojaCarga(CapturaDatosPrueba, CapturaHttpMixin, HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._sin_gastar_folios()
        cls._crear_datos_captura()
        env = cls.env
        cls.mama = cls._usuario("hoja_carga_mama", GRUPO_CAPTURA)
        cls.papa = cls._usuario("hoja_carga_papa", "sales_team.group_sale_manager")
        cls.otro_gerente = cls._usuario("hoja_carga_otro_gerente", "sales_team.group_sale_manager")
        cls.admin = cls._usuario("hoja_carga_admin", "base.group_system,sales_team.group_sale_manager")
        cls.vendedor = cls._usuario("hoja_carga_vendedor", "sales_team.group_sale_salesman")
        cls.almacen = env["stock.warehouse"].search([("company_id", "=", env.company.id)], limit=1)
        cls.accion = env.ref("duran_captura_tianguis.hoja_carga_action")
        cls.menu = env.ref("duran_captura_tianguis.hoja_carga_menu")
        sin_impuestos = {"taxes_id": [Command.clear()]}
        cls.pieza = cls._plantilla("Pieza hoja de carga", **sin_impuestos).product_variant_id
        cls.rollo = cls._plantilla(
            "Rollo hoja de carga", es_peso_variable=True, precio_por_kg=80.0, **sin_impuestos,
        ).product_variant_id
        cls.kilo = cls._plantilla(
            "Kilo hoja de carga", uom_id=env.ref("uom.product_uom_kgm").id, **sin_impuestos,
        ).product_variant_id
        cls.zona = cls.zona_con_clientes
        cls.zona_b = env["res.partner.category"].create({"name": "Zona prueba hoja B"})
        cls.cliente_b = cls._cliente("Cliente prueba hoja B", cls.zona_b)

    # === Ayudantes === #

    def _producto(self, nombre, **vals):
        return self._plantilla(nombre, taxes_id=[Command.clear()], **vals).product_variant_id

    def _pedido(self, lineas, cliente=None, zona=None, **vals):
        """ Orden confirmada con zona (como las de la app); `zona=False`: sin
        zona, como las creadas desde Odoo. """
        cliente = cliente or self.cliente
        zona = self.zona if zona is None else zona
        return self._confirmada(cliente, lineas, zona_id=zona.id if zona else False, **vals)

    def _renglones(self, productos=None, usuario=None):
        self.env.flush_all()
        self.env.invalidate_all()
        productos = productos or self._productos_prueba()
        return self.env["duran.hoja.carga"].with_user(usuario or self.papa).search(
            [("product_id", "in", productos.ids)],
        )

    def _hoja(self, productos=None):
        """ {(zona, producto): total} de lo que muestra la hoja. """
        return {(r.zona_id.id, r.product_id.id): r.total for r in self._renglones(productos)}

    def _renglon(self, producto, zona=None):
        zona = self.zona if zona is None else zona
        renglon = self._renglones(producto).filtered(lambda r: r.zona_id == (zona or self.env["res.partner.category"]))
        self.assertLessEqual(len(renglon), 1)
        return renglon

    def _estado(self, producto, zona=None):
        renglon = self._renglon(producto, zona)
        return (renglon.total, renglon.estado, renglon.aviso or None) if renglon else None

    def _acomodado(self, producto, zona=None, cantidad_vista=None, usuario=None):
        """ Toca "Acomodado" como lo hace la lista: con la cantidad del renglón
        que se veía en pantalla en el contexto del botón. """
        renglon = self._renglon(producto, zona).with_user(usuario or self.papa)
        vista = renglon.total if cantidad_vista is None else cantidad_vista
        return renglon.with_context(cantidad_vista=vista).action_acomodado()

    def _quitar(self, producto, zona=None):
        return self._renglon(producto, zona).with_user(self.papa).action_quitar()

    def _marcas(self, productos):
        return self.env["duran.hoja.carga.marca"].search([("product_id", "in", productos.ids)])

    def _productos_prueba(self):
        return self.env["product.product"].search([("name", "ilike", "hoja de carga")])

    def _parcial(self, orden, cantidad, backorder):
        picking = orden.picking_ids
        picking.move_ids.write({"quantity": cantidad, "picked": True})
        picking.with_context(cancel_backorder=not backorder)._action_done()
        return picking

    # === Pendiente === #

    def test_pendiente_en_todos_los_casos(self):
        casos = {}
        # Reservado ("Listo"): lo pedido completo.
        casos["listo"] = (self._producto("Listo hoja de carga"), 2, 2.0)
        # Parcial con backorder: lo que falta queda en otra entrega abierta.
        con_backorder = self._producto("Backorder hoja de carga")
        self._parcial(self._pedido([(con_backorder, 5)]), 2, backorder=True)
        casos["con backorder"] = (con_backorder, None, 3.0)
        # Parcial sin backorder: lo demás se canceló.
        sin_backorder = self._producto("Sin backorder hoja de carga")
        self._parcial(self._pedido([(sin_backorder, 5)]), 2, backorder=False)
        casos["sin backorder"] = (sin_backorder, None, None)
        # Devolución (sin validar y validada): no es carga.
        devuelto = self._producto("Devuelto hoja de carga")
        orden_devuelta = self._pedido([(devuelto, 3)])
        self._validar(orden_devuelta.picking_ids)
        asistente = self.env["stock.return.picking"].with_context(
            active_id=orden_devuelta.picking_ids.id, active_model="stock.picking",
        ).create({})
        asistente.product_return_moves.quantity = 1
        asistente._create_return()
        otra_devolucion = self.env["stock.return.picking"].with_context(
            active_id=orden_devuelta.picking_ids.filtered(lambda p: not p.return_id).id, active_model="stock.picking",
        ).create({})
        otra_devolucion.product_return_moves.quantity = 1
        self._validar(otra_devolucion._create_return())
        casos["devolución"] = (devuelto, None, None)
        # Orden cancelada.
        cancelado = self._producto("Cancelado hoja de carga")
        self._pedido([(cancelado, 4)])._action_cancel()
        casos["orden cancelada"] = (cancelado, None, None)
        # Sin existencia en sistema (almacenable sin stock) y parcialmente disponible.
        sin_existencia = self._producto("Sin existencia hoja de carga", is_storable=True)
        casos["sin existencia"] = (sin_existencia, 3, 3.0)
        parcial = self._producto("Parcial disponible hoja de carga", is_storable=True)
        self.env["stock.quant"]._update_available_quantity(parcial, self.almacen.lot_stock_id, 2)
        casos["parcialmente disponible"] = (parcial, 5, 5.0)
        # Pedido de días anteriores: también sale.
        atrasado = self._producto("Atrasado hoja de carga")
        self._pedido([(atrasado, 3)]).date_order = fields.Datetime.now() - timedelta(days=3)
        casos["atrasado"] = (atrasado, None, 3.0)

        for producto, cantidad, _esperado in casos.values():
            if cantidad:
                self._pedido([(producto, cantidad)])
        estados = {
            nombre: self.env["stock.move"].search([("product_id", "=", producto.id)]).mapped("state")
            for nombre, (producto, _c, _e) in casos.items()
        }
        self.assertEqual(estados["listo"], ["assigned"])
        self.assertEqual(estados["sin existencia"], ["confirmed"])
        self.assertEqual(estados["parcialmente disponible"], ["partially_available"])

        hoja = self._hoja()
        for nombre, (producto, _cantidad, esperado) in casos.items():
            with self.subTest(caso=nombre):
                self.assertEqual(hoja.get((self.zona.id, producto.id)), esperado)

    def test_bajado_por_el_modo_entrega(self):
        """ La mamá entrega 2 de 5 desde la app: lo demás no se carga. """
        producto = self._producto("Entrega app hoja de carga")
        self._pedido([(producto, 5)])
        self.assertEqual(self._hoja(producto), {(self.zona.id, producto.id): 5.0})
        self._entrar(self.mama)
        pendiente = self._resultado(RUTA_PENDIENTE, {"cliente_id": self.cliente.id, "zona_id": self.zona.id})
        self._resultado(RUTA_CONFIRMAR, {
            "cliente_id": self.cliente.id, "zona_id": self.zona.id, "rollos": [],
            "productos": [{"producto_id": producto.id, "cantidad": 2}],
            "movimientos_vistos": [m["move_id"] for p in pendiente["productos"] for m in p["movimientos"]],
            "token": uuid.uuid4().hex,
        })
        self.assertEqual(self._hoja(producto), {})

    def test_pedido_nuevo_del_modo_pedido_aparece_al_recargar(self):
        producto = self._producto("Pedido app hoja de carga")
        self._pedido([(producto, 1)])
        self.assertEqual(self._hoja(producto), {(self.zona.id, producto.id): 1.0})
        self._entrar(self.mama)
        self._enviar([(producto, 4)])
        self.assertEqual(self._hoja(producto), {(self.zona.id, producto.id): 5.0})

    def test_zona_de_la_orden_o_del_cliente(self):
        """ La de la orden; si no tiene, la del cliente si tiene una sola; si
        no, sin zona. Cada zona es un renglón. """
        producto = self._producto("Zonas hoja de carga")
        dos_zonas = self._cliente("Cliente dos zonas hoja", self.zona | self.zona_b)
        self._pedido([(producto, 2)])
        self._pedido([(producto, 3)], cliente=self.cliente_b, zona=self.zona_b)
        self._pedido([(producto, 4)], zona=False)  # cliente con una sola zona
        self._pedido([(producto, 5)], cliente=dos_zonas, zona=False)
        self._pedido([(producto, 6)], cliente=dos_zonas, zona=self.zona_b)
        self.assertEqual(self._hoja(producto), {
            (self.zona.id, producto.id): 6.0,
            (self.zona_b.id, producto.id): 9.0,
            (False, producto.id): 5.0,
        })

    def test_unidades(self):
        """ El total va en la unidad del producto: 500 g + 2 kg = 2.5 kg. Los
        rollos, en piezas (un rollo = 1). """
        gramo = self.env.ref("uom.product_uom_gram")
        self.kilo.product_tmpl_id.uom_ids = [Command.link(gramo.id)]
        orden = self._pedido([(self.kilo, 2)])
        orden.order_line = [Command.create({"product_id": self.kilo.id, "product_uom_qty": 500, "product_uom_id": gramo.id})]
        self._pedido([(self.rollo, 3)])
        renglones = self._renglones(self.kilo | self.rollo)
        self.assertEqual(
            {(r.product_id, r.total, r.unidad_producto_id) for r in renglones},
            {(self.kilo, 2.5, self.env.ref("uom.product_uom_kgm")), (self.rollo, 3.0, self.env.ref("uom.product_uom_unit"))},
        )

    # === Marcas === #

    def test_marcar_y_marcar_dos_veces(self):
        producto = self._producto("Marcar hoja de carga")
        self._pedido([(producto, 4)])
        self.assertEqual(self._estado(producto), (4.0, "sin_marcar", None))
        self._acomodado(producto)
        self.assertEqual(self._estado(producto), (4.0, "acomodado", "Acomodado"))
        marca = self._marcas(producto)
        self.assertEqual(
            (marca.zona_id, marca.fecha, marca.cantidad, marca.user_id), (self.zona, _hoy(), 4.0, self.papa),
        )
        # Doble toque (o un toque con la pantalla vieja): la misma marca.
        self._renglon(producto).with_user(self.papa).with_context(cantidad_vista=4.0).action_acomodado()
        self.assertEqual(self._marcas(producto), marca)
        self.assertEqual(self._estado(producto), (4.0, "acomodado", "Acomodado"))

    def test_se_marca_lo_que_se_veia_en_pantalla(self):
        """ Entró un pedido mientras el papá miraba (veía 3, ya son 4): se
        marca 3 y al recargar sale "Se agregó 1". """
        producto = self._producto("Vista hoja de carga")
        self._pedido([(producto, 3)])
        self._pedido([(producto, 1)])
        self._acomodado(producto, cantidad_vista=3.0)
        self.assertEqual(self._estado(producto), (4.0, "agregado", "Se agregó 1"))

    def test_total_sube_se_agrego_1_y_se_agregaron_x(self):
        producto = self._producto("Sube hoja de carga")
        self._pedido([(producto, 2)])
        self._acomodado(producto)
        self._pedido([(producto, 1)])
        self.assertEqual(self._estado(producto), (3.0, "agregado", "Se agregó 1"))
        self._pedido([(producto, 3)])
        self.assertEqual(self._estado(producto), (6.0, "agregado", "Se agregaron 4"))
        # Volver a tocar: se marca con el nuevo total y queda en verde.
        self._acomodado(producto)
        self.assertEqual(self._estado(producto), (6.0, "acomodado", "Acomodado"))
        self.assertEqual(self._marcas(producto).cantidad, 6.0)
        # Por kg, con decimales y sin ceros sobrantes.
        self._pedido([(self.kilo, 2)])
        self._acomodado(self.kilo)
        self._pedido([(self.kilo, 2.5)])
        self.assertEqual(self._estado(self.kilo), (4.5, "agregado", "Se agregaron 2,5"))  # es_419, como en duranDEV

    def test_total_baja_ahora_son_n(self):
        producto = self._producto("Baja hoja de carga")
        self._pedido([(producto, 3)])
        cancelado = self._pedido([(producto, 2)])
        self._acomodado(producto)
        self.assertEqual(self._estado(producto), (5.0, "acomodado", "Acomodado"))
        cancelado._action_cancel()
        self.assertEqual(self._estado(producto), (3.0, "bajo", "Ahora son 3"))
        self._acomodado(producto)
        self.assertEqual(self._estado(producto), (3.0, "acomodado", "Acomodado"))

    def test_quitar_es_idempotente(self):
        producto = self._producto("Quitar hoja de carga")
        self._pedido([(producto, 2)])
        self._acomodado(producto)
        renglon = self._renglon(producto).with_user(self.papa)
        renglon.action_quitar()
        renglon.action_quitar()
        self.assertFalse(self._marcas(producto))
        self.assertEqual(self._estado(producto), (2.0, "sin_marcar", None))

    def test_dia_nuevo_arranca_sin_marcas(self):
        producto = self._producto("Ayer hoja de carga")
        self._pedido([(producto, 2)])
        self.env["duran.hoja.carga.marca"].create({
            "product_id": producto.id, "zona_id": self.zona.id, "fecha": _hoy() - timedelta(days=1),
            "cantidad": 2.0, "user_id": self.papa.id,
        })
        self.assertEqual(self._estado(producto), (2.0, "sin_marcar", None))
        # Marcar hoy no toca la de ayer.
        self._acomodado(producto)
        self.assertEqual(len(self._marcas(producto)), 2)
        self.assertEqual(self._estado(producto), (2.0, "acomodado", "Acomodado"))

    def test_producto_nuevo_despues_de_otras_marcas(self):
        marcado = self._producto("Marcado antes hoja de carga")
        self._pedido([(marcado, 1)])
        self._acomodado(marcado)
        nuevo = self._producto("Nuevo hoja de carga")
        self._pedido([(nuevo, 2)])
        self.assertEqual(self._estado(nuevo), (2.0, "sin_marcar", None))
        self.assertEqual(self._estado(marcado), (1.0, "acomodado", "Acomodado"))

    def test_pendiente_cero_deja_de_aparecer(self):
        producto = self._producto("Entregado hoja de carga")
        orden = self._pedido([(producto, 2)])
        self._acomodado(producto)
        self._validar(orden.picking_ids)
        self.assertFalse(self._renglon(producto))
        self.assertEqual(len(self._marcas(producto)), 1, "la marca se queda, sin renglón")

    def test_mismo_producto_en_dos_zonas(self):
        producto = self._producto("Dos zonas hoja de carga")
        self._pedido([(producto, 2)])
        self._pedido([(producto, 5)], cliente=self.cliente_b, zona=self.zona_b)
        self._acomodado(producto, self.zona)
        self.assertEqual(self._estado(producto, self.zona), (2.0, "acomodado", "Acomodado"))
        self.assertEqual(self._estado(producto, self.zona_b), (5.0, "sin_marcar", None))
        # Un pedido nuevo en la OTRA zona no cambia el aviso de la zona marcada.
        self._pedido([(producto, 3)], cliente=self.cliente_b, zona=self.zona_b)
        self.assertEqual(self._estado(producto, self.zona), (2.0, "acomodado", "Acomodado"))
        self.assertEqual(self._estado(producto, self.zona_b), (8.0, "sin_marcar", None))
        # Marcar y quitar en la otra zona tampoco.
        self._acomodado(producto, self.zona_b)
        self._quitar(producto, self.zona_b)
        self.assertEqual(self._estado(producto, self.zona), (2.0, "acomodado", "Acomodado"))
        self.assertEqual(self._marcas(producto).zona_id, self.zona)

    def test_sin_zona_tambien_se_marca(self):
        producto = self._producto("Sin zona hoja de carga")
        dos_zonas = self._cliente("Cliente dos zonas marca hoja", self.zona | self.zona_b)
        self._pedido([(producto, 2)], cliente=dos_zonas, zona=False)
        self._acomodado(producto, False)
        self._acomodado(producto, False)
        self.assertEqual(self._estado(producto, False), (2.0, "acomodado", "Acomodado"))
        self.assertEqual(len(self._marcas(producto)), 1)

    def test_otro_gerente_marca_la_misma_marca(self):
        producto = self._producto("Dos gerentes hoja de carga")
        self._pedido([(producto, 2)])
        self._acomodado(producto)
        self._acomodado(producto, usuario=self.otro_gerente)
        self.assertEqual((len(self._marcas(producto)), self._marcas(producto).user_id), (1, self.otro_gerente))

    def test_unicidad_por_producto_zona_y_fecha(self):
        producto = self._producto("Única hoja de carga")
        Marca = self.env["duran.hoja.carga.marca"]
        for zona in (self.zona, self.env["res.partner.category"]):
            with self.subTest(zona=zona.name or "sin zona"):
                valores = {
                    "product_id": producto.id, "zona_id": zona.id, "fecha": _hoy(), "cantidad": 1.0,
                    "user_id": self.papa.id,
                }
                Marca.create(valores)
                with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.env.cr.savepoint():
                    Marca.create(valores)
                    self.env.flush_all()
        # Otra zona u otro día sí.
        Marca.create({"product_id": producto.id, "zona_id": self.zona_b.id, "fecha": _hoy(), "cantidad": 1.0,
                      "user_id": self.papa.id})
        Marca.create({"product_id": producto.id, "zona_id": self.zona.id, "fecha": _hoy() - timedelta(days=1),
                      "cantidad": 1.0, "user_id": self.papa.id})

    def test_aviso_con_el_separador_del_idioma(self):
        """ En es_419 (como los usuarios de duranDEV) el aviso usa coma
        decimal, igual que la columna Total; sin ceros sobrantes. """
        for codigo in ("es_419", "en_US"):
            self.env["res.lang"]._activate_lang(codigo)
        primero = self._pedido([(self.kilo, 2)])
        self._acomodado(self.kilo)
        self._pedido([(self.kilo, 2.5)])
        Hoja = self.env["duran.hoja.carga"].with_user(self.papa)

        def aviso(idioma):
            self.env.flush_all()
            self.env.invalidate_all()
            renglon = Hoja.with_context(lang=idioma).search([("product_id", "=", self.kilo.id)])
            return renglon.estado, renglon.aviso

        self.assertEqual(aviso("es_419"), ("agregado", "Se agregaron 2,5"))
        self.assertEqual(aviso("en_US"), ("agregado", "Se agregaron 2.5"))
        # Marcado en 4,5 y se cancela el pedido de 2: "Ahora son 2,5".
        self._acomodado(self.kilo)
        primero._action_cancel()
        self.assertEqual(aviso("es_419"), ("bajo", "Ahora son 2,5"))

    def test_columna_de_cantidad(self):
        """ Total y unidad juntos: piezas sin decimales y como "pz"; kg con los
        decimales necesarios y la coma de es_419. """
        self._pedido([(self.pieza, 4)])
        self._pedido([(self.rollo, 2)])
        self._pedido([(self.kilo, 2.5)])
        self.env.flush_all()
        self.env.invalidate_all()
        renglones = self.env["duran.hoja.carga"].with_user(self.papa).with_context(lang="es_419").search(
            [("product_id", "in", (self.pieza | self.rollo | self.kilo).ids)],
        )
        self.assertEqual(
            {r.product_id: r.cantidad_texto for r in renglones},
            {self.pieza: "4 pz", self.rollo: "2 pz", self.kilo: "2,5 kg"},
        )

    def test_cantidad_invalida_no_marca(self):
        producto = self._producto("Inválida hoja de carga")
        self._pedido([(producto, 2)])
        renglon = self._renglon(producto).with_user(self.papa)
        for cantidad in (None, 0, -1, "2", True):
            with self.subTest(cantidad=cantidad):
                with self.assertRaisesRegex(Exception, "Recarga la página"):
                    renglon.with_context(cantidad_vista=cantidad).action_acomodado()
        self.assertFalse(self._marcas(producto))

    # === Vista, acción, menú y permisos === #

    def test_lista_busqueda_y_accion(self):
        arch = etree.fromstring(self.env["duran.hoja.carga"].with_user(self.papa).get_views(
            [(self.accion.view_id.id, "list")],
        )["views"]["list"]["arch"])
        columnas = [c.get("name") for c in arch.xpath("//field") if not c.get("column_invisible")]
        # Sin columna Zona (va en el encabezado del grupo) y con Total y Unidad
        # en una sola columna: cabe en el celular. `total` va oculto (botón).
        self.assertEqual(columnas, ["product_id", "cantidad_texto", "aviso"])
        self.assertEqual(arch.xpath("//field[@name='total']/@column_invisible"), ["True"])
        # Zonas abiertas al entrar, recarga automática y piezas sin decimales.
        self.assertEqual(
            (arch.get("expand"), arch.get("js_class"), arch.get("class")), ("1", "hoja_carga_list", "o_hoja_carga"),
        )
        self.assertFalse(arch.xpath("//field[@sum]"), "sin suma en el pie: mezclaría kg con piezas")
        self.assertEqual(
            {c: self.env["duran.hoja.carga"].fields_get([c], ["aggregator"])[c].get("aggregator") for c in ("total",)},
            {"total": None},
        )
        self.assertEqual(
            {d: arch.get(d) for d in ("decoration-success", "decoration-warning", "decoration-info")},
            {
                "decoration-success": "estado == 'acomodado'",
                "decoration-warning": "estado == 'agregado'",
                "decoration-info": "estado == 'bajo'",
            },
        )
        # Cuadro de marcar: ☐ Acomodado / ☑ Quitar, con su nombre (string y title).
        self.assertEqual(
            [
                (b.get("name"), b.get("string"), b.get("title"), b.get("icon"), b.get("invisible"), b.get("context"))
                for b in arch.xpath("//button")
            ],
            [
                ("action_acomodado", "Acomodado", "Acomodado", "fa-square-o", "estado == 'acomodado'",
                 "{'cantidad_vista': total}"),
                ("action_quitar", "Quitar", "Quitar", "fa-check-square-o", "estado != 'acomodado'", None),
            ],
        )
        busqueda = etree.fromstring(self.env["duran.hoja.carga"].get_views(
            [(self.accion.search_view_id.id, "search")],
        )["views"]["search"]["arch"])
        self.assertEqual([f.get("name") for f in busqueda.xpath("//field")], ["zona_id"])
        self.assertFalse(busqueda.xpath("//filter"), "sin Hoy / Días anteriores ni agrupados")
        self.assertEqual(safe_eval(self.accion.context), {"group_by": ["zona_id"]})
        self.assertFalse(self.accion.domain)
        self.assertEqual(self.accion.res_model, "duran.hoja.carga")

    def test_solo_gerente_ve_y_marca(self):
        Menu = self.env["ir.ui.menu"]
        producto = self._producto("Permisos hoja de carga")
        self._pedido([(producto, 2)])
        self.assertEqual(self.menu.parent_id, self.env.ref("sale.sale_order_menu"))
        self.assertEqual(self.accion.group_ids, self.env.ref("sales_team.group_sale_manager"))
        for usuario in (self.papa, self.admin):
            with self.subTest(usuario=usuario.login):
                self.assertIn(self.menu.id, Menu.with_user(usuario)._visible_menu_ids())
                self.assertTrue(self._renglones(producto, usuario=usuario))
        renglon = self._renglon(producto)
        for usuario in (self.mama, self.vendedor):
            with self.subTest(usuario=usuario.login):
                self.assertNotIn(self.menu.id, Menu.with_user(usuario)._visible_menu_ids())
                with self.assertRaises(AccessError):
                    self.env["duran.hoja.carga"].with_user(usuario).search([])
                with self.assertRaises(AccessError):
                    renglon.with_user(usuario).with_context(cantidad_vista=2.0).action_acomodado()
                with self.assertRaises(AccessError):
                    renglon.with_user(usuario).action_quitar()
                with self.assertRaises(AccessError):
                    self.env["duran.hoja.carga.marca"].with_user(usuario).create({
                        "product_id": producto.id, "zona_id": self.zona.id, "fecha": _hoy(), "cantidad": 2.0,
                        "user_id": usuario.id,
                    })
        self.assertFalse(self._marcas(producto))
