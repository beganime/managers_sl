from django.db import migrations


def recreate_missing_0008_tables(apps, schema_editor):
    connection = schema_editor.connection
    existing_tables = set(connection.introspection.table_names())

    document_review = apps.get_model("documents", "DocumentReview")
    knowledge_test_attempt = apps.get_model("documents", "KnowledgeTestAttempt")

    if document_review._meta.db_table not in existing_tables:
        schema_editor.create_model(document_review)
        existing_tables.add(document_review._meta.db_table)

    if knowledge_test_attempt._meta.db_table not in existing_tables:
        schema_editor.create_model(knowledge_test_attempt)


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0008_documentreview_knowledgetestattempt"),
    ]

    operations = [
        migrations.RunPython(recreate_missing_0008_tables, migrations.RunPython.noop),
    ]