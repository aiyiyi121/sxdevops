from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('cloudsecurity', '0002_internal_security_posture')]

    operations = [
        migrations.CreateModel(
            name='InternalSecurityThreatActivity',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(choices=[('progress', '标记处理中'), ('isolate', '隔离主机'), ('resolve', '确认解决'), ('ignore', '忽略误报'), ('reopen', '重新打开')], max_length=24, verbose_name='处置动作')),
                ('from_status', models.CharField(choices=[('open', '待处理'), ('processing', '处理中'), ('isolated', '已隔离'), ('resolved', '已解决'), ('ignored', '已忽略')], max_length=16, verbose_name='原状态')),
                ('to_status', models.CharField(choices=[('open', '待处理'), ('processing', '处理中'), ('isolated', '已隔离'), ('resolved', '已解决'), ('ignored', '已忽略')], max_length=16, verbose_name='新状态')),
                ('message', models.TextField(blank=True, default='', verbose_name='处置说明')),
                ('actor', models.CharField(blank=True, default='', max_length=150, verbose_name='操作人')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='操作时间')),
                ('threat', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='activities', to='cloudsecurity.internalsecuritythreat', verbose_name='威胁事件')),
            ],
            options={
                'verbose_name': '主机威胁处置记录',
                'verbose_name_plural': '主机威胁处置记录',
                'ordering': ['-created_at', '-id'],
                'indexes': [models.Index(fields=['threat', 'created_at'], name='cloudsec_threat_act_time')],
            },
        ),
    ]
