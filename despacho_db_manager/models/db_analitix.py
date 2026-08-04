# -*- coding: utf-8 -*-
"""Conciliación de Analitix: sucursales que miden contra sucursales que pagan.

El addon `analitix` no bloquea la ingesta a propósito — una tienda que ya está
midiendo sigue midiendo pase lo que pase con la factura, porque dejar ciega la
tienda de un cliente por un tropiezo de cobro nuestro es peor negocio que el
hueco que eso deja. Lo único que exige código de activación es dar de alta una
sucursal NUEVA.

Ese diseño protege al cliente, así que el control de nuestro lado es **verlo**:
el censo trae, por cada BD, qué tiendas existen, cuáles siguen recibiendo
eventos y en qué estado de cobro están. La desviación se calcula aquí y se
avisa; nadie apaga nada a distancia.
"""
from odoo import api, fields, models


class DespachoDbAnalitixStore(models.Model):
    """Una sucursal de Analitix vista desde el despacho. Solo lectura: la llena
    el censo, y la fuente de verdad es la BD del cliente."""
    _name = 'despacho.db.analitix.store'
    _description = 'Sucursal Analitix de una BD'
    _order = 'measuring desc, code'

    project_id = fields.Many2one('project.project', string='Base de datos',
                                 required=True, ondelete='cascade', index=True)
    code = fields.Char('Código', required=True)
    name = fields.Char('Sucursal')
    plan = fields.Selection([
        ('counting', 'Conteo'),
        ('visual', 'Analíticos visuales'),
        ('actions', 'Acciones'),
    ], string='Plan')
    billing = fields.Selection([
        ('trial', 'Prueba'),
        ('active', 'Activa'),
        ('paused', 'Pausada'),
        ('cancelled', 'Cancelada'),
    ], string='Cobro')
    activated = fields.Boolean(
        'Activada', help='Recibió código de activación (o fue la primera de su '
        'base, que se activa sola).')
    monthly_fee = fields.Float('Cuota mensual', aggregator='sum')
    events_7d = fields.Integer(
        'Eventos 7 días', aggregator='sum',
        help='Cruces recibidos en la última semana. Es la prueba de que la '
             'sucursal está midiendo de verdad y no solo existe como registro.')
    measuring = fields.Boolean(
        'Midiendo', compute='_compute_measuring', store=True,
        help='Recibió eventos en la última semana.')
    drifting = fields.Boolean(
        'Sin cobro', compute='_compute_measuring', store=True,
        help='Está midiendo pero su cobro no está activo. Es la fila que hay '
             'que ir a conversar, no a apagar.')

    @api.depends('events_7d', 'billing')
    def _compute_measuring(self):
        for rec in self:
            rec.measuring = rec.events_7d > 0
            rec.drifting = rec.measuring and rec.billing != 'active'
