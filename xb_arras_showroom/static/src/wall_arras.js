/* Arras 3888 en el muro, con el lenguaje del mosaico de los anillos:
     1 · banda de oro  → el juego de 13 en su estuche, a sangre, con velo y logo;
     2 · banda de papel → el frente grande sobre fondo de estudio, título en la esquina baja;
     3 · banda de foto  → la vuelta grabada sobre satín, precio y QR sobre un velo.
   Se registra como pintor en window.XBWallPlugins; el muro lo consulta antes de su dibujo normal. */
(function () {
    "use strict";
    var IMG = "/xb_arras_showroom/static/src/img/";
    // Las monedas están fotografiadas en oro: el tono del metal se logra con filtros.
    var TINT = {
        s: "grayscale(1) brightness(1.14) contrast(1.06)", g: "none", g10: "saturate(.8) brightness(1.04)",
        g22: "saturate(1.25) hue-rotate(-4deg)", g24: "saturate(1.45) hue-rotate(-7deg) brightness(.98)",
    };
    // Centro de la cama de satín dentro de la foto del estuche (3:2) y su alto útil.
    var ESTUCHE = { cx: 51.6, cy: 49.7, ring: 20.6, coin: 9.8 };   // % del ancho de la escena

    function pintor(piece, panels, state, h) {
        var A = piece.arras;
        if (!A) { return null; }
        var el = h.el, shot = h.shot;
        var tint = TINT[A.tono] || "none";
        var conValores = A.valores && A.valores.length;

        function coin(url, cls, sombra) {
            var img = shot(url, cls);
            img.style.filter = tint + " " + sombra;
            return img;
        }

        function estuche() {
            var band = el("section", "band band-gold xbaw-case");
            var scene = el("div", "xbaw-scene");
            scene.style.backgroundImage = "url(" + IMG + "estuche.webp)";
            // 12 en círculo + 1 al centro, como se entregan.
            var pos = [[ESTUCHE.cx, ESTUCHE.cy]];
            for (var i = 0; i < 12; i++) {
                var a = (i / 12) * 2 * Math.PI - Math.PI / 2;
                pos.push([ESTUCHE.cx + ESTUCHE.ring * Math.cos(a), ESTUCHE.cy + ESTUCHE.ring * 1.5 * Math.sin(a)]);
            }
            pos.forEach(function (p) {
                var c = coin(A.frente, "xbaw-c13", "drop-shadow(0 .8vh .7vh rgba(70,48,14,.48)) drop-shadow(0 .1vh .1vh rgba(70,48,14,.35))");
                c.style.left = p[0] + "%";
                c.style.top = p[1] + "%";
                c.style.width = ESTUCHE.coin + "%";
                scene.appendChild(c);
            });
            band.appendChild(scene);
            band.appendChild(el("div", "band-veil top"));
            band.appendChild(el("div", "band-veil bottom"));
            var top = el("div", "xbaw-casetop over-top");
            top.appendChild(shot(A.logo_blanco, "xbaw-logo"));
            band.appendChild(top);
            var foot = el("div", "band-foot over-bottom");
            var left = el("div", "band-footcol");
            left.appendChild(el("div", "band-kicker", state.case_text || "En su estuche"));
            left.appendChild(el("div", "band-ref", "Juego de 13 arras"));
            foot.appendChild(left);
            band.appendChild(foot);
            return band;
        }

        function frente() {
            var band = el("section", "band band-light xbaw-front");
            if (piece.bg) { band.style.background = piece.bg; }
            var stage = el("div", "xbaw-hero");
            stage.appendChild(coin(A.frente, "xbaw-big",
                "drop-shadow(0 3.2vh 3.4vh rgba(43,35,23,.30)) drop-shadow(0 .5vh .6vh rgba(43,35,23,.22))"));
            band.appendChild(stage);
            var corner = el("div", "band-corner");
            var head = el("h1", "band-headline");
            head.appendChild(el("span", "band-name", A.nombre));
            head.appendChild(el("span", "band-sub", A.metal));
            corner.appendChild(head);
            corner.appendChild(el("div", "band-rule"));
            var strip = el("div", "band-strip inline");
            [["Tamaño", A.tamano], ["Vuelta", A.vuelta], ["Entrega", "3 semanas"]].forEach(function (s) {
                if (!s[1]) { return; }
                var it = el("span", "strip-item");
                it.appendChild(el("span", "strip-label", s[0]));
                it.appendChild(el("b", null, s[1]));
                strip.appendChild(it);
            });
            corner.appendChild(strip);
            band.appendChild(corner);
            var mark = el("div", "xbaw-mark");
            mark.appendChild(shot(A.logo, "xbaw-logo dorado"));
            band.appendChild(mark);
            return band;
        }

        function desdePorMetal() {
            // Precio del mismo tamaño en el metal más barato de cada grupo (imitación, plata, oro).
            var idx = 0;
            A.tamanos.forEach(function (t, i) { if (t.sel) { idx = i; } });
            var vistos = {}, out = [];
            A.filas.forEach(function (f) {
                if (vistos[f.g]) { return; }
                vistos[f.g] = true;
                out.push([f.g, f.p[idx]]);
            });
            return out;
        }

        function vuelta() {
            var band = el("section", "band band-photo xbaw-back");
            band.appendChild(shot(IMG + "satin.webp", "band-bleed"));
            if (A.vuelta_img) {
                var hold = el("div", "xbaw-lying");
                hold.appendChild(coin(A.vuelta_img, "xbaw-vcoin",
                    "drop-shadow(0 2.6vh 2.2vh rgba(60,42,14,.40)) drop-shadow(0 .4vh .5vh rgba(60,42,14,.35))"));
                band.appendChild(hold);
            }
            band.appendChild(el("div", "band-scrim xbaw-scrim"));
            var over = el("div", "band-over");
            over.appendChild(el("div", "band-kicker", "La vuelta"));
            over.appendChild(el("h2", "band-worn", A.vuelta || "Grabadas con su historia"));
            if (conValores) {
                over.appendChild(el("div", "xbaw-vals", A.valores.join("  ·  ")));
            } else {
                over.appendChild(el("div", "xbaw-vals", "Sus nombres, iniciales o la fecha de la boda"));
            }
            if (A.precio) {
                var pr = el("div", "xbaw-pricebox");
                pr.appendChild(el("div", "band-price", A.precio));
                pr.appendChild(el("div", "xbaw-pnote", "Juego de 13 · " + A.metal + " · " + A.tamano + " · IVA incluido"));
                over.appendChild(pr);
            }
            var alt = el("div", "band-strip xbaw-alt");
            desdePorMetal().forEach(function (g) {
                var it = el("span", "strip-item");
                it.appendChild(el("span", "strip-label", g[0]));
                it.appendChild(el("b", null, g[1]));
                alt.appendChild(it);
            });
            over.appendChild(alt);
            if (piece.qr) {
                var row = el("div", "band-qrow");
                row.appendChild(el("div", "band-note", state.qr_text || ""));
                row.appendChild(shot(piece.qr, "band-qr"));
                over.appendChild(row);
            }
            band.appendChild(over);
            return band;
        }

        var frag = document.createDocumentFragment();
        if (panels >= 3) { frag.appendChild(estuche()); frag.appendChild(frente()); frag.appendChild(vuelta()); }
        else if (panels === 2) { frag.appendChild(estuche()); frag.appendChild(vuelta()); }
        else { frag.appendChild(vuelta()); }
        return frag;
    }
    window.XBWallPlugins = window.XBWallPlugins || [];
    window.XBWallPlugins.push(pintor);
})();
