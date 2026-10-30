from django.db import migrations


ASSET_ITEM_FIELDS = (
    {
        'code': 'asset_code',
        'name': '资产编号',
        'field_type': 'string',
        'field_group': '基础信息',
        'required': True,
        'unique': True,
        'is_searchable': True,
        'sort_order': 10,
    },
    {
        'code': 'item_category',
        'name': '物品类型',
        'field_type': 'enum',
        'field_group': '基础信息',
        'required': True,
        'is_searchable': True,
        'options': [
            {'value': 'mobile_device', 'label': '移动终端'},
            {'value': 'office_equipment', 'label': '办公设备'},
            {'value': 'meeting_equipment', 'label': '会议设备'},
            {'value': 'network_peripheral', 'label': '网络外设'},
            {'value': 'furniture', 'label': '家具与工位'},
            {'value': 'other', 'label': '其他'},
        ],
        'sort_order': 20,
    },
    {
        'code': 'brand_model',
        'name': '品牌型号',
        'field_type': 'string',
        'field_group': '基础信息',
        'is_searchable': True,
        'sort_order': 30,
    },
    {
        'code': 'serial_number',
        'name': '序列号 / IMEI',
        'field_type': 'string',
        'field_group': '基础信息',
        'unique': True,
        'is_searchable': True,
        'sort_order': 40,
    },
    {
        'code': 'storage_location',
        'name': '存放地点',
        'field_type': 'string',
        'field_group': '保管信息',
        'required': True,
        'is_searchable': True,
        'sort_order': 50,
    },
    {
        'code': 'custodian',
        'name': '保管人',
        'field_type': 'string',
        'field_group': '保管信息',
        'is_searchable': True,
        'sort_order': 60,
    },
    {
        'code': 'usage_status',
        'name': '使用状态',
        'field_type': 'enum',
        'field_group': '状态信息',
        'default': 'available',
        'is_searchable': True,
        'options': [
            {'value': 'available', 'label': '可用'},
            {'value': 'in_use', 'label': '使用中'},
            {'value': 'maintenance', 'label': '维修中'},
            {'value': 'retired', 'label': '已报废'},
        ],
        'sort_order': 70,
    },
    {
        'code': 'purchase_date',
        'name': '采购日期',
        'field_type': 'date',
        'field_group': '生命周期',
        'sort_order': 80,
    },
    {
        'code': 'warranty_end_date',
        'name': '维保到期日',
        'field_type': 'date',
        'field_group': '生命周期',
        'sort_order': 90,
    },
    {
        'code': 'department',
        'name': '部门',
        'field_type': 'string',
        'field_group': '归属信息',
        'is_searchable': True,
        'sort_order': 890,
    },
    {
        'code': 'monthly_cost',
        'name': '月成本',
        'field_type': 'decimal',
        'field_group': '成本信息',
        'sort_order': 950,
    },
    {
        'code': 'cost_center',
        'name': '成本中心',
        'field_type': 'string',
        'field_group': '成本信息',
        'sort_order': 951,
    },
)


def promote_asset_item_builtin(apps, schema_editor):
    CIField = apps.get_model('cmdb', 'CIField')
    CIModelGroup = apps.get_model('cmdb', 'CIModelGroup')
    CIType = apps.get_model('cmdb', 'CIType')

    group, _ = CIModelGroup.objects.update_or_create(
        code='external',
        defaults={
            'name': '通用资源与服务',
            'description': '第三方服务、办公物品及其合同、账号、供应商和保管信息。',
            'sort_order': 80,
            'is_builtin': True,
            'is_active': True,
        },
    )
    asset_item = CIType.objects.filter(code='ASSET_ITEM').first()
    if asset_item is None:
        asset_item = CIType.objects.filter(name='资产物品').first()
    if asset_item is None:
        asset_item = CIType.objects.create(name='资产物品', code='ASSET_ITEM')

    asset_item.code = 'ASSET_ITEM'
    asset_item.group = group
    asset_item.icon = 'Goods'
    asset_item.color = '#475569'
    asset_item.description = '公共手机、办公设备、会议设备等可登记、保管和盘点的实物资产。'
    asset_item.is_builtin = True
    asset_item.is_active = True
    asset_item.save()

    for payload in ASSET_ITEM_FIELDS:
        defaults = {
            'name': payload['name'],
            'field_type': payload['field_type'],
            'field_group': payload['field_group'],
            'required': payload.get('required', False),
            'unique': payload.get('unique', False),
            'default': payload.get('default'),
            'options': payload.get('options', []),
            'validation': {},
            'sync_mode': 'manual',
            'is_builtin': True,
            'is_display': True,
            'is_searchable': payload.get('is_searchable', False),
            'is_sensitive': False,
            'is_active': True,
            'sort_order': payload['sort_order'],
        }
        CIField.objects.update_or_create(ci_type=asset_item, code=payload['code'], defaults=defaults)


class Migration(migrations.Migration):

    dependencies = [
        ('cmdb', '0017_remove_source_metadata_ci_fields'),
    ]

    operations = [
        migrations.RunPython(promote_asset_item_builtin, migrations.RunPython.noop),
    ]
