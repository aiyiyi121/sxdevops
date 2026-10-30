from django.db import migrations


def backfill_sync_record_batch_ids(apps, schema_editor):
    CISyncRecord = apps.get_model('cmdb', 'CISyncRecord')
    current_job_id = None
    current_batch_id = ''
    batch_number = 0
    previous_created_at = None

    for record in CISyncRecord.objects.filter(batch_id='').order_by('job_id', 'created_at', 'id').iterator():
        is_new_job = record.job_id != current_job_id
        is_new_batch = is_new_job or not previous_created_at or (record.created_at - previous_created_at).total_seconds() > 5
        if is_new_batch:
            if is_new_job:
                batch_number = 0
                current_job_id = record.job_id
            batch_number += 1
            current_batch_id = f'legacy-{record.job_id}-{batch_number}'
        CISyncRecord.objects.filter(pk=record.pk).update(batch_id=current_batch_id)
        previous_created_at = record.created_at


class Migration(migrations.Migration):

    dependencies = [
        ('cmdb', '0030_cisyncrecord_batch_id'),
    ]

    operations = [
        migrations.RunPython(backfill_sync_record_batch_ids, migrations.RunPython.noop),
    ]
