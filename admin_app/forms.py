from django import forms


class DecisionForm(forms.Form):
    revision_no = forms.IntegerField(min_value=1, widget=forms.HiddenInput)
    expected_head = forms.IntegerField(required=False, widget=forms.HiddenInput)
    report_id = forms.IntegerField(min_value=1, required=False)
    verdict = forms.ChoiceField(choices=[("", "Choose a verdict"), ("fraud", "Fraud"), ("legitimate", "Legitimate"), ("unresolved", "Unresolved")])
    reason = forms.CharField(max_length=5000, widget=forms.Textarea(attrs={"rows": 3}))
    evidence = forms.CharField(max_length=10000, widget=forms.Textarea(attrs={"rows": 4}))


class RulesetForm(forms.Form):
    version = forms.RegexField(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$", max_length=100)
    schema_id = forms.IntegerField(min_value=1)
    medium = forms.IntegerField(min_value=0, max_value=99, initial=40)
    high = forms.IntegerField(min_value=1, max_value=100, initial=75)
    max_age_hours = forms.IntegerField(min_value=1, max_value=168, initial=24)
    reason = forms.CharField(max_length=5000, widget=forms.Textarea(attrs={"rows": 2}))

    def clean(self):
        data = super().clean()
        if "medium" in data and "high" in data and data["medium"] >= data["high"]:
            raise forms.ValidationError("The Medium threshold must be below High.")
        return data


class ActivationForm(forms.Form):
    model_id = forms.IntegerField(min_value=1)
    ruleset_id = forms.IntegerField(min_value=1)
    expected_model = forms.IntegerField(required=False, widget=forms.HiddenInput)
    expected_ruleset = forms.IntegerField(required=False, widget=forms.HiddenInput)
    reason = forms.CharField(max_length=5000, widget=forms.Textarea(attrs={"rows": 2}))
    confirm = forms.BooleanField(label="I reviewed this pair; existing assessments will be reassessed asynchronously.")


class AuditFilterForm(forms.Form):
    actor = forms.IntegerField(min_value=1, required=False)
    event = forms.IntegerField(min_value=1, required=False)
    action = forms.CharField(max_length=64, required=False)
    start = forms.DateTimeField(required=False, label="From (Asia/Shanghai or explicit offset)")
    end = forms.DateTimeField(required=False, label="To (Asia/Shanghai or explicit offset)")

    def clean(self):
        data = super().clean()
        if data.get("start") and data.get("end") and data["end"] < data["start"]:
            raise forms.ValidationError("The end must follow the start.")
        return data


class ExportForm(forms.Form):
    version = forms.RegexField(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$", max_length=100)
    cutoff = forms.DateTimeField(label="Immutable cutoff (Asia/Shanghai or explicit offset)")
    seed = forms.IntegerField(min_value=0, max_value=2147483647, initial=42)
    reason = forms.CharField(max_length=5000, widget=forms.Textarea(attrs={"rows": 2}))
