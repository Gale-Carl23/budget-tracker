from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0002_assistantrequestlog"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="transaction",
            index=models.Index(
                fields=["user", "category", "currency", "kind", "date"],
                name="txn_user_cat_cur_kind_date",
            ),
        ),
        migrations.AddIndex(
            model_name="transaction",
            index=models.Index(
                fields=["user", "account"],
                name="txn_user_account_ix",
            ),
        ),
    ]
