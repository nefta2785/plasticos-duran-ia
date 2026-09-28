from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare


class DuranCambioProducto(models.TransientModel):
    _name = "duran.cambio.producto"
    _description = "Cambio de producto (devolución + venta de reemplazo)"

    order_id = fields.Many2one(
        "sale.order", string="Orden de venta", required=True,
        default=lambda self: self.env.context.get("active_id"),
    )
    currency_id = fields.Many2one(related="order_id.currency_id")
    sale_line_id = fields.Many2one(
        "sale.order.line", string="Línea a cambiar", required=True,
        domain="[('order_id', '=', order_id), ('display_type', '=', False), "
        "('qty_delivered', '=', 1), ('qty_invoiced', '=', 1)]",
    )
    product_id = fields.Many2one(related="sale_line_id.product_id", string="Producto")
    es_peso_variable = fields.Boolean(related="sale_line_id.product_id.es_peso_variable")
    peso_referencia = fields.Float(related="sale_line_id.product_id.peso_referencia")

    peso_devuelto = fields.Float(string="Peso devuelto (kg)", digits=(16, 3))
    peso_nuevo = fields.Float(string="Peso del rollo nuevo (kg)", digits=(16, 3))

    monto_abono_estimado = fields.Monetary(string="Abono (estimado)", compute="_compute_montos_estimados")
    monto_cobro_estimado = fields.Monetary(string="Cobro (estimado)", compute="_compute_montos_estimados")
    monto_diferencia_estimada = fields.Monetary(string="Diferencia a pagar (estimada)", compute="_compute_montos_estimados")

    hay_lineas_elegibles = fields.Boolean(compute="_compute_elegibilidad")
    lineas_no_elegibles_msg = fields.Text(compute="_compute_elegibilidad")

    cobra_ahora = fields.Boolean(string="¿Cobra ahora?", default=True)
    journal_id = fields.Many2one(
        "account.journal", string="Diario de cobro",
        domain=[("type", "=", "cash")],
        default=lambda self: self.env["account.journal"].search([("type", "=", "cash")], limit=1),
    )

    @api.depends(
        "peso_devuelto", "peso_nuevo", "sale_line_id",
        "sale_line_id.product_id.peso_referencia", "sale_line_id.product_id.precio_por_kg",
        "sale_line_id.product_id.lst_price",
    )
    def _compute_montos_estimados(self):
        """ Vista previa antes de confirmar. Para productos de peso variable el
        monto final coincide con este estimado (no depende de tarifas). Para
        productos normales es solo una referencia basada en el precio de lista:
        el monto real que se factura se calcula en `action_confirm` con el
        price_unit de la línea de la orden de reemplazo recién creada (puede
        diferir si hay una lista de precios con reglas especiales). """
        for wizard in self:
            product = wizard.sale_line_id.product_id
            if not product:
                wizard.monto_cobro_estimado = wizard.monto_abono_estimado = wizard.monto_diferencia_estimada = 0.0
                continue
            if wizard.es_peso_variable:
                cobro = wizard.peso_nuevo * product.precio_por_kg
                abono = wizard.peso_devuelto * product.precio_por_kg
            else:
                cobro = product.lst_price
                abono = 0.0
                if wizard.peso_devuelto and product.peso_referencia:
                    proporcion = min(wizard.peso_devuelto / product.peso_referencia, 1.0)
                    abono = proporcion * cobro
            wizard.monto_cobro_estimado = cobro
            wizard.monto_abono_estimado = abono
            wizard.monto_diferencia_estimada = cobro - abono

    @api.depends(
        "order_id.order_line.qty_delivered", "order_id.order_line.qty_invoiced",
        "order_id.order_line.product_id.invoice_policy", "order_id.order_line.move_ids.state",
        "order_id.order_line.move_ids.origin_returned_move_id",
    )
    def _compute_elegibilidad(self):
        for wizard in self:
            content_lines = wizard.order_id.order_line.filtered(lambda l: not l.display_type)
            msgs = []
            eligible = False
            for idx, line in enumerate(content_lines, start=1):
                motivo = wizard._motivo_no_elegible(line)
                if motivo:
                    msgs.append(_(
                        "#%(row)s · %(product)s: %(motivo)s",
                        row=idx, product=line.product_id.display_name, motivo=motivo,
                    ))
                else:
                    eligible = True
            wizard.hay_lineas_elegibles = eligible
            wizard.lineas_no_elegibles_msg = "\n".join(msgs) if msgs else False

    def _motivo_no_elegible(self, line):
        """ Motivo, en lenguaje de operación, por el que esta línea no se
        puede usar en un Cambio de producto. Devuelve None si sí califica.
        Se evalúa en el orden en que la persona debe resolver las cosas:
        primero la política de facturación del producto (configuración),
        luego que la entrega esté validada, luego que esté facturada. """
        self.ensure_one()
        qty_precision = self.env["decimal.precision"].precision_get("Product Unit of Measure")
        if line.product_id.invoice_policy != "delivery":
            return _("su política de facturación debe ser Cantidades entregadas")
        if float_compare(line.qty_delivered, 1.0, precision_digits=qty_precision) != 0:
            ya_cambiada = line.move_ids.filtered(
                lambda m: m.state == "done" and m.origin_returned_move_id
            )
            if ya_cambiada:
                return _("ya tuvo un cambio")
            return _("falta validar la entrega")
        if float_compare(line.qty_invoiced, 1.0, precision_digits=qty_precision) != 0:
            return _("falta facturar")
        return None

    # === Validación === #

    def _check_before_confirm(self):
        self.ensure_one()
        line = self.sale_line_id
        product = line.product_id
        qty_precision = self.env["decimal.precision"].precision_get("Product Unit of Measure")

        if product.invoice_policy != "delivery":
            raise UserError(_(
                'El producto "%(product)s" tiene la política de facturación '
                '"%(policy)s". Para usar el Cambio de producto, su política de '
                'facturación debe ser "Cantidades entregadas".',
                product=product.display_name, policy=product.invoice_policy,
            ))

        if float_compare(self.peso_devuelto, 0.0, precision_digits=3) <= 0:
            raise UserError(_("El peso devuelto debe ser mayor a 0."))

        if self.es_peso_variable:
            if float_compare(self.peso_nuevo, 0.0, precision_digits=3) <= 0:
                raise UserError(_("El peso del rollo nuevo debe ser mayor a 0."))
            if float_compare(self.peso_nuevo, self.peso_devuelto, precision_digits=3) <= 0:
                raise UserError(_("El peso del rollo nuevo debe ser mayor al peso devuelto."))
        elif float_compare(product.peso_referencia, 0.0, precision_digits=3) <= 0:
            raise UserError(_(
                'El producto "%(product)s" no tiene configurado un Peso de referencia (kg). '
                "Complétalo en la ficha del producto antes de hacer el cambio.",
                product=product.display_name,
            ))

        if (
            float_compare(line.qty_delivered, 1.0, precision_digits=qty_precision) != 0
            or float_compare(line.qty_invoiced, 1.0, precision_digits=qty_precision) != 0
        ):
            raise UserError(_(
                "Solo se pueden cambiar líneas totalmente entregadas y facturadas por 1 "
                "unidad (entregado: %(delivered)s, facturado: %(invoiced)s).",
                delivered=line.qty_delivered, invoiced=line.qty_invoiced,
            ))

        if not line.invoice_lines.move_id.filtered(lambda m: m.state == "posted"):
            raise UserError(_(
                'La línea de "%(product)s" no tiene ninguna factura publicada.',
                product=product.display_name,
            ))

        other_lines = self.order_id.order_line.filtered(lambda l: l.id != line.id and not l.display_type)
        pending = other_lines.filtered(
            lambda l: float_compare(l.qty_to_invoice, 0.0, precision_digits=qty_precision) != 0
        )
        if pending:
            raise UserError(_(
                "La orden %(order)s tiene otras líneas con cantidad pendiente de facturar "
                "distinta de cero (%(products)s). Resuélvelas antes de hacer un cambio de "
                "producto, para que la nota de crédito generada corresponda únicamente a "
                "esta línea.",
                order=self.order_id.name,
                products=", ".join(pending.mapped("product_id.display_name")),
            ))

        if self.cobra_ahora and not self.journal_id:
            raise UserError(_("Selecciona un diario de efectivo para registrar el cobro."))

    # === Acción principal === #

    def action_confirm(self):
        self.ensure_one()
        self._check_before_confirm()
        product = self.sale_line_id.product_id

        # a) Devolución de la línea original, con el peso devuelto.
        self._create_and_validate_return()

        # c) Orden de venta de reemplazo (antes de calcular el abono: su
        #    price_unit es la fuente de verdad para el cobro y, en productos
        #    normales, también para el abono).
        new_order, new_line = self._create_replacement_order(product)
        self._validate_replacement_delivery(new_order, product)

        cobro = new_line.price_unit
        if self.es_peso_variable:
            abono = self.peso_devuelto * product.precio_por_kg
        else:
            proporcion = min(self.peso_devuelto / product.peso_referencia, 1.0)
            abono = proporcion * cobro

        # b) Nota de crédito de la orden original.
        credit_note = self._create_credit_note(product, abono)

        # d) Factura de la orden de reemplazo.
        new_invoice = self._create_and_post_invoice(new_order)

        # e) Aplicar la nota de crédito contra la factura nueva.
        self._apply_credit_note(credit_note, new_invoice)

        # f) Cobro del saldo, si corresponde.
        if self.cobra_ahora:
            self._register_payment(new_invoice)

        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": new_invoice.id,
            "view_mode": "form",
            "target": "current",
        }

    # === Pasos === #

    def _validate_picking(self, picking):
        """ Valida una Entrega y exige que quede efectivamente en 'done'. Si
        Odoo devuelve una acción/wizard en vez de completar la validación
        (ej. pedir confirmación de backorder o transferencia parcial), se
        lanza una excepción para que toda la transacción del cambio de
        producto se revierta en vez de dejar documentos a medias. """
        result = picking.with_context(skip_backorder=True).button_validate()
        if result is not True:
            raise UserError(_(
                'La Entrega "%(picking)s" no se pudo validar automáticamente: Odoo pidió '
                "una confirmación adicional que el asistente de Cambio de producto no puede "
                "resolver por sí solo.",
                picking=picking.name,
            ))
        if picking.state != "done":
            raise UserError(_(
                'La Entrega "%(picking)s" quedó en estado "%(state)s" en vez de "Hecho" '
                "tras la validación.",
                picking=picking.name, state=picking.state,
            ))

    def _create_and_validate_return(self):
        self.ensure_one()
        line = self.sale_line_id
        delivery_move = line.move_ids.filtered(
            lambda m: m.state == "done" and m.location_dest_usage == "customer"
        ).sorted("date", reverse=True)[:1]
        if not delivery_move:
            raise UserError(_(
                'No se encontró la Entrega validada de "%(product)s" para generar la '
                "devolución.",
                product=line.product_id.display_name,
            ))
        picking = delivery_move.picking_id

        return_wizard = self.env["stock.return.picking"].with_context(
            active_id=picking.id, active_model="stock.picking",
        ).create({})
        return_wizard._compute_moves_locations()
        return_line = return_wizard.product_return_moves.filtered(lambda l: l.move_id == delivery_move)
        if not return_line:
            raise UserError(_(
                'No se pudo preparar la devolución de "%(product)s".',
                product=line.product_id.display_name,
            ))
        return_line.quantity = 1
        new_picking = return_wizard._create_return()

        return_move = new_picking.move_ids.filtered(lambda m: m.origin_returned_move_id == delivery_move)
        if not return_move:
            raise UserError(_(
                'La devolución no generó ningún movimiento para "%(product)s".',
                product=line.product_id.display_name,
            ))
        return_move.peso_real = self.peso_devuelto if self.es_peso_variable else 0.0
        new_picking.move_ids.write({"quantity": 1})
        self._validate_picking(new_picking)
        return new_picking

    def _create_replacement_order(self, product):
        self.ensure_one()
        line_vals = {
            "product_id": product.id,
            "product_uom_qty": 1,
        }
        if self.es_peso_variable:
            line_vals["peso_real"] = self.peso_nuevo
        new_order = self.env["sale.order"].create({
            "partner_id": self.order_id.partner_id.id,
            "order_line": [(0, 0, line_vals)],
        })
        new_order.action_confirm()
        if new_order.state != "sale":
            raise UserError(_(
                'La orden de venta de reemplazo "%(order)s" no quedó confirmada (estado '
                '"%(state)s").',
                order=new_order.name, state=new_order.state,
            ))
        new_line = new_order.order_line.filtered(lambda l: l.product_id == product)
        if len(new_line) != 1:
            raise UserError(_(
                'La orden de venta de reemplazo no generó exactamente una línea para '
                '"%(product)s".',
                product=product.display_name,
            ))
        return new_order, new_line

    def _validate_replacement_delivery(self, new_order, product):
        self.ensure_one()
        picking = new_order.picking_ids.filtered(lambda p: p.state not in ("done", "cancel"))
        if len(picking) != 1:
            raise UserError(_(
                "La orden de venta de reemplazo no generó exactamente una Entrega "
                "pendiente."
            ))
        move = picking.move_ids.filtered(lambda m: m.product_id == product)
        if self.es_peso_variable:
            move.peso_real = self.peso_nuevo
        picking.move_ids.write({"quantity": 1})
        self._validate_picking(picking)
        return picking

    def _create_credit_note(self, product, abono):
        self.ensure_one()
        credit_note = self.order_id._create_invoices(final=True)
        if len(credit_note) != 1:
            raise UserError(_(
                "Se esperaba generar exactamente una nota de crédito y se generaron "
                "%(count)s.",
                count=len(credit_note),
            ))
        if credit_note.move_type != "out_refund":
            raise UserError(_(
                'El comprobante generado ("%(name)s") no quedó como nota de crédito '
                '(tipo "%(type)s"). Revísalo manualmente antes de continuar.',
                name=credit_note.name, type=credit_note.move_type,
            ))
        content_lines = credit_note.invoice_line_ids.filtered(
            lambda l: l.display_type not in ("line_section", "line_subsection", "line_note")
        )
        if len(content_lines) != 1 or content_lines.product_id != product:
            raise UserError(_(
                'La nota de crédito generada ("%(name)s") no contiene únicamente la línea '
                'de "%(product)s" esperada para este cambio de producto.',
                name=credit_note.name, product=product.display_name,
            ))
        if not self.es_peso_variable:
            content_lines.price_unit = abono
        credit_note.action_post()
        if credit_note.state != "posted":
            raise UserError(_(
                'La nota de crédito "%(name)s" no quedó publicada (estado "%(state)s").',
                name=credit_note.name, state=credit_note.state,
            ))
        return credit_note

    def _create_and_post_invoice(self, new_order):
        self.ensure_one()
        invoice = new_order._create_invoices()
        if len(invoice) != 1:
            raise UserError(_(
                "Se esperaba generar exactamente una factura para la orden de reemplazo."
            ))
        invoice.action_post()
        if invoice.state != "posted":
            raise UserError(_(
                'La factura "%(name)s" no quedó publicada (estado "%(state)s").',
                name=invoice.name, state=invoice.state,
            ))
        return invoice

    def _apply_credit_note(self, credit_note, invoice):
        self.ensure_one()
        receivable_line = credit_note.line_ids.filtered(
            lambda l: l.account_id.account_type == "asset_receivable" and not l.reconciled
        )[:1]
        if not receivable_line:
            raise UserError(_(
                'No se encontró una línea por cobrar pendiente en la nota de crédito '
                '"%(name)s" para aplicarla contra la factura nueva.',
                name=credit_note.name,
            ))
        invoice.js_assign_outstanding_line(receivable_line.id)

    def _register_payment(self, invoice):
        self.ensure_one()
        if invoice.currency_id.is_zero(invoice.amount_residual):
            return
        payment_wizard = self.env["account.payment.register"].with_context(
            active_model="account.move", active_ids=invoice.ids,
        ).create({"journal_id": self.journal_id.id})
        payment_wizard._create_payments()
        invoice.invalidate_recordset(["amount_residual", "payment_state"])
        if not invoice.currency_id.is_zero(invoice.amount_residual):
            raise UserError(_(
                'El cobro se registró pero la factura "%(name)s" sigue con saldo '
                "pendiente (%(residual)s).",
                name=invoice.name, residual=invoice.amount_residual,
            ))
