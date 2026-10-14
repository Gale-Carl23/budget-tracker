import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(name="Account", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("name", models.CharField(max_length=80)), ("kind", models.CharField(choices=[("cash", "Cash"), ("checking", "Checking"), ("savings", "Savings"), ("wallet", "E-wallet"), ("credit", "Credit card")], default="checking", max_length=16)),
            ("opening_balance", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14)), ("currency", models.CharField(default="USD", max_length=3)), ("color", models.CharField(default="#78965d", max_length=7)), ("is_archived", models.BooleanField(default=False)), ("created_at", models.DateTimeField(auto_now_add=True)),
            ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="finance_accounts", to=settings.AUTH_USER_MODEL)),
        ], options={"ordering": ["name"]}),
        migrations.CreateModel(name="Category", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("name", models.CharField(max_length=64)), ("kind", models.CharField(choices=[("expense", "Expense"), ("income", "Income")], default="expense", max_length=8)), ("icon", models.CharField(default="•", max_length=12)), ("color", models.CharField(default="#91a96b", max_length=7)), ("created_at", models.DateTimeField(auto_now_add=True)),
            ("parent", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="children", to="finance.category")),
            ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="finance_categories", to=settings.AUTH_USER_MODEL)),
        ], options={"ordering": ["name"]}),
        migrations.CreateModel(name="Conversation", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("title", models.CharField(default="Money assistant", max_length=120)), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="ai_conversations", to=settings.AUTH_USER_MODEL)),
        ]),
        migrations.CreateModel(name="Debt", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("name", models.CharField(max_length=120)), ("kind", models.CharField(choices=[("owed", "I owe"), ("receivable", "Owed to me")], max_length=12)), ("original_amount", models.DecimalField(decimal_places=2, max_digits=14, validators=[django.core.validators.MinValueValidator(Decimal("0.01"))])), ("due_date", models.DateField(blank=True, null=True)), ("notes", models.TextField(blank=True)), ("created_at", models.DateTimeField(auto_now_add=True)),
            ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="debts", to=settings.AUTH_USER_MODEL)),
        ]),
        migrations.CreateModel(name="SavingsGoal", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("name", models.CharField(max_length=100)), ("target_amount", models.DecimalField(decimal_places=2, max_digits=14, validators=[django.core.validators.MinValueValidator(Decimal("0.01"))])), ("target_date", models.DateField(blank=True, null=True)), ("created_at", models.DateTimeField(auto_now_add=True)),
            ("account", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="goals", to="finance.account")), ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="savings_goals", to=settings.AUTH_USER_MODEL)),
        ]),
        migrations.CreateModel(name="Profile", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("currency", models.CharField(default="USD", max_length=3)), ("locale", models.CharField(default="en-US", max_length=20)), ("onboarding_complete", models.BooleanField(default=False)), ("created_at", models.DateTimeField(auto_now_add=True)),
            ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="profile", to=settings.AUTH_USER_MODEL)),
        ]),
        migrations.CreateModel(name="RecurringItem", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("name", models.CharField(max_length=120)), ("kind", models.CharField(choices=[("bill", "Bill"), ("income", "Income")], max_length=8)), ("amount", models.DecimalField(decimal_places=2, max_digits=14, validators=[django.core.validators.MinValueValidator(Decimal("0.01"))])), ("next_date", models.DateField()), ("frequency", models.CharField(choices=[("weekly", "Weekly"), ("monthly", "Monthly"), ("yearly", "Yearly")], default="monthly", max_length=8)), ("end_date", models.DateField(blank=True, null=True)), ("is_active", models.BooleanField(default=True)),
            ("account", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="recurring_items", to="finance.account")), ("category", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="finance.category")), ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="recurring_items", to=settings.AUTH_USER_MODEL)),
        ]),
        migrations.CreateModel(name="Transaction", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("kind", models.CharField(choices=[("expense", "Expense"), ("income", "Income"), ("transfer", "Transfer"), ("refund", "Refund"), ("adjustment", "Adjustment")], max_length=12)), ("amount", models.DecimalField(decimal_places=2, max_digits=14, validators=[django.core.validators.MinValueValidator(Decimal("0.01"))])), ("currency", models.CharField(default="USD", max_length=3)), ("description", models.CharField(max_length=160)), ("payee", models.CharField(blank=True, max_length=120)), ("notes", models.TextField(blank=True)), ("tags", models.CharField(blank=True, max_length=250)), ("date", models.DateField(db_index=True, default=django.utils.timezone.localdate)), ("source", models.CharField(choices=[("manual", "Manual"), ("assistant", "AI assistant")], default="manual", max_length=16)), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("account", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="transactions", to="finance.account")), ("category", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="transactions", to="finance.category")), ("destination", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="incoming_transfers", to="finance.account")), ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="transactions", to=settings.AUTH_USER_MODEL)),
        ], options={"ordering": ["-date", "-created_at"]}),
        migrations.CreateModel(name="GoalContribution", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("amount", models.DecimalField(decimal_places=2, max_digits=14, validators=[django.core.validators.MinValueValidator(Decimal("0.01"))])), ("date", models.DateField(default=django.utils.timezone.localdate)), ("note", models.CharField(blank=True, max_length=160)),
            ("goal", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="contributions", to="finance.savingsgoal")),
        ]),
        migrations.CreateModel(name="Budget", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("amount", models.DecimalField(decimal_places=2, max_digits=14, validators=[django.core.validators.MinValueValidator(Decimal("0.01"))])), ("starts_on", models.DateField()), ("ends_on", models.DateField()), ("rollover", models.BooleanField(default=False)), ("created_at", models.DateTimeField(auto_now_add=True)),
            ("category", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="budgets", to="finance.category")), ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="budgets", to=settings.AUTH_USER_MODEL)),
        ], options={"ordering": ["starts_on", "category__name"]}),
        migrations.CreateModel(name="DebtPayment", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("amount", models.DecimalField(decimal_places=2, max_digits=14, validators=[django.core.validators.MinValueValidator(Decimal("0.01"))])), ("date", models.DateField(default=django.utils.timezone.localdate)), ("notes", models.CharField(blank=True, max_length=160)),
            ("account", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="finance.account")), ("debt", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="payments", to="finance.debt")), ("transaction", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="debt_payment", to="finance.transaction")),
        ]),
        migrations.CreateModel(name="ChatMessage", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("role", models.CharField(choices=[("user", "User"), ("assistant", "Assistant")], max_length=12)), ("content", models.TextField()), ("metadata", models.JSONField(blank=True, default=dict)), ("created_at", models.DateTimeField(auto_now_add=True)),
            ("conversation", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="messages", to="finance.conversation")),
        ]),
        migrations.CreateModel(name="AssistantPreference", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("trigger", models.CharField(max_length=120)), ("note", models.CharField(blank=True, max_length=250)), ("enabled", models.BooleanField(default=True)), ("created_at", models.DateTimeField(auto_now_add=True)),
            ("account", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="finance.account")), ("category", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="finance.category")), ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="assistant_preferences", to=settings.AUTH_USER_MODEL)),
        ], options={"ordering": ["trigger"]}),
        migrations.CreateModel(name="AuditEntry", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("action", models.CharField(choices=[("create", "Created"), ("update", "Updated"), ("delete", "Deleted"), ("confirm_ai", "Confirmed AI proposal"), ("preference", "Saved assistant preference"), ("undo", "Undid a change")], max_length=16)), ("entity", models.CharField(max_length=40)), ("entity_id", models.CharField(blank=True, max_length=40)), ("summary", models.CharField(max_length=250)), ("before", models.JSONField(blank=True, default=dict)), ("after", models.JSONField(blank=True, default=dict)), ("source", models.CharField(choices=[("user", "User"), ("assistant", "AI assistant"), ("system", "System")], default="user", max_length=16)), ("confirmed", models.BooleanField(default=True)), ("undone", models.BooleanField(default=False)), ("created_at", models.DateTimeField(db_index=True, auto_now_add=True)),
            ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="audit_entries", to=settings.AUTH_USER_MODEL)),
        ], options={"ordering": ["-created_at"]}),
        migrations.AddConstraint(model_name="account", constraint=models.UniqueConstraint(fields=("user", "name"), name="uniq_account_name_per_user")),
        migrations.AddConstraint(model_name="category", constraint=models.UniqueConstraint(fields=("user", "name", "kind"), name="uniq_category_name_per_user")),
        migrations.AddIndex(model_name="transaction", index=models.Index(fields=["user", "date"], name="txn_user_date_ix")),
        migrations.AddIndex(model_name="transaction", index=models.Index(fields=["user", "kind", "date"], name="txn_user_kind_date_ix")),
        migrations.AddConstraint(model_name="budget", constraint=models.UniqueConstraint(fields=("user", "category", "starts_on", "ends_on"), name="uniq_budget_period_per_category")),
    ]
