import csv
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from accounts.models import StudentProfile, LecturerProfile
from .models import (
    Department, Programme, AcademicYear, AttachmentPeriod, InternshipPlacement,
    LecturerAssignment, Assessment, LogbookEntry, LogbookFeedback,
    AssessmentCategory, AssessmentCriteria, GradingScale, AssessmentMark,
    FinalResult, Notification, UploadedDocument, AuditLog,
)
from .permissions import IsAdmin, IsAdminOrReadOnly, IsLecturerOrAdmin
from .serializers import (
    UserSummarySerializer, UserManagementSerializer, UserSelfUpdateSerializer, StudentProfileSerializer,
    LecturerProfileSerializer, DepartmentSerializer, ProgrammeSerializer,
    AcademicYearSerializer, AttachmentPeriodSerializer, InternshipPlacementSerializer,
    LecturerAssignmentSerializer, AssessmentSerializer, LogbookEntrySerializer,
    LogbookFeedbackSerializer, AssessmentCategorySerializer, AssessmentCriteriaSerializer,
    GradingScaleSerializer, AssessmentMarkSerializer, FinalResultSerializer,
    NotificationSerializer, UploadedDocumentSerializer, AuditLogSerializer,
)

User = get_user_model()

def is_admin(user): return bool(user and user.is_authenticated and (user.is_superuser or user.role == "admin"))
def lecturer_profile(user): return getattr(user, "lecturer_profile", None)
def student_profile(user): return getattr(user, "student_profile", None)
def audit(actor, action, obj, details=None):
    AuditLog.objects.create(actor=actor if getattr(actor, "is_authenticated", False) else None, action=action,
                            entity_type=obj.__class__.__name__, entity_id=str(getattr(obj, "pk", "")), details=details or {})
def notify(user, title, message, kind="info", link=""):
    if user:
        Notification.objects.create(recipient=user, title=title, message=message, kind=kind, link=link)
def assigned_placements(user):
    profile = lecturer_profile(user)
    if not profile: return InternshipPlacement.objects.none()
    from functools import reduce
    from operator import or_
    assignments = LecturerAssignment.objects.filter(lecturer=profile, is_active=True).values_list("student_id", "attachment_period_id")
    conditions = [Q(student_id=student_id, attachment_period_id=period_id) for student_id, period_id in assignments]
    if not conditions: return InternshipPlacement.objects.none()
    return InternshipPlacement.objects.filter(reduce(or_, conditions))
def scoped_placements(user):
    if is_admin(user): return InternshipPlacement.objects.all()
    if user.role == "student":
        p = student_profile(user)
        return InternshipPlacement.objects.filter(student=p) if p else InternshipPlacement.objects.none()
    return assigned_placements(user)

def scoped_assessments(user):
    qs = Assessment.objects.select_related("placement__student__user", "lecturer__user", "placement__attachment_period")
    if is_admin(user): return qs
    if user.role == "lecturer":
        profile = lecturer_profile(user)
        return qs.filter(lecturer=profile) if profile else qs.none()
    p = student_profile(user)
    return qs.filter(placement__student=p) if p else qs.none()

def scoped_logbooks(user):
    qs = LogbookEntry.objects.select_related("placement__student__user", "placement__attachment_period")
    if is_admin(user): return qs
    if user.role == "lecturer": return qs.filter(placement__in=assigned_placements(user))
    p = student_profile(user)
    return qs.filter(placement__student=p) if p else qs.none()

class CurrentUserView(APIView):
    def get_payload(self, request):
        data = UserSummarySerializer(request.user).data
        data["permissions"] = {"is_admin": is_admin(request.user), "role": request.user.role}
        if request.user.role == "student" and student_profile(request.user):
            from .serializers import StudentProfileSerializer
            data["profile"] = StudentProfileSerializer(student_profile(request.user)).data
        elif request.user.role == "lecturer" and lecturer_profile(request.user):
            data["profile"] = LecturerProfileSerializer(lecturer_profile(request.user)).data
        return data
    def get(self, request): return Response(self.get_payload(request))
    def patch(self, request):
        serializer = UserSelfUpdateSerializer(request.user, data=request.data, partial=True, context={"request":request})
        serializer.is_valid(raise_exception=True); serializer.save()
        audit(request.user, "profile_updated", request.user)
        return Response(self.get_payload(request))

