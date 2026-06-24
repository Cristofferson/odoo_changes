# -*- coding: utf-8 -*-
import json
import logging
import time
from datetime import timedelta

import requests

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30
MAX_LOG_BODY = 2000


def _reload_action(notification=None):
    """Return a soft-reload action, optionally with a toast notification."""
    if notification:
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': notification.get('title'),
                'message': notification.get('message'),
                'type': notification.get('type', 'success'),
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }
    return {'type': 'ir.actions.client', 'tag': 'soft_reload'}


class XiboServer(models.Model):
    _name = 'xibo.server'
    _description = 'Xibo CMS Server'
    _inherit = ['mail.thread']
    _rec_name = 'name'

    name = fields.Char(string='Name', required=True, tracking=True)
    url = fields.Char(
        string='CMS URL', required=True, tracking=True,
        help="Base URL of your Xibo CMS, e.g. https://xibo.example.com (no trailing slash).",
    )
    client_id = fields.Char(string='Client ID', required=True, tracking=True)
    client_secret = fields.Char(string='Client Secret', required=True)
    active = fields.Boolean(default=True, tracking=True)
    company_id = fields.Many2one(
        'res.company', string='Company',
        default=lambda self: self.env.company, tracking=True,
    )

    xmr_enabled = fields.Boolean(
        string='Use Real-Time Refresh', default=True,
        help="When enabled, Odoo asks the CMS to push an XMR refresh "
             "to the affected display group(s) after data changes.",
    )

    access_token = fields.Char(readonly=True, copy=False, groups='xibo_connector.group_xibo_manager')
    token_expiry = fields.Datetime(readonly=True, copy=False)

    state = fields.Selection(
        [('draft', 'Draft'), ('connected', 'Connected'), ('error', 'Error')],
        default='draft', tracking=True, readonly=True,
    )
    last_error = fields.Text(readonly=True)
    log_api_calls = fields.Boolean(
        string='Log API Calls', default=True,
        help="Store every API call in the Xibo Event Log for auditing/debugging.",
    )

    display_count = fields.Integer(compute='_compute_counts')
    media_count = fields.Integer(compute='_compute_counts')
    dataset_count = fields.Integer(compute='_compute_counts')
    display_group_count = fields.Integer(compute='_compute_counts')
    layout_count = fields.Integer(compute='_compute_counts')
    broadcast_count = fields.Integer(compute='_compute_counts')

    _sql_constraints = [
        ('url_company_unique', 'unique(url, company_id)',
         'A server with this URL already exists for this company.'),
    ]

    @api.depends()
    def _compute_counts(self):
        for rec in self:
            rec.display_count = self.env['xibo.display'].search_count([('server_id', '=', rec.id)])
            rec.media_count = self.env['xibo.media'].search_count([('server_id', '=', rec.id)])
            rec.dataset_count = self.env['xibo.dataset'].search_count([('server_id', '=', rec.id)])
            rec.display_group_count = self.env['xibo.display.group'].search_count([('server_id', '=', rec.id)])
            rec.layout_count = self.env['xibo.layout'].search_count([('server_id', '=', rec.id)])
            rec.broadcast_count = self.env['xibo.broadcast'].search_count([('server_id', '=', rec.id)])

    @api.constrains('url')
    def _check_url(self):
        for rec in self:
            if not rec.url:
                continue
            if rec.url.endswith('/'):
                raise ValidationError(_("The CMS URL must not end with a slash."))
            if not rec.url.startswith(('http://', 'https://')):
                raise ValidationError(_("The CMS URL must start with http:// or https://"))

    # -------------------------------------------------------------------------
    # OAuth2
    # -------------------------------------------------------------------------
    def _fetch_access_token(self):
        self.ensure_one()
        token_url = f"{self.url}/api/authorize/access_token"
        start = time.time()
        try:
            response = requests.post(
                token_url,
                data={
                    'client_id': self.client_id,
                    'client_secret': self.client_secret,
                    'grant_type': 'client_credentials',
                },
                timeout=DEFAULT_TIMEOUT,
            )
            elapsed_ms = int((time.time() - start) * 1000)
            response.raise_for_status()
            payload = response.json()
        except requests.exceptions.HTTPError as e:
            elapsed_ms = int((time.time() - start) * 1000)
            body = ''
            status = 0
            try:
                status = e.response.status_code if e.response is not None else 0
                body = e.response.text[:500] if e.response is not None else ''
            except Exception:
                pass
            self._log_event('POST', '/api/authorize/access_token', status, False,
                            elapsed_ms, error=f"{e} | {body}")
            self.sudo().write({'state': 'error', 'last_error': str(e)})
            raise UserError(_("Could not authenticate with Xibo CMS:\n%s\n\n%s") % (e, body))
        except requests.exceptions.RequestException as e:
            self._log_event('POST', '/api/authorize/access_token', 0, False,
                            int((time.time() - start) * 1000), error=str(e))
            self.sudo().write({'state': 'error', 'last_error': str(e)})
            raise UserError(_("Could not reach Xibo CMS:\n%s") % e)
        except ValueError:
            raise UserError(_("Xibo returned a non-JSON response. Check the URL."))

        token = payload.get('access_token')
        expires_in = payload.get('expires_in', 3600)
        if not token:
            raise UserError(_("Xibo did not return an access token. Response: %s") % payload)

        self.sudo().write({
            'access_token': token,
            'token_expiry': fields.Datetime.now() + timedelta(seconds=int(expires_in) - 60),
            'state': 'connected',
            'last_error': False,
        })
        self._log_event('POST', '/api/authorize/access_token', response.status_code, True, elapsed_ms,
                        response_body='[token granted]')
        return token

    def _get_access_token(self):
        self.ensure_one()
        if self.access_token and self.token_expiry and self.token_expiry > fields.Datetime.now():
            return self.access_token
        return self._fetch_access_token()

    # -------------------------------------------------------------------------
    # Generic HTTP wrapper — logs ALL errors, including 4xx/5xx, before raising
    # -------------------------------------------------------------------------
    def _request(self, method, endpoint, params=None, data=None, files=None,
                 json_body=None, retry_on_401=True, raise_on_error=True):
        self.ensure_one()
        token = self._get_access_token()
        headers = {'Authorization': f'Bearer {token}'}
        if json_body is not None:
            headers['Content-Type'] = 'application/json'

        url = f"{self.url}{endpoint}"
        start = time.time()
        try:
            response = requests.request(
                method=method.upper(), url=url, headers=headers,
                params=params, data=data, files=files, json=json_body,
                timeout=DEFAULT_TIMEOUT,
            )
        except requests.exceptions.RequestException as e:
            elapsed_ms = int((time.time() - start) * 1000)
            self._log_event(method, endpoint, 0, False, elapsed_ms,
                            request_body=self._summarize_request(params, data, json_body),
                            error=str(e))
            self.sudo().write({'last_error': str(e)})
            if raise_on_error:
                raise UserError(_("Network error talking to Xibo:\n%s") % e)
            return None

        elapsed_ms = int((time.time() - start) * 1000)

        if response.status_code == 401 and retry_on_401:
            _logger.info("Xibo 401, refreshing token and retrying.")
            self._fetch_access_token()
            return self._request(method, endpoint, params, data, files, json_body,
                                 retry_on_401=False, raise_on_error=raise_on_error)

        # Parse body (best-effort)
        payload = None
        if response.content:
            try:
                payload = response.json()
            except ValueError:
                payload = {'raw': response.text[:1000]}

        success = response.ok
        log_body = ''
        if payload is not None:
            try:
                log_body = self._truncate(json.dumps(payload))
            except (TypeError, ValueError):
                log_body = self._truncate(str(payload))

        error_text = None if success else self._extract_error(payload, response)

        # ALWAYS log, success or failure
        self._log_event(method, endpoint, response.status_code, success, elapsed_ms,
                        request_body=self._summarize_request(params, data, json_body),
                        response_body=log_body,
                        error=error_text)

        if not success:
            self.sudo().write({'last_error': f"{response.status_code}: {error_text}"})
            if raise_on_error:
                raise UserError(_("Xibo API error %s:\n%s") % (response.status_code, error_text))
            return None

        if response.status_code == 204 or not response.content:
            return {}
        return payload

    @staticmethod
    def _extract_error(payload, response):
        if isinstance(payload, dict):
            return (payload.get('message')
                    or payload.get('error')
                    or payload.get('raw')
                    or response.text[:500])
        return response.text[:500] if response.text else f"HTTP {response.status_code}"

    @staticmethod
    def _truncate(text):
        if not text:
            return text
        return text[:MAX_LOG_BODY] + ('...' if len(text) > MAX_LOG_BODY else '')

    def _summarize_request(self, params, data, json_body):
        parts = []
        if params:
            parts.append(f"params={json.dumps(params, default=str)}")
        if data:
            safe_data = {}
            if isinstance(data, dict):
                for k, v in data.items():
                    if 'secret' in str(k).lower() or 'password' in str(k).lower():
                        safe_data[k] = '***'
                    else:
                        safe_data[k] = v
                parts.append(f"data={json.dumps(safe_data, default=str)}")
            else:
                parts.append(f"data={str(data)[:300]}")
        if json_body:
            parts.append(f"json={json.dumps(json_body, default=str)}")
        return self._truncate(' | '.join(parts)) if parts else ''

    def _log_event(self, method, endpoint, status, success, duration_ms,
                   request_body=None, response_body=None, error=None):
        if not self.log_api_calls:
            return
        try:
            self.env['xibo.event.log'].sudo().create({
                'server_id': self.id,
                'method': method,
                'endpoint': endpoint,
                'status_code': status,
                'success': success,
                'duration_ms': duration_ms,
                'request_summary': request_body or '',
                'response_summary': response_body or '',
                'error_message': error or '',
            })
        except Exception as e:
            _logger.warning("Could not write Xibo event log: %s", e)

    # -------------------------------------------------------------------------
    # XMR
    # -------------------------------------------------------------------------
    def _trigger_collect_now(self, display_group_ids):
        self.ensure_one()
        if not self.xmr_enabled or not display_group_ids:
            return False
        for dg_id in display_group_ids:
            try:
                self._request('POST', f'/api/displaygroup/{dg_id}/action/collectNow',
                              raise_on_error=False)
            except Exception as e:
                _logger.warning("Xibo collectNow failed for displayGroup %s: %s", dg_id, e)
        return True

    def _trigger_change_layout(self, display_group_ids, layout_id, duration=30, change_mode='queue'):
        self.ensure_one()
        if not display_group_ids:
            return False
        for dg_id in display_group_ids:
            try:
                self._request('POST', f'/api/displaygroup/{dg_id}/action/changeLayout',
                              data={
                                  'layoutId': layout_id, 'duration': duration,
                                  'downloadRequired': 0, 'changeMode': change_mode,
                              },
                              raise_on_error=False)
            except Exception as e:
                _logger.warning("Xibo changeLayout failed for displayGroup %s: %s", dg_id, e)
        return True

    # -------------------------------------------------------------------------
    # UI actions
    # -------------------------------------------------------------------------
    def action_test_connection(self):
        self.ensure_one()
        self._fetch_access_token()
        self._request('GET', '/api/about')
        return _reload_action({
            'title': _("Connection successful"),
            'message': _("Authenticated with %s") % self.url,
        })

    def action_sync_all(self):
        for rec in self:
            rec.env['xibo.display.group']._sync_from_server(rec)
            rec.env['xibo.display']._sync_from_server(rec)
            rec.env['xibo.layout']._sync_from_server(rec)
            rec.env['xibo.dataset']._sync_from_server(rec)
            rec.env['xibo.media']._sync_from_server(rec)
        return _reload_action({
            'title': _("Sync complete"),
            'message': _("Displays, groups, layouts, datasets and media metadata refreshed."),
        })

    def action_open_in_cms(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': self.url,
            'target': 'new',
        }

    def action_open_displays(self):
        self.ensure_one()
        return self._open_window('xibo.display', _('Displays'), 'list,form')

    def action_open_display_groups(self):
        self.ensure_one()
        return self._open_window('xibo.display.group', _('Display Groups'), 'list,form')

    def action_open_media(self):
        self.ensure_one()
        return self._open_window('xibo.media', _('Media'), 'kanban,list,form')

    def action_open_layouts(self):
        self.ensure_one()
        return self._open_window('xibo.layout', _('Layouts'), 'list,form')

    def action_open_datasets(self):
        self.ensure_one()
        return self._open_window('xibo.dataset', _('DataSets'), 'list,form')

    def action_open_broadcasts(self):
        self.ensure_one()
        return self._open_window('xibo.broadcast', _('Broadcasts'), 'list,form')

    def action_open_event_log(self):
        self.ensure_one()
        return self._open_window('xibo.event.log', _('Event Log'), 'list,form')

    def _open_window(self, model, name, view_mode):
        return {
            'type': 'ir.actions.act_window',
            'name': name,
            'res_model': model,
            'view_mode': view_mode,
            'domain': [('server_id', '=', self.id)],
            'context': {'default_server_id': self.id},
        }

    # =========================================================================
    # XMR helpers (Xibo Message Relay) — instant layout changes on displays
    # =========================================================================
    def change_layout(self, display_group_xibo_id, layout_xibo_id=None, duration=0, change_mode='replace', campaign_xibo_id=None):
        """Send a `changeLayout` action via XMR to a display group.

        :param display_group_xibo_id: the Xibo *displayGroupId* (not Odoo id)
        :param layout_xibo_id: the Xibo *layoutId* (changes on publish! use campaign_xibo_id when possible)
        :param duration: seconds to keep the layout; 0 = use layout's natural duration
        :param change_mode: 'replace' (interrupt) or 'queue' (after current)
        :param campaign_xibo_id: the Xibo *campaignId* (stable across publishes - PREFERRED)
        :returns: response dict from Xibo, or False on failure
        """
        self.ensure_one()
        try:
            payload = {
                'changeMode': change_mode,
            }
            # Prefer campaignId because it doesn't change on publish/unpublish.
            if campaign_xibo_id:
                payload['campaignId'] = campaign_xibo_id
            elif layout_xibo_id:
                payload['layoutId'] = layout_xibo_id
            else:
                return False
            if duration:
                payload['duration'] = int(duration)
            return self._request(
                'POST',
                f'/api/displaygroup/{display_group_xibo_id}/action/changeLayout',
                data=payload,
                raise_on_error=False,
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                "Xibo changeLayout failed (dg=%s, layout=%s): %s",
                display_group_xibo_id, layout_xibo_id, e
            )
            return False

    def revert_layout(self, display_group_xibo_id):
        """Send a `revertToSchedule` action via XMR — return the display group
        to its normal schedule. (Xibo 3.x+ renamed `revertLayout` to
        `revertToSchedule`.)
        """
        self.ensure_one()
        try:
            return self._request(
                'POST',
                f'/api/displaygroup/{display_group_xibo_id}/action/revertToSchedule',
                raise_on_error=False,
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                "Xibo revertToSchedule failed (dg=%s): %s",
                display_group_xibo_id, e
            )
            return False

    # =========================================================================
    # DataSet helpers — direct API access for child modules that need to push
    # rows without going through the Broadcast scheduler.
    # =========================================================================
    def _dataset_insert_row(self, dataset_xibo_id, row_data):
        """POST /api/dataset/data/{datasetId} — insert a single row.

        :param dataset_xibo_id: the Xibo *dataSetId* (integer, NOT the Odoo id)
        :param row_data: dict mapping column **heading** -> value.
                         Headings are case-sensitive and must match the
                         columns synced from Xibo. Unknown headings are
                         silently dropped with a warning in the log.
        :returns: response dict from Xibo (contains the new row ``id``) on
                  success, or ``False`` on failure. The call is logged via
                  the standard ``_log_event`` audit trail.

        Internally translates ``{heading: value}`` into Xibo's expected
        ``{dataSetColumnId_X: value}`` form using the synced ``xibo.dataset.column``
        metadata. Falls back to a column-resync if no columns are cached
        for the dataset yet.
        """
        self.ensure_one()
        if not dataset_xibo_id:
            _logger.warning("[XIBO] _dataset_insert_row called with no dataset_xibo_id")
            return False
        if not isinstance(row_data, dict) or not row_data:
            _logger.warning("[XIBO] _dataset_insert_row: row_data must be a non-empty dict")
            return False

        Dataset = self.env['xibo.dataset'].sudo()
        dataset = Dataset.search(
            [('server_id', '=', self.id),
             ('xibo_dataset_id', '=', int(dataset_xibo_id))],
            limit=1,
        )
        if not dataset:
            _logger.warning(
                "[XIBO] _dataset_insert_row: no xibo.dataset cached for server=%s dataset_xibo_id=%s",
                self.name, dataset_xibo_id,
            )
            return False

        # Lazily sync columns the first time.
        if not dataset.column_ids:
            try:
                self.env['xibo.dataset.column']._sync_columns(dataset)
            except Exception as e:
                _logger.warning("[XIBO] Could not sync columns for dataset %s: %s",
                                dataset.name, e)

        # Map heading (case-insensitive) AND code -> xibo_dataset_column_id.
        col_by_heading = {}
        col_by_code = {}
        for col in dataset.column_ids:
            if col.heading:
                col_by_heading[col.heading.strip().lower()] = col.xibo_dataset_column_id
            if col.code:
                col_by_code[col.code.strip().lower()] = col.xibo_dataset_column_id

        body = {}
        unknown = []
        for key, value in row_data.items():
            key_norm = (key or '').strip().lower()
            xcol_id = col_by_heading.get(key_norm) or col_by_code.get(key_norm)
            if not xcol_id:
                unknown.append(key)
                continue
            body[f"dataSetColumnId_{xcol_id}"] = value

        if unknown:
            _logger.warning(
                "[XIBO] _dataset_insert_row: dataset '%s' has no columns named %s — skipped",
                dataset.name, unknown,
            )
        if not body:
            _logger.warning(
                "[XIBO] _dataset_insert_row: nothing to insert into dataset '%s' (row_data=%s)",
                dataset.name, list(row_data.keys()),
            )
            return False

        return self._request(
            'POST',
            f'/api/dataset/data/{dataset_xibo_id}',
            data=body,
            raise_on_error=False,
        )
