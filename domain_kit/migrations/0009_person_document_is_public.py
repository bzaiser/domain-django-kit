from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("domain_kit", "0008_alter_domainmodulesettings_enable_accounts_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="document",
            name="is_public",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="person",
            name="is_public",
            field=models.BooleanField(default=False),
        ),
    ]