class DashboardView(APIView):
    def get(self, request):
        user = request.user
        if is_admin(user):
            students = StudentProfile.objects.select_related("user", "department", "programme")
            placements = InternshipPlacement.objects.select_related("student__user", "attachment_period")
            assessments = Assessment.objects.all()
            logbooks = LogbookEntry.objects.all()
            cards = [
                {"label":"Registered students", "value": students.count(), "icon":"users", "tone":"blue"},
                {"label":"Lecturers", "value": LecturerProfile.objects.count(), "icon":"graduation-cap", "tone":"violet"},
                {"label":"Pending placements", "value": placements.filter(status__in=["submitted", "under_review"]).count(), "icon":"clipboard-check", "tone":"amber"},
                {"label":"Students on attachment", "value": placements.filter(status__in=["approved", "in_progress"]).count(), "icon":"briefcase-business", "tone":"green"},
                {"label":"Scheduled assessments", "value": assessments.filter(status__in=["scheduled", "rescheduled"]).count(), "icon":"calendar-days", "tone":"blue"},
                {"label":"Logbooks to review", "value": logbooks.filter(status__in=["submitted", "under_review"]).count(), "icon":"book-open-check", "tone":"rose"},
            ]
            department_chart = list(students.values("department__name").annotate(total=Count("id")).order_by("department__name"))
            status_chart = list(placements.values("status").annotate(total=Count("id")).order_by("status"))
            pending_results = FinalResult.objects.filter(status__in=["draft", "pending_review"]).count()
            cards.append({"label":"Results to finalize", "value": pending_results, "icon":"award", "tone":"violet"})
            recent = AuditLog.objects.select_related("actor")[:8]
            activity = [{"id": x.id, "title": x.action.replace("_", " ").title(), "description": f"{x.entity_type} #{x.entity_id}", "time": x.created_at, "actor": x.actor.get_full_name() if x.actor else "System"} for x in recent]
            return Response({"role":"admin", "cards":cards, "charts":{"departments":[{"label":x["department__name"] or "Unassigned","value":x["total"]} for x in department_chart], "placements":[{"label":x["status"].replace("_"," ").title(),"value":x["total"]} for x in status_chart]}, "recent_activity":activity})
        if user.role == "lecturer":
            profile = lecturer_profile(user)
            assignment_qs = LecturerAssignment.objects.filter(lecturer=profile, is_active=True) if profile else LecturerAssignment.objects.none()
            placements = assigned_placements(user)
            assessments = scoped_assessments(user)
            logbooks = scoped_logbooks(user)
            cards = [
                {"label":"Assigned students", "value":assignment_qs.values("student_id").distinct().count(), "icon":"users", "tone":"blue"},
                {"label":"Upcoming assessments", "value":assessments.filter(status__in=["scheduled","rescheduled"], assessment_date__gte=timezone.localdate()).count(), "icon":"calendar-days", "tone":"violet"},
                {"label":"Assessments completed", "value":assessments.filter(status="completed").count(), "icon":"check-circle-2", "tone":"green"},
                {"label":"Logbooks to review", "value":logbooks.filter(status__in=["submitted","under_review"]).count(), "icon":"book-open-check", "tone":"amber"},
                {"label":"Reschedule requests", "value":assessments.filter(reschedule_requested=True).count(), "icon":"calendar-clock", "tone":"rose"},
            ]
            cards.append({"label":"Results awaiting review", "value":FinalResult.objects.filter(placement__in=placements, status__in=["draft","pending_review"]).count(), "icon":"award", "tone":"rose"})
            students = StudentProfile.objects.filter(lecturer_assignments__in=assignment_qs).distinct().select_related("user", "department", "programme")
            student_rows = [{"id":s.id,"name":s.user.get_full_name(),"registration_number":s.registration_number,"department":s.department.name,"programme":s.programme.name,"placement_status":(s.placements.filter(attachment_period__is_active=True).order_by("-created_at").first().status if s.placements.filter(attachment_period__is_active=True).exists() else "not registered")} for s in students[:12]]
            return Response({"role":"lecturer", "cards":cards, "students":student_rows, "upcoming_assessments":AssessmentSerializer(assessments.filter(status__in=["scheduled","rescheduled"], assessment_date__gte=timezone.localdate()).order_by("assessment_date","start_time")[:6], many=True).data})
        profile = student_profile(user)
        placements = InternshipPlacement.objects.filter(student=profile) if profile else InternshipPlacement.objects.none()
        placement = placements.order_by("-created_at").first()
        assessments = scoped_assessments(user)
        logbooks = scoped_logbooks(user)
        result = FinalResult.objects.filter(placement=placement, status="published").first() if placement else None
        upcoming = assessments.filter(status__in=["scheduled","rescheduled"], assessment_date__gte=timezone.localdate()).order_by("assessment_date","start_time")
        steps = ["Placement registration", "Placement approval", "Logbook submissions", "Assessments", "Final result"]
        completed = 0
        if placement and placement.status not in ("draft","submitted","under_review","rejected"): completed += 1
        if placement and placement.status in ("approved","in_progress","completed"): completed += 1
        if logbooks.filter(status="approved").exists(): completed += 1
        if assessments.filter(status="completed").exists(): completed += 1
        if result: completed += 1
        cards = [
            {"label":"Placement status", "value":placement.get_status_display() if placement else "Not registered", "icon":"briefcase-business", "tone":"blue"},
            {"label":"Progress", "value":f"{round(completed/len(steps)*100)}%", "icon":"chart-no-axes-combined", "tone":"green"},
            {"label":"Logbook entries", "value":logbooks.count(), "icon":"book-open", "tone":"violet"},
            {"label":"Awaiting review", "value":logbooks.filter(status__in=["submitted","under_review"]).count(), "icon":"clock-3", "tone":"amber"},
            {"label":"Upcoming assessments", "value":upcoming.count(), "icon":"calendar-days", "tone":"rose"},
            {"label":"Final score", "value":str(result.final_score) if result and result.final_score is not None else "Not published", "icon":"award", "tone":"blue"},
        ]
        notifications = Notification.objects.filter(recipient=user)[:5]
        return Response({"role":"student", "cards":cards, "progress":{"completed":completed,"total":len(steps),"steps":steps}, "placement":InternshipPlacementSerializer(placement, context={"request":request}).data if placement else None, "upcoming_assessments":AssessmentSerializer(upcoming[:6], many=True).data, "recent_notifications":NotificationSerializer(notifications, many=True).data})

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().order_by("last_name", "first_name")
    serializer_class = UserManagementSerializer
    permission_classes = [IsAdmin]
    search_fields = ["username", "email", "first_name", "last_name"]
    filterset_fields = ["role", "is_active"]
    ordering_fields = ["username", "first_name", "last_name", "date_joined"]
    def perform_create(self, serializer):
        obj = serializer.save(); audit(self.request.user, "user_created", obj, {"role":obj.role})
    def perform_update(self, serializer):
        obj = serializer.save(); audit(self.request.user, "user_updated", obj, {"role":obj.role})

