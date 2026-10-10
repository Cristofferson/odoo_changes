# -*- coding: utf-8 -*-
"""1.5.0: «Arras 3888» deja de ser casilla del producto y pasa a decidirse por la categoría.
Antes de cargar el módulo se marca la categoría de las arras que ya existen, para que el
campo calculado les dé lo mismo que tenían."""


def migrate(cr, version):
    cr.execute("ALTER TABLE product_category ADD COLUMN IF NOT EXISTS xb_arras_categoria boolean")
    cr.execute("""
        UPDATE product_category SET xb_arras_categoria = true
         WHERE id IN (SELECT DISTINCT categ_id FROM product_template WHERE xb_arras AND categ_id IS NOT NULL)
    """)
