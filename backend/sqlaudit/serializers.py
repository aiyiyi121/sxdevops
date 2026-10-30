from rest_framework import serializers
from .models import DataSource, SqlOrder, QueryOrder, SqlCheckResult


class DataSourceSerializer(serializers.ModelSerializer):
    status_label = serializers.SerializerMethodField()
    db_type_display = serializers.CharField(source='get_db_type_display', read_only=True)

    class Meta:
        model = DataSource
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']
        extra_kwargs = {
            'password': {'write_only': True},
        }

    def get_status_label(self, obj):
        return '启用' if obj.is_active else '停用'

    def validate(self, attrs):
        db_type = attrs.get('db_type', getattr(self.instance, 'db_type', 'mysql'))
        if db_type == 'postgresql':
            attrs['charset'] = 'UTF8'
            if self.instance is None:
                attrs.setdefault('port', 5432)
        return attrs


class SqlCheckResultSerializer(serializers.ModelSerializer):
    level_display = serializers.CharField(source='get_level_display', read_only=True)

    class Meta:
        model = SqlCheckResult
        fields = '__all__'
        read_only_fields = ('id', 'order', 'level', 'rule_name', 'message', 'line_no')


class SqlOrderSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    sql_type_display = serializers.CharField(source='get_sql_type_display', read_only=True)
    datasource_name = serializers.CharField(source='datasource.name', read_only=True)
    datasource_db_type = serializers.CharField(source='datasource.db_type', read_only=True)
    datasource_db_type_display = serializers.CharField(source='datasource.get_db_type_display', read_only=True)
    check_results = SqlCheckResultSerializer(many=True, read_only=True)

    class Meta:
        model = SqlOrder
        fields = '__all__'
        read_only_fields = [
            'status', 'submitter', 'reviewer', 'review_comment', 'reviewed_at',
            'execute_log', 'affected_rows', 'duration_ms', 'executed_at', 'created_at',
        ]


class QueryOrderSerializer(serializers.ModelSerializer):
    datasource_name = serializers.CharField(source='datasource.name', read_only=True)
    datasource_db_type = serializers.CharField(source='datasource.db_type', read_only=True)
    datasource_db_type_display = serializers.CharField(source='datasource.get_db_type_display', read_only=True)

    class Meta:
        model = QueryOrder
        fields = '__all__'
        read_only_fields = ['submitter', 'result_count', 'duration_ms', 'created_at']