class DepartmentViewSet(viewsets.ModelViewSet):
    queryset = Department.objects.all(); serializer_class = DepartmentSerializer; permission_classes = [IsAdminOrReadOnly]; search_fields = ["name","code"]; filterset_fields = ["is_active"]
class ProgrammeViewSet(viewsets.ModelViewSet):
    queryset = Programme.objects.select_related("department").all(); serializer_class = ProgrammeSerializer; permission_classes = [IsAdminOrReadOnly]; search_fields = ["name","code","department__name"]; filterset_fields = ["department","is_active"]
class AcademicYearViewSet(viewsets.ModelViewSet):
    queryset = AcademicYear.objects.all(); serializer_class = AcademicYearSerializer; permission_classes = [IsAdminOrReadOnly]; search_fields = ["label"]; filterset_fields = ["is_current"]
class AttachmentPeriodViewSet(viewsets.ModelViewSet):
    queryset = AttachmentPeriod.objects.select_related("academic_year").all(); serializer_class = AttachmentPeriodSerializer; permission_classes = [IsAdminOrReadOnly]; search_fields = ["name","academic_year__label"]; filterset_fields = ["academic_year","is_active"]

class StudentProfileViewSet(viewsets.ModelViewSet):
    queryset = StudentProfile.objects.select_related("user","department","programme","academic_year").all(); serializer_class = StudentProfileSerializer
    search_fields = ["registration_number","user__first_name","user__last_name","user__email"]
    filterset_fields = ["department","programme","academic_year","year_of_study"]
    def get_queryset(self):
        qs = super().get_queryset(); user = self.request.user
        if is_admin(user): return qs
        if user.role == "lecturer":
            profile = lecturer_profile(user)
            return qs.filter(lecturer_assignments__lecturer=profile, lecturer_assignments__is_active=True).distinct() if profile else qs.none()
        p = student_profile(user)
        return qs.filter(pk=p.pk) if p else qs.none()
    def get_permissions(self):
        if self.action in ("list", "retrieve"): return [IsAuthenticated()]
        return [IsAdmin()]

class LecturerProfileViewSet(viewsets.ModelViewSet):
    queryset = LecturerProfile.objects.select_related("user","department").all(); serializer_class = LecturerProfileSerializer; search_fields = ["staff_number","user__first_name","user__last_name"]; filterset_fields = ["department"]
    def get_permissions(self): return [IsAuthenticated()] if self.action in ("list","retrieve") else [IsAdmin()]
    def get_queryset(self):
        qs = super().get_queryset()
        if is_admin(self.request.user): return qs
        if self.request.user.role == "lecturer": return qs.filter(user=self.request.user)
        p = student_profile(self.request.user)
        if not p: return qs.none()
        return qs.filter(student_assignments__student=p, student_assignments__is_active=True).distinct()

class PlacementViewSet(viewsets.ModelViewSet):
    serializer_class = InternshipPlacementSerializer; parser_classes = [MultiPartParser, FormParser, JSONParser]
    queryset = InternshipPlacement.objects.select_related("student__user","student__department","student__programme","attachment_period","reviewed_by").all()
    search_fields = ["company_name","student__registration_number","student__user__first_name","student__user__last_name"]
    filterset_fields = ["status","attachment_period","student__department","student__programme"]
    ordering_fields = ["created_at","start_date","end_date","status"]
    def get_queryset(self): return scoped_placements(self.request.user).select_related("student__user","student__department","student__programme","attachment_period","reviewed_by")
    def get_permissions(self):
        if self.action in ("review",): return [IsAdmin()]
        if self.action in ("list","retrieve","submit"): return [IsAuthenticated()]
        return [IsAuthenticated()]
    def perform_create(self, serializer):
        user = self.request.user
        if user.role == "student":
            p = student_profile(user)
            if not p: raise ValidationError("Your account does not have a student profile.")
            obj = serializer.save(student=p)
        elif is_admin(user): obj = serializer.save()
        else: raise PermissionDenied("Lecturers cannot create placements on behalf of students.")
        audit(user, "placement_created", obj)
    def perform_update(self, serializer):
        user = self.request.user; obj = self.get_object()
        if not is_admin(user) and not (user.role == "student" and student_profile(user) and obj.student_id == student_profile(user).id): raise PermissionDenied()
        if not is_admin(user) and obj.status not in ("draft","rejected"): raise PermissionDenied("Only draft or rejected placements can be edited.")
        obj = serializer.save(); audit(user, "placement_updated", obj)
    def perform_destroy(self, instance):
        if not is_admin(self.request.user) and not (self.request.user.role == "student" and instance.student_id == getattr(student_profile(self.request.user), "id", None) and instance.status == "draft"):
            raise PermissionDenied("You cannot delete this placement.")
        audit(self.request.user, "placement_deleted", instance); instance.delete()
    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        placement = self.get_object()
        if request.user.role != "student" or placement.student_id != getattr(student_profile(request.user), "id", None): raise PermissionDenied("Only the owner can submit this placement.")
        if placement.status not in ("draft","rejected"): raise ValidationError("This placement cannot be submitted in its current state.")
        placement.status = "submitted"; placement.save(update_fields=["status","updated_at"])
        for admin in User.objects.filter(Q(role="admin") | Q(is_superuser=True), is_active=True): notify(admin,"Placement submitted",f"{placement.student.user.get_full_name()} submitted a placement at {placement.company_name}.","info","/placements")
        audit(request.user,"placement_submitted",placement)
        return Response(self.get_serializer(placement).data)
    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        if not is_admin(request.user): raise PermissionDenied("Only an administrator can change this placement status.")
        placement = self.get_object(); new_status = request.data.get("status")
        allowed = {"under_review", "in_progress", "completed"}
        if new_status not in allowed: raise ValidationError({"status":"Choose under_review, in_progress or completed."})
        placement.status = new_status; placement.save(update_fields=["status","updated_at"])
        notify(placement.student.user, "Placement status updated", f"Your placement status is now {placement.get_status_display()}.", "info", "/placement")
        audit(request.user, "placement_status_changed", placement, {"status":new_status})
        return Response(self.get_serializer(placement).data)
    @action(detail=True, methods=["post"])
    def review(self, request, pk=None):
        placement = self.get_object()
        decision = request.data.get("decision")
        feedback = str(request.data.get("feedback", "")).strip()
        if decision not in ("approved","rejected"): raise ValidationError({"decision":"Choose approved or rejected."})
        if decision == "rejected" and not feedback: raise ValidationError({"feedback":"Feedback is required when rejecting a placement."})
        placement.status = decision; placement.review_feedback = feedback; placement.reviewed_by = request.user; placement.reviewed_at = timezone.now(); placement.save()
        notify(placement.student.user, f"Placement {decision}", feedback or f"Your placement at {placement.company_name} has been approved.", "success" if decision == "approved" else "warning", "/placement")
        audit(request.user, f"placement_{decision}", placement, {"feedback":feedback})
        return Response(self.get_serializer(placement).data)

