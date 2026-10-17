from django.db import migrations, models


def preserve_submission_data(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Submission = apps.get_model("assessments", "Submission")
    for submission in Submission.objects.using(db_alias).iterator():
        submission.score = submission.grade
        submission.teacher_feedback = submission.feedback
        submission.save(
            using=db_alias,
            update_fields=["score", "teacher_feedback"],
        )


def restore_legacy_submission_data(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Submission = apps.get_model("assessments", "Submission")
    for submission in Submission.objects.using(db_alias).iterator():
        submission.grade = submission.score
        submission.feedback = submission.teacher_feedback
        submission.save(
            using=db_alias,
            update_fields=["grade", "feedback"],
        )


class Migration(migrations.Migration):

    dependencies = [
        ("assessments", "0003_course_relation"),
    ]

    operations = [
        migrations.RenameField(
            model_name="assignment",
            old_name="due_date",
            new_name="due_at",
        ),
        migrations.AddField(
            model_name="assignment",
            name="type",
            field=models.CharField(
                choices=[("quiz", "Quiz"), ("exercise", "Exercise")],
                default="exercise",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="assignment",
            name="max_score",
            field=models.PositiveIntegerField(default=100),
        ),
        migrations.AddField(
            model_name="submission",
            name="answers",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="submission",
            name="score",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=8,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="submission",
            name="teacher_feedback",
            field=models.TextField(blank=True),
        ),
        migrations.RunPython(
            preserve_submission_data,
            restore_legacy_submission_data,
        ),
        migrations.RemoveField(
            model_name="submission",
            name="grade",
        ),
        migrations.RemoveField(
            model_name="submission",
            name="feedback",
        ),
    ]
