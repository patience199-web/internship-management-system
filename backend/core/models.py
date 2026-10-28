from decimal import Decimal
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone

class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        abstract = True

class Department(TimeStampedModel):
    name = models.CharField(max_length=140, unique=True)
    code = models.CharField(max_length=20, unique=True)
    is_active = models.BooleanField(default=True)
    def __str__(self): return f"{self.code} — {self.name}"

class Programme(TimeStampedModel):
    name = models.CharField(max_length=160)
    code = models.CharField(max_length=30, unique=True)
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="programmes")
    is_active = models.BooleanField(default=True)
    class Meta: ordering = ["name"]
    def __str__(self): return self.name

class AcademicYear(TimeStampedModel):
    label = models.CharField(max_length=30, unique=True)
    starts_on = models.DateField()
    ends_on = models.DateField()
    is_current = models.BooleanField(default=False)
    def __str__(self): return self.label

class AttachmentPeriod(TimeStampedModel):
    name = models.CharField(max_length=120)
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.PROTECT, related_name="attachment_periods")
    starts_on = models.DateField()
    ends_on = models.DateField()
    registration_deadline = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    class Meta: ordering = ["-starts_on"]
    def __str__(self): return f"{self.name} ({self.academic_year})"

class InternshipPlacement(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT="draft", "Draft"
        SUBMITTED="submitted", "Submitted"
        UNDER_REVIEW="under_review", "Under Review"
        APPROVED="approved", "Approved"
        REJECTED="rejected", "Rejected"
        IN_PROGRESS="in_progress", "In Progress"
        COMPLETED="completed", "Completed"
    student = models.ForeignKey("accounts.StudentProfile", on_delete=models.CASCADE, related_name="placements")
    attachment_period = models.ForeignKey(AttachmentPeriod, on_delete=models.PROTECT, related_name="placements")
    company_name = models.CharField(max_length=180)
    industry = models.CharField(max_length=120, blank=True)
    physical_address = models.TextField()
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=40, blank=True)
    supervisor_name = models.CharField(max_length=140)
    supervisor_position = models.CharField(max_length=120, blank=True)
    supervisor_contact = models.CharField(max_length=80, blank=True)
    position_title = models.CharField(max_length=140)
    duties = models.TextField()
    start_date = models.DateField()
    end_date = models.DateField()
    acceptance_letter = models.FileField(upload_to="placements/%Y/%m/", blank=True, null=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    review_feedback = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_placements")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "attachment_period"], name="core_intern_status_9e5f5e_idx"), models.Index(fields=["student", "attachment_period"], name="core_intern_student_0f86c2_idx")]
    def __str__(self): return f"{self.company_name} — {self.student}"
    def clean(self):
        from django.core.exceptions import ValidationError
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "End date must be on or after the start date."})

class LecturerAssignment(TimeStampedModel):
    student = models.ForeignKey("accounts.StudentProfile", on_delete=models.CASCADE, related_name="lecturer_assignments")
    lecturer = models.ForeignKey("accounts.LecturerProfile", on_delete=models.CASCADE, related_name="student_assignments")
    attachment_period = models.ForeignKey(AttachmentPeriod, on_delete=models.PROTECT, related_name="lecturer_assignments")
    assigned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="created_assignments")
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["student", "attachment_period"], condition=models.Q(is_active=True), name="unique_active_student_period_assignment")]
        ordering = ["student__user__last_name"]
    def __str__(self): return f"{self.student} → {self.lecturer}"

class Assessment(TimeStampedModel):
    class Status(models.TextChoices):
        SCHEDULED="scheduled", "Scheduled"
        COMPLETED="completed", "Completed"
        RESCHEDULED="rescheduled", "Rescheduled"
        CANCELLED="cancelled", "Cancelled"
    class Mode(models.TextChoices):
        ONSITE="onsite", "On-site"
        ONLINE="online", "Online"
    placement = models.ForeignKey(InternshipPlacement, on_delete=models.CASCADE, related_name="assessments")
    lecturer = models.ForeignKey("accounts.LecturerProfile", on_delete=models.PROTECT, related_name="assessments")
    assessment_type = models.CharField(max_length=120, default="Supervisory visit")
    assessment_date = models.DateField()
    start_time = models.TimeField()
    duration_minutes = models.PositiveSmallIntegerField(default=60, validators=[MinValueValidator(15), MaxValueValidator(480)])
    mode = models.CharField(max_length=12, choices=Mode.choices, default=Mode.ONSITE)
    location = models.CharField(max_length=220, blank=True)
    meeting_url = models.URLField(blank=True)
    instructions = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=14, choices=Status.choices, default=Status.SCHEDULED, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    reschedule_requested = models.BooleanField(default=False)
    reschedule_reason = models.TextField(blank=True)
    reschedule_requested_at = models.DateTimeField(null=True, blank=True)
    class Meta:
        ordering = ["assessment_date", "start_time"]
        indexes = [models.Index(fields=["assessment_date", "status"], name="core_asses_assessm_6a3cc5_idx")]
    def __str__(self): return f"{self.assessment_type} — {self.placement.student} ({self.assessment_date})"

