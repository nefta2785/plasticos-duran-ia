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
| **"Este cliente tiene una factura en borrador; confírmala o cancélala en Odoo."** (aviso rojo, arriba y abajo del total, sin botones de pago) | Hay una factura de ese cliente sin confirmar. Mientras exista, la app no le cobra. | En Odoo, abrir esa factura y tocar **Confirmar**. Si ya no sirve, tocar **Cancelar**. Luego volver a abrir al cliente en la app. |
| **"Hay devoluciones sin nota de crédito (S000…). No entran en este cobro: haz la nota de crédito en Odoo."** | El cliente regresó mercancía y todavía no se hizo el papel que se lo descuenta. Sí se le puede cobrar, pero sin descontarle lo que regresó. | Cobrar normal. Después, en Odoo, abrir esa orden, tocar **Crear factura**: sale la **Nota de crédito**. Tocarle **Confirmar** (si no, se queda en Borrador y bloquea el siguiente cobro). En el siguiente cobro se le descuenta sola. |
| **"Otra persona facturó o cobró a este cliente mientras tanto. Se volvió a cargar lo que debe: revisa el total y cobra otra vez."** | Mientras cobraban, alguien más movió la cuenta de ese cliente (por ejemplo, registró un pago en Odoo). **No se registró nada.** | Revisar el total nuevo y volver a tocar cómo pagó. |
| **"No se pudo confirmar si el cobro llegó. Toca «Registrar cobro» otra vez: si ya había llegado, no se duplica."** | Se fue la señal justo al registrar. | Tocar **Registrar cobro** otra vez cuando haya señal. Aunque el cobro sí hubiera llegado, no se cobra dos veces. |

## 4. El corte del día (arqueo)

En Odoo: **Ventas › Órdenes › Resumen de ventas**.

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

## 6. Otras reglas importantes

**Para volver a la pantalla de Pedido, Entrega y Cobro, toquen INICIO** (arriba a la derecha),
desde cualquier pantalla.

**Nada queda en Odoo hasta tocar el botón verde de abajo** (✓ ENVIAR PEDIDO, ✓ CONFIRMAR
ENTREGA o ✓ REGISTRAR COBRO). Mientras falte, la pantalla dice arriba "Falta enviar el pedido"
(o "Falta confirmar la entrega", "Falta registrar el cobro") y, junto al botón, un aviso
amarillo "Falta un paso: … todavía NO se ha …". Cuando sí quedó, aparece un palomeo verde
grande con **PEDIDO ENVIADO**, **ENTREGA CONFIRMADA** o **COBRO REGISTRADO**.

Si tocan INICIO, Regresar o "atrás" con algo sin enviar, confirmar o registrar, la app pregunta
antes de salir (también al abrir el cobro de otro cliente con un cobro sin registrar):

- **Botón verde de arriba** ("✓ Enviar pedido ahora", "✓ Confirmar entrega ahora",
  "✓ Registrar cobro ahora"): lo hace en ese momento y se queda en la pantalla de éxito. Si
  todavía no están en la pantalla final, dice "Revisar y enviar" (o "Revisar y confirmar",
  "Revisar y registrar") y los lleva a ella. Si no hay señal o Odoo da un error, se quedan en la
  pantalla con el mensaje en rojo; tocar otra vez no duplica nada.
- **"Salir sin enviar"** (pedido): el pedido **se pierde**.
- **"Salir sin confirmar" / "Salir sin registrar"** (entrega y cobro): lo capturado (pesos,
  cantidades, cómo pagó, el monto) **se conserva**, pero **NO queda registrado en Odoo**. En
  Inicio aparece un aviso amarillo, por ejemplo "⚠ Entrega sin confirmar: Doña Carmen ·
  Continuar ›"; tocarlo los regresa a esa entrega o cobro. Se ven hasta dos avisos y "y N más".
- **Tocar fuera de la ventana** (la parte oscura): se quedan donde estaban.

Regresar a la pantalla anterior para cambiar algo (por ejemplo del resumen a la lista) no
pregunta. Lo capturado se pierde si cierran o recargan la página, o si Android cierra Chrome:
**no salgan sin tocar el botón verde.**

**Cliente nuevo (solo en Pedido).** Si el cliente todavía no está en Odoo, en la lista de clientes
de la zona toquen el botón verde **"+ Cliente nuevo"** (también sale cuando la zona no tiene
clientes). La zona es la de la pantalla; solo escriban el **nombre del cliente** y toquen
**"Guardar y levantar pedido"**: entra directo a sus productos.

- Si el nombre se parece a uno que ya existe, la app pregunta **"¿Es alguno de estos?"**. Si es
  uno de esta zona, tóquenlo y entra a su pedido. Si dice "Ya existe en [otra zona]", búsquenlo en
  esa zona. Si dice "Hay un cliente archivado con este nombre", pidan que lo reactiven en Odoo.
  Si no es ninguno, toquen **"No, es otro cliente"**.
- Si ya hay uno **con el mismo nombre en esta zona**, la app no deja crear otro igual: si son dos
  clientes distintos, agréguenle un apellido o el nombre del local.
- Si se va la señal al guardar, toquen **Guardar** otra vez: no se crea dos veces.
- **Teléfono, RFC y dirección no se piden en la app:** se completan después en Odoo
  (Contactos). En la nota interna del contacto queda "Creado desde la app el [fecha] por
  [usuario]".