class AssignmentViewSet(viewsets.ModelViewSet):
    serializer_class = LecturerAssignmentSerializer; queryset = LecturerAssignment.objects.select_related("student__user","lecturer__user","attachment_period").all(); search_fields = ["student__registration_number","student__user__first_name","student__user__last_name","lecturer__user__first_name","lecturer__user__last_name"]; filterset_fields = ["lecturer","student","attachment_period","is_active"]
    def get_queryset(self):
        qs = super().get_queryset(); user = self.request.user
        if is_admin(user): return qs
        if user.role == "lecturer": return qs.filter(lecturer=lecturer_profile(user)) if lecturer_profile(user) else qs.none()
        p = student_profile(user)
        return qs.filter(student=p) if p else qs.none()
    def get_permissions(self): return [IsAdmin()] if self.action not in ("list","retrieve") else [IsAuthenticated()]
    def perform_create(self, serializer):
        obj = serializer.save(assigned_by=self.request.user); notify(obj.student.user,"Lecturer assigned",f"{obj.lecturer.user.get_full_name()} has been assigned as your academic supervisor.","success","/placement"); audit(self.request.user,"lecturer_assigned",obj)
    def perform_update(self, serializer):
        obj = serializer.save(); audit(self.request.user,"lecturer_assignment_updated",obj)

class AssessmentViewSet(viewsets.ModelViewSet):
    serializer_class = AssessmentSerializer; queryset = Assessment.objects.select_related("placement__student__user","lecturer__user").all(); search_fields = ["placement__student__registration_number","placement__student__user__first_name","placement__student__user__last_name","assessment_type"]; filterset_fields = ["status","lecturer","assessment_date","placement__attachment_period"]; ordering_fields = ["assessment_date","start_time","status"]
    def get_queryset(self): return scoped_assessments(self.request.user)
    def get_permissions(self):
        if self.action in ("list", "retrieve", "request_reschedule"): return [IsAuthenticated()]
        if self.action in ("create", "update", "partial_update", "destroy"): return [IsLecturerOrAdmin()]
        return [IsAuthenticated()]
    def perform_create(self, serializer):
        obj = serializer.save(); notify(obj.placement.student.user,"Assessment scheduled",f"{obj.assessment_type} is scheduled for {obj.assessment_date} at {obj.start_time}.","assessment","/assessments"); audit(self.request.user,"assessment_scheduled",obj)
    def perform_update(self, serializer):
        previous = serializer.instance
        schedule_changed = ("assessment_date" in serializer.validated_data and serializer.validated_data["assessment_date"] != previous.assessment_date) or ("start_time" in serializer.validated_data and serializer.validated_data["start_time"] != previous.start_time)
        obj = serializer.save()
        if schedule_changed and obj.reschedule_requested:
            obj.reschedule_requested = False
            obj.reschedule_reason = ""
            obj.reschedule_requested_at = None
            obj.save(update_fields=["reschedule_requested", "reschedule_reason", "reschedule_requested_at", "updated_at"])
        notify(obj.placement.student.user,"Assessment updated",f"Your assessment has been updated to {obj.assessment_date} at {obj.start_time}.","assessment","/assessments")
        audit(self.request.user,"assessment_updated",obj,{"schedule_changed":schedule_changed})
    @action(detail=True, methods=["post"], url_path="request-reschedule")
    def request_reschedule(self, request, pk=None):
        assessment = self.get_object()
        profile = student_profile(request.user)
        if request.user.role != "student" or not profile or assessment.placement.student_id != profile.id:
            raise PermissionDenied("Only the student assigned to this assessment can request a reschedule.")
        if assessment.status not in ("scheduled", "rescheduled"):
            raise ValidationError("Only upcoming scheduled assessments can be rescheduled.")
        if assessment.reschedule_requested:
            raise ValidationError("A reschedule request is already awaiting a decision.")
        reason = str(request.data.get("reason", "")).strip()
        if len(reason) < 8:
            raise ValidationError({"reason":"Please provide a short reason (at least 8 characters)."})
        assessment.reschedule_requested = True
        assessment.reschedule_reason = reason
        assessment.reschedule_requested_at = timezone.now()
        assessment.save(update_fields=["reschedule_requested", "reschedule_reason", "reschedule_requested_at", "updated_at"])
        notify(assessment.lecturer.user,"Assessment reschedule requested",f"{profile.user.get_full_name()} requested a new time for {assessment.assessment_type} on {assessment.assessment_date}. Reason: {reason}","warning","/assessments")
        for admin in User.objects.filter(Q(role="admin") | Q(is_superuser=True), is_active=True):
            notify(admin,"Assessment reschedule request",f"{profile.user.get_full_name()} requested a new time for {assessment.assessment_type} on {assessment.assessment_date}.","warning","/assessments")
        audit(request.user,"assessment_reschedule_requested",assessment,{"reason":reason})
        return Response(self.get_serializer(assessment).data)
    def perform_destroy(self, instance):
        notify(instance.placement.student.user,"Assessment cancelled",f"Your {instance.assessment_type} scheduled for {instance.assessment_date} has been cancelled.","warning","/assessments"); audit(self.request.user,"assessment_deleted",instance); instance.delete()

