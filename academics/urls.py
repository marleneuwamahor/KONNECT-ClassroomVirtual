from rest_framework.routers import DefaultRouter

from .views import (
    AttendanceViewSet,
    CourseViewSet,
    EnrollmentViewSet,
    LiveSessionViewSet,
    SchoolClassViewSet,
)

router = DefaultRouter()
router.register("courses", CourseViewSet, basename="course")
router.register("classes", SchoolClassViewSet, basename="class")
router.register("enrollments", EnrollmentViewSet, basename="enrollment")
router.register("attendance", AttendanceViewSet, basename="attendance")
router.register("live-sessions", LiveSessionViewSet, basename="live-session")
urlpatterns = router.urls