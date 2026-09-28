# Configuración requerida para producción

Ajustes de Odoo de los que depende la captura del tianguis (`duran_captura_tianguis`). Revisarlos
al pasar a producción y cada vez que alguien cambie la configuración.

| Ajuste | Valor requerido | Dónde | Por qué |
|---|---|---|---|
| Bloquear órdenes confirmadas | **Desactivado** | Ventas › Configuración › Ajustes › Pedidos de venta › "Bloquear órdenes confirmadas" | Al confirmar una entrega, la app baja la cantidad pedida de cada línea a lo entregado. En una orden bloqueada Odoo no permite cambiar cantidades, y la confirmación de la entrega se rechazaría completa. |
| Límites de peso de un rollo | Los tres parámetros deben existir, con un número de kg mayor a 0 | Ajustes › Técnico › Parámetros del sistema (modo desarrollador): `duran_captura_tianguis.peso_bloqueo_max` (15), `duran_captura_tianguis.peso_advertencia_min` (0.5), `duran_captura_tianguis.peso_advertencia_max` (8) | Sin ellos, la vista previa y la confirmación de entregas dan error. Se crean al instalar el módulo; actualizarlo no pisa los valores ajustados. |
