from decimal import Decimal
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    currency = models.CharField(max_length=3, default="USD")
    locale = models.CharField(max_length=20, default="en-US")
    onboarding_complete = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self): return self.user.get_username()


class Account(models.Model):
    TYPES = [("cash", "Cash"), ("checking", "Checking"), ("savings", "Savings"), ("wallet", "E-wallet"), ("credit", "Credit card")]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="finance_accounts")
    name = models.CharField(max_length=80)
    kind = models.CharField(max_length=16, choices=TYPES, default="checking")
    opening_balance = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    currency = models.CharField(max_length=3, default="USD")
    color = models.CharField(max_length=7, default="#78965d")
    is_archived = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["user", "name"], name="uniq_account_name_per_user")]

    @property
    def current_balance(self):
        entries = self.transactions.all()
        balance = self.opening_balance
        for item in entries:
            if item.kind in ("income", "refund"):
                balance += item.amount
            elif item.kind in ("expense", "adjustment"):
                balance -= item.amount
            elif item.kind == "transfer":
                balance -= item.amount
        incoming = Transaction.objects.filter(user=self.user, kind="transfer", destination=self).aggregate(v=models.Sum("amount"))["v"] or Decimal("0.00")
        return balance + incoming

    def __str__(self): return self.name


class Category(models.Model):
    TYPES = [("expense", "Expense"), ("income", "Income")]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="finance_categories")
    name = models.CharField(max_length=64)
    kind = models.CharField(max_length=8, choices=TYPES, default="expense")
    icon = models.CharField(max_length=12, default="•")
    color = models.CharField(max_length=7, default="#91a96b")
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="children")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["user", "name", "kind"], name="uniq_category_name_per_user")]

    def __str__(self): return self.name


class Transaction(models.Model):
    TYPES = [("expense", "Expense"), ("income", "Income"), ("transfer", "Transfer"), ("refund", "Refund"), ("adjustment", "Adjustment")]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="transactions")
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="transactions")
    destination = models.ForeignKey(Account, null=True, blank=True, on_delete=models.PROTECT, related_name="incoming_transfers")
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.SET_NULL, related_name="transactions")
    kind = models.CharField(max_length=12, choices=TYPES)
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    currency = models.CharField(max_length=3, default="USD")
    description = models.CharField(max_length=160)
    payee = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)
    tags = models.CharField(max_length=250, blank=True)
    date = models.DateField(default=timezone.localdate, db_index=True)
    source = models.CharField(max_length=16, default="manual", choices=[("manual", "Manual"), ("assistant", "AI assistant")])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        indexes = [models.Index(fields=["user", "date"], name="txn_user_date_ix"), models.Index(fields=["user", "kind", "date"], name="txn_user_kind_date_ix")]

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.account_id and self.account.user_id != self.user_id:
            raise ValidationError({"account": "Choose an account owned by this user."})
        if self.category_id and self.category.user_id != self.user_id:
            raise ValidationError({"category": "Choose a category owned by this user."})
        if self.kind == "transfer":
            if not self.destination_id:
                raise ValidationError({"destination": "A destination account is required for transfers."})
            if self.destination_id == self.account_id:
                raise ValidationError({"destination": "Choose a different destination account."})
            if self.destination.user_id != self.user_id:
                raise ValidationError({"destination": "Choose an account owned by this user."})

    def __str__(self): return f"{self.description} · {self.amount} {self.currency}"


class Budget(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="budgets")
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="budgets")
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    starts_on = models.DateField()
    ends_on = models.DateField()
    rollover = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["starts_on", "category__name"]
        constraints = [models.UniqueConstraint(fields=["user", "category", "starts_on", "ends_on"], name="uniq_budget_period_per_category")]

    @property
    def spent(self):
        currency = getattr(getattr(self.user, "profile", None), "currency", "USD")
        return Transaction.objects.filter(user=self.user, category=self.category, kind="expense", currency=currency, date__range=(self.starts_on, self.ends_on)).aggregate(v=models.Sum("amount"))["v"] or Decimal("0.00")

    @property
    def percent(self):
        if not self.amount: return 0
        return min(100, int((self.spent / self.amount) * 100))

    @property
    def remaining(self):
        return max(Decimal("0.00"), self.amount - self.spent)


class SavingsGoal(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="savings_goals")
    name = models.CharField(max_length=100)
    target_amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    target_date = models.DateField(null=True, blank=True)
    account = models.ForeignKey(Account, null=True, blank=True, on_delete=models.SET_NULL, related_name="goals")
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def saved(self):
        return self.contributions.aggregate(v=models.Sum("amount"))["v"] or Decimal("0.00")


class GoalContribution(models.Model):
    goal = models.ForeignKey(SavingsGoal, on_delete=models.CASCADE, related_name="contributions")
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    date = models.DateField(default=timezone.localdate)
    note = models.CharField(max_length=160, blank=True)


class RecurringItem(models.Model):
    TYPES = [("bill", "Bill"), ("income", "Income")]
    FREQUENCIES = [("weekly", "Weekly"), ("monthly", "Monthly"), ("yearly", "Yearly")]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="recurring_items")
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=8, choices=TYPES)
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="recurring_items")
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.SET_NULL)
    next_date = models.DateField()
    frequency = models.CharField(max_length=8, choices=FREQUENCIES, default="monthly")
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)


class Debt(models.Model):
    TYPES = [("owed", "I owe"), ("receivable", "Owed to me")]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="debts")
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=12, choices=TYPES)
    original_amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    due_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def remaining(self):
        paid = self.payments.aggregate(v=models.Sum("amount"))["v"] or Decimal("0.00")
        return max(Decimal("0.00"), self.original_amount - paid)


class DebtPayment(models.Model):
    debt = models.ForeignKey(Debt, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    account = models.ForeignKey(Account, on_delete=models.PROTECT)
    transaction = models.OneToOneField("Transaction", null=True, blank=True, on_delete=models.SET_NULL, related_name="debt_payment")
    date = models.DateField(default=timezone.localdate)
    notes = models.CharField(max_length=160, blank=True)


class Conversation(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ai_conversations")
    title = models.CharField(max_length=120, default="Money assistant")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class ChatMessage(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=12, choices=[("user", "User"), ("assistant", "Assistant")])
    content = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class AssistantRequestLog(models.Model):
    """Content-free timestamps used to enforce per-account AI usage limits."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="assistant_requests")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [models.Index(fields=["user", "created_at"], name="ai_req_user_created_ix")]


class AssistantPreference(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="assistant_preferences")
    trigger = models.CharField(max_length=120)
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.SET_NULL)
    account = models.ForeignKey(Account, null=True, blank=True, on_delete=models.SET_NULL)
    note = models.CharField(max_length=250, blank=True)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["trigger"]


class AuditEntry(models.Model):
    ACTIONS = [("create", "Created"), ("update", "Updated"), ("delete", "Deleted"), ("confirm_ai", "Confirmed AI proposal"), ("preference", "Saved assistant preference"), ("undo", "Undid a change")]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="audit_entries")
    action = models.CharField(max_length=16, choices=ACTIONS)
    entity = models.CharField(max_length=40)
    entity_id = models.CharField(max_length=40, blank=True)
    summary = models.CharField(max_length=250)
    before = models.JSONField(default=dict, blank=True)
    after = models.JSONField(default=dict, blank=True)
    source = models.CharField(max_length=16, default="user", choices=[("user", "User"), ("assistant", "AI assistant"), ("system", "System")])
    confirmed = models.BooleanField(default=True)
    undone = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
