from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(name="Department", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)), ("name", models.CharField(max_length=140, unique=True)), ("code", models.CharField(max_length=20, unique=True)), ("is_active", models.BooleanField(default=True)),
        ]),
        migrations.CreateModel(name="AcademicYear", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)), ("label", models.CharField(max_length=30, unique=True)), ("starts_on", models.DateField()), ("ends_on", models.DateField()), ("is_current", models.BooleanField(default=False)),
        ]),
        migrations.CreateModel(name="Programme", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)), ("name", models.CharField(max_length=160)), ("code", models.CharField(max_length=30, unique=True)), ("is_active", models.BooleanField(default=True)), ("department", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="programmes", to="core.department")),
        ], options={"ordering": ["name"]}),
        migrations.CreateModel(name="AttachmentPeriod", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)), ("name", models.CharField(max_length=120)), ("starts_on", models.DateField()), ("ends_on", models.DateField()), ("registration_deadline", models.DateField(blank=True, null=True)), ("is_active", models.BooleanField(default=True)), ("academic_year", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="attachment_periods", to="core.academicyear")),
        ], options={"ordering": ["-starts_on"]}),
    ]
