from rest_framework.routers import DefaultRouter

from .views import AnnouncementViewSet, NotificationViewSet, SystemSettingViewSet

router = DefaultRouter()
router.register("announcements", AnnouncementViewSet, basename="announcement")
router.register("notifications", NotificationViewSet, basename="notification")
router.register("system-settings", SystemSettingViewSet, basename="system-setting")
urlpatterns = router.urls