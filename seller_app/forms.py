from decimal import Decimal
from django import forms
from marketplace.db import rows


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def clean(self, data, initial=None):
        if not data:
            return []
        return [super(MultipleFileField, self).clean(item, initial) for item in (data if isinstance(data, list) else [data])]


class ListingForm(forms.Form):
    expected_revision = forms.IntegerField(min_value=0, widget=forms.HiddenInput)
    draft_version = forms.IntegerField(min_value=0, widget=forms.HiddenInput)
    title = forms.CharField(max_length=200)
    description = forms.CharField(max_length=20000, widget=forms.Textarea(attrs={"rows": 7}))
    category_id = forms.TypedChoiceField(coerce=int, label="Category")
    condition = forms.ChoiceField(choices=[("like_new", "Like new"), ("good", "Good"), ("fair", "Fair"), ("poor", "Poor")])
    price = forms.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    original_price = forms.DecimalField(required=False, max_digits=12, decimal_places=2, min_value=0)
    location = forms.CharField(max_length=150)
    retain_images = forms.BooleanField(required=False, initial=True, label="Retain images from the current revision")
    clear_draft_images = forms.BooleanField(required=False, label="Discard previously saved private draft images")
    images = MultipleFileField(required=False, widget=MultipleFileInput, label="New images (up to six total)")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category_id"].choices = [(row["category_id"], row["name"]) for row in rows(
            "SELECT category_id,name FROM categories WHERE is_active ORDER BY name")]
        for field in self.fields.values():
            if not isinstance(field.widget, (forms.HiddenInput, forms.CheckboxInput)):
                field.widget.attrs["class"] = "form-control"
        self.fields["images"].widget.attrs["accept"] = "image/jpeg,image/png,image/webp"

    def clean_images(self):
        # Actual bounded multi-file validation belongs to the shared upload service.
        return None