class LogbookViewSet(viewsets.ModelViewSet):
    serializer_class = LogbookEntrySerializer; parser_classes = [MultiPartParser, FormParser, JSONParser]; queryset = LogbookEntry.objects.select_related("placement__student__user").all(); search_fields = ["placement__student__registration_number","placement__student__user__first_name","activities"]; filterset_fields = ["status","week_number","placement"]
    def get_queryset(self): return scoped_logbooks(self.request.user)
    def get_permissions(self):
        if self.action in ("list", "retrieve"): return [IsAuthenticated()]
        if self.action == "feedback": return [IsLecturerOrAdmin()]
        if self.action in ("create", "update", "partial_update", "destroy", "submit", "revise"): return [IsAuthenticated()]
        return [IsAuthenticated()]
    def perform_create(self, serializer):
        if self.request.user.role != "student" and not is_admin(self.request.user): raise PermissionDenied("Only students can create logbook entries.")
        obj = serializer.save(); audit(self.request.user,"logbook_created",obj)
    def perform_update(self, serializer):
        if self.request.user.role != "student" and not is_admin(self.request.user): raise PermissionDenied("Only the student can edit a draft logbook.")
        obj = self.get_object()
        if obj.status != "draft" and not is_admin(self.request.user): raise PermissionDenied("Create a new revision to preserve the submitted logbook history.")
        obj = serializer.save(); audit(self.request.user,"logbook_updated",obj)
    def perform_destroy(self, instance):
        if not is_admin(self.request.user) and not (self.request.user.role == "student" and instance.placement.student_id == getattr(student_profile(self.request.user),"id",None) and instance.status == "draft"):
            raise PermissionDenied("Only draft logbooks can be deleted by a student.")
        audit(self.request.user,"logbook_deleted",instance); instance.delete()
    @action(detail=True, methods=["post"])
    def revise(self, request, pk=None):
        old = self.get_object()
        if request.user.role != "student" or old.placement.student_id != getattr(student_profile(request.user),"id",None): raise PermissionDenied("Only the owner can create a revision.")
        if old.status != "requires_revision": raise ValidationError("A new revision can only be created when corrections have been requested.")
        latest_revision = LogbookEntry.objects.filter(placement=old.placement, week_number=old.week_number).order_by("-revision_number").values_list("revision_number", flat=True).first() or old.revision_number
        new = LogbookEntry.objects.create(placement=old.placement, week_number=old.week_number, revision_number=latest_revision+1,
            period_start=old.period_start, period_end=old.period_end, activities=old.activities, skills_acquired=old.skills_acquired,
            challenges=old.challenges, lessons_learned=old.lessons_learned, hours_worked=old.hours_worked,
            student_comments=old.student_comments, attachment=old.attachment, status="draft")
        audit(request.user,"logbook_revision_created",new,{"previous_revision":old.revision_number})
        return Response(self.get_serializer(new).data, status=status.HTTP_201_CREATED)
    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        entry = self.get_object()
        if request.user.role != "student" or entry.placement.student_id != getattr(student_profile(request.user),"id",None): raise PermissionDenied("Only the student can submit this logbook.")
        if entry.status not in ("draft","requires_revision"): raise ValidationError("This entry cannot be submitted in its current state.")
        latest = LogbookEntry.objects.filter(placement=entry.placement, week_number=entry.week_number).exclude(pk=entry.pk).order_by("-revision_number").first()
        if latest and entry.revision_number <= latest.revision_number: raise ValidationError("Create a new revision to preserve the previous submission.")
        entry.status="submitted"; entry.submitted_at=timezone.now(); entry.submitted_by=request.user; entry.save()
        assignment = LecturerAssignment.objects.filter(student=entry.placement.student, attachment_period=entry.placement.attachment_period, is_active=True).select_related("lecturer__user").first()
        if assignment: notify(assignment.lecturer.user,"Logbook submitted",f"{entry.placement.student.user.get_full_name()} submitted week {entry.week_number} for review.","feedback","/logbooks")
        audit(request.user,"logbook_submitted",entry)
        return Response(self.get_serializer(entry).data)
    @action(detail=True, methods=["post"])
    def feedback(self, request, pk=None):
        entry = self.get_object(); profile = lecturer_profile(request.user)
        if request.user.role != "admin" and (not profile or not LecturerAssignment.objects.filter(lecturer=profile,student=entry.placement.student,attachment_period=entry.placement.attachment_period,is_active=True).exists()): raise PermissionDenied("You are not assigned to this student.")
        comments = str(request.data.get("comments", "")).strip(); revision = bool(request.data.get("requests_revision", False))
        if not comments: raise ValidationError({"comments":"Feedback comments are required."})
        if not profile: raise ValidationError("An active lecturer profile is required to provide feedback.")
        feedback = LogbookFeedback.objects.create(entry=entry, lecturer=profile, comments=comments, requests_revision=revision)
        entry.status = "requires_revision" if revision else "approved"; entry.save(update_fields=["status","updated_at"])
        notify(entry.placement.student.user,"Logbook feedback received",comments,"warning" if revision else "success","/logbooks")
        audit(request.user,"logbook_feedback_added",entry,{"requests_revision":revision})
        return Response(LogbookFeedbackSerializer(feedback).data, status=status.HTTP_201_CREATED)

class LogbookFeedbackViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = LogbookFeedbackSerializer; queryset = LogbookFeedback.objects.select_related("entry__placement__student__user","lecturer__user").all()
    def get_queryset(self):
        qs = super().get_queryset(); user = self.request.user
        if is_admin(user): return qs
        if user.role == "lecturer": return qs.filter(lecturer=lecturer_profile(user)) if lecturer_profile(user) else qs.none()
        p = student_profile(user)
        return qs.filter(entry__placement__student=p) if p else qs.none()

class AssessmentCategoryViewSet(viewsets.ModelViewSet):
    queryset = AssessmentCategory.objects.prefetch_related("criteria").all(); serializer_class = AssessmentCategorySerializer; permission_classes = [IsAdminOrReadOnly]; search_fields = ["name"]
class AssessmentCriteriaViewSet(viewsets.ModelViewSet):
    queryset = AssessmentCriteria.objects.select_related("category").all(); serializer_class = AssessmentCriteriaSerializer; permission_classes = [IsAdminOrReadOnly]; search_fields = ["name","category__name"]; filterset_fields = ["category","is_active","is_required"]
class GradingScaleViewSet(viewsets.ModelViewSet):
    queryset = GradingScale.objects.all(); serializer_class = GradingScaleSerializer; permission_classes = [IsAdminOrReadOnly]; search_fields = ["label"]; filterset_fields = ["is_active"]

class AssessmentMarkViewSet(viewsets.ModelViewSet):
    serializer_class = AssessmentMarkSerializer; queryset = AssessmentMark.objects.select_related("assessment__placement__student__user","assessment__lecturer__user","criterion__category").all(); filterset_fields = ["assessment","criterion","is_final"]; search_fields = ["assessment__placement__student__registration_number","criterion__name"]
    def get_queryset(self):
        qs = super().get_queryset(); user = self.request.user
        if is_admin(user): return qs
        if user.role == "lecturer": return qs.filter(assessment__lecturer=lecturer_profile(user)) if lecturer_profile(user) else qs.none()
        p = student_profile(user)
        return qs.filter(assessment__placement__student=p, assessment__placement__final_result__status="published") if p else qs.none()
    def get_permissions(self):
        if self.action in ("list", "retrieve"): return [IsAuthenticated()]
        return [IsLecturerOrAdmin()]
    def _reopen_result_after_mark_change(self, placement):
        try: result = placement.final_result
        except FinalResult.DoesNotExist: return
        if result.status not in ("finalized", "published"): return
        previous_status = result.status
        result.final_score = None; result.grade = ""; result.status = "draft"
        result.finalized_by = None; result.finalized_at = None; result.published_at = None
        result.save(update_fields=["final_score", "grade", "status", "finalized_by", "finalized_at", "published_at", "updated_at"])
        notify(placement.student.user, "Attachment result reopened for review", "An authorized mark change was made. Your official result will be available again after recalculation and publication.", "warning", "/results")
        audit(self.request.user, "result_reopened_after_mark_change", result, {"previous_status": previous_status})
    def perform_create(self, serializer):
        obj = serializer.save(entered_by=self.request.user)
        if is_admin(self.request.user): self._reopen_result_after_mark_change(obj.assessment.placement)
        audit(self.request.user,"assessment_mark_saved",obj,{"mark":str(obj.mark_awarded)})
    def perform_update(self, serializer):
        previous_placement = serializer.instance.assessment.placement
        obj = serializer.save()
        if is_admin(self.request.user):
            self._reopen_result_after_mark_change(previous_placement)
            if obj.assessment.placement_id != previous_placement.id: self._reopen_result_after_mark_change(obj.assessment.placement)
        audit(self.request.user,"assessment_mark_updated",obj,{"mark":str(obj.mark_awarded)})

