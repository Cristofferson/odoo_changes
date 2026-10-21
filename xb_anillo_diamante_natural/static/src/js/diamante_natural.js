/* Ficha del anillo: al elegir «Diamante natural», el cliente escoge uno de los diamantes
 * naturales publicados. El anillo no se puede agregar al carrito sin diamante; el servidor
 * agrega el diamante ligado al anillo (ver sale_order._cart_add). */
(function () {
    "use strict";

    var NATURAL = "Diamante natural";
    var POR_PAGINA = 12;
    var RANGOS = [
        { id: "", nombre: "Todos" },
        { id: "0-0.3", nombre: "Hasta 0.29 ct", min: 0, max: 0.3 },
        { id: "0.3-0.5", nombre: "0.30 a 0.49 ct", min: 0.3, max: 0.5 },
        { id: "0.5-1", nombre: "0.50 a 0.99 ct", min: 0.5, max: 1 },
        { id: "1-2", nombre: "1.00 a 1.99 ct", min: 1, max: 2 },
        { id: "2-", nombre: "2.00 ct o más", min: 2, max: 1e9 },
    ];
    var ORDENES = [
        { id: "precio", nombre: "Precio: de menor a mayor" },
        { id: "-precio", nombre: "Precio: de mayor a menor" },
        { id: "-quilates", nombre: "Quilates: de mayor a menor" },
    ];

    function rpc(url, params) {
        return fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ jsonrpc: "2.0", method: "call", params: params || {} }),
        }).then(function (r) { return r.json(); }).then(function (d) {
            if (d.error) { throw d.error; }
            return d.result;
        });
    }

    function el(tag, cls, text) {
        var e = document.createElement(tag);
        if (cls) { e.className = cls; }
        if (text !== undefined) { e.textContent = text; }
        return e;
    }

    function dinero(n, simbolo) {
        return simbolo + " " + Number(n || 0).toLocaleString("es-MX", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    function numero(texto) {
        var limpio = (texto || "").replace(/[^\d.]/g, "");
        return parseFloat(limpio) || 0;
    }

    function init() {
        var input = document.querySelector('.js_add_cart_variants input[data-value-name="' + NATURAL + '"]');
        if (!input) { return; }
        var form = input.closest("form");
        var lista = input.closest("ul.js_add_cart_variants");
        var tmplInput = form && form.querySelector('input[name="product_template_id"]');
        if (!form || !lista || !tmplInput) { return; }
        var tmplId = parseInt(tmplInput.value, 10);
        var detalles = form.closest("#product_details") || document;
        var precioEl = detalles.querySelector(".product_price .oe_price, .oe_price");

        var estado = { datos: null, cargando: false, error: false, elegido: null, forma: "", rango: "", orden: "precio", mostrar: POR_PAGINA };

        // --- armado del panel ---
        var panel = el("section", "xbdn");
        panel.hidden = true;
        panel.setAttribute("aria-label", "Elige tu diamante natural");
        var cab = el("div", "xbdn-cab");
        cab.appendChild(el("h3", "xbdn-titulo", "Elige tu diamante natural"));
        cab.appendChild(el("p", "xbdn-sub", "Todos son piezas únicas con certificado. El precio de tu anillo es la montadura más el diamante que elijas."));
        panel.appendChild(cab);
        var resumen = el("div", "xbdn-resumen");
        panel.appendChild(resumen);
        var filtros = el("div", "xbdn-filtros");
        panel.appendChild(filtros);
        var cuenta = el("p", "xbdn-cuenta");
        panel.appendChild(cuenta);
        var rejilla = el("div", "xbdn-rejilla");
        panel.appendChild(rejilla);
        var mas = el("button", "xbdn-mas", "Ver más diamantes");
        mas.type = "button";
        mas.hidden = true;
        mas.addEventListener("click", function () { estado.mostrar += POR_PAGINA; pintarLista(); });
        panel.appendChild(mas);
        lista.insertAdjacentElement("afterend", panel);

        // Bajo el precio principal: qué incluye.
        var nota = el("div", "xbdn-nota");
        nota.hidden = true;
        if (precioEl) {
            var bloquePrecio = precioEl.closest(".product_price") || precioEl.parentElement;
            bloquePrecio.insertAdjacentElement("afterend", nota);
        }

        function esNatural() { return input.checked; }
        function montadura() { return precioEl ? numero(precioEl.textContent) : 0; }
        function simbolo() { return (estado.datos && estado.datos.moneda) || "$"; }

        function chips(titulo, opciones, actual, alElegir) {
            var grupo = el("div", "xbdn-grupo");
            grupo.appendChild(el("span", "xbdn-etq", titulo));
            var fila = el("div", "xbdn-chips");
            opciones.forEach(function (o) {
                var b = el("button", "xbdn-chip", o.nombre);
                b.type = "button";
                b.setAttribute("aria-pressed", o.id === actual ? "true" : "false");
                b.addEventListener("click", function () { alElegir(o.id); });
                fila.appendChild(b);
            });
            grupo.appendChild(fila);
            return grupo;
        }

        function pintarFiltros() {
            filtros.textContent = "";
            if (!estado.datos) { return; }
            var formas = [{ id: "", nombre: "Todas" }].concat(estado.datos.formas.map(function (f) { return { id: f, nombre: f }; }));
            filtros.appendChild(chips("Forma", formas, estado.forma, function (v) { estado.forma = v; estado.mostrar = POR_PAGINA; pintar(); }));
            filtros.appendChild(chips("Quilates", RANGOS, estado.rango, function (v) { estado.rango = v; estado.mostrar = POR_PAGINA; pintar(); }));
            var grupo = el("div", "xbdn-grupo");
            var etq = el("label", "xbdn-etq", "Ordenar");
            etq.setAttribute("for", "xbdn-orden");
            grupo.appendChild(etq);
            var sel = el("select", "xbdn-orden");
            sel.id = "xbdn-orden";
            ORDENES.forEach(function (o) {
                var op = el("option", "", o.nombre);
                op.value = o.id;
                op.selected = o.id === estado.orden;
                sel.appendChild(op);
            });
            sel.addEventListener("change", function () { estado.orden = sel.value; pintarLista(); });
            grupo.appendChild(sel);
            filtros.appendChild(grupo);
        }

        function filtrados() {
            var rango = RANGOS.filter(function (r) { return r.id === estado.rango; })[0];
            var res = estado.datos.diamantes.filter(function (d) {
                return (!estado.forma || d.forma === estado.forma)
                    && (!rango || !rango.id || (d.quilates >= rango.min && d.quilates < rango.max));
            });
            var campo = estado.orden.replace("-", "");
            var signo = estado.orden.charAt(0) === "-" ? -1 : 1;
            return res.slice().sort(function (a, b) { return signo * (a[campo] - b[campo]); });
        }

        function tarjeta(d) {
            var b = el("button", "xbdn-diamante");
            b.type = "button";
            b.setAttribute("aria-pressed", estado.elegido && estado.elegido.id === d.id ? "true" : "false");
            var img = el("img", "xbdn-img");
            img.src = d.imagen;
            img.alt = d.nombre;
            img.loading = "lazy";
            b.appendChild(img);
            var cuerpo = el("span", "xbdn-cuerpo");
            cuerpo.appendChild(el("span", "xbdn-forma", [d.forma, d.quilates ? d.quilates.toFixed(2) + " ct" : ""].filter(Boolean).join(" · ")));
            var specs = [d.color && "Color " + d.color, d.pureza && "Pureza " + d.pureza, d.corte && "Corte " + d.corte].filter(Boolean).join(" · ");
            if (specs) { cuerpo.appendChild(el("span", "xbdn-specs", specs)); }
            if (d.certificado) { cuerpo.appendChild(el("span", "xbdn-cert", "Certificado " + d.certificado)); }
            cuerpo.appendChild(el("span", "xbdn-precio", dinero(d.precio, simbolo())));
            b.appendChild(cuerpo);
            var sello = el("span", "xbdn-sello", "Elegido");
            b.appendChild(sello);
            b.addEventListener("click", function () { elegir(d); });
            return b;
        }

        function pintarLista() {
            rejilla.textContent = "";
            if (!estado.datos) {
                cuenta.textContent = estado.error ? "No pudimos cargar los diamantes. Recarga la página para intentarlo de nuevo." : "Cargando diamantes…";
                mas.hidden = true;
                return;
            }
            var res = filtrados();
            cuenta.textContent = res.length === 1 ? "1 diamante" : res.length + " diamantes";
            if (!res.length) {
                rejilla.appendChild(el("p", "xbdn-vacio", "No hay diamantes con estos filtros. Prueba con otra forma o con otros quilates."));
            }
            res.slice(0, estado.mostrar).forEach(function (d) { rejilla.appendChild(tarjeta(d)); });
            mas.hidden = res.length <= estado.mostrar;
        }

        function pintarResumen() {
            var m = montadura();
            resumen.textContent = "";
            nota.textContent = "";
            if (!estado.elegido) {
                resumen.className = "xbdn-resumen xbdn-pendiente";
                resumen.appendChild(el("p", "", "Elige un diamante para poder agregar el anillo al carrito."));
                nota.appendChild(el("span", "", "Precio de la montadura. Se suma el diamante natural que elijas abajo."));
                return;
            }
            var d = estado.elegido;
            resumen.className = "xbdn-resumen";
            var filas = [
                ["Montadura", dinero(m, simbolo())],
                ["Diamante " + [d.forma, d.quilates ? d.quilates.toFixed(2) + " ct" : ""].filter(Boolean).join(" "), dinero(d.precio, simbolo())],
            ];
            filas.forEach(function (f) {
                var fila = el("div", "xbdn-fila");
                fila.appendChild(el("span", "", f[0]));
                fila.appendChild(el("span", "", f[1]));
                resumen.appendChild(fila);
            });
            var total = el("div", "xbdn-fila xbdn-total");
            total.appendChild(el("span", "", "Total de tu anillo"));
            total.appendChild(el("span", "", dinero(m + d.precio, simbolo())));
            resumen.appendChild(total);
            var ver = el("a", "xbdn-ver", "Ver todos los datos del diamante");
            ver.href = d.url;
            ver.target = "_blank";
            ver.rel = "noopener";
            resumen.appendChild(ver);
            nota.appendChild(el("span", "", "Precio de la montadura. Con tu diamante: "));
            nota.appendChild(el("b", "", dinero(m + d.precio, simbolo())));
        }

        function pintar() {
            panel.hidden = !esNatural();
            nota.hidden = !esNatural();
            if (!esNatural()) { return; }
            pintarFiltros();
            pintarLista();
            pintarResumen();
        }

        function cargar() {
            if (estado.datos || estado.cargando) { return; }
            estado.cargando = true;
            rpc("/xb_diamante_natural/lista").then(function (res) {
                estado.datos = res;
                estado.cargando = false;
                pintar();
            }).catch(function () {
                estado.cargando = false;
                estado.error = true;
                pintar();
            });
        }

        function elegir(d) {
            estado.elegido = d;
            panel.classList.remove("xbdn-aviso");
            pintarLista();
            pintarResumen();
            rpc("/xb_diamante_natural/elegir", { product_template_id: tmplId, product_id: d.id }).then(function (r) {
                if (!r.ok) {
                    // Ya no se puede vender (se vendió o se despublicó): se quita de la lista.
                    estado.elegido = null;
                    estado.datos.diamantes = estado.datos.diamantes.filter(function (x) { return x.id !== d.id; });
                    pintar();
                }
            });
        }

        function sincronizar() {
            if (esNatural()) { cargar(); }
            pintar();
        }

        form.addEventListener("change", function () { setTimeout(sincronizar, 0); });
        // La montadura cambia con el metal y la medida: el total se recalcula con el precio nuevo.
        if (precioEl) {
            new MutationObserver(function () { if (esNatural()) { pintarResumen(); } }).observe(precioEl, { childList: true, characterData: true, subtree: true });
        }

        // Sin diamante elegido no se agrega al carrito: se lleva al cliente a la lista.
        document.addEventListener("click", function (ev) {
            var boton = ev.target.closest && ev.target.closest("#add_to_cart, .o_we_buy_now, .js_check_product");
            if (!boton || !form.contains(boton) || !esNatural() || estado.elegido) { return; }
            ev.preventDefault();
            ev.stopImmediatePropagation();
            panel.classList.add("xbdn-aviso");
            panel.scrollIntoView({ behavior: "smooth", block: "start" });
        }, true);

        sincronizar();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
