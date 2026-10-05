""" Acomodo de entregas: pedidos del día operativo con algo pendiente de
entregar, agrupados por zona y en el orden en que se levantaron (solo
lectura). """
from datetime import datetime

import pytz

from odoo.exceptions import AccessError
from odoo.tests import Form, HttpCase, tagged

from .common import GRUPO_CAPTURA, CapturaDatosPrueba, CapturaHttpMixin

RUTA = "/captura/api/acomodo"
CDMX = pytz.timezone("America/Mexico_City")
# Día operativo de las pruebas: el 10 de marzo de 2030 (lejos de los datos reales).
DIA = 10


def utc(dia, hora, minuto=0, zona=CDMX):
    """ Hora local de marzo de 2030 -> UTC sin zona horaria (como se guarda). """
    return zona.localize(datetime(2030, 3, dia, hora, minuto)).astimezone(pytz.utc).replace(tzinfo=None)


@tagged("post_install", "-at_install")
class TestAcomodo(CapturaDatosPrueba, CapturaHttpMixin, HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._sin_gastar_folios()
        cls._crear_datos_captura()
        env = cls.env
        cls.mama = cls._usuario("acomodo_mama", GRUPO_CAPTURA)
        cls.mama.tz = "America/Mexico_City"
        cls.otro_vendedor = cls._usuario("acomodo_otro_vendedor", "sales_team.group_sale_salesman")
        cls.ahora = utc(DIA, 10)
        cls.classPatch(type(env["duran.captura"]), "_ahora", lambda self: cls.ahora)

        zona_a = cls.zona_a = cls.zona_con_clientes
        zona_b = cls.zona_b = env["res.partner.category"].create({"name": "Zona prueba B"})
        zona_c = cls.zona_c = env["res.partner.category"].create({"name": "Zona prueba C"})
        cls.carmen = cls._cliente("Doña Carmen prueba", zona_a)
        cls.lupita = cls._cliente("Tortillería La Guadalupana de Doña Lupita prueba", zona_a)
        cls.beto = cls._cliente("Don Beto prueba", zona_b)
        cls.solo_b = cls._cliente("Cliente prueba solo zona B", zona_b)
        cls.dos_zonas = cls._cliente("Cliente prueba dos zonas", zona_a | zona_b)
        cls.sin_zona = env["res.partner"].create({"name": "Cliente prueba sin zona"})
        cls.parcial = cls._cliente("Cliente prueba entrega parcial", zona_c)
        normal, rollo, kilo = cls.normal, cls.pv_con_precio, cls.por_kilo

        def pedido(cliente, lineas, cuando, zona=None, **vals):
            orden = cls._confirmada(cliente, lineas, zona_id=zona.id if zona else False, **vals)
            orden.date_order = cuando
            return orden

        # Del día operativo (de ayer 20:00 a hoy 20:00, hora local).
        cls.o_carmen = pedido(cls.carmen, [(normal, 2), (rollo, 2), (normal, 3), (kilo, 1.5)], utc(DIA - 1, 20), zona_a)
        cls.o_dos_zonas = pedido(cls.dos_zonas, [(normal, 1)], utc(DIA - 1, 20, 1))
        cls.o_beto = pedido(cls.beto, [(rollo, 1)], utc(DIA - 1, 20, 30), zona_b, user_id=cls.otro_vendedor.id)
        cls.o_lupita = pedido(cls.lupita, [(kilo, 3)], utc(DIA - 1, 21), zona_a)
        cls.o_solo_b = pedido(cls.solo_b, [(normal, 4)], utc(DIA - 1, 22))  # sin zona: la del cliente
        cls.o_parcial = pedido(cls.parcial, [(normal, 5)], utc(DIA, 7), zona_c)
        cls.o_sin_zona = pedido(cls.sin_zona, [(normal, 1)], utc(DIA, 8))
        cls.o_beto_2 = pedido(cls.beto, [(normal, 1)], utc(DIA, 9), zona_b)  # mismo segundo:
        cls.o_solo_b_2 = pedido(cls.solo_b, [(kilo, 2)], utc(DIA, 9), zona_b)  # desempata el id
        cls.o_carmen_2 = pedido(cls.carmen, [(normal, 1)], utc(DIA, 19, 59), zona_a)  # vuelve a pedir
        # Entrega parcial validada en Odoo con backorder: solo queda lo que falta.
        picking = cls.o_parcial.picking_ids
        picking.move_ids.write({"quantity": 2, "picked": True})
        accion = picking.button_validate()
        Form(env["stock.backorder.confirmation"].with_context(accion["context"])).save().process()

        # Lo que NO debe aparecer.
        cls.o_antes_del_corte = pedido(cls.carmen, [(normal, 1)], utc(DIA - 1, 19, 59), zona_a)
        cls.o_despues_del_corte = pedido(cls.carmen, [(kilo, 1)], utc(DIA, 20), zona_a)
        cls.o_anterior = pedido(cls.beto, [(normal, 1)], utc(DIA - 2, 12), zona_b)
        cls.o_validada = pedido(cls.carmen, [(normal, 1)], utc(DIA - 1, 20, 10), zona_a)
        cls._validar(cls.o_validada.picking_ids)
        cls.o_cancelada = pedido(cls.carmen, [(normal, 1)], utc(DIA - 1, 20, 15), zona_a)
        cls.o_cancelada._action_cancel()
        cls.cotizacion = cls.env["sale.order"].create({
            "partner_id": cls.carmen.id, "zona_id": zona_a.id, "date_order": utc(DIA - 1, 23),
            "order_line": [(0, 0, {"product_id": normal.id, "product_uom_qty": 1})],
        })

    def setUp(self):
        super().setUp()
        self._entrar(self.mama)

    def _acomodo(self):
        """ [(zona, [(posición, cliente, [(producto, cantidad, unidad, es rollo)])])] """
        return [
            (zona["nombre"], [
                (pedido["posicion"], pedido["cliente"], [
                    (p["nombre"], p["cantidad"], p["unidad"], p["es_peso_variable"]) for p in pedido["productos"]
                ])
                for pedido in zona["pedidos"]
            ])
            for zona in self._resultado(RUTA)
        ]

    def test_pedidos_del_dia_por_zona_en_orden_de_llegada(self):
        normal = ("Normal prueba", 5.0, "c/u", False)
        self.assertEqual(self._acomodo(), [
            ("Zona prueba con clientes", [
                (1, "Doña Carmen prueba", [
                    normal,  # 2 + 3 de dos líneas del mismo producto
                    ("Peso variable con precio prueba", 2.0, "c/u", True),  # 2 rollos, sin peso
                    ("Por kilo prueba", 1.5, "kg", False),
                ]),
                (2, "Tortillería La Guadalupana de Doña Lupita prueba", [("Por kilo prueba", 3.0, "kg", False)]),
                (3, "Doña Carmen prueba", [("Normal prueba", 1.0, "c/u", False)]),
            ]),
            ("Zona prueba B", [
                (1, "Don Beto prueba", [("Peso variable con precio prueba", 1.0, "c/u", True)]),
                (2, "Cliente prueba solo zona B", [("Normal prueba", 4.0, "c/u", False)]),
                (3, "Don Beto prueba", [("Normal prueba", 1.0, "c/u", False)]),
                (4, "Cliente prueba solo zona B", [("Por kilo prueba", 2.0, "kg", False)]),
            ]),
            ("Zona prueba C", [
                (1, "Cliente prueba entrega parcial", [("Normal prueba", 3.0, "c/u", False)]),
            ]),
            ("Sin zona", [
                (1, "Cliente prueba dos zonas", [("Normal prueba", 1.0, "c/u", False)]),
                (2, "Cliente prueba sin zona", [("Normal prueba", 1.0, "c/u", False)]),
            ]),
        ])

    def test_productos_traen_por_kg(self):
        productos = {
            p["nombre"]: p["por_kg"]
            for zona in self._resultado(RUTA) for pedido in zona["pedidos"] for p in pedido["productos"]
        }
        self.assertEqual(productos, {
            "Normal prueba": False, "Peso variable con precio prueba": False, "Por kilo prueba": True,
        })

    def test_cada_bloque_es_un_pedido(self):
        ids = [pedido["id"] for zona in self._resultado(RUTA) for pedido in zona["pedidos"]]
        self.assertEqual(ids, (
            self.o_carmen | self.o_lupita | self.o_carmen_2
            | self.o_beto | self.o_solo_b | self.o_beto_2 | self.o_solo_b_2
            | self.o_parcial | self.o_dos_zonas | self.o_sin_zona
        ).ids)
        self.assertLess(self.o_beto_2.id, self.o_solo_b_2.id, "el empate se resuelve por id")

    def test_zona_de_la_orden_y_de_respaldo(self):
        zonas = {zona["nombre"]: zona["id"] for zona in self._resultado(RUTA)}
        self.assertEqual(zonas, {
            "Zona prueba con clientes": self.zona_a.id, "Zona prueba B": self.zona_b.id,
            "Zona prueba C": self.zona_c.id, "Sin zona": False,
        })

    def test_hora_de_corte(self):
        """ El día operativo que contiene `ahora`: de las 20:00 del día anterior
        (inclusive) a las 20:00 del día (exclusive), en hora local. """
        Captura = self.env["duran.captura"].with_user(self.mama)
        hoy = (utc(DIA - 1, 20), utc(DIA, 20))
        manana = (utc(DIA, 20), utc(DIA + 1, 20))
        for ahora, rango in (
            (utc(DIA, 0, 5), hoy),
            (utc(DIA, 19, 59), hoy),
            (utc(DIA, 20), manana),
            (utc(DIA, 20, 1), manana),
            (utc(DIA - 1, 20), hoy),
        ):
            with self.subTest(ahora=ahora):
                self.assertEqual(Captura._rango_dia_operativo(ahora), rango)

    def test_despues_del_corte_ya_es_el_dia_siguiente(self):
        self.patch(type(self.env["duran.captura"]), "_ahora", lambda captura: utc(DIA, 20, 1))
        self.assertEqual(self._acomodo(), [
            ("Zona prueba con clientes", [(1, "Doña Carmen prueba", [("Por kilo prueba", 1.0, "kg", False)])]),
        ])

    def test_zona_horaria_del_usuario(self):
        tijuana = pytz.timezone("America/Tijuana")
        for tz, desde in ((False, utc(DIA - 1, 20)), ("America/Tijuana", utc(DIA - 1, 20, zona=tijuana))):
            with self.subTest(tz=tz):
                self.mama.tz = tz
                self.assertEqual(self.env["duran.captura"].with_user(self.mama)._rango_dia_operativo(self.ahora)[0], desde)

    def test_sin_pedidos(self):
        self.patch(type(self.env["duran.captura"]), "_ahora", lambda captura: utc(DIA + 5, 10))
        self.assertEqual(self._resultado(RUTA), [])

    def test_ve_pedidos_de_otro_vendedor_sin_sudo(self):
        with self.assertRaises(AccessError, msg="Con sus permisos no puede leer la orden de otro vendedor"):
            self.o_beto.with_user(self.mama).read(["name"])
        ids = [pedido["id"] for zona in self._resultado(RUTA) for pedido in zona["pedidos"]]
        self.assertIn(self.o_beto.id, ids)

    def test_solo_lectura(self):
        ordenes = self.env["sale.order"].search([("partner_id", "in", (
            self.carmen | self.lupita | self.beto | self.solo_b | self.dos_zonas | self.sin_zona | self.parcial
        ).ids)])
        registros = [ordenes, ordenes.order_line, ordenes.picking_ids, ordenes.picking_ids.move_ids]
        antes = [r.read(["write_date"]) for r in registros]
        mensajes = self.env["mail.message"].search_count([])
        self._resultado(RUTA)
        self.env.invalidate_all()
        self.assertEqual([r.read(["write_date"]) for r in registros], antes)
        self.assertEqual(self.env["mail.message"].search_count([]), mensajes)
