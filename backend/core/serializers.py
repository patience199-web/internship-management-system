from datetime import datetime, timedelta
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import serializers
from accounts.models import StudentProfile, LecturerProfile
from .models import (
    Department, Programme, AcademicYear, AttachmentPeriod, InternshipPlacement,
    LecturerAssignment, Assessment, LogbookEntry, LogbookFeedback,
    AssessmentCategory, AssessmentCriteria, GradingScale, AssessmentMark, FinalResult,
    Notification, UploadedDocument, AuditLog,
)

User = get_user_model()
ALLOWED_UPLOAD_EXTENSIONS = {".pdf", ".doc", ".docx", ".png", ".jpg", ".jpeg"}

def validate_upload(file):
    if not file:
        return file
    name = getattr(file, "name", "").lower()
    ext = "." + name.rsplit(".", 1)[-1] if "." in name else ""
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise serializers.ValidationError("Unsupported file type. Upload PDF, DOC, DOCX, PNG or JPG files.")
    if getattr(file, "size", 0) > 10 * 1024 * 1024:
        raise serializers.ValidationError("File size must not exceed 10 MB.")
    return file

class UserSummarySerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name", "full_name", "role", "phone", "avatar", "is_active"]
        read_only_fields = fields
    def get_full_name(self, obj): return obj.get_full_name() or obj.username

class UserSelfUpdateSerializer(serializers.ModelSerializer):
    avatar = serializers.ImageField(required=False, allow_null=True, validators=[validate_upload])
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "phone", "avatar"]
    def validate_email(self, value):
        qs = User.objects.filter(email__iexact=value).exclude(pk=self.instance.pk)
        if qs.exists(): raise serializers.ValidationError("This email address is already in use.")
        return value

class UserManagementSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, min_length=8)
    full_name = serializers.SerializerMethodField()
    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name", "full_name", "role", "phone", "is_active", "password", "date_joined"]
        read_only_fields = ["id", "date_joined", "full_name"]
    def create(self, validated_data):
        password = validated_data.pop("password", None)
        if not password: raise serializers.ValidationError({"password": "A temporary password is required."})
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user
    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for key, value in validated_data.items(): setattr(instance, key, value)
        if password: instance.set_password(password)
        instance.save()
        return instance
    def get_full_name(self, obj): return obj.get_full_name() or obj.username

class DepartmentSerializer(serializers.ModelSerializer):
    class Meta: model = Department; fields = "__all__"; read_only_fields = ["id", "created_at", "updated_at"]
class ProgrammeSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source="department.name", read_only=True)
    class Meta: model = Programme; fields = "__all__"; read_only_fields = ["id", "created_at", "updated_at", "department_name"]
class AcademicYearSerializer(serializers.ModelSerializer):
    class Meta: model = AcademicYear; fields = "__all__"; read_only_fields = ["id", "created_at", "updated_at"]
class AttachmentPeriodSerializer(serializers.ModelSerializer):
    academic_year_label = serializers.CharField(source="academic_year.label", read_only=True)
    class Meta: model = AttachmentPeriod; fields = "__all__"; read_only_fields = ["id", "created_at", "updated_at", "academic_year_label"]
    def validate(self, attrs):
        start = attrs.get("starts_on", getattr(self.instance, "starts_on", None)); end = attrs.get("ends_on", getattr(self.instance, "ends_on", None))
        if start and end and end < start: raise serializers.ValidationError({"ends_on": "End date must not be before start date."})
        return attrs

class StudentProfileSerializer(serializers.ModelSerializer):
    user_details = UserSummarySerializer(source="user", read_only=True)
    department_name = serializers.CharField(source="department.name", read_only=True)
    programme_name = serializers.CharField(source="programme.name", read_only=True)
    academic_year_label = serializers.CharField(source="academic_year.label", read_only=True)
    class Meta:
        model = StudentProfile
        fields = ["id", "user", "user_details", "registration_number", "department", "department_name", "programme", "programme_name", "academic_year", "academic_year_label", "year_of_study"]
    def validate_user(self, value):
        if value.role != "student": raise serializers.ValidationError("The selected user must have the student role.")
        if hasattr(value, "student_profile") and (not self.instance or self.instance.user_id != value.id): raise serializers.ValidationError("This user already has a student profile.")
        return value

