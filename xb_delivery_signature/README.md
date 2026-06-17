# Delivery Receipt Signature (`xb_delivery_signature`)

Capture the customer's **"received" signature** when a delivery (`stock.picking`)
is handed over, and store it on the delivery and (optionally) on the linked Sale
Order. For Odoo 19.0. License OPL-1. © XUBAX.

## What it does

- **Backend / tablet** — a native signature pad pops up when an outgoing delivery
  is validated. If *Signature mandatory to validate* is on, the delivery cannot be
  completed until it is signed. A **Request signature** button on the delivery lets
  the operator capture it on demand.
- **Portal self-sign** — a secure page `/my/delivery/<id>/sign`, authorised by the
  linked sale order's `access_token`, lets the customer sign from their own phone
  (reuses the native `portal.signature_form` component).
- **Storage** — the signature is kept per delivery (`xb_delivery_signature` +
  `xb_delivery_signed_by` / `xb_delivery_signed_on`), so partial deliveries each
  keep their own. With *Copy signature to the Sale Order*, the latest is mirrored to
  the SO's native `signature` / `signed_by` / `signed_on`.

## Configuration

Settings ▸ Inventory ▸ *XUBAX - Delivery Receipt Signature*:

| Setting | Effect |
|---|---|
| Delivery receipt signature | Master toggle (per company) |
| Signature mandatory to validate | Block validation until signed |
| Allow portal self-signature | Expose the portal sign link |
| Copy signature to the Sale Order | Mirror to the SO native fields |

## POS

Install **`xb_delivery_signature_pos`** (auto-installs when Point of Sale is
present) to capture the signature inside the POS, right after the order is
validated. Enable it per POS under Settings ▸ Point of Sale.

## Technical notes

- Depends on `stock`, `sale_stock` (for `stock.picking.sale_id`), `portal`,
  `website`.
- Validation interception is done in `stock.picking._pre_action_done_hook`
  (returns the signature wizard action when mandatory + unsigned); the wizard
  re-launches `button_validate` with `xb_skip_signature_check=True`.
- Clean-room implementation; signature capture uses Odoo's own
  `web` signature widget / `portal.signature_form`.
