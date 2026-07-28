from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("workflow", "0002_alter_workflowsteptemplate_service_type_and_more"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.CreateModel(
                    name="WorkflowStepDependency",
                    fields=[
                        (
                            "id",
                            models.BigAutoField(
                                auto_created=True,
                                primary_key=True,
                                serialize=False,
                                verbose_name="ID",
                            ),
                        ),
                        (
                            "from_workflowsteptemplate",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="dependency_edges",
                                to="workflow.workflowsteptemplate",
                            ),
                        ),
                        (
                            "to_workflowsteptemplate",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="dependent_edges",
                                to="workflow.workflowsteptemplate",
                            ),
                        ),
                    ],
                    options={
                        "db_table": "workflow_workflowsteptemplate_depends_on",
                        "constraints": [
                            models.UniqueConstraint(
                                fields=("from_workflowsteptemplate", "to_workflowsteptemplate"),
                                name="unique_workflow_step_dependency",
                            ),
                        ],
                    },
                ),
                migrations.AlterField(
                    model_name="workflowsteptemplate",
                    name="depends_on",
                    field=models.ManyToManyField(
                        blank=True,
                        help_text="Steps that must be COMPLETED before this step becomes eligible to start.",
                        related_name="dependents",
                        through="workflow.WorkflowStepDependency",
                        through_fields=("from_workflowsteptemplate", "to_workflowsteptemplate"),
                        to="workflow.workflowsteptemplate",
                    ),
                ),
            ],
        ),
    ]
