# Orders — services and coupons

`orders/services.py` is one of the two deliberate deep modules. Callers never
build an `Order` or compute discounts directly.

- `quote_cart(cart, coupon_code=None)` prices a cart with an optional coupon.
  A `Coupon` is whole-order (discounts every line) or specific-products
  (discounts only its target lines). A blank code means no coupon; an
  unusable one raises `InvalidCoupon`, a `ValueError` with a message safe to
  show the customer.
- `place_order` recalculates the price through `quote_cart` — the same math
  the checkout preview showed — and revalidates the coupon at placement. A
  coupon that expired or was retired after the customer applied it raises
  `InvalidCoupon` and placement fails; an outdated discount is never
  silently applied. Placement is all-or-nothing: on failure there is no
  partial order and the cart stays intact.
- The order copies the coupon's normalized code and each line's discount, so
  later edits to or retirement of the coupon never change a placed order.

Related pieces:

- Checkout can fill its shipping or billing section from a saved
  `accounts.Address` via an HTMX endpoint (`orders:checkout_address`); orders
  copy address fields, so editing the address book never touches history.
- `orders/validators.py` validates card numbers and expiry dates.
- Coupons have a back-office CRUD under `/backoffice/coupons/`, with an
  active/inactive toggle.
