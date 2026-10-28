from django.contrib import admin
from .models import (
    Department, Programme, AcademicYear, AttachmentPeriod, InternshipPlacement,
    LecturerAssignment, Assessment, LogbookEntry, LogbookFeedback,
    AssessmentCategory, AssessmentCriteria, GradingScale, AssessmentMark,
    FinalResult, Notification, UploadedDocument, AuditLog,
)
for model in [Department, Programme, AcademicYear, AttachmentPeriod, InternshipPlacement,
              LecturerAssignment, Assessment, LogbookEntry, LogbookFeedback,
              AssessmentCategory, AssessmentCriteria, GradingScale, AssessmentMark,
              FinalResult, Notification, UploadedDocument, AuditLog]:
    admin.site.register(model)