class LogbookEntry(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT="draft", "Draft"
        SUBMITTED="submitted", "Submitted"
        UNDER_REVIEW="under_review", "Under Review"
        APPROVED="approved", "Approved"
        REQUIRES_REVISION="requires_revision", "Requires Revision"
    placement = models.ForeignKey(InternshipPlacement, on_delete=models.CASCADE, related_name="logbooks")
    week_number = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(60)])
    revision_number = models.PositiveSmallIntegerField(default=1)
    period_start = models.DateField()
    period_end = models.DateField()
    activities = models.TextField()
    skills_acquired = models.TextField(blank=True)
    challenges = models.TextField(blank=True)
    lessons_learned = models.TextField(blank=True)
    hours_worked = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"), validators=[MinValueValidator(0), MaxValueValidator(168)])
    student_comments = models.TextField(blank=True)
    attachment = models.FileField(upload_to="logbooks/%Y/%m/", blank=True, null=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="logbook_submissions")
    class Meta:
        ordering = ["-period_start", "-revision_number"]
        constraints = [models.UniqueConstraint(fields=["placement", "week_number", "revision_number"], name="unique_logbook_revision")]
    def clean(self):
        from django.core.exceptions import ValidationError
        if self.period_end and self.period_start and self.period_end < self.period_start:
            raise ValidationError({"period_end": "Period end must be on or after period start."})
    def __str__(self): return f"Week {self.week_number} — {self.placement.student} (v{self.revision_number})"

class LogbookFeedback(TimeStampedModel):
    entry = models.ForeignKey(LogbookEntry, on_delete=models.CASCADE, related_name="feedback_items")
    lecturer = models.ForeignKey("accounts.LecturerProfile", on_delete=models.PROTECT, related_name="logbook_feedback")
    comments = models.TextField()
    requests_revision = models.BooleanField(default=False)
    def __str__(self): return f"Feedback for {self.entry}"

class AssessmentCategory(TimeStampedModel):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    is_required = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    def __str__(self): return self.name

class GradingScale(TimeStampedModel):
    label = models.CharField(max_length=30, unique=True)
    minimum_score = models.DecimalField(max_digits=5, decimal_places=2, validators=[MinValueValidator(0), MaxValueValidator(100)])
    maximum_score = models.DecimalField(max_digits=5, decimal_places=2, validators=[MinValueValidator(0), MaxValueValidator(100)])
    description = models.CharField(max_length=180, blank=True)
    order = models.PositiveSmallIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    class Meta: ordering = ["-minimum_score"]
    def clean(self):
        from django.core.exceptions import ValidationError
        if self.maximum_score < self.minimum_score:
            raise ValidationError({"maximum_score": "Maximum score must be greater than or equal to minimum score."})
    def __str__(self): return f"{self.label} ({self.minimum_score}–{self.maximum_score})"

class AssessmentCriteria(TimeStampedModel):
    category = models.ForeignKey(AssessmentCategory, on_delete=models.CASCADE, related_name="criteria")
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    max_marks = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal("100.00"), validators=[MinValueValidator(Decimal("0.01"))])
    weighting = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"), validators=[MinValueValidator(0), MaxValueValidator(100)])
    is_required = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    class Meta:
        ordering = ["category__name", "name"]
        constraints = [models.UniqueConstraint(fields=["category", "name"], name="unique_criterion_per_category")]
    def __str__(self): return self.name

class AssessmentMark(TimeStampedModel):
    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, related_name="marks")
    criterion = models.ForeignKey(AssessmentCriteria, on_delete=models.PROTECT, related_name="marks")
    mark_awarded = models.DecimalField(max_digits=7, decimal_places=2, validators=[MinValueValidator(0)])
    comments = models.TextField(blank=True)
    is_final = models.BooleanField(default=False)
    entered_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="entered_marks")
    class Meta:
        constraints = [models.UniqueConstraint(fields=["assessment", "criterion"], name="unique_mark_for_assessment_criterion")]
        ordering = ["criterion__category__name", "criterion__name"]
    def clean(self):
        from django.core.exceptions import ValidationError
        if self.mark_awarded is not None and self.criterion_id and self.mark_awarded > self.criterion.max_marks:
            raise ValidationError({"mark_awarded": f"Mark cannot exceed {self.criterion.max_marks}."})
    def __str__(self): return f"{self.criterion}: {self.mark_awarded}"

class FinalResult(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT="draft", "Draft"
        PENDING_REVIEW="pending_review", "Pending Review"
        FINALIZED="finalized", "Finalized"
        PUBLISHED="published", "Published"
    placement = models.OneToOneField(InternshipPlacement, on_delete=models.CASCADE, related_name="final_result")
    final_score = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    grade = models.CharField(max_length=30, blank=True)
    lecturer_comments = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    finalized_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="finalized_results")
    finalized_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    def __str__(self): return f"Result — {self.placement.student} ({self.status})"

class Notification(TimeStampedModel):
    class Kind(models.TextChoices):
        INFO="info", "Information"
        SUCCESS="success", "Success"
        WARNING="warning", "Warning"
        ASSESSMENT="assessment", "Assessment"
        FEEDBACK="feedback", "Feedback"
        RESULT="result", "Result"
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField(max_length=180)
    message = models.TextField()
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.INFO)
    link = models.CharField(max_length=240, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    class Meta: ordering = ["-created_at"]
    @property
    def is_read(self): return self.read_at is not None
    def __str__(self): return f"{self.title} — {self.recipient}"

class UploadedDocument(TimeStampedModel):
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="uploaded_documents")
    placement = models.ForeignKey(InternshipPlacement, on_delete=models.CASCADE, related_name="documents")
    logbook_entry = models.ForeignKey(LogbookEntry, on_delete=models.CASCADE, null=True, blank=True, related_name="documents")
    title = models.CharField(max_length=180)
    file = models.FileField(upload_to="documents/%Y/%m/")
    def __str__(self): return self.title

class AuditLog(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="audit_entries")
    action = models.CharField(max_length=100)
    entity_type = models.CharField(max_length=100)
    entity_id = models.CharField(max_length=64, blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    class Meta: ordering = ["-created_at"]
    def __str__(self): return f"{self.action} {self.entity_type} #{self.entity_id}"
