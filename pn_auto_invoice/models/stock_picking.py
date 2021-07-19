from odoo import api, fields, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def auto_invoice(self, picking_id=None):
        if self:
            sp_id = self
        else:
            sp_id = picking_id
        if sp_id.group_id:
            data = {}
            if sp_id.picking_type_id.code == 'incoming':
                po = self.env['purchase.order'].search([('name', '=', sp_id.group_id.name)])
                origin = f'{po.name}: {sp_id.name}'
                payment_term_id = po.payment_term_id.id
                company_id = po.company_id.id
                journal_id = self.env['account.journal'].search(
                    [('type', '=', 'purchase'),
                     ('company_id', '=', company_id)])
                journal_id = journal_id[0].id
                account_id = self.env['account.account'].search(
                    [('internal_type', '=', 'payable'),
                     ('company_id', '=', company_id),
                     ('deprecated', '=', False)])
                account_id = account_id[0].id
                inv_type = 'in_invoice'
                user_id = self._uid
                data.update({
                    'reference': po.partner_ref
                })
            elif sp_id.picking_type_id.code == 'outgoing':
                so = self.env['sale.order'].search([('name', '=', sp_id.group_id.name)])
                origin = f'{so.name}: {sp_id.name}'
                payment_term_id = so.payment_term_id.id
                company_id = so.company_id.id
                journal_id = self.env['account.journal'].search(
                    [('type', '=', 'sale'),
                     ('company_id', '=', company_id)])
                journal_id = journal_id[0].id
                account_id = self.env['account.account'].search(
                    [('internal_type', '=', 'receivable'),
                     ('company_id', '=', company_id),
                     ('deprecated', '=', False)])
                account_id = account_id[0].id
                inv_type = 'out_invoice'
                user_id = so.user_id.id
                data.update({
                    'partner_shipping_id': so.partner_shipping_id.id,
                    'team_id': so.team_id.id
                })
            data.update({
                'type': inv_type,
                'journal_type': 'purchase',
                'release_to_pay': 'yes',
                'partner_id': sp_id.partner_id.id,
                'payment_term_id': payment_term_id,
                'account_id': account_id,
                'journal_id': journal_id,
                'company_id': company_id,
                'origin': origin,
                'user_id': user_id,
            })
            inv = self.env['account.invoice'].create(data)
            for move in sp_id.move_lines:
                if move.quantity_done:
                    data_line = {}
                    if sp_id.picking_type_id.code == 'incoming':
                        if move.product_id.default_code:
                            product_name = '%s: [%s] %s' % (po.name, move.product_id.default_code, move.product_id.name)
                        else:
                            product_name = '%s: %s' % (po.name, move.product_id.name)

                        uom_id = move.product_uom.id
                        account_id = self.env['account.account'].search(
                            [('code', '=', '202100'), ('company_id', '=', company_id)]).id
                        price_unit = move.purchase_line_id.price_unit * move.purchase_line_id.product_uom.factor
                        data_line.update({
                            'purchase_line_id': move.purchase_line_id.id,
                        })
                        tax_ids = [(6, 0, [x.id for x in move.purchase_line_id.taxes_id])]
                        analytic_account_id = move.purchase_line_id.account_analytic_id.id

                    elif sp_id.picking_type_id.code == 'outgoing':
                        if move.product_id.default_code:
                            product_name = '[%s] %s' % (move.product_id.default_code, move.product_id.name)
                        else:
                            product_name = '%s' % move.product_id.name

                        uom_id = move.product_uom.id
                        account_id = self.env['account.account'].search(
                            [('code', '=', '400100'), ('company_id', '=', company_id)]).id
                        price_unit = move.sale_line_id.price_unit * move.sale_line_id.product_uom.factor
                        tax_ids = [(6, 0, [x.id for x in move.sale_line_id.tax_id])]
                        analytic_account_id = so.analytic_account_id.id
                        data_line.update({
                            'discount': move.sale_line_id.discount
                        })

                    data_line.update({
                        'invoice_id': inv.id,
                        'product_id': move.product_id.id,
                        'quantity': move.quantity_done,
                        'uom_id': uom_id,
                        'account_id': account_id,
                        'name': product_name,
                        'price_unit': price_unit,
                        'account_analytic_id': analytic_account_id,
                        'invoice_line_tax_ids': tax_ids,
                    })
                    inv_line = self.env['account.invoice.line'].create(data_line)
                    if sp_id.picking_type_id.code == 'outgoing':
                        move.sale_line_id.update({
                            'invoice_lines': [(4, inv_line.id, 0)]
                        })

            inv.compute_taxes()
            return inv
        else:
            return False

    @api.multi
    def button_validate(self):
        res = super(StockPicking, self).button_validate()
        if not res and self.picking_type_id.code in ['incoming', 'outgoing']:
            self.auto_invoice()
        return res


class StockBackorderConfirmation(models.TransientModel):
    _inherit = 'stock.backorder.confirmation'

    def process(self):
        res = super(StockBackorderConfirmation, self).process()
        if self.pick_ids.picking_type_id.code in ['incoming', 'outgoing']:
            self.env['stock.picking'].auto_invoice(self.pick_ids)
        return res

    def process_cancel_backorder(self):
        res = super(StockBackorderConfirmation, self).process_cancel_backorder()
        if self.pick_ids.picking_type_id.code in ['incoming', 'outgoing']:
            self.env['stock.picking'].auto_invoice(self.pick_ids)
        return res


class StockImmediateTransfer(models.TransientModel):
    _inherit = 'stock.immediate.transfer'

    def process(self):
        res = super(StockImmediateTransfer, self).process()
        if not res and self.pick_ids.picking_type_id.code in ['incoming', 'outgoing']:
            self.env['stock.picking'].auto_invoice(self.pick_ids)
        return res