class LecturerProfileSerializer(serializers.ModelSerializer):
    user_details = UserSummarySerializer(source="user", read_only=True)
    department_name = serializers.CharField(source="department.name", read_only=True)
    class Meta:
        model = LecturerProfile
        fields = ["id", "user", "user_details", "staff_number", "department", "department_name", "job_title"]
    def validate_user(self, value):
        if value.role != "lecturer": raise serializers.ValidationError("The selected user must have the lecturer role.")
        if hasattr(value, "lecturer_profile") and (not self.instance or self.instance.user_id != value.id): raise serializers.ValidationError("This user already has a lecturer profile.")
        return value

class InternshipPlacementSerializer(serializers.ModelSerializer):
    student_details = StudentProfileSerializer(source="student", read_only=True)
    company = serializers.CharField(source="company_name", read_only=True)
    period_name = serializers.CharField(source="attachment_period.name", read_only=True)
    reviewed_by_name = serializers.CharField(source="reviewed_by.get_full_name", read_only=True, default="")
    acceptance_letter = serializers.FileField(required=False, allow_null=True, validators=[validate_upload])
    class Meta:
        model = InternshipPlacement
        fields = "__all__"
        extra_kwargs = {"student": {"required": False}}
        read_only_fields = ["id", "created_at", "updated_at", "status", "review_feedback", "reviewed_by", "reviewed_at", "student_details", "company", "period_name", "reviewed_by_name"]
    def validate(self, attrs):
        request = self.context.get("request")
        student = attrs.get("student", getattr(self.instance, "student", None))
        period = attrs.get("attachment_period", getattr(self.instance, "attachment_period", None))
        start = attrs.get("start_date", getattr(self.instance, "start_date", None)); end = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if request and request.user.role == "student":
            if not hasattr(request.user, "student_profile"): raise serializers.ValidationError("Your account does not have a student profile yet.")
            student = request.user.student_profile
            attrs["student"] = student
            if self.instance and self.instance.status not in ("draft", "rejected"):
                raise serializers.ValidationError("Only draft or rejected placements can be edited.")
        if start and end and end < start: raise serializers.ValidationError({"end_date": "End date must be on or after the start date."})
        if student and period:
            active = InternshipPlacement.objects.filter(student=student, attachment_period=period).exclude(status__in=["rejected", "completed"])
            if self.instance: active = active.exclude(pk=self.instance.pk)
            if active.exists(): raise serializers.ValidationError({"attachment_period": "An active placement already exists for this student and attachment period."})
        return attrs

class LecturerAssignmentSerializer(serializers.ModelSerializer):
    student_details = StudentProfileSerializer(source="student", read_only=True)
    lecturer_details = LecturerProfileSerializer(source="lecturer", read_only=True)
    period_name = serializers.CharField(source="attachment_period.name", read_only=True)
    class Meta: model = LecturerAssignment; fields = "__all__"; read_only_fields = ["id", "created_at", "updated_at", "assigned_by", "student_details", "lecturer_details", "period_name"]
    def validate(self, attrs):
        if attrs.get("student") and attrs.get("lecturer") and attrs["student"].department_id != attrs["lecturer"].department_id:
            # Cross-department assignments are permitted, but flagging this should be an administrative choice.
            pass
        return attrs

class AssessmentSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="placement.student.user.get_full_name", read_only=True)
    registration_number = serializers.CharField(source="placement.student.registration_number", read_only=True)
    company_name = serializers.CharField(source="placement.company_name", read_only=True)
    lecturer_name = serializers.CharField(source="lecturer.user.get_full_name", read_only=True)
    end_time = serializers.SerializerMethodField()
    class Meta: model = Assessment; fields = "__all__"; read_only_fields = ["id", "created_at", "updated_at", "completed_at", "reschedule_requested", "reschedule_reason", "reschedule_requested_at", "student_name", "registration_number", "company_name", "lecturer_name", "end_time"]
    def get_end_time(self, obj):
        dt = datetime.combine(obj.assessment_date, obj.start_time) + timedelta(minutes=obj.duration_minutes)
        return dt.time().strftime("%H:%M")
    def validate(self, attrs):
        request = self.context.get("request")
        placement = attrs.get("placement", getattr(self.instance, "placement", None))
        lecturer = attrs.get("lecturer", getattr(self.instance, "lecturer", None))
        date = attrs.get("assessment_date", getattr(self.instance, "assessment_date", None))
        start = attrs.get("start_time", getattr(self.instance, "start_time", None))
        duration = attrs.get("duration_minutes", getattr(self.instance, "duration_minutes", 60))
        if request and request.user.role == "lecturer":
            profile = getattr(request.user, "lecturer_profile", None)
            if not profile: raise serializers.ValidationError("Your lecturer profile is not configured.")
            if lecturer and lecturer.id != profile.id: raise serializers.ValidationError({"lecturer": "You can only schedule assessments under your own account."})
            attrs["lecturer"] = profile
            if placement and not LecturerAssignment.objects.filter(lecturer=profile, student=placement.student, attachment_period=placement.attachment_period, is_active=True).exists():
                raise serializers.ValidationError({"placement": "You can only schedule assessments for students assigned to you."})
        if placement and lecturer and date and start:
            assignment_ok = LecturerAssignment.objects.filter(lecturer=lecturer, student=placement.student, attachment_period=placement.attachment_period, is_active=True).exists()
            if not assignment_ok and not (request and (request.user.role == "admin" or request.user.is_superuser)):
                raise serializers.ValidationError({"placement": "The lecturer must be assigned to this student and attachment period."})
            start_dt = datetime.combine(date, start); end_dt = start_dt + timedelta(minutes=duration)
            for existing in Assessment.objects.filter(lecturer=lecturer, assessment_date=date).exclude(status="cancelled"):
                if self.instance and existing.pk == self.instance.pk: continue
                e_start = datetime.combine(existing.assessment_date, existing.start_time)
                e_end = e_start + timedelta(minutes=existing.duration_minutes)
                if start_dt < e_end and e_start < end_dt:
                    raise serializers.ValidationError({"start_time": f"This lecturer already has an assessment from {existing.start_time.strftime('%H:%M')} on this date."})
        return attrs

class LogbookEntrySerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="placement.student.user.get_full_name", read_only=True)
    registration_number = serializers.CharField(source="placement.student.registration_number", read_only=True)
    feedback_items = serializers.SerializerMethodField()
    attachment = serializers.FileField(required=False, allow_null=True, validators=[validate_upload])
    class Meta:
        model = LogbookEntry
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at", "revision_number", "status", "submitted_at", "submitted_by", "student_name", "registration_number", "feedback_items"]
    def get_feedback_items(self, obj): return LogbookFeedbackSerializer(obj.feedback_items.all(), many=True).data
    def validate(self, attrs):
        request = self.context.get("request")
        placement = attrs.get("placement", getattr(self.instance, "placement", None))
        start = attrs.get("period_start", getattr(self.instance, "period_start", None)); end = attrs.get("period_end", getattr(self.instance, "period_end", None))
        if start and end and end < start: raise serializers.ValidationError({"period_end": "Period end must be on or after period start."})
        if request and request.user.role == "student":
            profile = getattr(request.user, "student_profile", None)
            if not profile or not placement or placement.student_id != profile.id: raise serializers.ValidationError({"placement": "You can only submit logbooks for your own placement."})
            if placement.status not in ("approved", "in_progress"): raise serializers.ValidationError({"placement": "Logbooks are available after a placement is approved."})
            if self.instance and self.instance.status not in ("draft", "requires_revision"):
                raise serializers.ValidationError("Only draft or revision-requested logbooks can be edited.")
        return attrs

class LogbookFeedbackSerializer(serializers.ModelSerializer):
    lecturer_name = serializers.CharField(source="lecturer.user.get_full_name", read_only=True)
    week_number = serializers.IntegerField(source="entry.week_number", read_only=True)
    student_name = serializers.CharField(source="entry.placement.student.user.get_full_name", read_only=True)
    class Meta: model = LogbookFeedback; fields = "__all__"; read_only_fields = ["id", "created_at", "updated_at", "lecturer", "lecturer_name", "week_number", "student_name"]

class AssessmentCategorySerializer(serializers.ModelSerializer):
    criteria_count = serializers.SerializerMethodField()
    class Meta: model = AssessmentCategory; fields = "__all__"; read_only_fields = ["id", "created_at", "updated_at", "criteria_count"]
    def get_criteria_count(self, obj): return obj.criteria.count()
class GradingScaleSerializer(serializers.ModelSerializer):
    class Meta: model = GradingScale; fields = "__all__"; read_only_fields = ["id", "created_at", "updated_at"]
    def validate(self, attrs):
        low = attrs.get("minimum_score", getattr(self.instance, "minimum_score", 0)); high = attrs.get("maximum_score", getattr(self.instance, "maximum_score", 100))
        if high < low: raise serializers.ValidationError({"maximum_score": "Maximum score must be greater than or equal to minimum score."})
        return attrs

class AssessmentCriteriaSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    class Meta: model = AssessmentCriteria; fields = "__all__"; read_only_fields = ["id", "created_at", "updated_at", "category_name"]
    def validate(self, attrs):
        weight = attrs.get("weighting", getattr(self.instance, "weighting", 0))
        if weight < 0 or weight > 100: raise serializers.ValidationError({"weighting": "Weighting must be between 0 and 100."})
        return attrs

class AssessmentMarkSerializer(serializers.ModelSerializer):
    criterion_name = serializers.CharField(source="criterion.name", read_only=True)
    max_marks = serializers.DecimalField(source="criterion.max_marks", max_digits=7, decimal_places=2, read_only=True)
    weighting = serializers.DecimalField(source="criterion.weighting", max_digits=5, decimal_places=2, read_only=True)
    student_name = serializers.CharField(source="assessment.placement.student.user.get_full_name", read_only=True)
    class Meta: model = AssessmentMark; fields = "__all__"; read_only_fields = ["id", "created_at", "updated_at", "entered_by", "criterion_name", "max_marks", "weighting", "student_name"]
    def validate(self, attrs):
        assessment = attrs.get("assessment", getattr(self.instance, "assessment", None)); criterion = attrs.get("criterion", getattr(self.instance, "criterion", None))
        mark = attrs.get("mark_awarded", getattr(self.instance, "mark_awarded", None))
        if criterion and mark is not None and mark > criterion.max_marks: raise serializers.ValidationError({"mark_awarded": f"Mark cannot exceed {criterion.max_marks}."})
        request = self.context.get("request")
        if request and request.user.role == "lecturer":
            profile = getattr(request.user, "lecturer_profile", None)
            if not profile or not assessment or assessment.lecturer_id != profile.id: raise serializers.ValidationError("You can only mark your own assessments.")
        if assessment and hasattr(assessment.placement, "final_result") and assessment.placement.final_result.status in ("finalized", "published"):
            if not (request and (request.user.role == "admin" or request.user.is_superuser)): raise serializers.ValidationError("Finalized results are locked. Ask an administrator to authorize a change.")
        return attrs

class FinalResultSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="placement.student.user.get_full_name", read_only=True)
    registration_number = serializers.CharField(source="placement.student.registration_number", read_only=True)
    company_name = serializers.CharField(source="placement.company_name", read_only=True)
    components = serializers.SerializerMethodField()
    class Meta: model = FinalResult; fields = "__all__"; read_only_fields = ["id", "created_at", "updated_at", "final_score", "grade", "status", "finalized_by", "finalized_at", "published_at", "student_name", "registration_number", "company_name", "components"]
    def get_components(self, obj):
        # Publish only marks explicitly finalized by the assessor; draft marks are not official results.
        marks = AssessmentMark.objects.filter(assessment__placement=obj.placement, is_final=True).select_related("criterion", "criterion__category", "assessment")
        return [{"assessment_id": m.assessment_id, "assessment_type": m.assessment.assessment_type, "criterion": m.criterion.name, "category": m.criterion.category.name, "mark_awarded": str(m.mark_awarded), "max_marks": str(m.criterion.max_marks), "weighting": str(m.criterion.weighting), "comments": m.comments} for m in marks]
    def validate(self, attrs):
        if self.instance and "placement" in attrs and attrs["placement"].pk != self.instance.placement_id:
            raise serializers.ValidationError({"placement": "A result record cannot be moved to another placement."})
        return attrs

class NotificationSerializer(serializers.ModelSerializer):
    is_read = serializers.BooleanField(read_only=True)
    class Meta: model = Notification; fields = ["id", "title", "message", "kind", "link", "is_read", "read_at", "created_at"]; read_only_fields = fields
class UploadedDocumentSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.CharField(source="uploaded_by.get_full_name", read_only=True)
    file = serializers.FileField(validators=[validate_upload])
    class Meta: model = UploadedDocument; fields = "__all__"; read_only_fields = ["id", "created_at", "updated_at", "uploaded_by", "uploaded_by_name"]
class AuditLogSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.get_full_name", read_only=True, default="System")
    class Meta: model = AuditLog; fields = "__all__"; read_only_fields = fields
