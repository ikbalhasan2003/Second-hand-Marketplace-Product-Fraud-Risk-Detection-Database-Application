from django import forms


class SearchForm(forms.Form):
    q = forms.CharField(max_length=200, required=False, label="Search listings")
    category = forms.ChoiceField(required=False, choices=[("", "All categories")])
    minimum = forms.DecimalField(min_value=0, required=False, label="Minimum price")
    maximum = forms.DecimalField(min_value=0, required=False, label="Maximum price")
    condition = forms.ChoiceField(required=False, choices=[("", "All conditions")] + [(x, x.replace("_", " ").title()) for x in ("like_new", "good", "fair", "poor")])
    location = forms.CharField(max_length=150, required=False)
    risk = forms.ChoiceField(required=False, choices=[("", "All risk states"), ("low", "Current low risk"), ("medium", "Current medium risk"), ("high", "Current high risk"), ("unassessed", "Unassessed / stale")])
    sort = forms.ChoiceField(required=False, choices=[("", "Newest"), ("price", "Price: low to high")])

    def clean(self):
        data = super().clean()
        if data.get("minimum") is not None and data.get("maximum") is not None and data["minimum"] > data["maximum"]:
            raise forms.ValidationError("Minimum price must not exceed maximum price.")
        return data


class ReportForm(forms.Form):
    revision_no = forms.IntegerField(min_value=1, widget=forms.HiddenInput)
    order_id = forms.IntegerField(min_value=1, required=False, label="Your order ID (optional)")
    reason_code = forms.ChoiceField(choices=[(x, x.replace("_", " ").title()) for x in ("misleading_description", "suspicious_price", "duplicate_listing", "non_delivery", "counterfeit", "other")])
    comment = forms.CharField(max_length=5000, widget=forms.Textarea, label="Describe the concern")