class FinalResultViewSet(viewsets.ModelViewSet):
    serializer_class = FinalResultSerializer; queryset = FinalResult.objects.select_related("placement__student__user","placement__attachment_period").all(); filterset_fields = ["status","placement__attachment_period"]; search_fields = ["placement__student__registration_number","placement__student__user__first_name","placement__company_name"]
    def get_queryset(self):
        qs = super().get_queryset(); user = self.request.user
        if is_admin(user): return qs
        if user.role == "lecturer": return qs.filter(placement__in=assigned_placements(user))
        p = student_profile(user)
        return qs.filter(placement__student=p,status="published") if p else qs.none()
    def get_permissions(self): return [IsAuthenticated()]
    def perform_create(self, serializer):
        if not (is_admin(self.request.user) or self.request.user.role == "lecturer"): raise PermissionDenied()
        placement = serializer.validated_data.get("placement")
        if self.request.user.role == "lecturer" and placement not in assigned_placements(self.request.user): raise PermissionDenied("You are not assigned to this placement.")
        result = serializer.save(); audit(self.request.user,"result_created",result)
    def perform_update(self, serializer):
        if not (is_admin(self.request.user) or self.request.user.role == "lecturer"): raise PermissionDenied()
        result = self.get_object()
        if result.status in ("finalized","published") and not is_admin(self.request.user): raise PermissionDenied("Only an administrator can change a finalized result.")
        result = serializer.save(); audit(self.request.user,"result_updated",result)
    @action(detail=True, methods=["post"])
    def finalize(self, request, pk=None):
        if not is_admin(request.user): raise PermissionDenied("Only an administrator can finalize official results.")
        result = self.get_object(); criteria = AssessmentCriteria.objects.filter(is_active=True).select_related("category")
        criteria_list = list(criteria); total_weight = sum((c.weighting for c in criteria_list), Decimal("0"))
        if not criteria_list: raise ValidationError("Configure assessment criteria before finalizing results.")
        if total_weight != Decimal("100.00"): raise ValidationError({"weighting":f"Active criterion weightings must total 100. Current total: {total_weight}."})
        marks = AssessmentMark.objects.filter(assessment__placement=result.placement, is_final=True).select_related("criterion")
        scores_by_criterion = {}
        for mark in marks:
            scores_by_criterion.setdefault(mark.criterion_id, []).append(mark.mark_awarded / mark.criterion.max_marks)
        missing = [c.name for c in criteria_list if c.is_required and not scores_by_criterion.get(c.id)]
        if missing: raise ValidationError({"marks":"Required criteria are missing final marks: " + ", ".join(missing)})
        score = Decimal("0")
        for criterion in criteria_list:
            ratios = scores_by_criterion.get(criterion.id)
            if not ratios: continue
            average_ratio = sum(ratios, Decimal("0")) / Decimal(len(ratios))
            score += average_ratio * criterion.weighting
        score = score.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        grade = GradingScale.objects.filter(is_active=True, minimum_score__lte=score, maximum_score__gte=score).order_by("-minimum_score").first()
        result.final_score = score; result.grade = grade.label if grade else ""; result.status = "finalized"; result.finalized_by = request.user; result.finalized_at = timezone.now(); result.save()
        audit(request.user,"result_finalized",result,{"score":str(score),"grade":result.grade})
        return Response(self.get_serializer(result).data)
    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        if not is_admin(request.user): raise PermissionDenied("Only an administrator can publish official results.")
        result = self.get_object()
        if result.status != "finalized": raise ValidationError("Finalize the result before publishing it.")
        result.status = "published"; result.published_at = timezone.now(); result.save(update_fields=["status","published_at","updated_at"])
        notify(result.placement.student.user,"Final attachment result published",f"Your final attachment score is {result.final_score}. Open Results to view the breakdown.","result","/results")
        audit(request.user,"result_published",result)
        return Response(self.get_serializer(result).data)

class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificationSerializer; queryset = Notification.objects.all(); filterset_fields = ["kind"]
    def get_queryset(self): return Notification.objects.filter(recipient=self.request.user)
    @action(detail=False, methods=["post"])
    def mark_all_read(self, request):
        count = Notification.objects.filter(recipient=request.user,read_at__isnull=True).update(read_at=timezone.now())
        return Response({"updated":count})
    @action(detail=True, methods=["post"])
    def mark_read(self, request, pk=None):
        item=self.get_object()
        if not item.read_at: item.read_at=timezone.now(); item.save(update_fields=["read_at","updated_at"])
        return Response(self.get_serializer(item).data)

class UploadedDocumentViewSet(viewsets.ModelViewSet):
    serializer_class = UploadedDocumentSerializer; parser_classes = [MultiPartParser,FormParser,JSONParser]; queryset = UploadedDocument.objects.select_related("placement__student__user","uploaded_by").all()
    def get_queryset(self):
        qs=super().get_queryset(); user=self.request.user
        if is_admin(user): return qs
        return qs.filter(placement__in=scoped_placements(user))
    def perform_create(self, serializer):
        placement = serializer.validated_data.get("placement")
        if not placement or not scoped_placements(self.request.user).filter(pk=placement.pk).exists(): raise PermissionDenied("You cannot upload documents to this placement.")
        obj=serializer.save(uploaded_by=self.request.user)
        audit(self.request.user,"document_uploaded",obj)

class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AuditLog.objects.select_related("actor").all(); serializer_class = AuditLogSerializer; permission_classes = [IsAdmin]; search_fields = ["action","entity_type","entity_id","actor__username"]; filterset_fields = ["action","entity_type"]

