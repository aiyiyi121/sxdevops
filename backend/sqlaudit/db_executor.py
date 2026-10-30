"""
数据库执行器
支持 MySQL、PostgreSQL 与 MongoDB。
"""
import json
import time

import pymysql
import psycopg
import sqlparse
from psycopg.rows import dict_row
from pymysql.cursors import DictCursor

try:
    from pymongo import MongoClient
except ImportError:  # pragma: no cover
    MongoClient = None


MYSQL_LIKE_TYPES = {'mysql'}
MONGODB_TYPE = 'mongodb'
MYSQL_SYSTEM_DATABASES = {'information_schema', 'mysql', 'performance_schema', 'sys'}
MONGODB_SYSTEM_DATABASES = {'admin', 'config', 'local'}
MONGODB_READ_ACTIONS = {'find', 'aggregate', 'count', 'distinct'}
MONGODB_WRITE_ACTIONS = {
    'insertone', 'insertmany',
    'updateone', 'updatemany',
    'deleteone', 'deletemany',
    'createcollection', 'dropcollection',
    'createindex', 'dropindex',
}
DEMO_DATASOURCE_PROFILES = {
    'commerce-prod-postgresql': {
        'message': '演示数据源连接正常（模拟）',
        'databases': ['order_center', 'payment_center', 'member_center'],
    },
    'member-staging-mysql': {
        'message': '演示数据源连接正常（模拟）',
        'databases': ['order_center', 'member_center', 'scheduler'],
    },
    'risk-analytics-mongo': {
        'message': '演示数据源连接正常（模拟）',
        'databases': ['risk_events'],
    },
}


def _get_db_type(datasource):
    return getattr(datasource, 'db_type', 'mysql') or 'mysql'


def _get_demo_profile(datasource):
    return DEMO_DATASOURCE_PROFILES.get(getattr(datasource, 'name', ''))


def validate_query_content(datasource, sql_content):
    db_type = _get_db_type(datasource)
    if db_type == MONGODB_TYPE:
        try:
            action, _ = _parse_mongodb_command(sql_content)
        except ValueError as exc:
            return str(exc)
        if action not in MONGODB_READ_ACTIONS:
            return 'MongoDB 查询仅允许 find / aggregate / count / distinct 命令'
        return None

    if db_type == 'postgresql':
        statements = sqlparse.parse(sql_content or '')
        if len(statements) != 1:
            return 'PostgreSQL 查询仅允许一条 SELECT / WITH / SHOW 只读语句'
        statement = statements[0]
        if statement.get_type() != 'SELECT' and not str(statement).lstrip().upper().startswith('SHOW '):
            return 'PostgreSQL 查询仅允许 SELECT / WITH / SHOW 只读语句'
        for token in statement.flatten():
            if token.ttype in sqlparse.tokens.Keyword.DML and token.normalized != 'SELECT':
                return 'PostgreSQL 查询不允许在 WITH 中执行写入操作'
            if token.ttype in sqlparse.tokens.Keyword and token.normalized in {'INTO', 'FOR UPDATE', 'FOR SHARE'}:
                return 'PostgreSQL 查询不允许写入或加行锁'
        return None

    upper = sql_content.strip().upper()
    if not upper.startswith('SELECT') and not upper.startswith('SHOW') and not upper.startswith('DESC'):
        return '查询工单只允许 SELECT / SHOW / DESC 语句'
    return None


def test_connection(datasource):
    demo_profile = _get_demo_profile(datasource)
    if demo_profile:
        return True, demo_profile['message']

    db_type = _get_db_type(datasource)
    if db_type in MYSQL_LIKE_TYPES:
        return _test_mysql_connection(datasource)
    if db_type == 'postgresql':
        return _test_postgresql_connection(datasource)
    if db_type == MONGODB_TYPE:
        return _test_mongodb_connection(datasource)
    return False, f'暂不支持的数据源类型: {db_type}'


def get_databases(datasource):
    demo_profile = _get_demo_profile(datasource)
    if demo_profile:
        return demo_profile['databases']

    db_type = _get_db_type(datasource)
    if db_type in MYSQL_LIKE_TYPES:
        return _get_mysql_databases(datasource)
    if db_type == 'postgresql':
        return _get_postgresql_databases(datasource)
    if db_type == MONGODB_TYPE:
        return _get_mongodb_databases(datasource)
    return []


