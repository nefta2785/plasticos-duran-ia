# Configuración requerida para producción

Ajustes de Odoo de los que depende la captura del tianguis (`duran_captura_tianguis`). Revisarlos
al pasar a producción y cada vez que alguien cambie la configuración.

## Lista para duranPROD

Hacerlo en este orden. Las políticas y los impuestos por defecto se aplican **al crear** cada
producto, así que tienen que quedar listos **antes** de dar de alta productos.

1. Ventas › Configuración › Ajustes › Facturación › "Cantidades a facturar de las órdenes de
   venta" → **"Facturar lo entregado"**.
2. Facturación › Configuración › Ajustes › Impuestos › "Impuestos predeterminados" › "Impuesto de
   venta" → **vacío**.
3. Dar de alta los productos. Revisar que todos queden con **"Cantidades entregadas"** y **sin
   "Impuestos de venta"** (ver cómo revisarlo abajo).
4. Facturación › Configuración › Contabilidad › Diarios: **exactamente un** diario activo de tipo **Efectivo**.
5. Ventas › Configuración › Ajustes: **"Bloquear órdenes confirmadas" desactivado**.
6. Instalar `duran_captura_tianguis` y revisar los **tres parámetros de peso** (se crean al
   instalar).

## Detalle de cada ajuste

| Ajuste | Valor requerido | Dónde | Por qué |
|---|---|---|---|
| Bloquear órdenes confirmadas | **Desactivado** | Ventas › Configuración › Ajustes › Pedidos de venta › "Bloquear órdenes confirmadas" | Al confirmar una entrega, la app baja la cantidad pedida de cada línea a lo entregado. En una orden bloqueada Odoo no permite cambiar cantidades, y la confirmación de la entrega se rechazaría completa. |
| Límites de peso de un rollo | Los tres parámetros deben existir, con un número de kg mayor a 0 | Ajustes › Técnico › Parámetros del sistema (modo desarrollador): `duran_captura_tianguis.peso_bloqueo_max` (15), `duran_captura_tianguis.peso_advertencia_min` (0.5), `duran_captura_tianguis.peso_advertencia_max` (8) | Sin ellos, la vista previa y la confirmación de entregas dan error. Se crean al instalar el módulo; actualizarlo no pisa los valores ajustados. |
| Política de facturación de los productos | **"Cantidades entregadas"** ("Facturar lo entregado") en todos los productos que se venden, y como ajuste por defecto de Ventas | Para los productos nuevos: Ventas › Configuración › Ajustes › Facturación › "Cantidades a facturar de las órdenes de venta" → "Facturar lo entregado". En cada producto: pestaña Información general › "Política de facturación" | Al cobrar, la app factura lo entregado sin facturar. Con "Cantidades pedidas", Odoo factura lo pedido aunque todavía no se entregue, y aparecería en el cobro. La app no lo revisa. **Cambiar el Tipo de un producto le regresa "Cantidades pedidas"** (ver el detalle abajo). |
| Diario de efectivo | **Exactamente un** diario activo de tipo **Efectivo** en la compañía | Facturación › Configuración › Contabilidad › Diarios, columna "Tipo" | El efectivo que se cobra en el tianguis se registra en ese diario. Con 0 o con 2 o más, la app no registra "Pagó todo" ni "Pagó una parte" y avisa que hay que revisar los diarios ("No pagó hoy" sí funciona). Los diarios archivados no cuentan. |
| Impuestos por defecto | **Ninguno**: sin "Impuesto de venta" predeterminado, y ningún producto con "Impuestos de venta" | Facturación › Configuración › Ajustes › Impuestos › "Impuestos predeterminados" › "Impuesto de venta" (vacío). En cada producto: pestaña Información general › "Impuestos de venta" (vacío) | El precio del tianguis es el precio final. Odoo le pone a cada producto nuevo el impuesto de venta predeterminado de la compañía, y la app calcula el importe con los impuestos del producto: con IVA, un producto de $70/kg se cobraría a $81.20/kg. La app no lo revisa. |

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

### Detalle de los impuestos (verificado en Odoo 19)

- El impuesto predeterminado se guarda en la compañía (`account/models/company.py:126`) y se
  cambia en Ajustes, bloque "Impuestos" › "Impuestos predeterminados"
  (`account/models/res_config_settings.py:37-40`, `account/views/res_config_settings_views.xml:57-63`).
- Al crear un producto, Odoo le pone ese impuesto en "Impuestos de venta"
  (`account/models/product.py:40-44`). Quitarlo del ajuste no se lo quita a los productos que ya
  existen: hay que revisarlos.
- La app calcula lo que se cobra con los impuestos de la línea de venta, con el motor de impuestos
  de Odoo (`duran_captura_tianguis/models/captura.py`, `_importes_facturas`): el total incluye
  los impuestos.
- Para revisarlo: Ventas › Productos › Productos, vista de lista, agregar la columna "Impuestos de
  venta". En duranDEV (revisado el 28/09/2026 sin guardar nada): sin impuesto de venta
  predeterminado, 0 de los 23 productos vendibles con impuesto y un solo diario de Efectivo.

### Detalle del diario de efectivo (verificado en Odoo 19)

- La app busca los diarios de tipo Efectivo de la compañía (`duran_captura_tianguis/models/captura.py`,
  `_diario_efectivo`) y registra ahí el pago, como "Registrar pago" de Odoo con "Agrupar pagos".
- Tipo "Efectivo" es el valor `cash` del diario; en español aparece como "Efectivo".
