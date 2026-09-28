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
Órdenes > Entregas en tianguis).
""",
    "author": "Plásticos Durán",
    "license": "LGPL-3",
    "depends": ["sale_stock", "duran_peso_variable"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/sale_order_views.xml",
        "views/captura_entrega_views.xml",
        "views/captura_templates.xml",
    ],
    "installable": True,
    "application": False,
}
