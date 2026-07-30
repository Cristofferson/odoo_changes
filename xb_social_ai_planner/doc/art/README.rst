Artwork sources
===============

The published assets live in ``static/description/`` (``icon.png`` 256×256 RGBA,
``banner.png`` 1200×300). These are their sources.

Both follow the **Odoo 19 native icon typology**, which the previous artwork did
not: flat, no gradients, no shadow, transparent background, no rounded-square
container, two or three large shapes that overlap with the intersection taking a
third darker colour, filling the canvas nearly edge to edge. The palette is the
native one, sampled from the ``social``, ``crm``, ``planning`` and
``marketing_automation`` icons:

===========  =========================================
``#1AD3BB``  turquoise — the speech bubble
``#005E7A``  deep teal — the overlap, and the wordmark
``#985184``  plum — the spark
``#FBB945``  amber
``#F86126``  coral
===========  =========================================

icon.svg
--------
A speech bubble (social) crossed by a four-point spark (AI). The spark breaks
the silhouette at the top-right corner on purpose: that is what keeps the icon
readable at 64 px and what gives the overlap somewhere to show.

Rasterise at 1024 and downscale — rendering straight to 256 leaves the edges
dirty::

    /odoo/odoo-server/env/bin/python3 -c "
    import cairosvg; from PIL import Image
    cairosvg.svg2png(url='icon.svg', write_to='icon_master.png',
                     output_width=1024, output_height=1024)
    Image.open('icon_master.png').resize((256, 256), Image.LANCZOS).save(
        '../../static/description/icon.png')"

banner.html
-----------
Text-heavy, so it is HTML rendered by Chromium rather than SVG: the type stays
vectorially sharp and editing a word is editing HTML. Montserrat is loaded by
``file://`` from ``theme_xubax``, which is why the renderer needs
``--allow-file-access-from-files``. It embeds ``icon_master.png``::

    NODE_PATH=~/.npm/_npx/e41f203b7505f1fb/node_modules \
    CHROME_PATH=~/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome \
    node render_banner.js
    # then downscale banner_2x.png to 1200×300 with PIL/LANCZOS
