from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory, TestCase

from accounts.admin import UserAdmin
from accounts.models import User
from audit.models import AuditLog


class DjangoAdminAuditTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            "admin@example.com",
            "pass12345!",
            name="Admin",
        )
        self.site = AdminSite()
        self.model_admin = UserAdmin(User, self.site)
        self.factory = RequestFactory()
        self.request = self.factory.post("/admin/accounts/user/add/")
        self.request.user = self.admin_user

    def test_admin_site_create_is_attributed_to_admin_profile(self):
        user = User(
            name="Created from admin",
            email="created@example.com",
            role=User.Role.STUDENT,
        )

        self.model_admin.save_model(self.request, user, form=None, change=False)

        user.refresh_from_db()
        self.assertEqual(user.managed_by, self.admin_user.admin_profile)
        audit_log = AuditLog.objects.get(
            entity="user",
            entity_id=user.pk,
            action="create",
        )
        self.assertEqual(audit_log.admin_profile, self.admin_user.admin_profile)

    def test_admin_bulk_delete_is_audited(self):
        user = User.objects.create_user(
            "remove@example.com",
            "pass12345!",
            name="Remove",
            role=User.Role.STUDENT,
        )

        self.model_admin.delete_queryset(
            self.request,
            User.objects.filter(pk=user.pk),
        )

        audit_log = AuditLog.objects.get(
            entity="user",
            entity_id=user.pk,
            action="delete",
        )
        self.assertEqual(audit_log.admin_profile, self.admin_user.admin_profile)
