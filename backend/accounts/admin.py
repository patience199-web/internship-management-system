from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, StudentProfile, LecturerProfile

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("Internship System", {"fields": ("role", "phone", "avatar")}),)
    list_display = ("username", "email", "first_name", "last_name", "role", "is_active")
    list_filter = ("role", "is_active", "is_staff")

admin.site.register(StudentProfile)
admin.site.register(LecturerProfile)
