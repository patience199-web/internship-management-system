from datetime import date, time, timedelta
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from accounts.models import StudentProfile, LecturerProfile
from core.models import (
    Department, Programme, AcademicYear, AttachmentPeriod, InternshipPlacement,
    LecturerAssignment, Assessment, LogbookEntry, AssessmentCategory,
    AssessmentCriteria, AssessmentMark, FinalResult, Notification, GradingScale,
)

User = get_user_model()

class Command(BaseCommand):
    help = "Create realistic demo data for the Internship Management System. Demo credentials are for local development only."
    def handle(self, *args, **options):
        dept, _ = Department.objects.get_or_create(code="ICT", defaults={"name":"Information & Communication Technology"})
        prog, _ = Programme.objects.get_or_create(code="BTECH-ECOM", defaults={"name":"BTech Honours in Electronic Commerce", "department":dept})
        now_year = timezone.localdate().year
        year, _ = AcademicYear.objects.get_or_create(label=f"{now_year}/{now_year+1}", defaults={"starts_on":date(now_year,1,1), "ends_on":date(now_year+1,12,31), "is_current":True})
        period, _ = AttachmentPeriod.objects.get_or_create(name="Industrial Attachment", academic_year=year, defaults={"starts_on":date(now_year,1,1), "ends_on":date(now_year+1,12,31), "registration_deadline":date(now_year,12,31), "is_active":True})
        admin = self.user("admin", "admin@internship.local", "Admin", "Coordinator", "admin", "DemoAdmin123!")
        lecturer_user = self.user("lecturer", "lecturer@internship.local", "Tariro", "Moyo", "lecturer", "DemoLecturer123!")
        student1_user = self.user("student", "student@internship.local", "Patience", "Student", "student", "DemoStudent123!")
        student2_user = self.user("student2", "student2@internship.local", "Tendai", "Ncube", "student", "DemoStudent123!")
        lecturer, _ = LecturerProfile.objects.get_or_create(user=lecturer_user, defaults={"staff_number":"ICT-014", "department":dept, "job_title":"Industrial Attachment Supervisor"})
        students=[]
        for usr, reg in [(student1_user,"HIT/EC/2024/031"),(student2_user,"HIT/EC/2024/044")]:
            profile, _ = StudentProfile.objects.get_or_create(user=usr, defaults={"registration_number":reg,"department":dept,"programme":prog,"academic_year":year,"year_of_study":3})
            students.append(profile)
        placement, _ = InternshipPlacement.objects.get_or_create(student=students[0],attachment_period=period,defaults={
            "company_name":"Suwani Digital Solutions","industry":"Technology & Digital Services","physical_address":"Harare, Zimbabwe",
            "contact_email":"people@example.com","contact_phone":"+263 77 000 1000","supervisor_name":"Kudzai Dube","supervisor_position":"Digital Operations Lead","supervisor_contact":"+263 77 000 1001",
            "position_title":"Web Development Intern","duties":"Website development, SEO support, content updates and website quality assurance.",
            "start_date":date(now_year,2,1),"end_date":date(now_year,11,30),"status":"in_progress"})
        placement2, _ = InternshipPlacement.objects.get_or_create(student=students[1],attachment_period=period,defaults={
            "company_name":"Northstar Creative Studio","industry":"Marketing & Design","physical_address":"Borrowdale, Harare","contact_email":"hr@example.com","contact_phone":"+263 77 000 2000",
            "supervisor_name":"Nyasha Moyo","supervisor_position":"Creative Director","supervisor_contact":"+263 77 000 2001","position_title":"Digital Product Intern","duties":"Content production, website maintenance and analytics reporting.",
            "start_date":date(now_year,3,1),"end_date":date(now_year,12,1),"status":"submitted"})
        for student, plac in zip(students,[placement,placement2]):
            LecturerAssignment.objects.get_or_create(student=student,attachment_period=period,defaults={"lecturer":lecturer,"assigned_by":admin,"is_active":True})
        assessment, _ = Assessment.objects.get_or_create(placement=placement,lecturer=lecturer,assessment_type="First supervisory visit",defaults={
            "assessment_date":date.today()+timedelta(days=5),"start_time":time(10,0),"duration_minutes":60,"mode":"onsite","location":"Suwani Digital Solutions, Harare","instructions":"Review weekly activities, workplace conduct and progress against learning objectives.","status":"scheduled"})
        LogbookEntry.objects.get_or_create(placement=placement,week_number=1,revision_number=1,defaults={
            "period_start":date(now_year,2,1),"period_end":date(now_year,2,7),"activities":"Completed onboarding and updated two website landing pages.","skills_acquired":"WordPress page editing, responsive testing and content QA.","challenges":"Understanding the client's publishing workflow.","lessons_learned":"Confirm requirements before changing production content.","hours_worked":Decimal("40.00"),"student_comments":"A productive first week.","status":"approved","submitted_at":timezone.now(),"submitted_by":student1_user})
        categories = []
        for name, description in [("Workplace performance","Professional behaviour and reliability"),("Technical skills","Practical application of technical skills"),("Logbook and reporting","Quality and consistency of attachment records"),("Communication","Communication with the workplace and supervisor")]:
            category,_=AssessmentCategory.objects.get_or_create(name=name,defaults={"description":description,"is_required":True,"is_active":True}); categories.append(category)
        criteria_data=[("Workplace performance","Professional conduct",20),("Technical skills","Technical execution",40),("Logbook and reporting","Logbook quality",20),("Communication","Communication and teamwork",20)]
        criteria=[]
        for cat_name, criterion_name, weight in criteria_data:
            cat=next(c for c in categories if c.name==cat_name)
            criterion,_=AssessmentCriteria.objects.get_or_create(category=cat,name=criterion_name,defaults={"description":criterion_name,"max_marks":100,"weighting":weight,"is_required":True,"is_active":True})
            if criterion.weighting != Decimal(weight): criterion.weighting=weight; criterion.save(update_fields=["weighting","updated_at"])
            criteria.append(criterion)
        for grade, low, high in [("A",80,100),("B",70,79.99),("C",60,69.99),("D",50,59.99),("F",0,49.99)]:
            GradingScale.objects.get_or_create(label=grade,defaults={"minimum_score":low,"maximum_score":high,"description":"Demo grading band","order":int(low)})
        # Seed draft/final marks to make result components available, without automatically publishing a score.
        for criterion, mark in zip(criteria,[85,78,90,82]):
            AssessmentMark.objects.get_or_create(assessment=assessment,criterion=criterion,defaults={"mark_awarded":mark,"comments":"Demo mark — replace with an official assessment mark.","is_final":False,"entered_by":lecturer_user})
        Notification.objects.get_or_create(recipient=student1_user,title="Welcome to your attachment dashboard",defaults={"message":"Your placement and weekly logbook are ready to view. Check your upcoming assessment date.","kind":"info","link":"/dashboard"})
        self.stdout.write(self.style.SUCCESS("Demo data is ready. Login: admin / DemoAdmin123!, lecturer / DemoLecturer123!, student / DemoStudent123!"))
    def user(self, username, email, first, last, role, password):
        user, created = User.objects.get_or_create(username=username, defaults={"email":email,"first_name":first,"last_name":last,"role":role,"is_active":True})
        changed = False
        for key, value in {"email":email,"first_name":first,"last_name":last,"role":role,"is_active":True}.items():
            if getattr(user,key) != value: setattr(user,key,value); changed=True
        if created or not user.has_usable_password(): user.set_password(password); changed=True
        if changed: user.save()
        return user
