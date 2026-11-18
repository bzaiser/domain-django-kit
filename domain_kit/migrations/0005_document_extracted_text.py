from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("domain_kit", "0004_document_file"),
    ]

    operations = [
        migrations.AddField(
            model_name="document",
            name="extracted_text",
            field=models.TextField(blank=True, default=""),
        ),
    ]
