"""Cart and checkout views — thin per the architecture convention.

The three HTMX interactions of the core live here: add-to-cart, quantity
change, and line removal. Each renders a partial (never ``base.html``);
the responses carry the navbar badge as an out-of-band swap via the
``oob_badge`` context flag. Checkout is conventional full-page work:
validate the form, hand everything to ``place_order``.
"""

from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Count
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    FormView,
    ListView,
    TemplateView,
    UpdateView,
)

from accounts.mixins import StaffRequiredMixin
from accounts.models import Address
from products.models import Product

from .forms import CheckoutForm, CouponForm, OrderStatusForm
from .models import Cart, CartItem, Coupon, Order
from .services import InvalidCoupon, place_order, quote_cart


class CartView(LoginRequiredMixin, TemplateView):
    """The customer's cart page."""

    template_name = "orders/cart.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["cart"] = Cart.for_user(self.request.user)
        return context


class AddToCartView(LoginRequiredMixin, View):
    """HTMX: add a product; the button swaps and the badge updates OOB.

    Looks the product up through ``available()``, so adding an
    unavailable product 404s — the same not-for-sale semantics as the
    public catalog.
    """

    def post(self, request, pk):
        product = get_object_or_404(Product.objects.available(), pk=pk)
        item = Cart.for_user(request.user).add(product)
        return render(
            request,
            "orders/partials/_add_button.html",
            {"product": product, "in_cart": item.quantity, "oob_badge": True},
        )


class CartItemActionView(LoginRequiredMixin, View):
    """Base for HTMX line mutations: act, then re-render the cart contents.

    Items are always fetched through the owner's cart — never by bare pk.
    """

    def post(self, request, pk):
        item = get_object_or_404(CartItem, pk=pk, cart__user=request.user)
        self.act(item)
        return render(
            request,
            "orders/partials/_cart_contents.html",
            {"cart": item.cart, "oob_badge": True},
        )

    def act(self, item):
        raise NotImplementedError


class IncrementCartItemView(CartItemActionView):
    def act(self, item):
        item.increment()


class DecrementCartItemView(CartItemActionView):
    def act(self, item):
        item.decrement()


class RemoveCartItemView(CartItemActionView):
    def act(self, item):
        item.delete()


class CheckoutView(LoginRequiredMixin, FormView):
    """The single checkout page: validate the form, hand off to the service.

    A cart that can't check out (empty, or holding a product that has
    since become unavailable) is sent back to the cart page to be fixed —
    ``place_order`` enforces the same rules transactionally as the
    backstop.
    """

    template_name = "orders/checkout.html"
    form_class = CheckoutForm

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        cart = Cart.for_user(request.user)
        if not cart.items.exists():
            messages.info(request, "Your cart is empty — add something first.")
            return redirect("orders:cart")
        unavailable = [
            line.product.name for line in cart.lines() if not line.product.is_available
        ]
        if unavailable:
            messages.warning(
                request,
                f"No longer available: {', '.join(unavailable)}. "
                "Remove them from the cart to check out.",
            )
            return redirect("orders:cart")
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        """Prefill both sections from the default address, if there is one.

        "Save this address" starts ticked only for an empty address book,
        so a first order builds the book without collecting one-offs later.
        """
        initial = super().get_initial()
        addresses = Address.objects.filter(user=self.request.user)
        default = addresses.filter(is_default=True).first()
        if default:
            initial |= default.as_initial("shipping") | default.as_initial("billing")
        has_addresses = addresses.exists()
        initial["save_shipping"] = initial["save_billing"] = not has_addresses
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = context["form"]
        code = form["coupon_code"].value() if form.is_bound else ""
        context |= order_summary_context(Cart.for_user(self.request.user), code)
        context["saved_addresses"] = Address.objects.filter(user=self.request.user)
        return context

    def form_valid(self, form):
        cart = Cart.for_user(self.request.user)
        try:
            order = place_order(
                cart,
                self.request.user,
                form.cleaned_data,
                coupon_code=form.cleaned_data["coupon_code"],
            )
        except InvalidCoupon as error:
            # The code went bad between Apply and submit (or was never
            # applied): nothing was placed; show why, keep every field.
            form.add_error("coupon_code", str(error))
            return self.form_invalid(form)
        messages.success(self.request, f"Order {order.number} placed. Thank you!")
        return redirect(reverse("orders:confirmation", kwargs={"pk": order.pk}))


def order_summary_context(cart, coupon_code):
    """Context for ``_order_summary.html``: the quote and the code's fate.

    An unusable code falls back to the undiscounted quote, with the
    reason in ``coupon_error`` — checkout never crashes on a bad code.
    """
    coupon_code = Coupon.normalize_code(coupon_code)
    try:
        quote = quote_cart(cart, coupon_code)
        coupon_error = ""
    except InvalidCoupon as error:
        quote = quote_cart(cart)
        coupon_error = str(error)
    return {
        "cart": cart,
        "quote": quote,
        "coupon_code": coupon_code,
        "coupon_error": coupon_error,
    }


class CheckoutCouponView(LoginRequiredMixin, View):
    """HTMX: apply (or remove) a promo code and re-render the order summary.

    Only a preview — ``place_order`` re-checks the code on submit. The
    submit button's total updates out of band.
    """

    def post(self, request):
        context = order_summary_context(
            Cart.for_user(request.user), request.POST.get("coupon_code", "")
        )
        return render(
            request, "orders/partials/_order_summary.html", context | {"oob": True}
        )


