---
name: database_query
description: 查询数据库信息，支持 MySQL、PostgreSQL、SQLite3 等多种数据库。当 Agent 需要读取数据库中的数据、查询表结构、执行 SQL 查询或获取数据库元数据时调用此技能。
category: io
requires_confirmation: False
version: "1.0"
author: Local Agent
tags: ["database", "sql", "mysql", "postgresql", "sqlite", "query", "data"]
parameters:
  - name: "db_type"
    type: "string"
    description: "数据库类型，支持 mysql、postgresql、sqlite3。根据目标数据库选择对应类型。"
    required: true
    enum: ["mysql", "postgresql", "sqlite3"]
  - name: "connection_string"
    type: "string"
    description: "数据库连接字符串。sqlite3 为文件路径；mysql/postgresql 为 host:port:database:user:password 格式。"
    required: true
  - name: "query"
    type: "string"
    description: "要执行的 SQL 查询语句。仅支持 SELECT 查询，不支持 INSERT、UPDATE、DELETE 等修改操作。"
    required: true
---

## Core Capability
连接数据库并执行 SQL 查询，返回 JSON 格式的结果。支持 MySQL、PostgreSQL、SQLite3 三大主流数据库，是 Agent 进行数据分析、数据库审计、数据验证的核心能力。

## Trigger Scenario（Agent 使用场景）

以下场景应调用此技能：

- **数据查询**：用户要求"查询用户表中前10条数据"、"统计订单数量"
- **表结构查看**：需要了解数据库有哪些表、表有哪些字段、字段类型
- **数据验证**：验证某个数据是否存在，如"检查用户ID为100的用户是否存在"
- **数据分析**：对数据库中的数据进行聚合、分组、排序分析
- **配置读取**：某些配置存储在数据库中，需要查询获取
- **安全审计**：检查数据库中是否存在敏感信息泄露、异常数据

**判断标准**：当 Agent 需要从数据库中读取数据或元数据时，使用此技能。

## Parameters

| Name              | Type   | Description                                           | Required | Default |
| ----------------- | ------ | ----------------------------------------------------- | -------- | ------- |
| db_type           | string | 数据库类型：mysql、postgresql、sqlite3                | Yes      | -       |
| connection_string | string | 连接字符串，格式见下方详细说明                        | Yes      | -       |
| query             | string | SQL 查询语句，仅支持 SELECT                           | Yes      | -       |

## Connection String Format

### SQLite3
直接传入数据库文件路径，或 `:memory:` 表示内存数据库。

```
data/mydb.db
:memory:
./database/app.sqlite3
```

### MySQL
格式：`host:port:database:user:password`

```
localhost:3306:testdb:root:123456
192.168.1.100:3306:myapp:appuser:secret_pass
```

### PostgreSQL
格式：`host:port:database:user:password`

```
localhost:5432:testdb:postgres:123456
10.0.0.5:5432:analytics:dbuser:pg_pass
```

## Example Usage

### 场景1：查询 SQLite3 数据库
```json
{
  "skill": "database_query",
  "args": {
    "db_type": "sqlite3",
    "connection_string": "data/mydb.db",
    "query": "SELECT * FROM users LIMIT 5"
  }
}
```

### 场景2：查询 MySQL 数据库
```json
{
  "skill": "database_query",
  "args": {
    "db_type": "mysql",
    "connection_string": "localhost:3306:testdb:root:123456",
    "query": "SELECT id, username, email FROM users WHERE created_at > '2024-01-01'"
  }
}
```

### 场景3：查看表结构（SQLite3）
```json
{
  "skill": "database_query",
  "args": {
    "db_type": "sqlite3",
    "connection_string": "data/mydb.db",
    "query": "PRAGMA table_info(users)"
  }
}
```

### 场景4：聚合统计查询
```json
{
  "skill": "database_query",
  "args": {
    "db_type": "postgresql",
    "connection_string": "localhost:5432:analytics:postgres:pass",
    "query": "SELECT status, COUNT(*) as count FROM orders GROUP BY status ORDER BY count DESC"
  }
}
```

## Execution Signature
```python
def database_query.execute(db_type: str, connection_string: str, query: str, **kwargs) -> str:
    ...
```

## Output Format

### 成功返回
返回 JSON 格式的查询结果：

```json
{
  "columns": ["id", "username", "email"],
  "rows": [
    [1, "admin", "admin@example.com"],
    [2, "user1", "user1@example.com"]
  ],
  "row_count": 2,
  "execution_time_ms": 15
}
```

### 错误返回
- 连接失败：`错误: 无法连接到数据库: [详细错误信息]`
- SQL 语法错误：`错误: SQL 语法错误: [详细错误信息]`
- 查询类型不支持：`错误: 仅支持 SELECT 查询，不支持 INSERT/UPDATE/DELETE`

## Agent Workflow（工作流协作）

此技能通常与其他技能配合使用：

1. **database_query → python_exec**：查询数据后，使用 Python 进行进一步分析和可视化
2. **database_query → file_write**：将查询结果导出为 CSV/JSON 文件
3. **file_read → database_query**：读取配置文件获取数据库连接信息后，执行查询

## Best Practices（最佳实践）

1. **先查结构再查数据**：首次查询某个数据库时，先执行 `PRAGMA table_info(table_name)`（SQLite）或 `SHOW COLUMNS FROM table_name`（MySQL）了解表结构
2. **限制返回行数**：查询大数据表时，务必使用 `LIMIT` 限制返回行数，避免返回过多数据
3. **参数化查询**：虽然此技能直接执行 SQL，但应避免在 SQL 中拼接用户输入，防止 SQL 注入
4. **连接信息保密**：不要在对话中明文展示数据库密码，使用环境变量或配置文件引用

## Safety Notes（安全提示）

- **只读限制**：此技能仅支持 SELECT 查询，不支持任何数据修改操作
- **连接安全**：确保数据库连接使用 SSL/TLS，避免明文传输密码
- **权限最小化**：数据库用户应仅具有 SELECT 权限，避免使用高权限账号
- **敏感数据**：查询结果中可能包含敏感信息，注意在展示时脱敏处理

## Notes
- 该技能现在接受额外参数通过 `**kwargs`；未知参数会被安全忽略
- 查询结果以 JSON 字符串形式返回，最大返回数据量可能有限制
- 对于超大结果集，建议使用 `LIMIT` 分页查询
- 连接超时时间默认为 30 秒，复杂查询可适当延长
