{
    "name": "Durán - Peso Variable",
    "version": "19.0.1.0.0",
    "category": "Inventory/Inventory",
    "summary": "Marca productos que se facturan por peso variable y define su precio por kg",
    "description": """
Agrega a la ficha de producto la posibilidad de marcar que un producto se
factura según su peso real (peso variable) en lugar de su cantidad de venta
fija, y define el precio por kilogramo aplicable a todas sus variantes.
""",
    "author": "Plásticos Durán",
    "license": "LGPL-3",
    "depends": ["product", "stock", "sale_stock", "account"],
    "data": [
        "security/ir.model.access.csv",
        "views/product_template_views.xml",
        "views/stock_picking_views.xml",
        "wizard/duran_cambio_producto_views.xml",
        "views/sale_order_views.xml",
        "views/account_move_views.xml",
    ],
    "installable": True,
    "application": False,
}
