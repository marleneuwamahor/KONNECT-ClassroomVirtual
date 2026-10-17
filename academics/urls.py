from rest_framework.routers import DefaultRouter

from .views import (
    AttendanceViewSet,
    CourseViewSet,
    EnrollmentViewSet,
    ExamViewSet,
    GradeViewSet,
    LiveSessionViewSet,
    SchoolClassViewSet,
    StudentFlagViewSet,
)

router = DefaultRouter()
router.register("courses", CourseViewSet, basename="course")
router.register("classes", SchoolClassViewSet, basename="class")
router.register("enrollments", EnrollmentViewSet, basename="enrollment")
router.register("attendance", AttendanceViewSet, basename="attendance")
router.register("exams", ExamViewSet, basename="exam")
router.register("grades", GradeViewSet, basename="grade")
router.register("student-flags", StudentFlagViewSet, basename="student-flag")
router.register("live-sessions", LiveSessionViewSet, basename="live-session")
urlpatterns = router.urls