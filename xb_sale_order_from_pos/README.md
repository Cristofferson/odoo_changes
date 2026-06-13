# XUBAX — Sale Order / Quotation from POS

**Author:** XUBAX · soporte@xubax.com · https://www.xubax.com
**License:** OPL-1 · **Odoo:** 19.0 Enterprise · **Technical name:** `xb_sale_order_from_pos`

> Original, clean-room module: it does **not** copy or derive from any third-party
> module. All ERP logic (taxes, fiscal position, down payment, settlement, CFDI) is
> based on native Odoo (`point_of_sale`, `pos_sale`, `sale`, `l10n_mx_edi`).

---

## 1. Overview

Create **Quotations, Sale Orders and Layaways (apartados)** directly from the Point of
Sale, collect one or more **advances (down payments)**, **settle** the remaining balance,
and print an **enriched receipt** showing the order balance and an online-payment QR.

It **coexists** with — does not replace — the native `pos_sale` "Quotation/Order" loader.

**Works with any localization.** Includes **first-class support for Mexican CFDI 4.0**
(advances/settlement invoicing, SAT payment forms, branch RFC on the receipt). Note:
`l10n_mx_edi` is installed as a dependency but **remains dormant unless your company uses
the Mexican localization** — on a non-Mexican company every CFDI/SAT touchpoint is inert
and invoices keep pure native behaviour (see §5).

**Three document types** (the cashier chooses the kind):

| Type | Created as | Advance | Confirmed |
|---|---|---|---|
| **Quotation** | sent quotation | optional | natively, on payment |
| **Order** | sent quotation | optional | natively, on payment |
| **Layaway (apartado)** | sent quotation | **required ( > 0 )** | natively, on payment |

Semantics learned/verified in testing:

- **None of the three is confirmed on creation.** All are created as a *sent* quotation
  (portal-ready, payable online). The Sale Order is confirmed **natively by `pos_sale`**
  when the advance/payment is validated at the POS — not by this module.
- A **Layaway requires an advance > 0** (enforced at payment validation).
- Advances reuse the **native `pos_sale` down-payment product**; **multiple partial
  advances are supported**. The remaining balance is collected with the native **Settle**
  flow.

---

## 2. Requirements & dependencies

- **Odoo 19.0 Enterprise.**
- **Depends:** `point_of_sale`, `pos_sale`, `sale`, `l10n_mx_edi`.
  - `l10n_mx_edi` is a **hard dependency** so the Mexican CFDI features ship in a single
    module, but it stays **dormant on non-Mexican companies**: the dormancy is keyed on the
    company's **fiscal country** (`account_fiscal_country_id`, as `l10n_mx_edi` itself does),
    so a company running a generic chart of accounts gets pure native behaviour — no SAT
    forma de pago written, no cash-rounding change to invoices, the SAT field hidden in the
    payment-method form, and the receipt footer using the native VAT/Tax-ID line.
- **Soft dependency (NOT a hard dep):** `sale.order.internal_note` is provided by
  `sale_subscription`. The module maps the POS **order-level** internal note to it **only
  when the field exists** (field-existence guard). Without `sale_subscription`, the
  order-level internal note is simply not mapped — **no error**, the module stays
  installable. (Per-line notes use the module's own `xb_customer_note` / `xb_internal_note`
  fields and are unaffected.)

---

## 3. Required setup (critical — per selling company)

> These are **configuration requirements**, not bugs. The module attributes the invoice to
> the correct company automatically, but the fiscal/accounting master data must exist on
> each selling company.

1. **Down-payment product (native POS).** Configure it at
   `Point of Sale ▸ Settings ▸ this POS ▸ Down Payment Product`. Its **income account must
   be set for every selling company** — on the product, or on its **product category**, per
   company. On a branch without it, invoicing the advance fails with *"Falta la cuenta
   requerida en la línea contable"* (this happened with the Anello branch: the product
   category had no income account on the branch).