def execute_sql(datasource, database, sql_content):
    demo_profile = _get_demo_profile(datasource)
    if demo_profile:
        return _execute_demo_sql(datasource, database, sql_content)

    db_type = _get_db_type(datasource)
    if db_type in MYSQL_LIKE_TYPES:
        return _execute_mysql_sql(datasource, database, sql_content)
    if db_type == 'postgresql':
        return _execute_postgresql_sql(datasource, database, sql_content)
    if db_type == MONGODB_TYPE:
        return _execute_mongodb_write(datasource, database, sql_content)
    return False, 0, 0, f'暂不支持的数据源类型: {db_type}'


def execute_query(datasource, database, sql_content, limit=200):
    demo_profile = _get_demo_profile(datasource)
    if demo_profile:
        return _execute_demo_query(datasource, database, sql_content, limit)

    db_type = _get_db_type(datasource)
    if db_type in MYSQL_LIKE_TYPES:
        return _execute_mysql_query(datasource, database, sql_content, limit)
    if db_type == 'postgresql':
        return _execute_postgresql_query(datasource, database, sql_content, limit)
    if db_type == MONGODB_TYPE:
        return _execute_mongodb_query(datasource, database, sql_content, limit)
    return False, [], [], 0, 0, f'暂不支持的数据源类型: {db_type}'


def _build_mysql_connect_kwargs(datasource, database=None, cursorclass=None, autocommit=None, timeout=5):
    kwargs = {
        'host': datasource.host,
        'port': datasource.port,
        'user': datasource.user,
        'password': datasource.password,
        'charset': datasource.charset,
        'connect_timeout': timeout,
    }
    if database:
        kwargs['database'] = database
    if cursorclass:
        kwargs['cursorclass'] = cursorclass
    if autocommit is not None:
        kwargs['autocommit'] = autocommit
    return kwargs


def _test_mysql_connection(datasource):
    try:
        conn = pymysql.connect(**_build_mysql_connect_kwargs(datasource, timeout=5))
        conn.close()
        return True, '连接成功'
    except pymysql.Error as exc:
        return False, f'连接失败: {exc}'
    except Exception as exc:
        return False, f'连接异常: {exc}'


def _get_mysql_databases(datasource):
    try:
        conn = pymysql.connect(**_build_mysql_connect_kwargs(datasource, timeout=5))
        with conn.cursor() as cursor:
            cursor.execute('SHOW DATABASES')
            databases = [row[0] for row in cursor.fetchall()]
        conn.close()
        return [db for db in databases if db not in MYSQL_SYSTEM_DATABASES]
    except Exception:
        return []


def _execute_mysql_sql(datasource, database, sql_content):
    start = time.time()
    try:
        conn = pymysql.connect(**_build_mysql_connect_kwargs(datasource, database=database, autocommit=False, timeout=10))
        total_affected = 0
        logs = []
        try:
            with conn.cursor() as cursor:
                statements = [statement.strip() for statement in sql_content.split(';') if statement.strip()]
                for index, statement in enumerate(statements, 1):
                    cursor.execute(statement)
                    affected = cursor.rowcount
                    total_affected += max(affected, 0)
                    logs.append(f'语句 #{index}: 影响 {affected} 行')
            conn.commit()
            duration = int((time.time() - start) * 1000)
            return True, total_affected, duration, '\n'.join(logs)
        except Exception as exc:
            conn.rollback()
            duration = int((time.time() - start) * 1000)
            return False, 0, duration, f'执行失败: {exc}'
        finally:
            conn.close()
    except pymysql.Error as exc:
        duration = int((time.time() - start) * 1000)
        return False, 0, duration, f'连接失败: {exc}'
    except Exception as exc:
        duration = int((time.time() - start) * 1000)
        return False, 0, duration, f'执行异常: {exc}'


def _execute_mysql_query(datasource, database, sql_content, limit):
    start = time.time()
    try:
        conn = pymysql.connect(
            **_build_mysql_connect_kwargs(
                datasource,
                database=database,
                cursorclass=DictCursor,
                timeout=10,
            ),
        )
        with conn.cursor() as cursor:
            cursor.execute(sql_content)
            rows = cursor.fetchmany(limit)
            count = cursor.rowcount
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
        conn.close()
        duration = int((time.time() - start) * 1000)
        return True, columns, rows, count, duration, None
    except Exception as exc:
        duration = int((time.time() - start) * 1000)
        return False, [], [], 0, duration, str(exc)


def _postgresql_connect_kwargs(datasource, database=None):
    return {
        'host': datasource.host,
        'port': datasource.port,
        'user': datasource.user,
        'password': datasource.password,
        'dbname': database or getattr(datasource, 'database', '') or 'postgres',
        'connect_timeout': 10,
        'client_encoding': 'UTF8',
    }


