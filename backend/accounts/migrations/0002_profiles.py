from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [("accounts", "0001_initial"), ("core", "0001_initial")]
    operations = [
        migrations.CreateModel(name="LecturerProfile", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("staff_number", models.CharField(max_length=40, unique=True)), ("job_title", models.CharField(default="Lecturer", max_length=100)),
            ("department", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="lecturers", to="core.department")),
            ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="lecturer_profile", to="accounts.user")),
        ]),
        migrations.CreateModel(name="StudentProfile", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("registration_number", models.CharField(max_length=40, unique=True)), ("year_of_study", models.PositiveSmallIntegerField(default=3)),
            ("academic_year", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="students", to="core.academicyear")),
            ("department", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="students", to="core.department")),
            ("programme", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="students", to="core.programme")),
            ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="student_profile", to="accounts.user")),
        ]),
    ]
