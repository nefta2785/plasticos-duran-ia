# Guía para el día a día: cobros en el tianguis

Estas son las reglas que dependen de ustedes para que la app cobre bien. La app hace las
facturas y registra el efectivo sola; lo que se hace a mano en Odoo es lo que hay que cuidar.

## 1. Si cambian una factura en Odoo, confírmenla antes de salir a cobrar

A veces hay que corregir una factura en Odoo, por ejemplo para agregar unos pesos. Mientras se
está corrigiendo, la factura queda como **Borrador**.

- Al terminar, toquen el botón **Confirmar** de la factura.
- Si se queda en Borrador, **la app no deja cobrarle a ese cliente**: sale un aviso rojo y no
  aparecen los botones de pago.
- Antes de salir al tianguis, revisen en Odoo (Facturación › Clientes › Facturas) que ninguna
  factura se haya quedado en **Borrador**.
- Si la factura en Borrador ya no sirve, tóquenle **Cancelar**.

## 2. No cambien facturas que ya están pagadas

Si una factura ya está pagada y faltó cobrar algo (por ejemplo, unos pesos de más), **no la
cambien**. Lo que faltó va en la **siguiente factura** de ese cliente.

Si se cambia una factura ya pagada, lo que se cobró deja de cuadrar con lo que dice la factura.

## 3. Qué significa cada aviso de la app

| Lo que dice la app | Qué pasa | Qué hacer |
|---|---|---|
| **"Este cliente tiene una factura en borrador; publícala o cancélala en Odoo."** (aviso rojo, arriba y abajo del total, sin botones de pago) | Hay una factura de ese cliente sin confirmar. Mientras exista, la app no le cobra. | En Odoo, abrir esa factura y tocar **Confirmar** ("publicarla" es lo mismo que confirmarla). Si ya no sirve, tocar **Cancelar**. Luego volver a abrir al cliente en la app. |
| **"Hay devoluciones sin nota de crédito (S000…). No entran en este cobro: haz la nota de crédito en Odoo."** | El cliente regresó mercancía y todavía no se hizo el papel que se lo descuenta. Sí se le puede cobrar, pero sin descontarle lo que regresó. | Cobrar normal. Después, en Odoo, abrir esa orden, tocar **Crear factura**: sale la **Nota de crédito**. Tocarle **Confirmar** (si no, se queda en Borrador y bloquea el siguiente cobro). En el siguiente cobro se le descuenta sola. |
| **"Otra persona facturó o cobró a este cliente mientras tanto. Se volvió a cargar lo que debe: revisa el total y cobra otra vez."** | Mientras cobraban, alguien más movió la cuenta de ese cliente (por ejemplo, registró un pago en Odoo). **No se registró nada.** | Revisar el total nuevo y volver a tocar cómo pagó. |
| **"No se pudo confirmar si el cobro llegó. Toca «Registrar cobro» otra vez: si ya había llegado, no se duplica."** | Se fue la señal justo al registrar. | Tocar **Registrar cobro** otra vez cuando haya señal. Aunque el cobro sí hubiera llegado, no se cobra dos veces. |

## 4. El corte del día (arqueo)

En Odoo: **Ventas › Órdenes › Cobros en tianguis**.

- Se abre con los cobros de **hoy**, agrupados por día y, dentro, por **quién cobró**.
- En el renglón de cada persona se ven las sumas:
  - **Efectivo recibido**: lo que esa persona debe traer en efectivo.
  - **Queda pendiente**: lo que los clientes quedaron debiendo.
- Cuenten el efectivo de cada quien y compárenlo con su **Efectivo recibido**. Si no cuadra,
  abran el grupo y revisen cobro por cobro.
- Para ver otro día: quiten el filtro **Hoy** y escojan la fecha en **Fecha**.
- El papá ve los cobros de todos. La mamá ve solo los suyos.

## 5. Una factura "Revertido" también está pagada

En Odoo, en **Estado del pago**, una factura puede decir **Revertido** en lugar de **Pagado**.
Pasa cuando se saldó completa con un saldo a favor del cliente (una nota de crédito) y no con
efectivo. **Esa factura también está saldada**: el cliente ya no la debe.
