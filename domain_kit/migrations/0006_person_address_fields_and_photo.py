from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("domain_kit", "0005_document_extracted_text"),
    ]

    operations = [
        migrations.AddField(
            model_name="address",
            name="address_addition",
            field=models.CharField(blank=True, default="", max_length=140),
        ),
        migrations.AddField(
            model_name="address",
            name="email",
            field=models.CharField(blank=True, default="", max_length=140),
        ),
        migrations.AddField(
            model_name="address",
            name="phone",
            field=models.CharField(blank=True, default="", max_length=60),
        ),
        migrations.AddField(
            model_name="address",
            name="state",
            field=models.CharField(blank=True, default="", max_length=80),
        ),
        migrations.AddField(
            model_name="person",
            name="birth_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="person",
            name="job_title",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="person",
            name="photo",
            field=models.FileField(blank=True, null=True, upload_to="domain_kit/persons/%Y/%m/"),
        ),
        migrations.AddField(
            model_name="person",
            name="salutation",
            field=models.CharField(blank=True, default="", max_length=30),
        ),
        migrations.AddField(
            model_name="person",
            name="tax_id",
            field=models.CharField(blank=True, default="", max_length=60),
        ),
        migrations.AddField(
            model_name="person",
            name="title_prefix",
            field=models.CharField(blank=True, default="", max_length=40),
        ),
        migrations.AddField(
            model_name="person",
            name="website",
            field=models.URLField(blank=True, default=""),
        ),
    ]