def _test_postgresql_connection(datasource):
    try:
        with psycopg.connect(**_postgresql_connect_kwargs(datasource)) as conn:
            conn.execute('SELECT 1').fetchone()
        return True, '连接成功'
    except Exception as exc:
        return False, f'连接失败: {exc}'


def _get_postgresql_databases(datasource):
    try:
        with psycopg.connect(**_postgresql_connect_kwargs(datasource)) as conn:
            rows = conn.execute(
                "SELECT datname FROM pg_database WHERE datallowconn AND NOT datistemplate "
                "AND has_database_privilege(current_user, oid, 'CONNECT') ORDER BY datname"
            ).fetchall()
            return [row[0] for row in rows]
    except Exception:
        return []


def _execute_postgresql_sql(datasource, database, sql_content):
    start = time.monotonic()
    try:
        statements = sqlparse.split(sql_content or '')
        if not statements:
            raise ValueError('SQL 内容不能为空')
        # The executor owns the transaction: user statements must not commit a partial order.
        for statement in statements:
            parsed = sqlparse.parse(statement)[0]
            tokens = [token for token in parsed.flatten() if not token.is_whitespace
                      and token.ttype not in sqlparse.tokens.Comment]
            first = tokens[0].normalized if tokens else ''
            if first in {'BEGIN', 'START', 'COMMIT', 'END', 'ROLLBACK', 'ABORT', 'PREPARE', 'SAVEPOINT', 'RELEASE'}:
                raise ValueError('工单事务由平台管理，不允许自行提交、回滚或准备事务')
        logs = []
        affected_rows = 0
        with psycopg.connect(**_postgresql_connect_kwargs(datasource, database)) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SET LOCAL statement_timeout = '60s'")
                for index, statement in enumerate(statements, 1):
                    cursor.execute(statement)
                    affected = max(cursor.rowcount, 0)
                    affected_rows += affected
                    logs.append(f'语句 #{index}: 影响 {affected} 行')
        return True, affected_rows, int((time.monotonic() - start) * 1000), '\n'.join(logs)
    except Exception as exc:
        return False, 0, int((time.monotonic() - start) * 1000), f'执行失败（事务已回滚）: {exc}'


def _execute_postgresql_query(datasource, database, sql_content, limit):
    start = time.monotonic()
    error = validate_query_content(datasource, sql_content)
    if error:
        return False, [], [], 0, 0, error
    try:
        with psycopg.connect(**_postgresql_connect_kwargs(datasource, database), row_factory=dict_row) as conn:
            with conn.cursor() as control:
                # A server-enforced read-only transaction also blocks writes hidden in CTEs/functions.
                control.execute('SET TRANSACTION READ ONLY')
                control.execute("SET LOCAL statement_timeout = '30s'")
            # A server cursor limits transferred rows instead of buffering a large SELECT in Python.
            statement = sqlparse.parse(sql_content)[0]
            with conn.cursor(name='sqlaudit_query' if statement.get_type() == 'SELECT' else '') as cursor:
                cursor.execute(sql_content)
                rows = cursor.fetchmany(max(1, min(int(limit), 2000)))
                columns = [column.name for column in cursor.description] if cursor.description else []
        return True, columns, rows, len(rows), int((time.monotonic() - start) * 1000), None
    except Exception as exc:
        return False, [], [], 0, int((time.monotonic() - start) * 1000), str(exc)


def _execute_demo_sql(datasource, database, sql_content):
    start = time.time()
    content = (sql_content or '').lower()
    if 'task_run_log' in content and 'delete from' in content:
        affected_rows = 18432
        log = '演示执行完成：已清理 30 天前测试环境任务日志 18432 行'
    elif 'payment_callback_log' in content and 'update' in content:
        affected_rows = 362
        log = '演示执行完成：已修正支付回调幂等标记 362 行'
    elif 'alter table' in content:
        affected_rows = 0
        log = '演示执行完成：DDL 变更已提交，建议继续观察元数据锁与回滚窗口'
    else:
        affected_rows = 12
        log = '演示执行完成：已按模拟策略执行 SQL 变更'
    duration = max(int((time.time() - start) * 1000), 80)
    return True, affected_rows, duration, log


def _execute_demo_query(datasource, database, sql_content, limit):
    start = time.time()
    db_type = _get_db_type(datasource)
    content = (sql_content or '').strip()
    lowered = content.lower()

    if db_type == MONGODB_TYPE:
        rows = _build_demo_mongodb_rows(lowered)
    else:
        rows = _build_demo_sql_rows(lowered, database)

    rows = rows[:limit]
    columns = _extract_columns(rows)
    duration = max(int((time.time() - start) * 1000), 60)
    return True, columns, rows, len(rows), duration, None


