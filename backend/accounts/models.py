from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    class Role(models.TextChoices):
        STUDENT = "student", "Student"
        LECTURER = "lecturer", "Lecturer / Assessor"
        ADMIN = "admin", "Administrator"
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.STUDENT, db_index=True)
    phone = models.CharField(max_length=30, blank=True)
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)

    def __str__(self):
        return self.get_full_name() or self.username

class StudentProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="student_profile")
    registration_number = models.CharField(max_length=40, unique=True)
    department = models.ForeignKey("core.Department", on_delete=models.PROTECT, related_name="students")
    programme = models.ForeignKey("core.Programme", on_delete=models.PROTECT, related_name="students")
    academic_year = models.ForeignKey("core.AcademicYear", on_delete=models.PROTECT, related_name="students")
    year_of_study = models.PositiveSmallIntegerField(default=3)

    def __str__(self):
        return f"{self.registration_number} — {self.user.get_full_name()}"

class LecturerProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="lecturer_profile")
    staff_number = models.CharField(max_length=40, unique=True)
    department = models.ForeignKey("core.Department", on_delete=models.PROTECT, related_name="lecturers")
    job_title = models.CharField(max_length=100, default="Lecturer")

    def __str__(self):
        return f"{self.staff_number} — {self.user.get_full_name()}"
