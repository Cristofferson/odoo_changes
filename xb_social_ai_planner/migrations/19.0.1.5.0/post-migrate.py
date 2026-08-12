# -*- coding: utf-8 -*-
"""Recompute the plan state, now that it is derived from the posts.

``state`` used to be a plain stored field written by hand at each step. Turning
it into a stored computed field does not touch rows that already have a value,
so every existing plan would keep whatever it was left at — including the ones
this change exists to fix: a plan stuck in *Generating* after its posts were
pushed from the list. Force the recomputation once.
"""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Plan = env["xb.social.content.plan"]
    plans = Plan.search([])
    if not plans:
        return
    env.add_to_compute(Plan._fields["state"], plans)
    env.flush_all()
