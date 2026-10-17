from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0004_billnotification"),
    ]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="email_verified",
            field=models.BooleanField(default=True),
        ),
        migrations.CreateModel(
            name="LoginThrottle",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key_hash", models.CharField(max_length=64, unique=True)),
                ("window_started", models.DateTimeField()),
                ("failures", models.PositiveSmallIntegerField(default=0)),
                ("locked_until", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.AddIndex(
            model_name="loginthrottle",
            index=models.Index(fields=["updated_at"], name="login_throttle_updated_ix"),
        ),
    ]
