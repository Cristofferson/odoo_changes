/* Arras 3888 · ficha configuradora. Se monta encima de los controles nativos de website_sale:
   los radios reales siguen en el formulario (ocultos) y cada elección hace input.click(), así
   Odoo calcula variante, precio y carrito como siempre. El texto del grabado se escribe en el
   campo nativo de valor personalizado. */
(function () {
    "use strict";
    var TINT = {
        s: "grayscale(1) brightness(1.18) contrast(1.05)", g: "none", g10: "saturate(.8) brightness(1.04)",
        g22: "saturate(1.25) hue-rotate(-4deg)", g24: "saturate(1.45) hue-rotate(-7deg) brightness(.98)",
    };
    var CAMPO = { v: "Valor", n: "Nombres", i: "Iniciales", d: "Fecha de la boda" };

    function esc(s) {
        return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
            return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
        });
    }

    function init() {
        var flow = document.querySelector(".xba-flow");
        var stage = document.querySelector(".xba-stage");
        if (!flow || !stage || flow.dataset.ready) return;
        flow.dataset.ready = "1";
        var D = JSON.parse(flow.dataset.xba);
        var form = flow.closest("form");
        var page = document.getElementById("product_detail");
        if (page) page.classList.add("xba-page");
        // «Ficha de la pieza» (peso del juego) sobra: el resumen ya dice los gramos por arra.
        form.querySelectorAll(".o_wsale_product_details_content_section").forEach(function (s) {
            var h = s.querySelector("h1,h2,h3,h4,h5,h6,b,strong");
            if (h && /ficha de la pieza/i.test(h.textContent)) s.classList.add("xba-oculto");
        });
        var g = { n1: "", n2: "", i1: "", i2: "", d: "" };
        var aviso = "";

        function radios(attr) {
            return Array.prototype.slice.call(form.querySelectorAll('input.js_variant_change[data-attribute-name="' + attr + '"]'));
        }
        function actual(attr) {
            var r = radios(attr).filter(function (i) { return i.checked; })[0];
            return r ? parseInt(r.value, 10) : null;
        }
        function elegir(attr, id) {
            var r = radios(attr).filter(function (i) { return parseInt(i.value, 10) === id; })[0];
            if (r && !r.checked) r.click();
            setTimeout(pintar, 0);
        }
        function dinero(v) {
            if (v == null) return "por confirmar";
            return D.moneda + Number(v).toLocaleString("es-MX", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        }
        function metalPorId(id) {
            var r = null;
            D.metales.forEach(function (G) { G.o.forEach(function (o) { if (o.id === id) r = o; }); });
            return r || { n: "", t: "g" };
        }
        function vueltaPorId(id) { return D.vueltas.filter(function (v) { return v.id === id; })[0] || D.vueltas[0]; }
        function tamPorId(id) { return D.tamanos.filter(function (t) { return t.id === id; })[0] || D.tamanos[0]; }
        function textoGrabado(v) {
            var p = [];
            if (v.f.indexOf("v") !== -1) p.push("un valor distinto en cada arra");
            if (v.f.indexOf("n") !== -1 && (g.n1 || g.n2)) p.push((g.n1 || "…") + " & " + (g.n2 || "…"));
            if (v.f.indexOf("i") !== -1 && (g.i1 || g.i2)) p.push((g.i1 || "…") + " & " + (g.i2 || "…"));
            if (v.f.indexOf("d") !== -1 && g.d) p.push(g.d.split("-").reverse().join("-"));
            return p.join(" · ");
        }
        function faltantes(v) {
            var f = [];
            if (v.f.indexOf("n") !== -1 && (!g.n1.trim() || !g.n2.trim())) f.push("los dos nombres");
            if (v.f.indexOf("i") !== -1 && (!g.i1.trim() || !g.i2.trim())) f.push("las dos iniciales");
            if (v.f.indexOf("d") !== -1 && !g.d) f.push("la fecha de la boda");
            return f;
        }
        function escribirNativo(v) {
            var inp = form.querySelector(".variant_custom_value");
            if (!inp) return;
            var t = textoGrabado(v);
            if (inp.value !== t) {
                inp.value = t;
                inp.dispatchEvent(new Event("input", { bubbles: true }));
                inp.dispatchEvent(new Event("change", { bubbles: true }));
            }
        }

        function pintar() {
            var mId = actual("Metal"), tId = actual("Tamaño de arra"), vId = actual("Vuelta");
            var m = metalPorId(mId), t = tamPorId(tId), v = vueltaPorId(vId);
            var pr = D.precios[mId + "-" + tId] || {};
            var tint = TINT[m.t] || "none";
            var px = Math.round(parseFloat(t.cm || "2.5") / 2.5 * 190);
            var conValores = v.f.indexOf("v") !== -1 || D.valores_frente;
            var grab = textoGrabado(v);
            escribirNativo(v);

            // ---------- escenario ----------
            var ring = "";
            if (conValores) {
                ring = '<div class="xba-ring" aria-label="Los 13 valores">' + D.valores.map(function (x, i) {
                    var a = i === 12 ? null : (i / 12) * 2 * Math.PI - Math.PI / 2;
                    var X = a === null ? 50 : 50 + 40 * Math.cos(a), Y = a === null ? 50 : 50 + 40 * Math.sin(a);
                    return '<span style="left:' + X + "%;top:" + Y + '%"><small>' + (i + 1) + "</small>" + esc(x[0]) + "</span>";
                }).join("") + "</div>";
            }
            stage.innerHTML =
                '<div class="xba-pair">' +
                '<figure><div class="xba-disc"><img src="' + D.frente_img + '" alt="Frente ' + esc(D.nombre) + '" style="width:' + px + "px;filter:" + tint + ' drop-shadow(0 12px 12px rgba(0,0,0,.2))"></div><figcaption>Frente · ' + esc(D.nombre) + "</figcaption></figure>" +
                '<figure><div class="xba-disc"><img class="xba-rev" src="' + v.img + '" alt="Vuelta ' + esc(v.n) + '" style="width:' + Math.round(px * 0.92) + "px;filter:" + tint + ' drop-shadow(0 12px 12px rgba(0,0,0,.2))"></div><figcaption>Vuelta · ' + esc(v.n) + "</figcaption></figure>" +
                "</div>" +
                '<div class="xba-scale"><i style="width:' + px + 'px"></i><span>' + esc(t.cm) + " cm · " + esc(t.c) + "</span></div>" +
                (grab ? '<p class="xba-engr">Grabado: <b>' + esc(grab) + "</b></p>" : "") + ring +
                (D.fotos.length ? '<div class="xba-mini">' + D.fotos.map(function (f) { return '<div style="background-image:url(' + f + ')"></div>'; }).join("") + "</div>" : "");

            // ---------- pasos ----------
            var campos = [];
            if (v.f.indexOf("n") !== -1) campos.push('<label class="xba-fld"><span>Nombre</span><input data-g="n1" maxlength="14" value="' + esc(g.n1) + '" placeholder="Rosy"></label><label class="xba-fld"><span>Nombre</span><input data-g="n2" maxlength="14" value="' + esc(g.n2) + '" placeholder="Marco"></label>');
            if (v.f.indexOf("i") !== -1) campos.push('<label class="xba-fld s"><span>Inicial</span><input data-g="i1" maxlength="1" value="' + esc(g.i1) + '" placeholder="R"></label><label class="xba-fld s"><span>Inicial</span><input data-g="i2" maxlength="1" value="' + esc(g.i2) + '" placeholder="M"></label>');
            if (v.f.indexOf("d") !== -1) campos.push('<label class="xba-fld"><span>Fecha de la boda</span><input data-g="d" type="date" value="' + esc(g.d) + '"></label>');
            var valores = conValores ? '<div class="xba-v13"><div class="xba-v13h"><b>Los 13 valores</b><span>Cada arra lleva uno de estos valores' + (D.valores_frente && v.f.indexOf("v") === -1 ? " en el frente" : "") + '; son siempre los mismos 13.</span></div><ol>' + D.valores.map(function (x) { return "<li><b>" + esc(x[0]) + "</b><small>" + esc(x[1]) + "</small></li>"; }).join("") + "</ol></div>" : "";

            flow.innerHTML =
                '<p class="xba-top"><b>' + dinero(pr.p) + '</b><small>juego de 13 arras · IVA incluido</small></p>' +
                '<div class="xba-stp"><div class="xba-sh"><b>1</b><div><h3>Frente</h3><p>' + esc(D.nombre) + "</p></div></div>" +
                '<div class="xba-strip">' + D.frentes.map(function (f) {
                    return '<a class="xba-th" href="' + f.url + '" title="' + esc(f.n) + '" aria-current="' + (f.id === D.tmpl) + '"><img src="' + f.img + '" alt="' + esc(f.n) + '" loading="lazy"></a>';
                }).join("") + "</div></div>" +

                '<div class="xba-stp"><div class="xba-sh"><b>2</b><div><h3>¿Qué grabamos en la vuelta?</h3><p>' + esc(v.n) + "</p></div></div>" +
                '<div class="xba-rcards">' + D.vueltas.map(function (x) {
                    return '<button type="button" class="xba-rc" data-v="' + x.id + '" aria-pressed="' + (x.id === v.id) + '"><img src="' + x.img + '" alt="">' + esc(x.n) + "</button>";
                }).join("") + "</div>" +
                (campos.length ? '<div class="xba-flds">' + campos.join("") + "</div>" : "") + valores +
                (aviso ? '<p class="xba-aviso" role="alert">' + esc(aviso) + "</p>" : "") + "</div>" +

                '<div class="xba-stp"><div class="xba-sh"><b>3</b><div><h3>Tamaño de cada arra</h3><p>' + esc(t.cm) + " cm</p></div></div>" +
                '<div class="xba-szs">' + D.tamanos.map(function (x) {
                    var d = Math.round(parseFloat(x.cm) * 16);
                    return '<button type="button" class="xba-sz" data-t="' + x.id + '" aria-pressed="' + (x.id === t.id) + '"><span class="c"><i style="width:' + d + "px;height:" + d + 'px"></i></span><b>' + esc(x.cm) + " cm · " + esc(x.l) + "</b><small>" + esc(x.c) + "</small></button>";
                }).join("") + "</div></div>" +

                '<div class="xba-stp"><div class="xba-sh"><b>4</b><div><h3>Metal</h3><p>' + esc(m.n) + "</p></div></div>" +
                D.metales.map(function (G) {
                    return '<div class="xba-mg"><div class="xba-mgh">' + esc(G.g) + "<small>" + esc(G.s) + "</small></div>" + G.o.map(function (o) {
                        var p = (D.precios[o.id + "-" + t.id] || {}).p;
                        return '<button type="button" class="xba-mrow" data-m="' + o.id + '" aria-pressed="' + (o.id === m.id) + '"><span class="rad"></span><span class="sw ' + (o.t === "s" ? "plata" : "oro") + '"></span><span class="nm">' + esc(o.n) + '</span><span class="pr">' + dinero(p) + "</span></button>";
                    }).join("") + "</div>";
                }).join("") + "</div>" +

                '<div class="xba-sum"><div class="xba-sumh"><span>Tu juego de 13 arras</span><b>' + dinero(pr.p) + "</b></div><ul>" +
                "<li>Frente: " + esc(D.nombre) + "</li><li>Vuelta: " + esc(v.n) + (grab ? " («" + esc(grab) + "»)" : "") + "</li>" +
                (conValores ? "<li>Valores: los 13 de la colección</li>" : "") +
                "<li>Tamaño: " + esc(t.cm) + " cm</li><li>Metal: " + esc(m.n) + (pr.g ? " · " + pr.g.toFixed(1) + " g por arra" : "") + "</li></ul>" +
                '<p class="xba-eta">Listas en 3 semanas después de que aprueben el diseño · IVA incluido</p></div>';
        }

        flow.addEventListener("click", function (e) {
            var b = e.target.closest("button");
            if (!b) return;
            if (b.dataset.v) { aviso = ""; elegir("Vuelta", parseInt(b.dataset.v, 10)); }
            else if (b.dataset.t) elegir("Tamaño de arra", parseInt(b.dataset.t, 10));
            else if (b.dataset.m) elegir("Metal", parseInt(b.dataset.m, 10));
        });
        flow.addEventListener("change", function (e) {
            var k = e.target.dataset.g;
            if (!k) return;
            g[k] = k[0] === "i" ? e.target.value.toUpperCase() : e.target.value;
            aviso = "";
            pintar();
        });
        // No dejar comprar sin los datos del grabado.
        document.addEventListener("click", function (e) {
            var btn = e.target.closest("#add_to_cart, .o_we_buy_now");
            if (!btn || !form.contains(btn)) return;
            var falta = faltantes(vueltaPorId(actual("Vuelta")));
            if (falta.length) {
                e.preventDefault();
                e.stopImmediatePropagation();
                aviso = "Para grabar la vuelta nos falta " + falta.join(", ") + ".";
                pintar();
                var a = flow.querySelector(".xba-aviso");
                if (a) a.scrollIntoView({ behavior: "smooth", block: "center" });
            } else {
                escribirNativo(vueltaPorId(actual("Vuelta")));
            }
        }, true);
        form.addEventListener("change", function (e) {
            if (e.target.classList && e.target.classList.contains("js_variant_change")) setTimeout(pintar, 0);
        });
        pintar();
        // El campo nativo del texto lo crea Odoo después de cargar: volver a escribirlo cuando aparezca.
        var tries = 0, iv = setInterval(function () {
            tries++;
            if (form.querySelector(".variant_custom_value") || tries > 40) { clearInterval(iv); pintar(); }
        }, 250);
    }
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
    else init();
    window.addEventListener("load", init);
})();

/* Página /arras: filtro de frentes (Todos / No religiosos / Religiosos). */
(function () {
    "use strict";
    function initFiltro() {
        var pills = document.querySelectorAll("[data-xbap-f]");
        if (!pills.length || pills[0].dataset.ready) return;
        pills.forEach(function (p) {
            p.dataset.ready = "1";
            p.addEventListener("click", function () {
                var f = p.dataset.xbapF;
                pills.forEach(function (q) { q.setAttribute("aria-pressed", q === p); });
                document.querySelectorAll(".xbap-card").forEach(function (c) {
                    c.hidden = f !== "todos" && ((f === "rel") !== (c.dataset.rel === "1"));
                });
            });
        });
    }
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initFiltro);
    else initFiltro();
    window.addEventListener("load", initFiltro);
})();