def _build_demo_sql_rows(sql_content, database):
    if 'from orders' in sql_content and 'failed' in sql_content:
        return [
            {'order_id': 'SO202604010021', 'status': 'FAILED', 'amount': 299.00, 'updated_at': '2026-04-01 09:42:18'},
            {'order_id': 'SO202604010017', 'status': 'FAILED', 'amount': 88.00, 'updated_at': '2026-04-01 09:18:05'},
            {'order_id': 'SO202603312241', 'status': 'FAILED', 'amount': 156.50, 'updated_at': '2026-03-31 23:57:44'},
        ]
    if 'payment_callback_log' in sql_content and 'group by merchant_id' in sql_content:
        return [
            {'merchant_id': 'mch_live_001', 'callback_count': 128},
            {'merchant_id': 'mch_live_017', 'callback_count': 92},
            {'merchant_id': 'mch_live_008', 'callback_count': 75},
        ]
    if 'from member_profile' in sql_content and 'last_login_at' in sql_content:
        return [
            {'id': 1024, 'nickname': '晨星用户', 'last_login_at': '2026-04-01 08:11:45'},
            {'id': 2048, 'nickname': '风铃计划', 'last_login_at': '2026-03-31 21:08:12'},
            {'id': 4096, 'nickname': 'demo_vip', 'last_login_at': '2026-03-31 19:36:54'},
        ]
    if 'show table status' in sql_content and 'task_run_log' in sql_content:
        return [
            {
                'Name': 'task_run_log',
                'Rows': 284231,
                'Data_length': 52428800,
                'Index_length': 7340032,
                'Update_time': '2026-03-31 09:15:13',
            },
        ]
    if 'from member_profile' in sql_content and 'group by city' in sql_content:
        return [
            {'city': '上海', 'total': 8421},
            {'city': '杭州', 'total': 6330},
            {'city': '深圳', 'total': 5124},
        ]
    return [
        {
            'database': database,
            'message': '演示查询已命中模拟数据集',
            'preview_rows': 3,
        },
    ]


def _build_demo_mongodb_rows(sql_content):
    if 'count' in sql_content:
        return [{'count': 27}]
    if 'distinct' in sql_content:
        return [{'value': 'high'}, {'value': 'medium'}, {'value': 'low'}]
    if 'aggregate' in sql_content:
        return [
            {'_id': 'open', 'total': 16},
            {'_id': 'processing', 'total': 7},
            {'_id': 'closed', 'total': 4},
        ]
    return [
        {'event_id': 'risk-evt-1001', 'level': 'high', 'status': 'open', 'score': 92},
        {'event_id': 'risk-evt-1002', 'level': 'high', 'status': 'open', 'score': 88},
        {'event_id': 'risk-evt-1011', 'level': 'high', 'status': 'open', 'score': 84},
    ]


def _ensure_pymongo():
    if MongoClient is None:
        raise RuntimeError('未安装 pymongo，无法连接 MongoDB 数据源')


def _get_mongo_client(datasource):
    _ensure_pymongo()
    kwargs = {
        'host': datasource.host,
        'port': datasource.port,
        'serverSelectionTimeoutMS': 5000,
    }
    if datasource.user:
        kwargs['username'] = datasource.user
    if datasource.password:
        kwargs['password'] = datasource.password
        kwargs['authSource'] = 'admin'
    return MongoClient(**kwargs)


def _test_mongodb_connection(datasource):
    try:
        client = _get_mongo_client(datasource)
        client.admin.command('ping')
        client.close()
        return True, '连接成功'
    except Exception as exc:
        return False, f'连接失败: {exc}'


def _get_mongodb_databases(datasource):
    try:
        client = _get_mongo_client(datasource)
        databases = [name for name in client.list_database_names() if name not in MONGODB_SYSTEM_DATABASES]
        client.close()
        return databases
    except Exception:
        return []


def _parse_mongodb_command(sql_content):
    command = (sql_content or '').strip()
    if not command:
        raise ValueError('MongoDB 命令不能为空')
    action, separator, payload = command.partition(' ')
    if not separator or not payload.strip():
        raise ValueError('MongoDB 命令格式应为：动作 + JSON 参数')
    try:
        return action.strip().lower(), json.loads(payload.strip())
    except json.JSONDecodeError as exc:
        raise ValueError(f'MongoDB 命令 JSON 解析失败: {exc}') from exc


