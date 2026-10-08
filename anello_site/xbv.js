/* Anello · selector de variantes (propuestas B y C). Se monta ENCIMA de los
   radios nativos de website_sale: los inputs reales siguen en el DOM y cada
   clic nuestro hace input.click(), así que Odoo recalcula precio, exclusiones
   y carrito exactamente igual que hoy. */
(function () {
    "use strict";
    var MODE = (document.currentScript && document.currentScript.dataset.mode) || "B";

    var FAM = {
        amarillo: { label: "Amarillo", css: "xbv-amarillo", rank: 1 },
        blanco: { label: "Blanco", css: "xbv-blanco", rank: 2 },
        rosa: { label: "Rosa", css: "xbv-rosa", rank: 3 },
        bitono: { label: "Bitono", css: "xbv-bitono", rank: 4 },
        florentino: { label: "Florentino", css: "xbv-florentino", rank: 5 },
        platino: { label: "Platino", css: "xbv-platino", rank: 6 },
        plata: { label: "Plata", css: "xbv-plata", rank: 7 },
        otro: { label: "Otro", css: "xbv-otro", rank: 9 },
    };

    function metalInfo(name) {
        var n = (name || "").toLowerCase();
        var fam = "otro", explicit = true;
        if (n.indexOf("amarillo") !== -1) fam = "amarillo";
        else if (n.indexOf("blanco") !== -1) fam = "blanco";
        else if (n.indexOf("rosa") !== -1) fam = "rosa";
        else if (n.indexOf("bitono") !== -1) fam = "bitono";
        else if (n.indexOf("florentino") !== -1) fam = "florentino";
        else if (n.indexOf("platino") !== -1) fam = "platino";
        else if (n.indexOf("plata") !== -1) fam = "plata";
        else if (n.indexOf("oro") === 0) { fam = "amarillo"; explicit = false; } // «Oro 14Kt» = misma ley que «Oro amarillo 14kt»
        var kt = "";
        var m = n.match(/(\d+)\s*k/);
        if (m) kt = m[1] + "K";
        else if (/\(999\)/.test(n)) kt = fam === "platino" ? "Pt 999" : "999";
        else if (/\(9[25]0\)|925/.test(n)) kt = "Ley " + (n.match(/9[25][05]/) || ["925"])[0];
        else if (fam === "plata") kt = n.indexOf("rodio") !== -1 ? "Baño rodio" : n.indexOf("baño oro") !== -1 ? "Baño oro" : "Ley 925";
        else if (n.indexOf("24") !== -1) kt = "24K";
        var nice = (fam === "otro" ? name : (fam === "platino" || fam === "plata" ? FAM[fam].label : "Oro " + FAM[fam].label.toLowerCase())) + (kt ? " · " + kt : "");
        return { fam: fam, kt: kt, explicit: explicit, nice: nice };
    }

    var STONE_TXT = {
        "zirconia": "Brillo clásico. Es la opción incluida en el precio que ves.",
        "diamante de laboratorio": "Diamante real, creado en laboratorio. Elige su tamaño:",
        "diamante natural": "Extraído de la tierra y certificado. Un asesor te cotiza la piedra.",
    };
    var ZIRC = { blanco: "xbv-z-blanco", rojo: "xbv-z-rojo", multicolor: "xbv-z-multi" };

    function el(tag, cls, html) {
        var e = document.createElement(tag);
        if (cls) e.className = cls;
        if (html != null) e.innerHTML = html;
        return e;
    }
    function isNA(input) {
        var li = input.closest(".js_attribute_value");
        return !!(li && li.classList.contains("css_not_available"));
    }
    function pick(input) {
        if (!input.checked) input.click();
    }

    var syncers = [];
    function syncAll() { syncers.forEach(function (f) { f(); }); }

    function header(title, valueEl) {
        var h = el("div", "xbv-head");
        h.appendChild(el("span", "xbv-title", title));
        h.appendChild(valueEl);
        return h;
    }

    /* ---------- Metal ---------- */
    function buildMetal(li, inputs) {
        var opts = inputs.map(function (i) { var mi = metalInfo(i.dataset.valueName); mi.input = i; return mi; });
        // Una sola opción visible por (familia, kilataje): gana el nombre explícito.
        var byKey = {};
        opts.forEach(function (o) {
            var k = o.fam + "|" + o.kt;
            if (!byKey[k] || (o.explicit && !byKey[k].explicit)) byKey[k] = o;
        });
        var uniq = Object.keys(byKey).map(function (k) { return byKey[k]; });
        uniq.sort(function (a, b) { return FAM[a.fam].rank - FAM[b.fam].rank || (parseInt(a.kt) || 99) - (parseInt(b.kt) || 99); });
        function current() {
            var c = opts.filter(function (o) { return o.input.checked; })[0];
            return c ? (byKey[c.fam + "|" + c.kt] || c) : uniq[0];
        }
        var val = el("b", "xbv-value");
        var box = el("div", "xbv-body");
        li.appendChild(header("Metal", val));
        li.appendChild(box);

        if (MODE === "B") {
            var fams = [];
            uniq.forEach(function (o) { if (fams.indexOf(o.fam) === -1) fams.push(o.fam); });
            var sw = el("div", "xbv-sw");
            var seg = el("div", "xbv-seg");
            var segWrap = el("div", "xbv-kt");
            segWrap.appendChild(el("span", "xbv-sub", "Kilataje"));
            segWrap.appendChild(seg);
            fams.forEach(function (f) {
                var b = el("button", "xbv-swb", '<span class="xbv-dot ' + FAM[f].css + '"></span><span class="xbv-swl">' + FAM[f].label + "</span>");
                b.type = "button"; b.dataset.fam = f;
                b.addEventListener("click", function () {
                    var cur = current();
                    var target = byKey[f + "|" + cur.kt] || uniq.filter(function (o) { return o.fam === f; })[0];
                    pick(target.input); syncAll();
                });
                sw.appendChild(b);
            });
            box.appendChild(sw);
            box.appendChild(segWrap);
            syncers.push(function () {
                var cur = current();
                val.textContent = cur.nice;
                sw.querySelectorAll("button").forEach(function (b) { b.setAttribute("aria-pressed", b.dataset.fam === cur.fam); });
                seg.innerHTML = "";
                var kts = uniq.filter(function (o) { return o.fam === cur.fam; });
                segWrap.hidden = kts.length < 2 && !kts[0].kt;
                kts.forEach(function (o) {
                    var b = el("button", isNA(o.input) ? "is-na" : "", o.kt || "Único");
                    b.type = "button";
                    b.setAttribute("aria-pressed", o === cur);
                    b.addEventListener("click", function () { pick(o.input); syncAll(); });
                    seg.appendChild(b);
                });
            });
        } else {
            var list = el("div", "xbv-tiles");
            uniq.forEach(function (o) {
                var b = el("button", "", '<span class="xbv-dot sm ' + FAM[o.fam].css + '"></span><span>' + o.nice + "</span>");
                b.type = "button";
                b.addEventListener("click", function () { pick(o.input); syncAll(); });
                o.btn = b;
                list.appendChild(b);
            });
            box.appendChild(list);
            syncers.push(function () {
                var cur = current();
                val.innerHTML = '<span class="xbv-dot xs ' + FAM[cur.fam].css + '"></span>' + cur.nice;
                uniq.forEach(function (o) { o.btn.setAttribute("aria-pressed", o === cur); o.btn.classList.toggle("is-na", isNA(o.input)); });
            });
        }
    }

    /* ---------- Medida (chips) ---------- */
    function buildChips(li, inputs, title) {
        var val = el("b", "xbv-value");
        var box = el("div", "xbv-body");
        li.appendChild(header(title, val));
        var grid = el("div", "xbv-chips");
        inputs.forEach(function (i) {
            var t = i.dataset.valueName.replace(/\.0$/, "");
            var b = el("button", "", t);
            b.type = "button";
            b.addEventListener("click", function () { pick(i); syncAll(); });
            i._xbv = b;
            grid.appendChild(b);
        });
        box.appendChild(grid);
        li.appendChild(box);
        syncers.push(function () {
            inputs.forEach(function (i) {
                i._xbv.setAttribute("aria-pressed", i.checked);
                i._xbv.classList.toggle("is-na", isNA(i));
                if (i.checked) val.textContent = i.dataset.valueName.replace(/\.0$/, "");
            });
        });
    }

    /* ---------- Medida (desplegable) ---------- */
    function buildSelect(li, inputs, title) {
        var val = el("b", "xbv-value");
        var box = el("div", "xbv-body");
        var head = header(title, val);
        // Liga a la guía de medidas (módulo xb_website_size_guide): viene dentro del
        // encabezado nativo, que aquí se oculta; se pasa al encabezado propio.
        var guia = li.querySelector(".attribute_name .xb_size_guide_link");
        if (guia) head.appendChild(guia);
        li.appendChild(head);
        var wrap = el("div", "xbv-select");
        var sel = el("select");
        sel.setAttribute("aria-label", title);
        inputs.forEach(function (i, n) {
            var o = el("option", null, i.dataset.valueName.replace(/\.0$/, ""));
            o.value = n;
            sel.appendChild(o);
        });
        sel.addEventListener("change", function () { pick(inputs[+sel.value]); syncAll(); });
        wrap.appendChild(sel);
        box.appendChild(wrap);
        li.appendChild(box);
        syncers.push(function () {
            inputs.forEach(function (i, n) {
                var o = sel.options[n];
                var na = isNA(i);
                o.textContent = i.dataset.valueName.replace(/\.0$/, "") + (na ? " · no disponible" : "");
                if (i.checked) sel.value = n;
            });
        });
    }

    /* ---------- Piedra (tarjetas) ----------
       Los tamaños del diamante de laboratorio («Diamante de laboratorio 1.00 ct») son valores
       distintos del atributo, pero se muestran como UNA tarjeta con sus tamaños dentro: al elegir
       la tarjeta se toma el tamaño marcado (o 1.00 ct) y los botones de tamaño cambian el valor. */
    var LAB_RE = /^diamante de laboratorio\s+([\d.]+)\s*ct$/i;
    function buildCards(li, inputs, title) {
        var val = el("b", "xbv-value");
        var box = el("div", "xbv-body");
        li.appendChild(header(title, val));
        var cards = el("div", "xbv-cards");
        var labs = inputs.filter(function (i) { return LAB_RE.test(i.dataset.valueName); });
        var labCard = null, labSizes = null;
        function card(nm, txt) {
            var b = el("button", "", '<span class="xbv-ring"></span><span class="xbv-cn">' + nm + '</span><span class="xbv-cd">' + txt + "</span>");
            b.type = "button";
            return b;
        }
        inputs.forEach(function (i) {
            var nm = i.dataset.valueName;
            if (labs.indexOf(i) !== -1) {
                if (labCard) return;
                var wrap = el("div", "xbv-labwrap");
                labCard = card("Diamante de laboratorio", STONE_TXT["diamante de laboratorio"]);
                labCard.addEventListener("click", function () {
                    var on = labs.filter(function (x) { return x.checked; })[0];
                    var def = labs.filter(function (x) { return LAB_RE.exec(x.dataset.valueName)[1] === "1.00"; })[0] || labs[0];
                    pick(on || def); syncAll();
                });
                labSizes = el("div", "xbv-chips xbv-labsizes");
                labs.forEach(function (x) {
                    var b = el("button", "", LAB_RE.exec(x.dataset.valueName)[1] + " ct");
                    b.type = "button";
                    b.addEventListener("click", function (e) { e.stopPropagation(); pick(x); syncAll(); });
                    x._xbv = b;
                    labSizes.appendChild(b);
                });
                wrap.appendChild(labCard);
                wrap.appendChild(labSizes);
                cards.appendChild(wrap);
                return;
            }
            var b = card(nm, STONE_TXT[nm.toLowerCase()] || "");
            b.addEventListener("click", function () { pick(i); syncAll(); });
            i._xbv = b;
            cards.appendChild(b);
        });
        box.appendChild(cards);
        li.appendChild(box);
        syncers.push(function () {
            var labOn = false;
            inputs.forEach(function (i) {
                i._xbv.setAttribute("aria-pressed", i.checked);
                if (labs.indexOf(i) !== -1 && i.checked) labOn = true;
                if (i.checked) val.textContent = i.dataset.valueName;
            });
            if (labCard) {
                labCard.setAttribute("aria-pressed", labOn);
                labSizes.hidden = !labOn;
            }
        });
    }

    /* ---------- Color de zirconias (muestras) ---------- */
    function buildZirc(li, inputs, title) {
        var val = el("b", "xbv-value");
        var box = el("div", "xbv-body");
        li.appendChild(header(title, val));
        var sw = el("div", "xbv-sw");
        inputs.forEach(function (i) {
            var k = i.dataset.valueName.toLowerCase();
            var b = el("button", "xbv-swb", '<span class="xbv-dot ' + (ZIRC[k] || "xbv-otro") + '"></span><span class="xbv-swl">' + i.dataset.valueName + "</span>");
            b.type = "button";
            b.addEventListener("click", function () { pick(i); syncAll(); });
            i._xbv = b;
            sw.appendChild(b);
        });
        box.appendChild(sw);
        li.appendChild(box);
        syncers.push(function () {
            inputs.forEach(function (i) {
                i._xbv.setAttribute("aria-pressed", i.checked);
                if (i.checked) val.textContent = i.dataset.valueName;
            });
        });
    }

    function init() {
        var root = document.querySelector(".js_main_product ul.js_add_cart_variants");
        if (!root || root.dataset.xbv) return;
        root.dataset.xbv = "1";
        root.classList.add("xbv", "xbv-" + MODE);
        var fixed = [];
        Array.prototype.forEach.call(root.querySelectorAll(":scope > li.variant_attribute"), function (li) {
            var name = li.dataset.attributeName || "";
            var inputs = Array.prototype.slice.call(li.querySelectorAll("input.js_variant_change"));
            if (!inputs.length || li.dataset.attributeDisplayType !== "radio") return; // select/pills/color se quedan nativos
            if (li.classList.contains("d-none")) {
                fixed.push([name, inputs[0].dataset.valueName]);
                return;
            }
            li.classList.add("xbv-li");
            li.querySelector(".attribute_name").classList.add("xbv-native");
            li.querySelector("ul.o_wsale_product_attribute").classList.add("xbv-native");
            if (name === "Metal") buildMetal(li, inputs);
            else if (name === "Piedra") buildCards(li, inputs, name);
            else if (/zirconia/i.test(name)) buildZirc(li, inputs, name);
            else if (name === "Medida") buildSelect(li, inputs, name);
            else buildChips(li, inputs, name);
        });
        if (fixed.length) {
            var f = el("li", "xbv-fixed");
            fixed.forEach(function (p) { f.appendChild(el("span", "", "<small>" + p[0] + "</small>" + p[1])); });
            root.appendChild(f);
        }
        if (MODE === "C") {
            root.querySelectorAll("li.xbv-li").forEach(function (li) {
                var head = li.querySelector(".xbv-head");
                head.setAttribute("role", "button");
                head.tabIndex = 0;
                head.appendChild(el("span", "xbv-chev", ""));
                function toggle() {
                    var open = !li.classList.contains("is-open");
                    root.querySelectorAll("li.xbv-li.is-open").forEach(function (o) { o.classList.remove("is-open"); o.querySelector(".xbv-head").setAttribute("aria-expanded", "false"); });
                    li.classList.toggle("is-open", open);
                    head.setAttribute("aria-expanded", open);
                }
                head.addEventListener("click", toggle);
                head.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); } });
            });
        }
        root.addEventListener("change", function () { setTimeout(syncAll, 0); });
        // Solo reaccionar a cambios de Odoo en los valores nativos (exclusiones); los nuestros no cuentan.
        new MutationObserver(function (muts) {
            if (muts.some(function (m) { return m.target.closest && m.target.closest(".js_attribute_value"); })) syncAll();
        }).observe(root, { subtree: true, attributes: true, attributeFilter: ["class"] });
        syncAll();
    }
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
    else init();
})();
