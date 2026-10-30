"""
SQL 语法检查规则引擎
纯 Python 实现，检测常见 SQL 安全和规范问题。
"""
import json
import re
import sqlparse


class CheckItem:
    """单条检查结果"""
    def __init__(self, level, rule_name, message, line_no=None):
        self.level = level
        self.rule_name = rule_name
        self.message = message
        self.line_no = line_no

    def to_dict(self):
        return {
            'level': self.level,
            'rule_name': self.rule_name,
            'message': self.message,
            'line_no': self.line_no,
        }


def check_sql(sql_content, sql_type='DML', db_type='mysql'):
    """
    对 SQL 文本进行语法/安全检查。
    返回 CheckItem 列表。
    """
    if db_type == 'mongodb':
        return _check_mongodb_command(sql_content, sql_type)

    results = []
    statements = _split_statements(sql_content)

    for idx, stmt in enumerate(statements, 1):
        stmt_stripped = stmt.strip()
        if not stmt_stripped:
            continue

        upper = sqlparse.format(stmt_stripped, strip_comments=True).strip().upper()
        statement_type = sqlparse.parse(stmt_stripped)[0].get_type()

        if db_type == 'postgresql':
            if re.search(r'`|\bAUTO_INCREMENT\b|\bUNSIGNED\b|\bENGINE\s*=|\bADD\s+INDEX\b', upper):
                results.append(CheckItem('error', 'POSTGRESQL_DIALECT',
                                         f'语句 #{idx}: 包含 MySQL 专用语法，请改为 PostgreSQL 语法', line_no=idx))
            if re.match(r'^(BEGIN|START\s+TRANSACTION|COMMIT|END|ROLLBACK|ABORT|PREPARE\s+TRANSACTION|SAVEPOINT|RELEASE)\b', upper):
                results.append(CheckItem('error', 'TRANSACTION_CONTROL',
                                         f'语句 #{idx}: 工单事务由平台统一提交或回滚', line_no=idx))

        if statement_type == 'DELETE' and 'WHERE' not in upper:
            results.append(CheckItem(
                'error', 'NO_WHERE_DELETE',
                f'语句 #{idx}: DELETE 语句缺少 WHERE 条件，可能删除全表数据',
                line_no=idx,
            ))

        if statement_type == 'UPDATE' and 'WHERE' not in upper:
            results.append(CheckItem(
                'error', 'NO_WHERE_UPDATE',
                f'语句 #{idx}: UPDATE 语句缺少 WHERE 条件，可能更新全表数据',
                line_no=idx,
            ))

        if re.search(r'\bSELECT\s+\*', upper):
            results.append(CheckItem(
                'warning', 'SELECT_STAR',
                f'语句 #{idx}: 建议指定具体列名，避免使用 SELECT *',
                line_no=idx,
            ))

        if upper.startswith('INSERT') and re.search(r'INSERT\s+INTO\s+\S+\s+VALUES', upper):
            results.append(CheckItem(
                'warning', 'INSERT_NO_COLUMNS',
                f'语句 #{idx}: INSERT 语句建议指定目标列名',
                line_no=idx,
            ))

        if upper.startswith('TRUNCATE'):
            results.append(CheckItem(
                'error', 'TRUNCATE_TABLE',
                f'语句 #{idx}: TRUNCATE TABLE 操作风险极高，建议使用 DELETE 并添加 WHERE 条件',
                line_no=idx,
            ))

        if sql_type == 'DML' and upper.startswith('DROP'):
            results.append(CheckItem(
                'error', 'DROP_IN_DML',
                f'语句 #{idx}: DML 工单中不允许 DROP 操作，请提交 DDL 工单',
                line_no=idx,
            ))

        if sql_type == 'DDL' and upper.startswith('CREATE TABLE'):
            table_match = re.search(r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`"]?(\w+)[`"]?', upper)
            if table_match:
                table_name = table_match.group(1)
                if not re.match(r'^[a-z][a-z0-9_]*$', table_name, re.IGNORECASE):
                    results.append(CheckItem(
                        'warning', 'TABLE_NAME_CONVENTION',
                        f'语句 #{idx}: 表名 "{table_name}" 建议使用字母开头的小写 + 下划线命名',
                        line_no=idx,
                    ))

        if len(stmt_stripped) > 10000:
            results.append(CheckItem(
                'warning', 'SQL_TOO_LONG',
                f'语句 #{idx}: SQL 长度超过 10000 字符，建议拆分',
                line_no=idx,
            ))

        if re.search(r';\s*--', stmt_stripped) or re.search(r'/\*.*\*/', stmt_stripped):
            results.append(CheckItem(
                'info', 'COMMENT_PATTERN',
                f'语句 #{idx}: 检测到注释模式，请确认是否为预期内容',
                line_no=idx,
            ))

    if not results:
        results.append(CheckItem(
            'info', 'ALL_PASSED',
            '所有检查项已通过',
        ))

    return results


def _check_mongodb_command(sql_content, sql_type):
    command = (sql_content or '').strip()
    if not command:
        return [CheckItem('error', 'EMPTY_COMMAND', 'MongoDB 命令不能为空')]

    action, separator, payload = command.partition(' ')
    if not separator or not payload.strip():
        return [CheckItem('error', 'INVALID_FORMAT', 'MongoDB 命令格式应为：动作 + JSON 参数')]

    try:
        payload_data = json.loads(payload.strip())
    except json.JSONDecodeError as exc:
        return [CheckItem('error', 'INVALID_JSON', f'MongoDB 命令 JSON 解析失败: {exc}')]

    action = action.strip().lower()
    dml_actions = {'insertone', 'insertmany', 'updateone', 'updatemany', 'deleteone', 'deletemany'}
    ddl_actions = {'createcollection', 'dropcollection', 'createindex', 'dropindex'}
    allowed_actions = dml_actions if sql_type == 'DML' else ddl_actions
    results = []

    if action not in allowed_actions:
        results.append(CheckItem(
            'error', 'INVALID_COMMAND_TYPE',
            f'{sql_type} 工单不支持 {action} 命令',
        ))

    if action in {'updateone', 'updatemany'} and not payload_data.get('filter'):
        results.append(CheckItem(
            'error', 'NO_FILTER_UPDATE',
            'MongoDB update 命令必须提供非空 filter 条件',
        ))

    if action in {'deleteone', 'deletemany'} and not payload_data.get('filter'):
        results.append(CheckItem(
            'error', 'NO_FILTER_DELETE',
            'MongoDB delete 命令必须提供非空 filter 条件',
        ))

    if action == 'insertmany' and len(payload_data.get('documents', [])) > 1000:
        results.append(CheckItem(
            'warning', 'INSERT_MANY_LARGE_BATCH',
            'insertMany 单次写入文档较多，建议拆分批次',
        ))

    if action in {'dropcollection', 'dropindex'}:
        results.append(CheckItem(
            'warning', 'DESTRUCTIVE_DDL',
            f'{action} 属于高风险变更，请确认影响范围',
        ))

    if not results:
        results.append(CheckItem('info', 'ALL_PASSED', '所有检查项已通过'))
    return results


def _split_statements(sql_content):
    """Preserve quoted semicolons, comments and PostgreSQL dollar-quoted bodies."""
    return sqlparse.split(sql_content or '')
