{
    'name': 'XB Joyería · peso y precio por combinación',
    'summary': 'Proyecta el peso y el metal fino de cada combinación de una '
               'joya, y cobra en proporción en vez de sumando',
    'description': """
El precio de una joya no se suma, se multiplica
===============================================

Odoo suma los recargos de los atributos. Si el oro de 18 Kt vale +$5,000 y el
ancho de 4 mm vale +$3,500, una pieza de 18 Kt y 4 mm cobra ambos. Pero en
joyería los factores se multiplican: el ancho doble lleva el doble de oro, y
ese oro doble vale más si es de 18 quilates. Sumando se queda corto hasta un
29% en las combinaciones extremas, y siempre por debajo.

Este módulo hace dos cosas:

* **Proyecta el peso** y los gramos de metal fino de cualquier combinación, a
  partir de una pieza de referencia, la densidad y la ley de cada metal, el
  ancho en milímetros y la circunferencia de la talla. Sirve para responderle
  al cliente cuánto va a pesar su pieza antes de fabricarla.
* **Multiplica en vez de sumar** los recargos de atributo, de modo que el
  precio de cada combinación sea el valor real de su metal al día.

No guarda datos nuevos: los pesos son calculados y el precio se expresa con el
mismo campo de recargo que Odoo ya usa, así que la tienda web, el punto de
venta y los reportes lo leen sin cambio alguno.

Requiere que los valores del atributo Metal tengan capturadas su **ley** y su
**densidad**, y que la plantilla tenga el peso de la pieza de referencia.
""",
    'version': '19.0.1.3.0',
    'category': 'Sales/Sales',
    'author': 'XUBAX',
    'license': 'LGPL-3',
    'depends': ['product'],
    'data': ['views/product_views.xml'],
    'installable': True,
    'application': False,
}