class CheckoutAddressFieldsView(LoginRequiredMixin, View):
    """HTMX: one checkout address section, filled from a saved address.

    ``?address=<pk>`` picks one of the customer's own addresses (another
    customer's pk 404s); an empty value returns the section blank. The
    fields stay editable — the checkout POST is unchanged.
    """

    SECTIONS = ("shipping", "billing")

    def get(self, request, section):
        if section not in self.SECTIONS:
            raise Http404("No such checkout section.")
        initial = {}
        pk = request.GET.get("address", "")
        if pk:
            if not pk.isdigit():
                raise Http404("No such address.")
            address = get_object_or_404(Address, pk=pk, user=request.user)
            initial = address.as_initial(section)
        form = CheckoutForm(initial=initial)
        return render(
            request,
            "orders/partials/_address_fields.html",
            {"fields": form.address_fields(section)},
        )


class OwnOrdersMixin(LoginRequiredMixin):
    """Orders are always fetched through the owner — never by bare pk."""

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user)


class OrderConfirmationView(OwnOrdersMixin, DetailView):
    template_name = "orders/confirmation.html"
    context_object_name = "order"


class OrderHistoryView(OwnOrdersMixin, ListView):
    """The customer's orders, most recent first per the model ordering."""

    template_name = "orders/order_history.html"
    context_object_name = "orders"


class OrderDetailView(OwnOrdersMixin, DetailView):
    template_name = "orders/order_detail.html"
    context_object_name = "order"

    def get_queryset(self):
        return super().get_queryset().prefetch_related("items")


# --- The back office --------------------------------------------------------
#
# Staff-only order oversight: every customer's orders, filterable by
# status, with the status dropdown on the detail page. The ``section``
# context entry drives the active tab in the staff shell.


class ManageOrderListView(StaffRequiredMixin, ListView):
    """All orders, most recent first, filterable via ``?status=``."""

    template_name = "orders/manage_orders.html"
    context_object_name = "orders"
    paginate_by = 20
    extra_context = {"section": "orders"}

    def get_queryset(self):
        orders = Order.objects.select_related("user")
        status = self.request.GET.get("status", "")
        if status in Order.Status.values:
            orders = orders.filter(status=status)
        return orders

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["statuses"] = Order.Status.choices
        context["active_status"] = self.request.GET.get("status", "")
        return context


class ManageOrderDetailView(StaffRequiredMixin, DetailView):
    """Any order's detail, with the status form alongside."""

    template_name = "orders/manage_order_detail.html"
    context_object_name = "order"
    queryset = Order.objects.select_related("user").prefetch_related("items")
    extra_context = {"section": "orders"}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_form"] = OrderStatusForm(instance=self.object)
        return context


class UpdateOrderStatusView(StaffRequiredMixin, View):
    """POST-only: set an order's status from the back-office dropdown."""

    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        form = OrderStatusForm(request.POST, instance=order)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                f"{order.number} is now {order.get_status_display().lower()}.",
            )
        else:
            messages.error(request, "That isn't a status an order can have.")
        return redirect("orders:manage_order_detail", pk=order.pk)


# --- Coupons (back office) ---------------------------------------------------
#
# Marketing manages coupons here without a developer: create, edit,
# retire (and reactivate), and delete only what no order has used.


class ManageCouponListView(StaffRequiredMixin, ListView):
    """Every coupon with its live status and use count; ``?status=`` filters."""

    template_name = "orders/manage_coupons.html"
    context_object_name = "coupons"
    paginate_by = 20
    extra_context = {"section": "coupons"}

    def get_queryset(self):
        return (
            Coupon.objects.with_status(self.request.GET.get("status", ""))
            .annotate(order_count=Count("orders"))
            .prefetch_related("products")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["statuses"] = Coupon.Status.choices
        context["active_status"] = self.request.GET.get("status", "")
        return context


class ManageCouponCreateView(StaffRequiredMixin, SuccessMessageMixin, CreateView):
    model = Coupon
    form_class = CouponForm
    template_name = "orders/manage_coupon_form.html"
    success_url = reverse_lazy("orders:manage_coupons")
    success_message = "Coupon %(code)s created."
    extra_context = {"section": "coupons"}

    def get_initial(self):
        """Starts now, runs 30 days — the common case, easy to change."""
        now = timezone.localtime().replace(second=0, microsecond=0)
        return {"starts_at": now, "expires_at": now + timedelta(days=30)}


class ManageCouponUpdateView(StaffRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Coupon
    form_class = CouponForm
    template_name = "orders/manage_coupon_form.html"
    success_url = reverse_lazy("orders:manage_coupons")
    success_message = "Coupon %(code)s saved."
    extra_context = {"section": "coupons"}


class ManageCouponDeleteView(StaffRequiredMixin, SuccessMessageMixin, DeleteView):
    """Delete a coupon no order has used — a used coupon 404s here.

    Used coupons are retired instead; ``on_delete=PROTECT`` on
    ``Order.coupon`` backs this up at the database level.
    """

    queryset = Coupon.objects.filter(orders__isnull=True)
    context_object_name = "coupon"
    template_name = "orders/manage_coupon_confirm_delete.html"
    success_url = reverse_lazy("orders:manage_coupons")
    success_message = "Coupon deleted."
    extra_context = {"section": "coupons"}


class ToggleCouponActiveView(StaffRequiredMixin, View):
    """POST-only: retire an active coupon, or reactivate a retired one."""

    def post(self, request, pk):
        coupon = get_object_or_404(Coupon, pk=pk)
        coupon.is_active = not coupon.is_active
        coupon.save(update_fields=["is_active"])
        verb = "reactivated" if coupon.is_active else "retired"
        messages.success(request, f"Coupon {coupon.code} {verb}.")
        return redirect("orders:manage_coupons")
