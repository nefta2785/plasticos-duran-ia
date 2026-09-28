# Configuración requerida para producción

Ajustes de Odoo de los que depende la captura del tianguis (`duran_captura_tianguis`). Revisarlos
al pasar a producción y cada vez que alguien cambie la configuración.

| Ajuste | Valor requerido | Dónde | Por qué |
|---|---|---|---|
| Bloquear órdenes confirmadas | **Desactivado** | Ventas › Configuración › Ajustes › Pedidos de venta › "Bloquear órdenes confirmadas" | Al confirmar una entrega, la app baja la cantidad pedida de cada línea a lo entregado. En una orden bloqueada Odoo no permite cambiar cantidades, y la confirmación de la entrega se rechazaría completa. |
| Límites de peso de un rollo | Los tres parámetros deben existir, con un número de kg mayor a 0 | Ajustes › Técnico › Parámetros del sistema (modo desarrollador): `duran_captura_tianguis.peso_bloqueo_max` (15), `duran_captura_tianguis.peso_advertencia_min` (0.5), `duran_captura_tianguis.peso_advertencia_max` (8) | Sin ellos, la vista previa y la confirmación de entregas dan error. Se crean al instalar el módulo; actualizarlo no pisa los valores ajustados. |
| Política de facturación de los productos | **"Cantidades entregadas"** ("Facturar lo entregado") en todos los productos que se venden | Para los productos nuevos: Ventas › Configuración › Ajustes › Facturación › "Cantidades a facturar de las órdenes de venta" → "Facturar lo entregado". En cada producto: pestaña Información general › "Política de facturación" | Al cobrar, la app factura lo entregado sin facturar. Con "Cantidades pedidas", Odoo factura lo pedido aunque todavía no se entregue, y aparecería en el cobro. La app no lo revisa. |

### Detalle de la política de facturación (verificado en Odoo 19)

- El ajuste de Ventas **sí aplica a los productos nuevos**, creados desde el formulario o desde
  una importación. Se guarda como valor por defecto del producto solo cuando alguien lo cambia en
  Ajustes (`sale/wizard/res_config_settings.py:10-16`, `base/models/res_config.py:316-317`), y
  Odoo lo usa al crear el producto (`orm/models.py:1582-1600`). En duranDEV ya está en "Facturar
  lo entregado" desde el 23/09/2026.
- **Si nadie lo cambia, Odoo usa "Cantidades pedidas"** (`default='order'` en el mismo ajuste).
  duranPROD nace limpia: hay que cambiarlo **antes** de dar de alta productos.
- **Cambiar el Tipo de un producto** en su formulario (por ejemplo a Servicio y de regreso) lo
  regresa a "Cantidades pedidas", aunque el ajuste diga lo contrario: Odoo lo recalcula al
  cambiar el tipo (`sale/models/product_template.py:162-164`). Después de cambiar el tipo hay que
  volver a poner "Cantidades entregadas". Se comprobó en duranDEV sin guardar nada (transacción
  deshecha): producto nuevo → "entregadas"; mismo producto tras cambiar el tipo → "pedidas".
- Para revisarlo: Ventas › Productos › Productos, vista de lista, "Agrupar por" › agrupación
  personalizada › "Política de facturación". En duranDEV, los 23 productos activos están en "Cantidades entregadas" (los 79
  en "pedidas" están archivados).
