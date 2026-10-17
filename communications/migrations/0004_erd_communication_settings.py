import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


def backfill_announcement_teachers(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Announcement = apps.get_model("communications", "Announcement")
    Teacher = apps.get_model("accounts", "Teacher")
    for announcement in Announcement.objects.using(db_alias).iterator():
        teacher = Teacher.objects.using(db_alias).filter(
            user_id=announcement.author_id
        ).first()
        if teacher:
            Announcement.objects.using(db_alias).filter(pk=announcement.pk).update(
                teacher_id=teacher.pk
            )


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_student_bio_student_grade_level_and_more"),
        ("academics", "0006_erd_course"),
        ("communications", "0003_course_relation"),
    ]

    operations = [
        migrations.AddField(
            model_name="announcement",
            name="teacher",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="announcements",
                to="accounts.teacher",
            ),
        ),
        migrations.AddField(
            model_name="notification",
            name="type",
            field=models.CharField(default="general", max_length=50),
        ),
        migrations.CreateModel(
            name="SystemSetting",
            fields=[
                ("key", models.CharField(max_length=100, primary_key=True, serialize=False)),
                ("value", models.TextField()),
                ("updated_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="system_settings",
                        to="accounts.adminprofile",
                    ),
                ),
            ],
            options={
                "db_table": "system_settings",
                "ordering": ["key"],
            },
        ),
        migrations.RunPython(
            backfill_announcement_teachers,
            migrations.RunPython.noop,
        ),
    ]