- **Si quedó en la zona equivocada**, la corrige alguien con permisos en Contactos (cambiando su
  etiqueta de zona). Quien captura no puede editar contactos.

**Cada operación tiene su nombre y su color arriba**, en todas sus pantallas: **Pedido** azul,
**Entrega** verde, **Cobro** naranja y **Acomodo** morado. Los botones de la pantalla de inicio
tienen los mismos colores.

**Al levantar un pedido, para agregar más de uno toquen "+"; para quitar, toquen "−".** Con 1,
el "−" quita el producto del pedido. Tocar el nombre del producto no hace nada.

**Para acomodar el carrito, toquen "Acomodo de entregas"** en la pantalla de inicio. Salen los
pedidos que falta entregar, separados por zona y **del último pedido al primero, en el orden en
que se carga el carrito**: el primero de la lista se carga primero y va hasta el fondo. El
número de cada pedido es su turno de entrega: el 1 (el último de la lista) se entrega primero y
queda hasta arriba del carrito. Cuentan los pedidos levantados desde las 8 de
la noche del día anterior; los de después de las 8 de la noche salen al día siguiente.

**Si en el celular llegan a Odoo por error**, toquen la app **Captura** en el menú de Odoo:
los regresa a la pantalla de captura.

**Cobren siempre con la app.** Si un pago se anota directamente en Odoo, ese dinero **no aparece
en "Resumen de ventas"** y no sale en el corte del día. La deuda del cliente sí baja, pero el
corte no lo cuenta.

**Debe haber una sola caja de Efectivo en Odoo.** En Facturación › Configuración › Contabilidad ›
Diarios debe haber **uno solo** de tipo **Efectivo**. No creen otro ni archiven el que hay: si
hay dos o ninguno, la app no puede registrar lo que pagan y avisa que hay que revisar los
diarios.

**Cambiar un producto que ya se llevó el cliente, solo después de que se le facturó.** Si el
cliente quiere cambiar un rollo o un producto, primero tiene que estar en una factura (se hace
sola al cobrarle con la app, aunque sea con "No pagó hoy"). Después ya se puede hacer el cambio
en Odoo.

**Las entregas de rollos se registran siempre desde la app.** No validen entregas de rollos
desde Odoo: la app es la que pide el peso de cada rollo y con ese peso se cobra.

**Al dar de alta un producto o cambiarle el Tipo**, revisen en la pestaña Información general:

- "Política de facturación" debe decir **Cantidades entregadas**. Si le cambian el Tipo al
  producto, Odoo lo regresa solo a "Cantidades pedidas": hay que volver a ponerlo.
- "Impuestos de venta" debe estar **vacío**. Si tiene un impuesto, el cliente pagaría más que el
  precio del tianguis.

**Un cobro no se puede deshacer desde la app.** Si se registró mal (por ejemplo, otra cantidad),
hay que corregirlo en Odoo. El cobro equivocado **sigue apareciendo** en "Resumen de ventas", así
que al hacer el corte tómenlo en cuenta.

## 7. Si se pierde un celular

La app se queda con la sesión abierta en el celular, para no tener que volver a escribir la
contraseña. Por eso, **si se pierde o se roban un celular, cambien de inmediato la contraseña de
ese usuario** desde Odoo:

1. Ajustes › Usuarios y empresas › Usuarios.
2. Abrir el usuario del celular perdido.
3. En el menú **Acciones** (el engrane), tocar **Cambiar contraseña** y poner una nueva.

Al cambiar la contraseña, **el celular perdido queda fuera**: la próxima vez que alguien intente
usar la app en ese celular, le pedirá la contraseña nueva.

## 8. Hoja de carga (para el papá)

En **Ventas › Órdenes › Hoja de carga** sale todo lo que falta entregar, **agrupado por zona**
(las zonas ya vienen abiertas): un renglón por producto con su cantidad ("4 pz" son piezas,
"2,5 kg" kilos). Solo la ven el papá y el administrador. Al ir acomodando, toquen el **cuadro**
de cada producto:

- **☐ (cuadro vacío)**: toquen para marcarlo como acomodado.
- **Verde, ☑ (cuadro palomeado)**: acomodado; lo que marcaron alcanza para lo pendiente (el
  total es igual o menor que lo marcado, por ejemplo porque se canceló un pedido o ya se
  entregó una parte). Para desmarcarlo, toquen el cuadro palomeado.
- **Naranja** ("Se agregó 1", "Se agregaron 3"): después de marcarlo entraron pedidos de ese
  producto en esa zona. Acomoden lo nuevo y toquen otra vez el cuadro.

Las marcas empiezan en blanco cada día. La hoja **se actualiza sola cada 30 segundos** mientras
la pantalla esté abierta: no hace falta recargarla para ver los pedidos nuevos. En el celular
cabe a lo ancho, sin deslizar a los lados.

## 9. Pendiente de cobro (para el papá)

En **Ventas › Órdenes › Pendiente de cobro** se ve, por zona y cliente, **lo entregado hoy más los saldos anteriores** (facturas sin pagar, saldos a favor y entregas de otros días sin cobrar); un renglón en **rojo** es un saldo con **más de 7 días**, y el **Total a cobrar** de cada cliente es el mismo que muestra la pantalla de **Cobro** de la app.
