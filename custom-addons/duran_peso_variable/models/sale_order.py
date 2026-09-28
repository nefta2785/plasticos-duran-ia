from odoo import models
from odoo.http import request


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _update_order_line_info(
        self, product_id, quantity, *, section_id=False, child_field="order_line", **kwargs
    ):
        """ Para productos de peso variable, cada rollo debe quedar en su
        propia línea (cantidad = 1). El catálogo envía la cantidad TOTAL
        deseada para el producto, así que en vez de escribir esa cantidad
        en una sola línea, se agregan o quitan líneas de cantidad 1 hasta
        igualar la cantidad pedida.

        No se puede delegar esto al comportamiento nativo: `create()`/`write()`
        de `sale.order.line` ya dividen automáticamente las líneas, lo que
        deja `sol` (variable local del método base) como un recordset de
        varias líneas, y `_get_discounted_price()` exige `ensure_one()`.
        """
        product = self.env["product.product"].browse(product_id)
        if not product.es_peso_variable:
            return super()._update_order_line_info(
                product_id, quantity, section_id=section_id, child_field=child_field, **kwargs
            )

        request.update_context(catalog_skip_tracking=True)
        existing_lines = self.order_line.filtered(
            lambda l: l.product_id.id == product_id
            and l.get_parent_section_line().id == section_id
        )
        target_qty = int(quantity)

        if target_qty <= 0:
            if self.state in ("draft", "sent"):
                price = self.pricelist_id._get_product_price(
                    product=product,
                    quantity=1.0,
                    currency=self.currency_id,
                    date=self.date_order,
                    **kwargs,
                )
                existing_lines.unlink()
                return price
            existing_lines.product_uom_qty = 0
            return existing_lines[:1]._get_discounted_price() if existing_lines else 0.0

        current_count = len(existing_lines)
        if current_count < target_qty:
            for _i in range(target_qty - current_count):
                self.env["sale.order.line"].create({
                    "order_id": self.id,
                    "product_id": product_id,
                    "product_uom_qty": 1,
                    "sequence": self._get_new_line_sequence(child_field, section_id),
                })
        elif current_count > target_qty:
            existing_lines[target_qty:].unlink()

        remaining = self.order_line.filtered(
            lambda l: l.product_id.id == product_id
            and l.get_parent_section_line().id == section_id
        )
        return remaining[:1]._get_discounted_price() if remaining else 0.0
