from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0003_transaction_query_indexes"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="BillNotification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("due_date", models.DateField()),
                ("days_before", models.PositiveSmallIntegerField(choices=[(7, "7 days"), (3, "3 days"), (1, "1 day")])),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("currency", models.CharField(default="USD", max_length=3)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("read_at", models.DateTimeField(blank=True, null=True)),
                ("email_sent", models.BooleanField(default=False)),
                ("email_attempts", models.PositiveSmallIntegerField(default=0)),
                ("recurring_item", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notifications", to="finance.recurringitem")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="bill_notifications", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["read_at", "due_date", "-created_at"]},
        ),
        migrations.AddConstraint(
            model_name="billnotification",
            constraint=models.UniqueConstraint(fields=("recurring_item", "due_date", "days_before"), name="uniq_bill_notice_occurrence"),
        ),
    ]
