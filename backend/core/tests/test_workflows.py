from datetime import date, time
from decimal import Decimal
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from accounts.models import StudentProfile, LecturerProfile
from core.models import (
    Department, Programme, AcademicYear, AttachmentPeriod, InternshipPlacement,
    LecturerAssignment, Assessment, LogbookEntry, AssessmentCategory,
    AssessmentCriteria, AssessmentMark, FinalResult, GradingScale,
)

User = get_user_model()

class InternshipWorkflowTests(APITestCase):
    def setUp(self):
        self.department = Department.objects.create(name="Computing", code="COMP")
        self.programme = Programme.objects.create(name="BTech Software Engineering", code="BTECH-SE", department=self.department)
        self.year = AcademicYear.objects.create(label="2026/2027", starts_on=date(2026,1,1), ends_on=date(2027,12,31), is_current=True)
        self.period = AttachmentPeriod.objects.create(name="Industrial Attachment", academic_year=self.year, starts_on=date(2026,1,1), ends_on=date(2026,12,31), is_active=True)
        self.admin = User.objects.create_user(username="coord", email="coord@example.test", password="TestPassword123!", role="admin", first_name="Ava", last_name="Coordinator")
        self.lecturer_user = User.objects.create_user(username="lecturer", email="lecturer@example.test", password="TestPassword123!", role="lecturer", first_name="Lee", last_name="Lecturer")
        self.student_user = User.objects.create_user(username="student", email="student@example.test", password="TestPassword123!", role="student", first_name="Sam", last_name="Student")
        self.other_user = User.objects.create_user(username="other", email="other@example.test", password="TestPassword123!", role="student", first_name="Alex", last_name="Other")
        self.lecturer = LecturerProfile.objects.create(user=self.lecturer_user, staff_number="L001", department=self.department)
        self.student = StudentProfile.objects.create(user=self.student_user, registration_number="STU001", department=self.department, programme=self.programme, academic_year=self.year)
        self.other_student = StudentProfile.objects.create(user=self.other_user, registration_number="STU002", department=self.department, programme=self.programme, academic_year=self.year)
        self.placement = InternshipPlacement.objects.create(student=self.student, attachment_period=self.period, company_name="Northstar Labs", industry="Technology", physical_address="Harare", supervisor_name="Work Supervisor", position_title="Developer Intern", duties="Build web features", start_date=date(2026,2,1), end_date=date(2026,11,30), status="approved")
        self.other_placement = InternshipPlacement.objects.create(student=self.other_student, attachment_period=self.period, company_name="Other Company", physical_address="Bulawayo", supervisor_name="Industry Supervisor", position_title="Trainee", duties="Support operations", start_date=date(2026,2,1), end_date=date(2026,11,30), status="approved")
        LecturerAssignment.objects.create(student=self.student, lecturer=self.lecturer, attachment_period=self.period, assigned_by=self.admin)
        self.assessment = Assessment.objects.create(placement=self.placement, lecturer=self.lecturer, assessment_type="Supervisory visit", assessment_date=date(2026,8,1), start_time=time(10,0), duration_minutes=60, status="completed")

    def test_student_cannot_retrieve_another_students_placement(self):
        self.client.force_authenticate(self.student_user)
        response = self.client.get(f"/api/placements/{self.other_placement.id}/")
        self.assertEqual(response.status_code, 404)

    def test_student_cannot_schedule_assessments(self):
        self.client.force_authenticate(self.student_user)
        response = self.client.post("/api/assessments/", {"placement":self.placement.id,"lecturer":self.lecturer.id,"assessment_type":"Visit","assessment_date":"2026-09-01","start_time":"10:00","duration_minutes":60,"mode":"onsite","location":"Harare"}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_lecturer_only_sees_assigned_placements(self):
        self.client.force_authenticate(self.lecturer_user)
        response = self.client.get("/api/placements/")
        self.assertEqual(response.status_code, 200)
        payload = response.data.get("results", response.data)
        self.assertEqual([row["id"] for row in payload], [self.placement.id])

    def test_student_only_sees_published_results(self):
        FinalResult.objects.create(placement=self.placement, status="draft")
        self.client.force_authenticate(self.student_user)
        response = self.client.get("/api/final-results/")
        self.assertEqual(response.status_code, 200)
        payload = response.data.get("results", response.data)
        self.assertEqual(payload, [])

    def test_final_score_uses_configured_weightings(self):
        cat_a = AssessmentCategory.objects.create(name="Technical")
        cat_b = AssessmentCategory.objects.create(name="Reporting")
        criteria_a = AssessmentCriteria.objects.create(category=cat_a, name="Technical work", max_marks=100, weighting=50, is_required=True)
        criteria_b = AssessmentCriteria.objects.create(category=cat_b, name="Logbook quality", max_marks=100, weighting=50, is_required=True)
        AssessmentMark.objects.create(assessment=self.assessment, criterion=criteria_a, mark_awarded=80, is_final=True, entered_by=self.lecturer_user)
        AssessmentMark.objects.create(assessment=self.assessment, criterion=criteria_b, mark_awarded=60, is_final=True, entered_by=self.lecturer_user)
        GradingScale.objects.create(label="B", minimum_score=70, maximum_score=79.99)
        result = FinalResult.objects.create(placement=self.placement, status="draft")
        self.client.force_authenticate(self.admin)
        response = self.client.post(f"/api/final-results/{result.id}/finalize/", {}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(Decimal(response.data["final_score"]), Decimal("70.00"))
        self.assertEqual(response.data["grade"], "B")
        self.assertEqual(response.data["status"], "finalized")

    def test_logbook_revision_preserves_previous_entry(self):
        entry = LogbookEntry.objects.create(placement=self.placement, week_number=2, revision_number=1, period_start=date(2026,2,8), period_end=date(2026,2,14), activities="Original submission", status="requires_revision")
        self.client.force_authenticate(self.student_user)
        response = self.client.post(f"/api/logbooks/{entry.id}/revise/", {}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["revision_number"], 2)
        self.assertEqual(LogbookEntry.objects.filter(placement=self.placement, week_number=2).count(), 2)
        entry.refresh_from_db()
        self.assertEqual(entry.activities, "Original submission")

    def test_student_can_request_reschedule_for_own_upcoming_assessment(self):
        upcoming = Assessment.objects.create(placement=self.placement, lecturer=self.lecturer, assessment_type="Follow-up visit", assessment_date=date(2026,11,5), start_time=time(11,0), duration_minutes=45, status="scheduled")
        self.client.force_authenticate(self.student_user)
        response = self.client.post(f"/api/assessments/{upcoming.id}/request-reschedule/", {"reason":"I have a required university examination."}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        upcoming.refresh_from_db()
        self.assertTrue(upcoming.reschedule_requested)
        self.assertIn("university examination", upcoming.reschedule_reason)

    def test_student_cannot_request_reschedule_for_another_student(self):
        other_assessment = Assessment.objects.create(placement=self.other_placement, lecturer=self.lecturer, assessment_type="Follow-up visit", assessment_date=date(2026,11,6), start_time=time(12,0), duration_minutes=45, status="scheduled")
        self.client.force_authenticate(self.student_user)
        response = self.client.post(f"/api/assessments/{other_assessment.id}/request-reschedule/", {"reason":"I need a different time for this."}, format="json")
        self.assertEqual(response.status_code, 404)
        other_assessment.refresh_from_db()
        self.assertFalse(other_assessment.reschedule_requested)
