/** @odoo-module ignore **/
// XUBAX - Set methods for older browsers (see __manifest__.py).
(function () {
    "use strict";
    // Set methods (ES2025) for browsers older than Chrome 122 / Safari 17 / Firefox 127.
    const S = Set.prototype;
    const def = (name, fn) => {
        if (!S[name]) {
            Object.defineProperty(S, name, { value: fn, writable: true, configurable: true });
        }
    };
    const list = (other) => [...other.keys()];
    def("union", function (other) { const r = new Set(this); for (const v of list(other)) r.add(v); return r; });
    def("intersection", function (other) { const r = new Set(); for (const v of this) if (other.has(v)) r.add(v); return r; });
    def("difference", function (other) { const r = new Set(this); for (const v of this) if (other.has(v)) r.delete(v); return r; });
    def("symmetricDifference", function (other) {
        const r = new Set(this);
        for (const v of list(other)) { if (this.has(v)) r.delete(v); else r.add(v); }
        return r;
    });
    def("isSubsetOf", function (other) { for (const v of this) if (!other.has(v)) return false; return true; });
    def("isSupersetOf", function (other) { for (const v of list(other)) if (!this.has(v)) return false; return true; });
    def("isDisjointFrom", function (other) { for (const v of this) if (other.has(v)) return false; return true; });
})();