2. **Settle rounding product (optional — Option 2).** Only needed if you settle all-16%-tax
   orders and want the last rounding cent absorbed cleanly.
   - **Service** product, **0% IVA**.
   - **`Available in POS` = OFF (mandatory).** It is added programmatically at settle, never
     sold from the product grid. **If it is left visible as a product card, the POS can
     fail to load** (the frontend can't resolve a product whose template is not wired). The
     module force-loads its template so the programmatic use keeps working.
   - **Income account per selling company.**
   - **Mexico:** set its **ClaveProdServ (SAT)** with your accountant (placeholder
     `01010101` if there is no specific catalog code).
   - Select it at `Settings ▸ Point of Sale ▸ Settle rounding product`.
   - If **not configured**, settling an all-16% order simply tolerates a **±0.01** residual
     (opt-in, no error).

3. **POS payment method → SAT "Forma de pago".** The module adds a **`Forma de pago (SAT)`**
   field to `pos.payment.method`. Map each method, e.g. (Mexico): **Efectivo → 01**,
   **Transferencia → 03**, **Tarjeta de débito → 28**, **Tarjeta de crédito → 04**. The CFDI
   of a POS-issued invoice then reports the real payment form. (Editing a payment method
   requires its POS sessions to be closed — native constraint.)

4. **Multi-company / branches.** When selling from branch companies that **share a sales
   journal** with the parent, the module forces the invoice `company_id` to the **order's
   company** (the branch) so the branch's income accounts resolve. The **CFDI is issued
   under the branch's own RFC if it has one**; if not, under the RFC of the **nearest
   ancestor company that has a VAT** (the legal entity) — this is native `l10n_mx_edi`
   issuer behaviour that the module respects, and with which the **receipt RFC is
   consistent**. The income accounts must therefore **exist on each selling company**.

5. **Cash rounding.** If the POS uses cash rounding with **"Only apply rounding on cash"**,
   the module **excludes that rounding from the CFDI** automatically — the fiscal document
   stays at the exact amount and the cash-tendering difference stays in the POS session
   (cash drawer). This is **intended behaviour**.

---

## 4. Configuration reference

`Settings ▸ Point of Sale ▸ "XUBAX – Sale Order / Quotation"` (shown when a POS is
selected). English-source strings with an `es_MX` translation (`i18n/es_MX.po`).

| Setting | What it does | Visible only when |
|---|---|---|
| **Create Sale Order / Quotation** | Master switch — enables the whole feature for this POS. | — |
| Default document state | Pre-selects which document type is highlighted by default in the create dialog (Quotation, or Order / Layaway). It does not confirm anything — confirmation happens natively on payment. | master ON |
| Allow quotations | Let the cashier save the order as a draft quotation. | master ON |
| Differentiate Order and Layaway | Show separate "Order" / "Layaway" actions instead of one combined. | master ON |
| Show total & pending balance | Show order total + pending balance in the POS order panel. | master ON |
| Detailed order receipt | Print the order's product detail, total and balance on the receipt. | master ON |
| Show customer reference | Print the customer reference code before the name. | master ON |
| Auto-print receipt on create | Print the receipt right after the order is created. | master ON |
| Show online portal link on receipt | Add the payment QR (review / pay the balance online). | master ON **and** *Detailed order receipt* ON |
| Self-invoice QR only when settled | Show the native "Need an invoice?" QR only on settled/paid tickets (avoids a double QR on advances); off = native (every ticket). | master ON **and** *Self-Invoicing* (`point_of_sale_use_ticket_qr_code`) ON |
| Settle rounding product | Product used to absorb the rounding cent on an all-16% settle (Option 2). | master ON |

---

## 5. Behaviour notes

- **Install over existing data (`post_init_hook`).** On install/upgrade the module
  recomputes `amount_unpaid` for every Sale Order linked to POS orders. It overrides the
  native compute — which subtracted the **whole** linked pos.order total, wrongly counting
  loose products sold in the same ticket as an advance — to subtract only the **linked
  lines**. **This may surface a pending balance on orders that previously looked fully
  paid**: it is the correction of an imprecise native computation, not a regression. Advise
  the implementer before installing on a live database.
- **Balance is payment-based.** Multiple partial advances are supported; the balance is
  driven by the native stored field `sale.order.amount_unpaid`, kept fresh on the receipt
  via a round-trip in `sync_from_ui` (the recomputed SO is injected into the sync response,
  so the receipt shows the post-payment balance on the initial print).
- **No delivery during advances.** Confirming a POS-originated SO uses the native
  `skip_procurement` context, so **no SO delivery picking** is created while advances are
  collected. Delivery is fulfilled **once, through the POS picking**, when the order is
  settled.
- **Receipt.** Title by document **state** (a confirmed quotation prints "PEDIDO"); a payment
  summary (Total / Advance / Balance); the **payment QR while a balance remains ( > 0 )**;
  a **configurable self-invoice QR**; the advance's **product detail** on advance tickets;
  and a cash-rounding line that always reconciles (Total + Rounding = To Pay; Cash − To Pay
  = Change).
- **Mexican support is dormant off-MX.** Every CFDI/SAT touchpoint is gated on the company's
  fiscal country being `MX` (the same key `l10n_mx_edi` uses). On a non-Mexican company:
  the invoice keeps its **native cash rounding** (we don't drop `invoice_cash_rounding_id`),
  **no SAT forma de pago** is written by this module (any default present is native
  `l10n_mx_edi`, identical to a vanilla invoice), the **"Forma de pago (SAT)"** field is
  **hidden** in the payment-method form, and the receipt footer uses the **native** VAT/Tax-ID
  line. On a Mexican company these features activate automatically — one module, no setting
  to flip.

---

## 6. Known limitations

- Only a **single rounding currency (MXN)** has been tested.
- The **SO header `delivery_status`** stays empty — delivery is fulfilled through the **POS
  picking** (`pos.order`), not an SO picking. Documented behaviour, not a bug.
- **No customer signature** capture in the POS (roadmap).

---

*This README is the base content reused for the apps.odoo.com store listing
(`static/description/index.html`).*
