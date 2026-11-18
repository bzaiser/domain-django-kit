from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("domain_kit", "0003_alter_assetitem_asset_type_alter_category_purpose_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="document",
            name="file",
            field=models.FileField(blank=True, null=True, upload_to="domain_kit/documents/%Y/%m/"),
        ),
    ]
