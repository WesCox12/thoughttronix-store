from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import Address, User


class AddressForm(forms.ModelForm):
    """Add or edit an address-book entry; the model fields carry the rules."""

    class Meta:
        model = Address
        fields = ["label", *Address.FIELDS]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            is_select = isinstance(field.widget, forms.Select)
            field.widget.attrs["class"] = (
                "select w-full" if is_select else "input w-full"
            )


class SignupForm(UserCreationForm):
    """Django's stock signup fields — username plus password and confirmation.

    No email: signing up asks for the minimum. The widgets carry DaisyUI
    classes because plain Django forms own their own styling here.
    """

    class Meta(UserCreationForm.Meta):
        model = User

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "input w-full"


class SignInForm(AuthenticationForm):
    """The stock authentication form, dressed in DaisyUI."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "input w-full"
