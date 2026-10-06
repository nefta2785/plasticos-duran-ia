""" "+ Cliente nuevo" (modo Pedido): alta de un cliente en la zona desde la que
se entró, con aviso de clientes parecidos, sin duplicados por doble toque y con
el permiso acotado (sudo) solo en el `create`. """
import uuid

from odoo import Command, fields
from odoo.exceptions import AccessError, ConcurrencyError, UserError
from odoo.sql_db import db_connect
from odoo.tests import HttpCase, tagged
from odoo.tools import html2plaintext
from odoo.tools.safe_eval import safe_eval

from .common import GRUPO_CAPTURA, CapturaDatosPrueba, CapturaHttpMixin

RUTA = "/captura/api/cliente/nuevo"
ZONA_HORARIA = "America/Mexico_City"


@tagged("post_install", "-at_install")
class TestClienteNuevo(CapturaDatosPrueba, CapturaHttpMixin, HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._sin_gastar_folios()
        cls._crear_datos_captura()
        env = cls.env
        cls.mama = cls._usuario("cliente_nuevo_mama", GRUPO_CAPTURA)
        cls.otra_persona = cls._usuario("cliente_nuevo_otra", GRUPO_CAPTURA)
        (cls.mama | cls.otra_persona).tz = ZONA_HORARIA
        cls.zona = cls.zona_con_clientes
        cls.zona_b = env["res.partner.category"].create({"name": "Zona prueba cliente nuevo B"})
        # Nombres raros: la búsqueda de parecidos recorre todos los contactos con zona.
        cls.carmen = cls._cliente("Doña Qwerzia Carmen", cls.zona)
        cls.beto = cls._cliente("Don Qwerzio Beto", cls.zona_b)
        cls.archivado = cls._cliente("Tortillería Qwerzil Vieja", cls.zona)
        cls.archivado.action_archive()
        cls.pieza = cls._plantilla(
            "Pieza cliente nuevo", invoice_policy="delivery", taxes_id=[Command.clear()],
        ).product_variant_id

    def setUp(self):
        super().setUp()
        self._entrar(self.mama)

    # === Ayudantes === #

    def _params(self, nombre, zona=None, token=None, es_otro=False, **extra):
        return {
            "zona_id": (zona or self.zona).id, "nombre": nombre,
            "token": token or uuid.uuid4().hex, "es_otro": es_otro, **extra,
        }

    def _crear(self, nombre, **kwargs):
        return self._resultado(RUTA, self._params(nombre, **kwargs))

    def _error(self, params):
        respuesta = self._jsonrpc(RUTA, params)
        self.assertNotIn("result", respuesta)
        return respuesta["error"]["data"]

    def _contacto(self, resultado):
        return self.env["res.partner"].browse(resultado["cliente"]["id"])

    def _con_nombre(self, nombre):
        return self.env["res.partner"].with_context(active_test=False).search([("name", "=", nombre)])

    # === Alta === #

    def test_campos_del_cliente_creado(self):
        resultado = self._crear("  Abarrotes   Qwerzon  ")
        cliente = self._contacto(resultado)
        self.assertEqual(resultado, {"cliente": {"id": cliente.id, "nombre": "Abarrotes Qwerzon"}, "ya_existia": False})
        self.assertEqual(
            (cliente.name, cliente.category_id, cliente.is_company, cliente.customer_rank, cliente.active),
            ("Abarrotes Qwerzon", self.zona, True, 1, True),
            "Solo la zona de la pantalla, sin etiquetas extra",
        )
        self.assertFalse(cliente.parent_id or cliente.vat or cliente.phone or cliente.street or cliente.company_id)
        hoy = fields.Date.context_today(self.env["res.partner"].with_context(tz=ZONA_HORARIA))
        self.assertEqual(
            html2plaintext(cliente.comment).strip(),
            f"Creado desde la app el {hoy.strftime('%d/%m/%Y')} por {self.mama.name}",
        )
        self.assertEqual(cliente.create_uid, self.mama, "sudo conserva a quien captura como creador")
        self.assertTrue(cliente.captura_token)
        self.assertIn(
            {"id": cliente.id, "nombre": "Abarrotes Qwerzon"},
            self._resultado("/captura/api/clientes", {"zona_id": self.zona.id}),
        )

    def test_campos_de_mas_se_ignoran(self):
        resultado = self._crear(
            "Puesto Qwerzal", vat="XAXX010101000", parent_id=self.carmen.id, is_company=False,
            category_id=[self.zona_b.id], comment="otra nota", user_id=self.otra_persona.id, active=False,
        )
        cliente = self._contacto(resultado)
        self.assertEqual(
            (cliente.vat, cliente.parent_id, cliente.is_company, cliente.category_id, cliente.user_id, cliente.active),
            (False, self.env["res.partner"], True, self.zona, self.env["res.users"], True),
        )
        self.assertIn("Creado desde la app", html2plaintext(cliente.comment))

    def test_token_no_duplica(self):
        token = uuid.uuid4().hex
        primero = self._crear("Fonda Qwerzita", token=token)
        # Doble toque o reintento sin señal: el mismo token devuelve el mismo
        # cliente, sin preguntar por parecidos (el primero ya sería uno).
        segundo = self._crear("Fonda Qwerzita", token=token)
        self.assertEqual(segundo, {**primero, "ya_existia": True})
        self.assertEqual(len(self._con_nombre("Fonda Qwerzita")), 1)

    def test_mama_no_puede_crear_contactos_directamente(self):
        Contacto = self.env["res.partner"].with_user(self.mama)
        with self.assertRaises(AccessError):
            Contacto.create({"name": "Contacto directo Qwerz"})
        with self.assertRaises(AccessError):
            self.env["res.partner.category"].with_user(self.mama).create({"name": "Zona directa Qwerz"})
        with self.assertRaises(AccessError):
            self.carmen.with_user(self.mama).write({"name": "Cambio Qwerz"})

    # === Validaciones === #

    def test_validaciones_del_nombre(self):
        casos = [
            ("", "Escribe el nombre del cliente."),
            ("   ", "Escribe el nombre del cliente."),
            (None, "Escribe el nombre del cliente."),
            (123, "Escribe el nombre del cliente."),
            ("A", "El nombre debe tener al menos 2 letras."),
            ("1 2 3", "El nombre debe tener al menos 2 letras."),
            ("Q" * 61, "El nombre puede tener máximo 60 caracteres."),
            ("Tacos 🌮 Qwerz", "El nombre solo puede llevar letras, números, espacios y . , ' - & # ( ) /"),
            ("Qwerz\x07bell", "El nombre solo puede llevar letras, números, espacios y . , ' - & # ( ) /"),
            ("Qwerz <b>", "El nombre solo puede llevar letras, números, espacios y . , ' - & # ( ) /"),
        ]
        for nombre, mensaje in casos:
            with self.subTest(nombre=nombre):
                self.assertEqual(self._error(self._params(nombre))["message"], mensaje)
        # Lo permitido: acentos, ñ, números y . , ' - & # ( ) /; las mayúsculas quedan como se escribieron.
        nombre = "Ñeli Qwérz (Local #3) - O'Hara & Co., S.A./2"
        self.assertEqual(self._contacto(self._crear(nombre)).name, nombre)
        self.assertEqual(self._contacto(self._crear("qwerzi minúsculas")).name, "qwerzi minúsculas")
        self.assertEqual(len(self._con_nombre("Q" * 60)), 0)
        self.assertEqual(self._contacto(self._crear("Q" * 60)).name, "Q" * 60)

    def test_zona_inexistente_o_token_invalido(self):
        zona_borrada = self.env["res.partner.category"].create({"name": "Zona prueba borrada"})
        zona_borrada.unlink()
        self.assertEqual(self._error(self._params("Qwerz Zona", zona=zona_borrada))["message"], "La zona ya no existe.")
        self.assertIn("No se pudo identificar el cliente nuevo", self._error(self._params("Qwerz Token", token="x"))["message"])
        self.assertFalse(self._con_nombre("Qwerz Zona") | self._con_nombre("Qwerz Token"))

    # === Parecidos === #

    def test_identico_en_la_misma_zona_no_se_crea(self):
        # Acentos, mayúsculas y espacios de más no cuentan.
        for nombre in ("  dona QWERZIA   carmen ", "Doña Qwerzia Carmen"):
            for es_otro in (False, True):
                with self.subTest(nombre=nombre, es_otro=es_otro):
                    self.assertEqual(self._crear(nombre, es_otro=es_otro), {
                        "parecidos": [{
                            "id": self.carmen.id, "nombre": "Doña Qwerzia Carmen", "zona": self.zona.display_name,
                            "misma_zona": True, "archivado": False, "identico": True,
                        }],
                        "puede_crear": False,
                    })
        self.assertEqual(len(self._con_nombre("Doña Qwerzia Carmen")), 1)

    def test_contiene_otra_zona_y_archivado(self):
        resultado = self._crear("qwerzi")  # 6 letras: "contiene" sí cuenta
        self.assertEqual(resultado["puede_crear"], True)
        self.assertEqual(
            [(p["nombre"], p["id"], p["zona"], p["misma_zona"], p["archivado"], p["identico"]) for p in resultado["parecidos"]],
            [
                ("Doña Qwerzia Carmen", self.carmen.id, self.zona.display_name, True, False, False),
                ("Tortillería Qwerzil Vieja", False, self.zona.display_name, True, True, False),
                ("Don Qwerzio Beto", False, self.zona_b.display_name, False, False, False),
            ],
            "Primero los de la misma zona; sin id los que no se pueden tocar",
        )
        # "No, es otro cliente": se crea.
        cliente = self._contacto(self._crear("qwerzi", es_otro=True))
        self.assertEqual((cliente.name, cliente.category_id), ("qwerzi", self.zona))

    def test_identico_de_otra_zona_o_archivado_no_bloquea(self):
        for nombre in ("Don Qwerzio Beto", "Tortilleria qwerzil vieja"):
            with self.subTest(nombre=nombre):
                resultado = self._crear(nombre)
                self.assertTrue(resultado["parecidos"][0]["identico"])
                self.assertEqual((resultado["parecidos"][0]["id"], resultado["puede_crear"]), (False, True))
                self.assertEqual(self._contacto(self._crear(nombre, es_otro=True)).category_id, self.zona)

    def test_menos_de_4_letras_no_cuenta_como_contiene(self):
        resultado = self._crear("Qwe")
        self.assertIn("cliente", resultado, "«Qwe» está dentro de otros nombres, pero es muy corto")

    def test_maximo_5_parecidos_primero_los_identicos(self):
        for numero in range(7):
            self._cliente(f"Puesto Qwerzopa {numero}", self.zona)
        self._cliente("Puesto Qwerzopa", self.zona_b)
        resultado = self._crear("Puesto Qwerzopa")
        self.assertEqual(len(resultado["parecidos"]), 5)
        self.assertEqual(
            (resultado["parecidos"][0]["nombre"], resultado["parecidos"][0]["identico"], resultado["puede_crear"]),
            ("Puesto Qwerzopa", True, True),
            "El idéntico de otra zona va primero, y no bloquea",
        )

    # === Dos personas a la vez === #

    def test_dos_personas_con_el_mismo_nombre_a_la_vez(self):
        Captura = self.env["duran.captura"].with_user(self.otra_persona)
        normalizado = Captura._normalizar_nombre("Carnitas Qwerzote")
        # Otra conexión tiene "tomado" el nombre (la primera persona está
        # guardando): la segunda petición se repite desde cero (Odoo reintenta
        # con ConcurrencyError) en vez de esperar con una vista vieja.
        otra = db_connect(self.env.cr.dbname).cursor()
        try:
            otra.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", [Captura._clave_bloqueo_cliente(normalizado)])
            with self.assertRaises(ConcurrencyError):
                Captura.crear_cliente(self.zona.id, "Carnitas Qwerzote", uuid.uuid4().hex)
        finally:
            otra.rollback()
            otra.close()
        # Al reintentar ya ve al cliente de la primera persona: idéntico en la
        # misma zona, no se crea otro.
        self._crear("Carnitas Qwerzote")
        resultado = Captura.crear_cliente(self.zona.id, "carnitas  qwerzote", uuid.uuid4().hex, es_otro=True)
        self.assertEqual(resultado["puede_crear"], False)
        self.assertEqual(len(self._con_nombre("Carnitas Qwerzote")), 1)

    # === Flujo completo === #

    def test_flujo_completo_pedido_entrega_y_cobro(self):
        cliente = self._contacto(self._crear("Cremería Qwerzina"))
        self._enviar([(self.pieza, 3)], cliente=cliente)
        self.assertIn(
            cliente.id, [c["id"] for c in self._resultado("/captura/api/entrega/clientes", {"zona_id": self.zona.id})],
        )
        acomodo = {z["nombre"]: [p["cliente"] for p in z["pedidos"]] for z in self._resultado("/captura/api/acomodo")}
        self.assertIn("Cremería Qwerzina", acomodo[self.zona.display_name])

        pendiente = self._resultado("/captura/api/entrega/pendiente", {"cliente_id": cliente.id, "zona_id": self.zona.id})
        self._resultado("/captura/api/entrega/confirmar", {
            "cliente_id": cliente.id, "zona_id": self.zona.id, "rollos": [],
            "productos": [{"producto_id": self.pieza.id, "cantidad": 3}],
            "movimientos_vistos": [m["move_id"] for p in pendiente["productos"] for m in p["movimientos"]],
            "token": uuid.uuid4().hex,
        })
        self.assertIn(
            cliente.id, [c["id"] for c in self._resultado("/captura/api/cobro/clientes", {"zona_id": self.zona.id})],
        )
        accion = self.env.ref("duran_captura_tianguis.pendiente_cobro_action")
        en_pendiente = self.env["stock.move"].search(safe_eval(accion.domain) + [("cliente_id", "=", cliente.id)])
        self.assertEqual(en_pendiente.mapped("importe_entregado"), [30.0])

        detalle = self._resultado("/captura/api/cobro/detalle", {"cliente_id": cliente.id, "zona_id": self.zona.id})
        self.assertEqual((detalle["total_a_cobrar"], detalle["puede_cobrar"]), (30.0, True))
        cobrado = self._resultado("/captura/api/cobro/confirmar", {
            "cliente_id": cliente.id, "zona_id": self.zona.id, "tipo": "todo",
            "visto": detalle["visto"], "token": uuid.uuid4().hex,
        })
        self.assertEqual((cobrado["monto_recibido"], cobrado["saldo_pendiente"]), (30.0, 0.0))
        factura = self.env["account.move"].search([("partner_id", "=", cliente.id), ("move_type", "=", "out_invoice")])
        self.assertEqual((factura.state, factura.payment_state, factura.amount_total), ("posted", "paid", 30.0))
        self.assertGreaterEqual(cliente.customer_rank, 1)

    # === Seguridad === #

    def test_sin_grupo_no_crea(self):
        sin_grupo = self._usuario("cliente_nuevo_sin_grupo", "sales_team.group_sale_salesman")
        self._entrar(sin_grupo)
        self.assertEqual(self._error(self._params("Qwerz Sin Grupo"))["name"], "odoo.exceptions.AccessError")
        self.assertFalse(self._con_nombre("Qwerz Sin Grupo"))

    def test_validacion_en_el_metodo(self):
        # Llamado directo al método (sin la ruta): mismas validaciones.
        Captura = self.env["duran.captura"].with_user(self.mama)
        with self.assertRaises(UserError):
            Captura.crear_cliente(self.zona.id, "🌮", uuid.uuid4().hex)
