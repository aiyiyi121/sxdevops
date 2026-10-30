from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from cmdb.models import ResourceNode
from ops.models import DeploymentApprovalFlow, TransactionTicket


class TransactionTicketApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_superuser('ticket-admin', 'ticket@example.com', 'Admin@123456')
        self.client.force_authenticate(user=self.user)
        self.biz_node = ResourceNode.objects.create(name='电商业务', node_type='biz')
        ResourceNode.objects.create(name='prod', node_type='env', parent=self.biz_node)
        ResourceNode.objects.create(name='test', node_type='env', parent=self.biz_node)
        self.flow = DeploymentApprovalFlow.objects.create(
            name='生产标准审批',
            environment='prod',
            is_active=True,
            created_by=self.user.username,
        )

    def test_create_transaction_ticket_sets_applicant_from_request_user(self):
        response = self.client.post(
            '/api/transaction-tickets/',
            {
                'title': '生产跳板机账号收口',
                'ticket_type': 'access',
                'priority': 'high',
                'business_line': '电商业务',
                'environment': 'prod',
                'approval_flow': self.flow.id,
                'owner': '平台运维',
                'window': '今晚 22:00-23:00',
                'description': '统一收敛临时账号并核对最小权限。',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        ticket = TransactionTicket.objects.get()
        self.assertEqual(ticket.applicant, self.user.username)
        self.assertEqual(ticket.status, TransactionTicket.STATUS_PENDING)
        self.assertEqual(ticket.approval_flow_id, self.flow.id)

    def test_create_vulnerability_ticket_uses_vulnerability_type(self):
        response = self.client.post(
            '/api/transaction-tickets/',
            {
                'title': 'OpenSSH 漏洞处理',
                'ticket_type': TransactionTicket.TYPE_VULNERABILITY,
                'priority': 'high',
                'business_line': '电商业务',
                'environment': 'prod',
                'approval_flow': self.flow.id,
                'owner': '安全运营',
                'window': '2026-09-03 前完成',
                'description': '完成补丁修复并由安全负责人复测确认。',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        ticket = TransactionTicket.objects.get()
        self.assertEqual(ticket.ticket_type, TransactionTicket.TYPE_VULNERABILITY)
        self.assertEqual(ticket.get_ticket_type_display(), '漏洞处理')

    def test_transaction_ticket_workflow_actions_persist_status(self):
        ticket = TransactionTicket.objects.create(
            title='预发核心链路巡检',
            ticket_type='inspection',
            priority='medium',
            business_line='电商业务',
            environment='prod',
            approval_flow=self.flow,
            owner='值班运维',
            applicant='dev-a',
            description='巡检发布前链路、Redis 和容器副本状态。',
        )

        approve_res = self.client.post(f'/api/transaction-tickets/{ticket.id}/approve/', format='json')
        self.assertEqual(approve_res.status_code, 200)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, TransactionTicket.STATUS_APPROVED)

        process_res = self.client.post(f'/api/transaction-tickets/{ticket.id}/start_process/', format='json')
        self.assertEqual(process_res.status_code, 200)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, TransactionTicket.STATUS_PROCESSING)

        complete_res = self.client.post(f'/api/transaction-tickets/{ticket.id}/complete/', format='json')
        self.assertEqual(complete_res.status_code, 200)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, TransactionTicket.STATUS_DONE)
