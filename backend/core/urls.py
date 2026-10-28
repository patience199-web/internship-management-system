from rest_framework.routers import DefaultRouter
from .views import (
    UserViewSet, DepartmentViewSet, ProgrammeViewSet, AcademicYearViewSet,
    AttachmentPeriodViewSet, StudentProfileViewSet, LecturerProfileViewSet,
    PlacementViewSet, AssignmentViewSet, AssessmentViewSet, LogbookViewSet,
    LogbookFeedbackViewSet, AssessmentCategoryViewSet, AssessmentCriteriaViewSet,
    GradingScaleViewSet, AssessmentMarkViewSet, FinalResultViewSet,
    NotificationViewSet, UploadedDocumentViewSet, AuditLogViewSet,
)

router = DefaultRouter()
router.register("users", UserViewSet)
router.register("departments", DepartmentViewSet)
router.register("programmes", ProgrammeViewSet)
router.register("academic-years", AcademicYearViewSet)
router.register("attachment-periods", AttachmentPeriodViewSet)
router.register("student-profiles", StudentProfileViewSet)
router.register("lecturer-profiles", LecturerProfileViewSet)
router.register("placements", PlacementViewSet)
router.register("assignments", AssignmentViewSet)
router.register("assessments", AssessmentViewSet)
router.register("logbooks", LogbookViewSet)
router.register("logbook-feedback", LogbookFeedbackViewSet)
router.register("assessment-categories", AssessmentCategoryViewSet)
router.register("assessment-criteria", AssessmentCriteriaViewSet)
router.register("grading-scales", GradingScaleViewSet)
router.register("assessment-marks", AssessmentMarkViewSet)
router.register("final-results", FinalResultViewSet)
router.register("notifications", NotificationViewSet)
router.register("documents", UploadedDocumentViewSet)
router.register("audit-logs", AuditLogViewSet)
urlpatterns = router.urls