def _normalize_mongo_value(value):
    if isinstance(value, dict):
        return {key: _normalize_mongo_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_mongo_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    return str(value)


def _extract_columns(rows):
    columns = []
    seen = set()
    for row in rows:
        for key in row.keys():
            if key not in seen:
                seen.add(key)
                columns.append(key)
    return columns


def _execute_mongodb_query(datasource, database, sql_content, limit):
    start = time.time()
    client = None
    try:
        action, payload = _parse_mongodb_command(sql_content)
        if action not in MONGODB_READ_ACTIONS:
            return False, [], [], 0, 0, 'MongoDB 查询仅允许 find / aggregate / count / distinct 命令'

        client = _get_mongo_client(datasource)
        db = client[database]

        if action == 'find':
            collection = db[payload['collection']]
            cursor = collection.find(
                payload.get('filter', {}),
                payload.get('projection'),
            )
            sort = payload.get('sort')
            if sort:
                cursor = cursor.sort(list(sort.items()))
            skip = payload.get('skip')
            if skip:
                cursor = cursor.skip(int(skip))
            cursor = cursor.limit(int(payload.get('limit', limit)))
            rows = [_normalize_mongo_value(item) for item in cursor]
        elif action == 'aggregate':
            collection = db[payload['collection']]
            pipeline = payload.get('pipeline', [])
            rows = [_normalize_mongo_value(item) for item in collection.aggregate(pipeline)]
            rows = rows[:int(payload.get('limit', limit))]
        elif action == 'count':
            collection = db[payload['collection']]
            rows = [{'count': collection.count_documents(payload.get('filter', {}))}]
        else:
            collection = db[payload['collection']]
            rows = [{'value': _normalize_mongo_value(item)} for item in collection.distinct(payload['field'], payload.get('filter', {}))]
            rows = rows[:int(payload.get('limit', limit))]

        columns = _extract_columns(rows)
        duration = int((time.time() - start) * 1000)
        return True, columns, rows, len(rows), duration, None
    except Exception as exc:
        duration = int((time.time() - start) * 1000)
        return False, [], [], 0, duration, str(exc)
    finally:
        if client is not None:
            client.close()


def _execute_mongodb_write(datasource, database, sql_content):
    start = time.time()
    client = None
    try:
        action, payload = _parse_mongodb_command(sql_content)
        if action not in MONGODB_WRITE_ACTIONS:
            return False, 0, 0, 'MongoDB 变更仅支持 insert/update/delete/collection/index 相关命令'

        client = _get_mongo_client(datasource)
        db = client[database]
        affected_rows = 0

        if action == 'insertone':
            result = db[payload['collection']].insert_one(payload['document'])
            affected_rows = 1
            log = f'insertOne 成功，_id={result.inserted_id}'
        elif action == 'insertmany':
            result = db[payload['collection']].insert_many(payload.get('documents', []))
            affected_rows = len(result.inserted_ids)
            log = f'insertMany 成功，插入 {affected_rows} 条'
        elif action == 'updateone':
            result = db[payload['collection']].update_one(payload.get('filter', {}), payload['update'], upsert=payload.get('upsert', False))
            affected_rows = result.modified_count
            log = f'updateOne 完成，匹配 {result.matched_count} 条，修改 {result.modified_count} 条'
        elif action == 'updatemany':
            result = db[payload['collection']].update_many(payload.get('filter', {}), payload['update'], upsert=payload.get('upsert', False))
            affected_rows = result.modified_count
            log = f'updateMany 完成，匹配 {result.matched_count} 条，修改 {result.modified_count} 条'
        elif action == 'deleteone':
            result = db[payload['collection']].delete_one(payload.get('filter', {}))
            affected_rows = result.deleted_count
            log = f'deleteOne 完成，删除 {result.deleted_count} 条'
        elif action == 'deletemany':
            result = db[payload['collection']].delete_many(payload.get('filter', {}))
            affected_rows = result.deleted_count
            log = f'deleteMany 完成，删除 {result.deleted_count} 条'
        elif action == 'createcollection':
            db.create_collection(payload['name'])
            log = f'createCollection 完成，集合 {payload["name"]} 已创建'
        elif action == 'dropcollection':
            db.drop_collection(payload['name'])
            log = f'dropCollection 完成，集合 {payload["name"]} 已删除'
        elif action == 'createindex':
            index_name = db[payload['collection']].create_index(list(payload['keys'].items()), **payload.get('options', {}))
            log = f'createIndex 完成，索引名 {index_name}'
        else:
            db[payload['collection']].drop_index(payload['name'])
            log = f'dropIndex 完成，索引 {payload["name"]} 已删除'

        duration = int((time.time() - start) * 1000)
        return True, affected_rows, duration, log
    except Exception as exc:
        duration = int((time.time() - start) * 1000)
        return False, 0, duration, f'执行失败: {exc}'
    finally:
        if client is not None:
            client.close()
