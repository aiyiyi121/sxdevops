from django.contrib.auth import get_user_model
from django.test import TestCase

from cmdb.models import CIResourceAuthorization, CIType, ConfigItem, ResourceNode
from rbac.models import PermissionDefinition, Role
from rbac.services import ensure_builtin_rbac

from .models import AIOpsChatMessage, AIOpsChatSession, AIOpsKnowledgeEnvironment
from .services import (
    _cmdb_grounded_query_arguments,
    _enrich_cmdb_query_arguments,
    _extract_cmdb_business_line,
    query_cmdb_items,
    query_cmdb_quality,
)


class CMDBNaturalLanguageScopeTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(username='cmdb-scope-admin')
        self.session = AIOpsChatSession.objects.create(user=self.user, title='CMDB 查询范围')
        self.message = AIOpsChatMessage.objects.create(session=self.session, role='user', content='查询资产')
        ci_type = CIType.objects.create(name='服务器', code='CMDB_SCOPE_SERVER')
        trade = ResourceNode.objects.create(name='交易系统', node_type='biz')
        data = ResourceNode.objects.create(name='数据平台', node_type='biz')
        prod_trade = ResourceNode.objects.create(name='prod', node_type='env', parent=trade)
        prod_data = ResourceNode.objects.create(name='prod', node_type='env', parent=data)
        dev_trade = ResourceNode.objects.create(name='dev', node_type='env', parent=trade)
        self.trade_prod = ConfigItem.objects.create(
            name='trade-prod-01', ci_type=ci_type, business_line='交易系统',
            environment='prod', environment_node=prod_trade,
        )
        self.data_prod = ConfigItem.objects.create(
            name='data-prod-01', ci_type=ci_type, business_line='数据平台',
            environment='prod', environment_node=prod_data,
        )
        self.trade_dev = ConfigItem.objects.create(
            name='trade-dev-01', ci_type=ci_type, business_line='交易系统',
            environment='dev', environment_node=dev_trade,
        )
        AIOpsKnowledgeEnvironment.objects.create(name='prod', aliases=['生产环境', '生产'])

    def test_quality_question_does_not_turn_missing_business_ownership_into_filter(self):
        question = '交接前帮我检查 CMDB 资产数据质量：哪些资产缺少关键属性、负责人或业务归属？按影响排序给出整改建议。'
        self.assertEqual(_extract_cmdb_business_line(question, self.user), '')
        result = query_cmdb_quality(self.session, self.message, self.user, query=question)
        self.assertEqual(result['summary']['business_line'], '')
        self.assertEqual(result['summary']['total'], 3)

    def test_platform_data_phrase_does_not_select_data_platform_business(self):
        question = '盘点 prod 环境服务器资产，列出 IP 和负责人，只引用平台数据。'
        grounded = _cmdb_grounded_query_arguments(question, self.user)
        self.assertEqual(grounded['business_line'], '')
        self.assertEqual(_extract_cmdb_business_line(question, self.user), '')
        arguments = _enrich_cmdb_query_arguments(
            {'query': question}, None, question, self.user,
            session=self.session, user_message=self.message,
        )
        result = query_cmdb_items(
            self.session, self.message, self.user,
            **{key: value for key, value in arguments.items() if key in {
                'query', 'environment', 'business_line', 'ci_type', 'search_terms', 'attribute_names',
            }},
        )
        self.assertEqual({item['id'] for item in result['items']}, {self.trade_prod.id, self.data_prod.id})
        self.assertEqual(result['summary']['environment'], 'prod')

    def test_full_business_name_and_unambiguous_alias_keep_environment_filter(self):
        for business in ['数据平台', '交易']:
            with self.subTest(business=business):
                question = f'检查 CMDB {business}生产环境资产数据质量'
                expected = '数据平台' if business == '数据平台' else '交易系统'
                self.assertEqual(_extract_cmdb_business_line(question, self.user), expected)
                self.assertEqual(_cmdb_grounded_query_arguments(question, self.user)['business_line'], expected)
                result = query_cmdb_quality(self.session, self.message, self.user, query=question)
                self.assertEqual(result['summary']['total'], 1)
                self.assertEqual(result['summary']['environment'], 'prod')

    def test_unknown_business_ownership_prose_does_not_invent_catalog_value(self):
        self.assertEqual(_extract_cmdb_business_line('检查资产是否缺少业务归属', self.user), '')
        self.assertEqual(_extract_cmdb_business_line('查看全部业务线资产', self.user), '')
        self.assertEqual(_extract_cmdb_business_line('检查CMDB数据平台prod资产', self.user), '数据平台')

    def test_empty_environment_tree_nodes_keep_matching_unbound_legacy_assets(self):
        ConfigItem.objects.filter(pk__in=[self.trade_prod.pk, self.data_prod.pk]).update(environment_node=None)
        conflicting = ConfigItem.objects.create(
            name='conflicting-prod-field', ci_type=self.trade_dev.ci_type,
            business_line='交易系统', environment='prod', environment_node=self.trade_dev.environment_node,
        )
        result = query_cmdb_items(
            self.session, self.message, self.user,
            query='盘点 prod 环境服务器资产', environment='prod', search_terms=[],
        )
        self.assertTrue(result['summary']['environment_node_ids'])
        self.assertEqual({item['id'] for item in result['items']}, {self.trade_prod.id, self.data_prod.id})
        self.assertNotIn(conflicting.id, {item['id'] for item in result['items']})

    def test_explicit_unauthorized_business_does_not_widen_to_authorized_assets(self):
        ensure_builtin_rbac()
        role = Role.objects.create(code='cmdb-scope-reader', name='CMDB 范围读者')
        role.permissions.add(*PermissionDefinition.objects.filter(code='cmdb.ci.view'))
        user = get_user_model().objects.create_user(username='cmdb-scope-reader')
        user.rbac_roles.add(role)
        CIResourceAuthorization.objects.create(
            name='交易系统授权', principal_type='user', principal=user.username,
            permission='view', business_line='交易系统',
        )
        session = AIOpsChatSession.objects.create(user=user)
        message = AIOpsChatMessage.objects.create(session=session, role='user', content='检查数据平台业务资产质量')
        result = query_cmdb_quality(session, message, user, query=message.content)
        self.assertEqual(result['summary']['total'], 0)
        self.assertEqual(result['summary']['business_line'], '数据平台')
