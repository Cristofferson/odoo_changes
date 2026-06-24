# -*- coding: utf-8 -*-
import json
import logging
from datetime import timedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

WEEKDAY_MAP = {'mon': 1, 'tue': 2, 'wed': 3, 'thu': 4, 'fri': 5, 'sat': 6, 'sun': 7}
XIBO_EVENT_TYPE = {'fullscreen': 1, 'overlay': 3, 'command': 4, 'ticker': 1}


class XiboBroadcast(models.Model):
    _name = 'xibo.broadcast'
    _description = 'Xibo Broadcast (Scheduled Event)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'
    _order = 'from_dt desc, id desc'

    name = fields.Char(string='Title', required=True, tracking=True,
                       default=lambda self: _('New Broadcast'))
    server_id = fields.Many2one('xibo.server', required=True, ondelete='restrict', tracking=True,
                                 default=lambda self: self._default_server())
    company_id = fields.Many2one(related='server_id.company_id', store=True)

    display_mode = fields.Selection(
        [('fullscreen', 'Full-screen (interrupts current layout)'),
         ('overlay', 'Overlay popup (does not interrupt)'),
         ('ticker', 'Ticker (DataSet row)')],
        default='overlay', required=True, tracking=True,
    )
    layout_id = fields.Many2one('xibo.layout', string='Layout',
                                 domain="[('server_id', '=', server_id)]")
    dataset_id = fields.Many2one('xibo.dataset', string='DataSet',
                                  domain="[('server_id', '=', server_id)]")
    dataset_values_json = fields.Text(string='DataSet Values (JSON)')

    display_group_ids = fields.Many2many(
        'xibo.display.group', 'xibo_broadcast_displaygroup_rel',
        'broadcast_id', 'group_id', string='Display Groups',
        domain="[('server_id', '=', server_id)]",
    )
    display_ids = fields.Many2many(
        'xibo.display', 'xibo_broadcast_display_rel',
        'broadcast_id', 'display_id', string='Displays',
        domain="[('server_id', '=', server_id)]",
    )

    from_dt = fields.Datetime(string='From', required=True,
                               default=lambda self: fields.Datetime.now(), tracking=True)
    to_dt = fields.Datetime(string='To', required=True, tracking=True,
                             default=lambda self: fields.Datetime.now() + timedelta(minutes=1))
    duration_seconds = fields.Integer(string='Display Duration (s)', default=15)

    time_from = fields.Float(string='Daily From', default=0.0)
    time_to = fields.Float(string='Daily To', default=24.0)

    dow_mon = fields.Boolean(default=True)
    dow_tue = fields.Boolean(default=True)
    dow_wed = fields.Boolean(default=True)
    dow_thu = fields.Boolean(default=True)
    dow_fri = fields.Boolean(default=True)
    dow_sat = fields.Boolean(default=True)
    dow_sun = fields.Boolean(default=True)

    recurrence_type = fields.Selection(
        [('none', 'No recurrence'),
         ('minute', 'Every N minutes'),
         ('hour', 'Every N hours'),
         ('day', 'Daily'),
         ('week', 'Weekly'),
         ('month', 'Monthly'),
         ('year', 'Yearly')],
        default='none', required=True,
    )
    recurrence_detail = fields.Integer(string='Every', default=1)
    recurrence_until = fields.Date(string='Until')

    is_priority = fields.Boolean(default=False)
    instant_push = fields.Boolean(default=True)

    state = fields.Selection(
        [('draft', 'Draft'), ('scheduled', 'Scheduled'), ('active', 'Active'),
         ('done', 'Done'), ('cancelled', 'Cancelled'), ('error', 'Error')],
        default='draft', tracking=True, readonly=True, copy=False,
    )
    xibo_event_id = fields.Integer(string='Xibo Event ID', readonly=True, copy=False)
    last_error = fields.Text(readonly=True)

    origin_model = fields.Char(readonly=True)
    origin_res_id = fields.Integer(readonly=True)
    origin_description = fields.Char(readonly=True)

    # -------------------------------------------------------------------------
    def _default_server(self):
        return self.env['xibo.server'].search(
            [('state', '=', 'connected'), ('active', '=', True),
             ('company_id', '=', self.env.company.id)], limit=1)

    @api.onchange('layout_id')
    def _onchange_layout_id(self):
        if self.layout_id and self.layout_id.duration and not self.duration_seconds:
            self.duration_seconds = self.layout_id.duration

    @api.constrains('from_dt', 'to_dt')
    def _check_dates(self):
        for rec in self:
            if rec.from_dt and rec.to_dt and rec.to_dt <= rec.from_dt:
                raise ValidationError(_("End date must be after start date."))

    @api.constrains('time_from', 'time_to')
    def _check_time_window(self):
        for rec in self:
            if not (0 <= rec.time_from <= 24) or not (0 <= rec.time_to <= 24):
                raise ValidationError(_("Daily From/To must be between 0 and 24."))
            if rec.time_from > rec.time_to:
                raise ValidationError(_("Daily From must be earlier than Daily To."))

    @api.constrains('display_mode', 'layout_id', 'dataset_id')
    def _check_required(self):
        for rec in self:
            if rec.display_mode in ('fullscreen', 'overlay') and not rec.layout_id:
                raise ValidationError(_("Mode '%s' requires a Layout.") % rec.display_mode)
            if rec.display_mode == 'ticker' and not rec.dataset_id:
                raise ValidationError(_("Ticker mode requires a DataSet."))

    def _all_display_group_ids(self):
        self.ensure_one()
        xibo_ids = set()
        for group in self.display_group_ids:
            if group.xibo_display_group_id:
                xibo_ids.add(group.xibo_display_group_id)
        for disp in self.display_ids:
            if disp.own_display_group_id:
                xibo_ids.add(disp.own_display_group_id)
        return list(xibo_ids)

    def _dow_string(self):
        self.ensure_one()
        return ','.join(str(WEEKDAY_MAP[k]) for k in WEEKDAY_MAP if getattr(self, f"dow_{k}"))

    def action_send(self):
        for rec in self:
            try:
                rec._send_to_xibo()
            except Exception as e:
                rec.write({'state': 'error', 'last_error': str(e)})
                raise
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Broadcast sent"),
                'message': _("%s broadcast(s) dispatched to Xibo.") % len(self),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }

    def _send_to_xibo(self):
        self.ensure_one()
        if not self.server_id:
            raise UserError(_("No Xibo server configured."))
        xibo_group_ids = self._all_display_group_ids()
        if not xibo_group_ids:
            raise UserError(_("Select at least one display or display group."))

        if self.display_mode == 'ticker':
            self._push_ticker_row(xibo_group_ids)
            self.write({'state': 'active'})
            return True

        if not self.layout_id or not self.layout_id.xibo_campaign_id:
            raise UserError(_("Layout missing or not synced. Sync layouts first."))

        body = {
            'eventTypeId': XIBO_EVENT_TYPE[self.display_mode],
            'campaignId': self.layout_id.xibo_campaign_id,
            'displayGroupIds[]': xibo_group_ids,
            'fromDt': self.from_dt.strftime('%Y-%m-%d %H:%M:%S'),
            'toDt': self.to_dt.strftime('%Y-%m-%d %H:%M:%S'),
            'isPriority': 1 if self.is_priority else 0,
            'displayOrder': 0,
        }

        if self.recurrence_type and self.recurrence_type != 'none':
            body['recurrenceType'] = self.recurrence_type.capitalize()
            body['recurrenceDetail'] = self.recurrence_detail or 1
            if self.recurrence_until:
                body['recurrenceRange'] = self.recurrence_until.strftime('%Y-%m-%d 23:59:59')
            if self.recurrence_type == 'week':
                dow = self._dow_string()
                if dow:
                    body['recurrenceRepeatsOn'] = dow

        clean_body = {k.rstrip('[]'): v for k, v in body.items()}
        resp = self.server_id._request('POST', '/api/schedule', data=clean_body)
        event_id = resp.get('eventId') if isinstance(resp, dict) else False
        self.write({
            'xibo_event_id': event_id,
            'state': 'scheduled' if self.from_dt > fields.Datetime.now() else 'active',
            'last_error': False,
        })
        self.message_post(body=_("Scheduled in Xibo as event %s.") % event_id)

        if self.instant_push:
            self.server_id._trigger_collect_now(xibo_group_ids)
        return True

    def _push_ticker_row(self, xibo_group_ids):
        self.ensure_one()
        try:
            values = json.loads(self.dataset_values_json) if self.dataset_values_json else {}
        except ValueError:
            raise UserError(_("Invalid JSON in DataSet Values."))
        if not values:
            raise UserError(_("DataSet Values is empty for ticker mode."))
        self.dataset_id.push_row(values, trigger_collect_now_for=xibo_group_ids if self.instant_push else None)
        self.message_post(body=_("Pushed ticker row to DataSet '%s'.") % self.dataset_id.name)

    def action_cancel(self):
        for rec in self:
            if rec.xibo_event_id and rec.server_id:
                try:
                    rec.server_id._request('DELETE', f'/api/schedule/{rec.xibo_event_id}',
                                            raise_on_error=False)
                except Exception as e:
                    _logger.warning("Could not delete Xibo event %s: %s", rec.xibo_event_id, e)
            rec.write({'state': 'cancelled'})
        return True

    def action_reset_to_draft(self):
        for rec in self:
            rec.write({'state': 'draft', 'xibo_event_id': 0, 'last_error': False})
        return True

    @api.model
    def quick_send(self, server, *, mode, layout=None, dataset=None,
                   values=None, displays=None, display_groups=None,
                   duration=15, priority=False, origin=None, instant=True, name=None):
        """Create + send a broadcast in one call. Used by add-on modules."""
        from_dt = fields.Datetime.now()
        to_dt = from_dt + timedelta(seconds=duration)
        vals = {
            'name': name or _('Auto broadcast'),
            'server_id': server.id,
            'display_mode': mode,
            'from_dt': from_dt,
            'to_dt': to_dt,
            'duration_seconds': duration,
            'is_priority': priority,
            'instant_push': instant,
            'recurrence_type': 'none',
        }
        if layout:
            vals['layout_id'] = layout.id
        if dataset:
            vals['dataset_id'] = dataset.id
        if values:
            vals['dataset_values_json'] = json.dumps(values)
        if displays:
            vals['display_ids'] = [(6, 0, displays.ids)]
        if display_groups:
            vals['display_group_ids'] = [(6, 0, display_groups.ids)]
        if origin:
            vals['origin_model'] = origin[0]
            vals['origin_res_id'] = origin[1]
            vals['origin_description'] = origin[2] if len(origin) > 2 else False

        broadcast = self.create(vals)
        broadcast._send_to_xibo()
        return broadcast
