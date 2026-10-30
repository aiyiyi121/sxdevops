from django.db.models import OuterRef, Subquery

from .models import CIResourceMetricSnapshot, ConfigItem


def latest_metric_snapshots(ci_ids, metric_names, *, queryset=None):
    snapshots = queryset if queryset is not None else CIResourceMetricSnapshot.objects.all()
    metric_names = list(dict.fromkeys(metric_names))
    latest_ids = []
    assets = ConfigItem.objects.filter(pk__in=ci_ids).order_by()
    for offset in range(0, len(metric_names), 32):
        annotations = {
            f'latest_metric_{position}': Subquery(
                snapshots.filter(ci_id=OuterRef('pk'), metric=metric)
                .order_by('ci_id', 'metric', '-collected_at', '-id')
                .values('pk')[:1]
            )
            for position, metric in enumerate(metric_names[offset:offset + 32])
        }
        for row in assets.annotate(**annotations).values_list(*annotations):
            latest_ids.extend(snapshot_id for snapshot_id in row if snapshot_id is not None)
    return snapshots.filter(pk__in=latest_ids).order_by('-collected_at', '-id')
