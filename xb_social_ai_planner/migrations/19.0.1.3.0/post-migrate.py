# -*- coding: utf-8 -*-
"""1.2.0 -> 1.3.0: image backends became explicit.

Until 1.2.0 the only way to make an image was the vector/SVG route, and the
`image_provider_type` field sat unused at its 'none' default. 1.3.0 turns that
field into the real selector, where 'none' now means *disabled*. Move existing
providers to 'svg' so image generation keeps working exactly as before.
"""


def migrate(cr, version):
    cr.execute("""
        UPDATE xb_social_ai_provider
           SET image_provider_type = 'svg'
         WHERE image_provider_type IS NULL
            OR image_provider_type = 'none'
    """)