class ReportExportView(APIView):
    def get(self, request, report_type):
        user = request.user
        if not user.is_authenticated: raise PermissionDenied()
        kind = report_type.lower().replace(".csv", "").replace(".pdf", "")
        fmt = request.query_params.get("format", "csv").lower()
        if report_type.endswith(".pdf"): fmt="pdf"
        if report_type.endswith(".csv"): fmt="csv"
        if fmt not in ("csv","pdf"): raise ValidationError("Format must be csv or pdf.")
        if kind in ("placements", "placement-register", "placement-approvals"):
            rows = scoped_placements(user).select_related("student__user","student__department","student__programme","attachment_period")
            headers=["Registration number","Student","Department","Programme","Company","Position","Attachment period","Start date","End date","Status"]
            data=[[x.student.registration_number,x.student.user.get_full_name(),x.student.department.name,x.student.programme.name,x.company_name,x.position_title,x.attachment_period.name,x.start_date,x.end_date,x.get_status_display()] for x in rows]
        elif kind in ("assessments","assessment-schedule"):
            rows=scoped_assessments(user).select_related("placement__student__user","lecturer__user")
            headers=["Student","Registration number","Assessment","Lecturer","Date","Start time","Duration minutes","Mode","Status"]
            data=[[x.placement.student.user.get_full_name(),x.placement.student.registration_number,x.assessment_type,x.lecturer.user.get_full_name(),x.assessment_date,x.start_time,x.duration_minutes,x.get_mode_display(),x.get_status_display()] for x in rows]
        elif kind in ("logbooks","logbook-submissions"):
            rows=scoped_logbooks(user).select_related("placement__student__user")
            headers=["Student","Registration number","Week","Period start","Period end","Hours worked","Status","Submitted at"]
            data=[[x.placement.student.user.get_full_name(),x.placement.student.registration_number,x.week_number,x.period_start,x.period_end,x.hours_worked,x.get_status_display(),x.submitted_at or ""] for x in rows]
        elif kind in ("results","final-results","assessment-marks"):
            rows=FinalResult.objects.select_related("placement__student__user")
            if not is_admin(user):
                if user.role == "lecturer": rows=rows.filter(placement__in=assigned_placements(user))
                else: rows=rows.filter(placement__student=student_profile(user),status="published")
            headers=["Student","Registration number","Company","Final score","Grade","Status","Published at"]
            data=[[x.placement.student.user.get_full_name(),x.placement.student.registration_number,x.placement.company_name,x.final_score or "",x.grade,x.get_status_display(),x.published_at or ""] for x in rows]
        elif kind == "students":
            students=StudentProfile.objects.select_related("user","department","programme")
            if not is_admin(user):
                if user.role == "lecturer": students=students.filter(lecturer_assignments__lecturer=lecturer_profile(user),lecturer_assignments__is_active=True).distinct()
                else: students=students.filter(user=user)
            headers=["Registration number","Student","Email","Department","Programme","Year of study"]
            data=[[x.registration_number,x.user.get_full_name(),x.user.email,x.department.name,x.programme.name,x.year_of_study] for x in students]
        else: raise ValidationError("Unknown report. Use placements, assessments, logbooks, results or students.")
        if fmt == "csv":
            response=HttpResponse(content_type="text/csv; charset=utf-8")
            response["Content-Disposition"]=f'attachment; filename="internship-{kind}.csv"'
            writer=csv.writer(response); writer.writerow(headers); writer.writerows(data)
            return response
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import landscape, A4
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
            from reportlab.lib.styles import getSampleStyleSheet
            buff=BytesIO(); doc=SimpleDocTemplate(buff,pagesize=landscape(A4),rightMargin=24,leftMargin=24,topMargin=28,bottomMargin=28)
            styles=getSampleStyleSheet(); story=[Paragraph(f"Internship Management System — {kind.replace('-', ' ').title()}",styles["Title"]),Spacer(1,12)]
            table=Table([headers]+[[str(v) for v in r] for r in data],repeatRows=1)
            table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#1e40af")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),7),("GRID",(0,0),(-1,-1),0.35,colors.HexColor("#dbe3ef")),("VALIGN",(0,0),(-1,-1),"TOP"),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#f5f8fc")]),("LEFTPADDING",(0,0),(-1,-1),5),("RIGHTPADDING",(0,0),(-1,-1),5)]))
            story.append(table); doc.build(story); response=HttpResponse(buff.getvalue(),content_type="application/pdf"); response["Content-Disposition"]=f'attachment; filename="internship-{kind}.pdf"'; return response
        except ImportError: raise ValidationError("PDF export dependency is missing. Install the requirements.txt packages.")

class ProtectedMediaView(APIView):
    """Serve uploaded files only to authenticated users authorized to see the related record."""
    permission_classes = [IsAuthenticated]
    def get(self, request, file_path):
        import mimetypes
        from pathlib import Path
        from django.conf import settings
        from django.http import FileResponse, Http404
        root = Path(settings.MEDIA_ROOT).resolve()
        target = (root / file_path).resolve()
        if not target.is_relative_to(root) or not target.is_file(): raise Http404()
        user = request.user
        allowed = False
        for placement in InternshipPlacement.objects.filter(acceptance_letter=file_path):
            if scoped_placements(user).filter(pk=placement.pk).exists(): allowed = True; break
        if not allowed:
            for entry in LogbookEntry.objects.filter(attachment=file_path):
                if scoped_logbooks(user).filter(pk=entry.pk).exists(): allowed = True; break
        if not allowed:
            for doc in UploadedDocument.objects.filter(file=file_path):
                if scoped_placements(user).filter(pk=doc.placement_id).exists(): allowed = True; break
        if not allowed and getattr(user, "avatar", None) and user.avatar.name == file_path:
            allowed = True
        if not allowed: raise PermissionDenied("You do not have permission to access this file.")
        content_type, _ = mimetypes.guess_type(str(target))
        response = FileResponse(target.open("rb"), content_type=content_type or "application/octet-stream")
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Disposition"] = "inline" if content_type in ("application/pdf","image/png","image/jpeg") else "attachment"
        return response
