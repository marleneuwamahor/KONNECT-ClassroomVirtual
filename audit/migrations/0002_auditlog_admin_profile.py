import django.db.models.deletion
from django.db import migrations, models


def backfill_admin_profiles(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    AuditLog = apps.get_model("audit", "AuditLog")
    AdminProfile = apps.get_model("accounts", "AdminProfile")
    for log in AuditLog.objects.using(db_alias).exclude(user_id=None).iterator():
        profile = AdminProfile.objects.using(db_alias).filter(
            user_id=log.user_id
        ).first()
        if profile:
            AuditLog.objects.using(db_alias).filter(pk=log.pk).update(
                admin_profile_id=profile.pk
            )


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_student_bio_student_grade_level_and_more"),
        ("audit", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="auditlog",
            name="admin_profile",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="audit_logs",
                to="accounts.adminprofile",
            ),
        ),
        migrations.RunPython(
            backfill_admin_profiles,
            migrations.RunPython.noop,
        ),
    ]
