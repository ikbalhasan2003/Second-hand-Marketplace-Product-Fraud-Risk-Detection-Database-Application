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
    target_type = forms.ChoiceField(required=False, choices=[("", "Any target")] + [(name, name.title()) for name in ("product", "user", "transaction", "report", "model", "ruleset", "dataset")])
    target_id = forms.IntegerField(min_value=1, required=False)
    start = forms.DateTimeField(required=False, label="From (Asia/Shanghai or explicit offset)")
    end = forms.DateTimeField(required=False, label="To (Asia/Shanghai or explicit offset)")

    def clean(self):
        data = super().clean()
        if data.get("start") and data.get("end") and data["end"] < data["start"]:
            raise forms.ValidationError("The end must follow the start.")
        if bool(data.get("target_type")) != bool(data.get("target_id")):
            raise forms.ValidationError("Choose both a target type and target ID.")
        return data


class QueueFilterForm(forms.Form):
    source = forms.ChoiceField(required=False, choices=[("", "All sources"), ("reports", "Open reports"), ("ai", "Current High risk"), ("combined", "Both sources")])
    risk = forms.ChoiceField(required=False, choices=[("", "Any assessment"), ("low", "Low"), ("medium", "Medium"), ("high", "High"), ("unassessed", "Unassessed")])
    status = forms.ChoiceField(required=False, choices=[("", "Any open report status"), ("pending", "Pending"), ("reviewing", "Under Review")])
    assignee = forms.IntegerField(min_value=1, required=False, label="Assigned administrator ID")
    unassigned = forms.BooleanField(required=False, label="Has unassigned open report")
    age_days = forms.IntegerField(min_value=0, max_value=36500, required=False, label="Waiting at least (days)")


class ExportForm(forms.Form):
    version = forms.RegexField(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$", max_length=100)
    cutoff = forms.DateTimeField(label="Immutable cutoff (Asia/Shanghai or explicit offset)")
    seed = forms.IntegerField(min_value=0, max_value=2147483647, initial=42)
    reason = forms.CharField(max_length=5000, widget=forms.Textarea(attrs={"rows": 2}))


class DirectoryFilterForm(forms.Form):
    q = forms.CharField(max_length=150, required=False, label="Search ID, name or email")


class RiskFilterForm(forms.Form):
    level = forms.ChoiceField(required=False, choices=[("", "All levels"), ("low", "Low"), ("medium", "Medium"), ("high", "High")])
    category = forms.IntegerField(min_value=1, required=False, label="Category ID")
    start = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    end = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))

    def clean(self):
        data = super().clean()
        if data.get("start") and data.get("end") and data["end"] < data["start"]:
            raise forms.ValidationError("The end must follow the start.")
        return data


class PolicyForm(forms.Form):
    timeout_hours = forms.IntegerField(min_value=1, max_value=8760, label="Unanswered order timeout (hours)")
    expected_hours = forms.DecimalField(widget=forms.HiddenInput)
    reason = forms.CharField(max_length=5000, widget=forms.Textarea)


class TrainingSettingsForm(forms.Form):
    dataset_id = forms.TypedChoiceField(coerce=int, choices=(), label="Frozen training dataset")
    reason = forms.CharField(max_length=5000, widget=forms.Textarea(attrs={"rows": 2}))
