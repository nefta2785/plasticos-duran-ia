{
    "name": "Durán - Captura de pedidos en tianguis",
    "version": "19.0.1.0.0",
    "category": "Sales/Sales",
    "summary": "Pantalla para celular para levantar pedidos por zona en el tianguis",
    "description": """
Agrega a la orden de venta la zona (etiqueta de contacto) desde la que se
levantó el pedido, y una página propia (/captura) pensada para usarse desde el
celular por un usuario del grupo "Captura tianguis".

Cada entrega confirmada desde la pantalla queda en una bitácora (Ventas >
Órdenes > Entregas en tianguis), y cada cobro en otra (Ventas > Órdenes >
Resumen de ventas).
""",
    "author": "Plásticos Durán",
    "license": "LGPL-3",
    "depends": ["sale_stock", "duran_peso_variable"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/ir_config_parameter.xml",
        "views/sale_order_views.xml",
        "views/captura_entrega_views.xml",
        "views/captura_cobro_views.xml",
        "views/hoja_carga_views.xml",
        "views/pendiente_cobro_views.xml",
        "views/captura_templates.xml",
        "views/captura_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "duran_captura_tianguis/static/src/hoja_carga.css",
            "duran_captura_tianguis/static/src/hoja_carga_list.js",
        ],
    },
    "installable": True,
    "application": False,
}
