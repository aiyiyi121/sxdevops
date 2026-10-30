from datetime import timedelta
from unittest.mock import patch
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from multicloud.models import CloudCredential
from rbac.models import PermissionDefinition, Role

from .models import (
    InternalPlatformSecurityControl,
    InternalPlatformSecurityFinding,
    InternalSecurityAsset,
    InternalSecurityThreat,
    SoftwareSecurityItem,
)

from .services import (
    _describe_alarm_banner,
    _describe_base_rule_details,
    _describe_instance,
    _describe_log_status,
    _describe_resources,
    _describe_trend,
    _trend_point_timestamp,
    _describe_top_rule_ids,
    _describe_top_rule_types,
    _describe_top_event_urls,
    _describe_upstream_response_codes,
    _apply_event_hits_to_trend,
    _event_matches_filters,
    _decorate_events_with_rule_details,
    _normalize_event,
    _resource_is_healthy,
    get_waf_credential,
    normalize_region,
)


User = get_user_model()


class WafServiceTests(TestCase):
    def test_region_is_normalized_to_waf_control_plane(self):
        self.assertEqual(normalize_region('cn-shanghai'), 'cn-hangzhou')
        self.assertEqual(normalize_region('cn-hongkong'), 'ap-southeast-1')
        self.assertEqual(normalize_region(''), 'cn-hangzhou')

    def test_credential_must_be_enabled_aliyun_aksk(self):
        credential = CloudCredential.objects.create(
            provider='aliyun',
            name='aliyun-waf-prod',
            access_key_id='test-ak',
            access_key_secret='test-sk',
        )

        self.assertEqual(get_waf_credential(credential.id), credential)

    def test_active_resource_is_counted_as_healthy(self):
        self.assertTrue(_resource_is_healthy({'status': 'active'}))
        self.assertTrue(_resource_is_healthy({'status': 'online'}))
        self.assertFalse(_resource_is_healthy({'status': 'inactive'}))

    def test_event_normalizes_alibaba_snake_case_payload(self):
        event = _normalize_event({
            'timestamp': '1786495639',
            'matched_host': 'we.example.com-waf',
            'real_client_ip': '203.0.113.1',
            'remote_country_id': 'CN',
            'request_method': 'GET',
            'request_path': '/static/lib/document.URL',
            'request_traceid': 'trace-123',
            'terminating_rules': '[{"id":"120037","type":"xss","action":"block","defense_scene":"waf_base"}]',
            'final_defense_scene_block_detail': '{"request_uri":{"hit":["/static/lib/document.url"]}}',
        }, 1)
        self.assertEqual(event['resource'], 'we.example.com-waf')
        self.assertEqual(event['client_ip'], '203.0.113.1')
        self.assertEqual(event['rule_type'], 'xss')
        self.assertEqual(event['action'], 'block')
        self.assertEqual(event['rules'][0]['id'], '120037')
        self.assertEqual(event['matched_detail']['request_uri']['hit'][0], '/static/lib/document.url')
        self.assertNotIn('raw', event)

    def test_base_rule_metadata_decorates_attack_events(self):
        from alibabacloud_waf_openapi20211001 import models

        class FakeClient:
            def describe_base_system_rules(self, request):
                self.request = request
                return SimpleNamespace(body={
                    'Rules': [{
                        'RuleId': 120037,
                        'RuleName': '跨站脚本攻击',
                        'Description': '检测跨站脚本攻击请求',
                        'RiskLevel': 'high',
                    }],
                })

        event = _normalize_event({
            'terminating_rules': '[{"id":"120037","type":"xss","action":"block"}]',
        }, 1)
        client = FakeClient()
        details = _describe_base_rule_details(client, models, 'waf-cn-test', 'cn-hangzhou', ['120037'])
        _decorate_events_with_rule_details([event], details)

        self.assertEqual(client.request.lang, 'zh')
        self.assertEqual(client.request.rule_ids, [120037])
        self.assertEqual(event['rule_name'], '跨站脚本攻击')
        self.assertEqual(event['rules'][0]['description'], '检测跨站脚本攻击请求')

    def test_event_filters_accept_alibaba_rule_aliases(self):
        event = {
            'rule_type': 'sql_injection',
            'action': 'deny',
            'request_path': '/api/v1/orders',
            'querystring': 'page=1',
            'rule_id': '120037',
        }
        self.assertTrue(_event_matches_filters(event, {
            'rule_type': 'sqli', 'action': 'block', 'request_url': '/orders', 'rule_id': '1200',
            'keyword': '', 'resource': '', 'client_ip': '',
        }))
        self.assertFalse(_event_matches_filters(event, {
            'rule_type': '', 'action': '', 'request_url': '/users', 'rule_id': '',
            'keyword': '', 'resource': '', 'client_ip': '',
        }))
        self.assertTrue(_event_matches_filters(event, {
            'rule_type': 'waf', 'action': '', 'request_url': '', 'rule_id': '',
            'keyword': '', 'resource': '', 'client_ip': '',
        }))

    def test_sdk_responses_are_normalized_for_frontend(self):
        from alibabacloud_waf_openapi20211001 import models

        class FakeClient:
            def describe_instance(self, request):
                details = models.DescribeInstanceResponseBodyDetails(
                    defense_object_max_count=50,
                    free_qps=1000,
                    ipv_6=True,
                    log_service=True,
                )
                body = models.DescribeInstanceResponseBody(
                    instance_id='waf-cn-test',
                    edition='pro',
                    status=1,
                    details=details,
                )
                return SimpleNamespace(body=body)

            def describe_defense_resources(self, request):
                resource = models.DescribeDefenseResourcesResponseBodyResources(
                    resource='www.example.com',
                    product='waf',
                    resource_status='online',
                    xff_status=1,
                )
                body = models.DescribeDefenseResourcesResponseBody(resources=[resource], total_count=1)
                return SimpleNamespace(body=body)

            def describe_peak_trend(self, request):
                point = models.DescribePeakTrendResponseBodyFlowChart(
                    index=1700000000,
                    count=120,
                    waf_sum=4,
                    cc_sum=3,
                    acl_sum=2,
                    anti_scan_sum=1,
                )
                return SimpleNamespace(body=models.DescribePeakTrendResponseBody(flow_chart=[point]))

        client = FakeClient()
        instance = _describe_instance(client, models, 'cn-hangzhou')
        resources = _describe_resources(client, models, instance['instance_id'], 'cn-hangzhou')
        trend = _describe_trend(client, models, instance['instance_id'], 'cn-hangzhou', 1, 2, 60)

        self.assertEqual(instance['capacity']['protected_object_limit'], 50)
        self.assertTrue(instance['capacity']['ipv6'])
        self.assertEqual(resources['items'][0]['resource'], 'www.example.com')
        self.assertTrue(resources['items'][0]['xff_enabled'])
        self.assertEqual(trend[0]['attacks'], 10)

    def test_trend_bucket_indexes_are_mapped_to_the_selected_time_range(self):
        self.assertEqual(_trend_point_timestamp(0, 1_700_000_000, 60, 0), 1_700_000_000)
        self.assertEqual(_trend_point_timestamp(3, 1_700_000_000, 60, 3), 1_700_000_180)
        self.assertEqual(_trend_point_timestamp(1_700_000_000, 1, 60, 0), 1_700_000_000)

    def test_attack_events_fill_rule_hit_trend_when_waf_summary_is_empty(self):
        trend = [
            {'timestamp': 1_700_000_000, 'attacks': 0},
            {'timestamp': 1_700_000_060, 'attacks': 0},
        ]

        result = _apply_event_hits_to_trend(trend, {
            'event_count': 3,
            'rule_hits_by_bucket': {1_700_000_000: 2, 1_700_000_060: 1},
        })

        self.assertEqual([item['attacks'] for item in result], [2, 1])

    def test_security_insight_responses_are_normalized_for_frontend(self):
        from alibabacloud_waf_openapi20211001 import models

        class FakeClient:
            def describe_rule_hits_top_rule_id(self, request):
                self.rule_id_request = request
                return SimpleNamespace(body={
                    'RuleHitsTopRuleId': [{'RuleId': '120037', 'Count': 12}],
                })

            def describe_rule_hits_top_tule_type(self, request):
                return SimpleNamespace(body={
                    'RuleHitsTopTuleType': [{'RuleType': 'cc_system', 'Count': 8}],
                })

            def describe_alarm_banner(self, request):
                return SimpleNamespace(body={
                    'BannerStatus': {'Status': True, 'Type': 'sandbox', 'Cause': 'fivefold', 'Count': 2},
                })

            def describe_resource_log_status(self, request):
                self.log_status_request = request
                return SimpleNamespace(body={
                    'Result': [
                        {'Resource': 'www.example.com', 'Status': True, 'TraceStatus': False},
                        {'Resource': 'api.example.com', 'Status': False, 'TraceStatus': True},
                    ],
                })

            def describe_response_code_trend_graph(self, request):
                self.response_code_request = request
                return SimpleNamespace(body={
                    'ResponseCodes': [{'Index': 1700000000, '5xxPv': 3, '499Pv': 2}],
                })

        client = FakeClient()
        top_rule_ids = _describe_top_rule_ids(client, models, 'waf-cn-test', 'cn-hangzhou', 1, 2)
        top_rule_types = _describe_top_rule_types(client, models, 'waf-cn-test', 'cn-hangzhou', 1, 2)
        alarm = _describe_alarm_banner(client, models, 'waf-cn-test', 'cn-hangzhou')
        log_status = _describe_log_status(client, models, 'waf-cn-test', 'cn-hangzhou', [
            {'resource': 'www.example.com'}, {'resource': 'api.example.com'},
        ])
        response_codes = _describe_upstream_response_codes(client, models, 'waf-cn-test', 'cn-hangzhou', 1, 2, 60)

        self.assertEqual(client.rule_id_request.is_group_resource, 'true')
        self.assertEqual(top_rule_ids[0], {'rule_id': '120037', 'resource': '', 'count': 12})
        self.assertEqual(top_rule_types[0]['rule_type'], 'cc_system')
        self.assertTrue(alarm['active'])
        self.assertEqual(log_status['enabled'], 1)
        self.assertEqual(log_status['trace_enabled'], 1)
        self.assertEqual(client.log_status_request.resources, 'www.example.com,api.example.com')
        self.assertEqual(client.response_code_request.type, 'upstream')
        self.assertEqual(response_codes[0]['5xx'], 3)

    def test_top_urls_are_aggregated_from_attack_events(self):
        from alibabacloud_waf_openapi20211001 import models

        class FakeClient:
            def describe_security_event_logs(self, request):
                self.requests = getattr(self, 'requests', []) + [request]
                if request.page_number == 1:
                    return SimpleNamespace(body={
                        'SecurityEventLogsTotalCount': 101,
                        'SecurityEventLogs': [
                            {'request_path': '/api/v1/orders'},
                            {'request_path': '/api/v1/users'},
                        ],
                    })
                return SimpleNamespace(body={
                    'SecurityEventLogs': [{'request_path': '/api/v1/orders'}],
                })

        client = FakeClient()
        top_urls = _describe_top_event_urls(client, models, 'waf-cn-test', 'cn-hangzhou', 1, 2)

        self.assertEqual(top_urls, [
            {'url': '/api/v1/orders', 'count': 2},
            {'url': '/api/v1/users', 'count': 1},
        ])
        self.assertEqual([request.page_number for request in client.requests], [1, 2])


class WafApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username='waf-admin', password='Admin@123456')
        self.client.force_login(self.user)

    @patch('cloudsecurity.views.list_waf_accounts')
    def test_accounts_endpoint_does_not_expose_secrets(self, list_accounts):
        list_accounts.return_value = [{'id': 1, 'name': 'prod', 'configured': True}]

        response = self.client.get('/api/cloud-security/waf/accounts/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['accounts'][0]['name'], 'prod')
        self.assertNotIn('access_key_secret', response.content.decode('utf-8'))

    @patch('cloudsecurity.views.get_waf_overview')
    def test_overview_endpoint_returns_normalized_payload(self, get_overview):
        get_overview.return_value = {
            'summary': {'protected_resources': 3, 'attack_count': 9},
            'trend': [],
            'warnings': [],
        }

        response = self.client.get('/api/cloud-security/waf/overview/?hours=24')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['summary']['protected_resources'], 3)

    def test_waf_endpoint_requires_authentication(self):
        self.client.logout()

        response = self.client.get('/api/cloud-security/waf/accounts/')

        self.assertIn(response.status_code, {401, 403})

    @patch('cloudsecurity.views.list_waf_accounts', return_value=[])
    def test_waf_endpoint_enforces_registered_permission(self, list_accounts):
        user = User.objects.create_user(username='waf-viewer', password='Viewer@123456')
        self.client.force_login(user)

        denied = self.client.get('/api/cloud-security/waf/accounts/')

        permission = PermissionDefinition.objects.get(code='cloudsecurity.waf.view')
        role = Role.objects.create(code='waf-viewer', name='WAF 查看者')
        role.permissions.add(permission)
        role.users.add(user)
        allowed = self.client.get('/api/cloud-security/waf/accounts/')

        self.assertEqual(denied.status_code, 403)
        self.assertEqual(allowed.status_code, 200)


class InternalPlatformSecurityApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.asset = InternalSecurityAsset.objects.create(
            name='example-api-01',
            ip_address='192.0.2.10',
            agent_status='offline',
            risk_level='high',
        )
        InternalSecurityThreat.objects.create(
            asset=cls.asset,
            threat_type='suspicious_script',
            title='Synthetic test threat',
            severity='high',
            status='open',
            detected_at=timezone.now(),
        )
        SoftwareSecurityItem.objects.bulk_create([
            SoftwareSecurityItem(
                row_number=index,
                deployment_type='self_hosted',
                software_name=f'example-service-{index}',
                priority=priority,
            )
            for index, priority in enumerate(('P0', 'P1', 'P3'), start=1)
        ])

    def setUp(self):
        self.user = User.objects.create_superuser(username='security-admin', password='Admin@123456')
        self.client.force_login(self.user)

    def test_overview_exposes_seeded_controls_and_workbench_summary(self):
        response = self.client.get('/api/cloud-security/internal-platform/overview/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['controls']), 7)
        self.assertGreaterEqual(response.json()['summary']['open_count'], 4)

    def test_posture_exposes_host_threat_and_software_summary(self):
        response = self.client.get('/api/cloud-security/internal-platform/posture/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['summary']['asset_total'], InternalSecurityAsset.objects.count())
        self.assertEqual(response.json()['summary']['software_total'], 3)
        self.assertGreaterEqual(response.json()['summary']['open_threat_count'], 1)
        vsphere = next(item for item in response.json()['connectors'] if item['value'] == 'vsphere')
        self.assertEqual(vsphere['status'], 'planned')

    def test_software_high_filter_returns_only_p0_and_p1_items(self):
        response = self.client.get('/api/cloud-security/internal-platform/software/?priority=HIGH')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json())
        self.assertTrue(all(item['priority'] in {'P0', 'P1'} for item in response.json()))

    def test_threat_can_be_isolated_and_resolved(self):
        threat = InternalSecurityThreat.objects.filter(status='open').first()

        isolated = self.client.post(
            f'/api/cloud-security/internal-platform/threats/{threat.id}/action/',
            {'action': 'isolate', 'message': '已断开网络。'},
            content_type='application/json',
        )
        resolved = self.client.post(
            f'/api/cloud-security/internal-platform/threats/{threat.id}/action/',
            {'action': 'resolve', 'message': '已清理并完成复核。'},
            content_type='application/json',
        )

        threat.refresh_from_db()
        self.assertEqual(isolated.status_code, 200)
        self.assertEqual(resolved.status_code, 200)
        self.assertEqual(threat.status, 'resolved')
        self.assertIsNotNone(threat.resolved_at)
        self.assertEqual(threat.activities.count(), 2)
        self.assertEqual(resolved.json()['activities'][0]['action'], 'resolve')

    def test_threat_ignore_requires_reason_and_can_be_reopened(self):
        threat = InternalSecurityThreat.objects.filter(status='open').first()

        invalid = self.client.post(
            f'/api/cloud-security/internal-platform/threats/{threat.id}/action/',
            {'action': 'ignore'},
            content_type='application/json',
        )
        ignored = self.client.post(
            f'/api/cloud-security/internal-platform/threats/{threat.id}/action/',
            {'action': 'ignore', 'message': '确认是授权压测脚本。'},
            content_type='application/json',
        )
        reopened = self.client.post(
            f'/api/cloud-security/internal-platform/threats/{threat.id}/action/',
            {'action': 'reopen', 'message': '复核发现来源账号不在授权范围。'},
            content_type='application/json',
        )

        threat.refresh_from_db()
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(ignored.status_code, 200)
        self.assertEqual(reopened.status_code, 200)
        self.assertEqual(threat.status, 'open')
        self.assertIsNone(threat.resolved_at)
        self.assertEqual(threat.activities.count(), 2)

    def test_asset_protection_gap_and_asset_threat_filters(self):
        gap_response = self.client.get('/api/cloud-security/internal-platform/assets/?protection_status=gap')
        asset = self.asset
        threat_response = self.client.get(
            f'/api/cloud-security/internal-platform/threats/?asset_id={asset.id}&owner_status=unassigned'
        )

        self.assertEqual(gap_response.status_code, 200)
        self.assertTrue(gap_response.json())
        self.assertTrue(all(item['protection_status'] != 'healthy' for item in gap_response.json()))
        self.assertEqual(threat_response.status_code, 200)
        self.assertTrue(threat_response.json())
        self.assertTrue(all(item['asset'] == asset.id and not item['owner'] for item in threat_response.json()))

    def test_software_governance_status_can_be_updated(self):
        item = SoftwareSecurityItem.objects.get(row_number=1)

        response = self.client.post(
            f'/api/cloud-security/internal-platform/software/{item.id}/status/',
            {'status': 'planned', 'plan_time': '2026 Q4', 'owner_feedback': '已进入测试计划。'},
            content_type='application/json',
        )

        item.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(item.status, 'planned')
        self.assertEqual(item.plan_time, '2026 Q4')

    def test_control_open_count_excludes_monthly_review_tasks(self):
        control = InternalPlatformSecurityControl.objects.first()
        InternalPlatformSecurityFinding.objects.create(
            control=control,
            platform=control.platform,
            title='额外月度检查',
            finding_type='monthly_review',
        )

        response = self.client.get('/api/cloud-security/internal-platform/overview/')
        control_data = next(item for item in response.json()['controls'] if item['id'] == control.id)
        expected = InternalPlatformSecurityFinding.objects.filter(
            control=control,
            finding_type='rectification',
            status__in=['pending', 'in_progress', 'pending_review'],
        ).count()

        self.assertEqual(control_data['open_findings'], expected)

    def test_finding_can_be_created_progressed_closed_and_reopened(self):
        create_response = self.client.post('/api/cloud-security/internal-platform/findings/', {
            'platform': 'jenkins',
            'scope': '生产发布',
            'title': '测试整改项',
            'severity': 'high',
            'owner': 'CI/CD 负责人',
            'due_date': '2026-08-20',
        }, content_type='application/json')

        self.assertEqual(create_response.status_code, 201)
        finding_id = create_response.json()['id']
        progress_response = self.client.post(f'/api/cloud-security/internal-platform/findings/{finding_id}/progress/', {
            'status': 'pending_review',
            'message': '权限已收敛，等待复核。',
            'ticket_ref': 'SEC-202608-001',
        }, content_type='application/json')
        close_response = self.client.post(f'/api/cloud-security/internal-platform/findings/{finding_id}/close/', {
            'message': '已核对权限和发布记录，满足控制要求。',
            'evidence': 'SEC-202608-001',
        }, content_type='application/json')
        reopen_response = self.client.post(f'/api/cloud-security/internal-platform/findings/{finding_id}/reopen/', {
            'message': '复核发现范围遗漏。',
        }, content_type='application/json')

        finding = InternalPlatformSecurityFinding.objects.get(pk=finding_id)
        self.assertEqual(progress_response.status_code, 200)
        self.assertEqual(close_response.status_code, 200)
        self.assertEqual(reopen_response.status_code, 200)
        self.assertEqual(finding.status, 'pending')
        self.assertEqual(finding.activities.count(), 4)

    def test_high_risk_filter_includes_high_and_critical_findings(self):
        high = InternalPlatformSecurityFinding.objects.create(
            platform='jenkins', title='高风险整改', severity='high', finding_type='rectification'
        )
        critical = InternalPlatformSecurityFinding.objects.create(
            platform='aliyun', title='严重风险整改', severity='critical', finding_type='rectification'
        )
        low = InternalPlatformSecurityFinding.objects.create(
            platform='nacos', title='低风险整改', severity='low', finding_type='rectification'
        )

        response = self.client.get('/api/cloud-security/internal-platform/findings/?finding_type=rectification&severity=high_risk')
        finding_ids = {item['id'] for item in response.json()}

        self.assertEqual(response.status_code, 200)
        self.assertTrue({high.id, critical.id}.issubset(finding_ids))
        self.assertNotIn(low.id, finding_ids)

    def test_overdue_filter_excludes_future_and_closed_findings(self):
        today = timezone.localdate()
        overdue = InternalPlatformSecurityFinding.objects.create(
            platform='archery', title='逾期整改', severity='medium', finding_type='rectification',
            due_date=today - timedelta(days=1),
        )
        future = InternalPlatformSecurityFinding.objects.create(
            platform='nacos', title='未到期整改', severity='medium', finding_type='rectification',
            due_date=today + timedelta(days=1),
        )
        closed = InternalPlatformSecurityFinding.objects.create(
            platform='jenkins', title='已关闭逾期整改', severity='high', finding_type='rectification',
            due_date=today - timedelta(days=2), status='closed',
        )

        response = self.client.get('/api/cloud-security/internal-platform/findings/?finding_type=rectification&overdue=true')
        finding_ids = {item['id'] for item in response.json()}

        self.assertEqual(response.status_code, 200)
        self.assertIn(overdue.id, finding_ids)
        self.assertNotIn(future.id, finding_ids)
        self.assertNotIn(closed.id, finding_ids)

    def test_write_operations_require_manage_permission(self):
        user = User.objects.create_user(username='security-viewer', password='Viewer@123456')
        view_permission = PermissionDefinition.objects.get(code='cloudsecurity.internal_platform.view')
        role = Role.objects.create(code='internal-platform-viewer', name='内部平台安全查看者')
        role.permissions.add(view_permission)
        role.users.add(user)
        self.client.force_login(user)

        response = self.client.post('/api/cloud-security/internal-platform/findings/', {
            'platform': 'nacos',
            'title': '不应允许创建',
            'severity': 'medium',
        }, content_type='application/json')
        threat = InternalSecurityThreat.objects.first()
        threat_response = self.client.post(
            f'/api/cloud-security/internal-platform/threats/{threat.id}/action/',
            {'action': 'resolve'},
            content_type='application/json',
        )
        software = SoftwareSecurityItem.objects.first()
        software_response = self.client.post(
            f'/api/cloud-security/internal-platform/software/{software.id}/status/',
            {'status': 'planned'},
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(threat_response.status_code, 403)
        self.assertEqual(software_response.status_code, 403)
