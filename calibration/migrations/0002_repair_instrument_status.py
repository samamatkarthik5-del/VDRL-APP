from django.db import migrations


def add_missing_status_column(apps, schema_editor):
    Instrument = apps.get_model(
        "calibration",
        "Instrument",
    )

    table_name = Instrument._meta.db_table

    with schema_editor.connection.cursor() as cursor:
        existing_columns = {
            column.name
            for column in (
                schema_editor.connection.introspection
                .get_table_description(cursor, table_name)
            )
        }

    if "status" in existing_columns:
        return

    status_field = Instrument._meta.get_field("status")

    schema_editor.add_field(
        Instrument,
        status_field,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("calibration", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            add_missing_status_column,
            migrations.RunPython.noop,
        ),
    ]