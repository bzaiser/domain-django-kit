from django.db import migrations, models


def create_initial_django_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    for name in ("Gast", "Mitarbeiter", "Personalverantwortlicher"):
        Group.objects.get_or_create(name=name)


class Migration(migrations.Migration):
    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("domain_kit", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="role",
            name="custom_color",
            field=models.CharField(blank=True, default="", max_length=16),
        ),
        migrations.AddField(
            model_name="status",
            name="custom_color",
            field=models.CharField(blank=True, default="", max_length=16),
        ),
        migrations.RunPython(create_initial_django_groups, migrations.RunPython.noop),
    ]
