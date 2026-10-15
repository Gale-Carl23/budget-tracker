from django import forms
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password
from .models import Account, Budget, Category, Debt, DebtPayment, GoalContribution, Profile, RecurringItem, SavingsGoal, Transaction

class SignupForm(forms.Form):
    username = forms.CharField(max_length=150)
    email = forms.EmailField()
    currency = forms.ChoiceField(choices=[("USD", "US Dollar (USD)"), ("PHP", "Philippine Peso (PHP)"), ("EUR", "Euro (EUR)"), ("GBP", "British Pound (GBP)"), ("CNY", "Chinese Yuan (CNY)"), ("JPY", "Japanese Yen (JPY)"), ("CAD", "Canadian Dollar (CAD)"), ("AUD", "Australian Dollar (AUD)")])
    password1 = forms.CharField(widget=forms.PasswordInput, min_length=8)
    password2 = forms.CharField(widget=forms.PasswordInput, min_length=8)

    def clean_username(self):
        from django.contrib.auth import get_user_model
        name = self.cleaned_data["username"]
        if get_user_model().objects.filter(username__iexact=name).exists():
            raise ValidationError("That username is already in use.")
        return name

    def clean_email(self):
        from django.contrib.auth import get_user_model
        email = self.cleaned_data["email"].strip()
        if get_user_model().objects.filter(email__iexact=email).exists():
            raise ValidationError("An account already uses this email address.")
        return email

    def clean(self):
        data = super().clean()
        if data.get("password1") and data.get("password2") and data["password1"] != data["password2"]:
            self.add_error("password2", "The passwords do not match.")
        if data.get("password1"):
            try:
                validate_password(data["password1"])
            except ValidationError as exc:
                self.add_error("password1", exc)
        return data

class AccountForm(forms.ModelForm):
    class Meta:
        model = Account
        fields = ["name", "kind", "opening_balance", "currency"]
    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs); self.user = user
        if not self.instance.pk: self.instance.user = user
    def clean_name(self):
        name = self.cleaned_data["name"]
        qs = Account.objects.filter(user=self.user, name__iexact=name)
        if self.instance.pk: qs = qs.exclude(pk=self.instance.pk)
        if qs.exists(): raise ValidationError("You already have an account with that name.")
        return name

class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "kind", "icon", "color", "parent"]
        widgets = {"color": forms.TextInput(attrs={"type": "color"})}
    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs); self.user = user
        self.fields["parent"].queryset = Category.objects.filter(user=user)
        self.fields["parent"].required = False
    def clean_name(self):
        name = self.cleaned_data["name"]
        qs = Category.objects.filter(user=self.user, name__iexact=name, kind=self.cleaned_data.get("kind"))
        if self.instance.pk: qs = qs.exclude(pk=self.instance.pk)
        if qs.exists(): raise ValidationError("You already have a category with that name and type.")
        return name

class TransactionForm(forms.ModelForm):
    class Meta:
        model = Transaction
        fields = ["kind", "amount", "date", "account", "destination", "category", "description", "payee", "notes", "tags"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"}), "notes": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        if not self.instance.pk:
            self.instance.user = user
        self.fields["account"].queryset = Account.objects.filter(user=user, is_archived=False)
        self.fields["destination"].queryset = Account.objects.filter(user=user, is_archived=False)
        self.fields["category"].queryset = Category.objects.filter(user=user)
        self.fields["destination"].required = False
        self.fields["category"].required = False

    def clean(self):
        data = super().clean()
        if data.get("account") and data["account"].user_id != self.user.id:
            self.add_error("account", "Choose one of your own accounts.")
        if data.get("category") and data["category"].user_id != self.user.id:
            self.add_error("category", "Choose one of your own categories.")
        if data.get("category") and data.get("kind") in {"income", "expense"} and data["category"].kind != data["kind"]:
            self.add_error("category", "Choose a category for this transaction type.")
        if data.get("kind") == "transfer":
            if not data.get("destination"):
                self.add_error("destination", "Choose a destination account for this transfer.")
            elif data.get("destination") == data.get("account"):
                self.add_error("destination", "Choose a different destination account.")
        return data

class BudgetForm(forms.ModelForm):
    class Meta:
        model = Budget
        fields = ["category", "amount", "starts_on", "ends_on", "rollover"]
        widgets = {"starts_on": forms.DateInput(attrs={"type": "date"}), "ends_on": forms.DateInput(attrs={"type": "date"})}
    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        if not self.instance.pk: self.instance.user = user
        self.fields["category"].queryset = Category.objects.filter(user=user, kind="expense")
    def clean(self):
        data = super().clean()
        if data.get("starts_on") and data.get("ends_on") and data["ends_on"] < data["starts_on"]:
            self.add_error("ends_on", "End date must be on or after the start date.")
        return data

class GoalForm(forms.ModelForm):
    class Meta:
        model = SavingsGoal
        fields = ["name", "target_amount", "target_date", "account"]
        widgets = {"target_date": forms.DateInput(attrs={"type": "date"})}
    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["account"].queryset = Account.objects.filter(user=user, is_archived=False)
        self.fields["account"].required = False

class ContributionForm(forms.ModelForm):
    class Meta:
        model = GoalContribution
        fields = ["amount", "date", "note"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"})}

class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ["currency", "locale"]
        widgets = {"locale": forms.TextInput(attrs={"placeholder": "en-US"})}

class RecurringItemForm(forms.ModelForm):
    class Meta:
        model = RecurringItem
        fields = ["name", "kind", "amount", "account", "category", "next_date", "frequency", "end_date"]
        widgets = {"next_date": forms.DateInput(attrs={"type": "date"}), "end_date": forms.DateInput(attrs={"type": "date"})}
    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs); self.user = user
        self.fields["account"].queryset = Account.objects.filter(user=user, is_archived=False)
        kind = self.data.get("kind") or getattr(self.instance, "kind", "")
        category_kind = "expense" if kind == "bill" else "income" if kind == "income" else None
        categories = Category.objects.filter(user=user)
        self.fields["category"].queryset = categories.filter(kind=category_kind) if category_kind else categories
        self.fields["category"].required = False; self.fields["end_date"].required = False
    def clean(self):
        data = super().clean()
        if data.get("end_date") and data.get("next_date") and data["end_date"] < data["next_date"]:
            self.add_error("end_date", "End date must be on or after the next scheduled date.")
        return data

class DebtForm(forms.ModelForm):
    class Meta:
        model = Debt
        fields = ["name", "kind", "original_amount", "due_date", "notes"]
        widgets = {"due_date": forms.DateInput(attrs={"type": "date"}), "notes": forms.Textarea(attrs={"rows": 3})}

class DebtPaymentForm(forms.ModelForm):
    class Meta:
        model = DebtPayment
        fields = ["amount", "account", "date", "notes"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"})}
    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["account"].queryset = Account.objects.filter(user=user, is_archived=False)
