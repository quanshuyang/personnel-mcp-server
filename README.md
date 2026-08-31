# Personnel MCP Server

面向公司人员数据的 MCP Server。提供数据读取、字段标准化、人员汇总、部门统计、人员筛选、数据质量校验，以及**多工作表 Excel 报告导出**能力。

## 数据源（双模式）

每个工具都接受可选的 `source_file` / `sheet_name` 参数：

- **未传 `source_file`（默认）**：从 **MySQL 人员表**读取（`PERSONNEL_TABLE`，默认 `employees`）。连接参数通过环境变量 `MYSQL_*` 注入。
- **传入 `source_file`**：从 **本地 Excel / CSV 文件**读取（`source_file` 必须是 `PERSONNEL_DATA_DIR` 内的相对路径）。

这样同一个 MCP Server 既能直接连库，也能被另一个需要"读上传文件"的项目复用，互不干扰。

## 功能

- `get_headcount_summary`：返回总人数、男女数量及比例、部门数量。
- `get_department_statistics`：按部门统计人数、男女数量和比例。
- `filter_employees`：按部门、性别、姓名关键词筛选人员，支持分页。
- `list_departments`：列出部门及人数。
- `validate_personnel_data`：发现必填字段空缺、未识别性别、未知部门、重复人员和列格式问题。
- `export_statistics_report`：导出多工作表 Excel 报告，包含以下工作表：
  - `汇总`：总人数、部门数、性别分布、问题计数与字段映射。
  - `部门统计`：各部门人数与性别拆分。
  - `性别统计`：男女数量与比例。
  - `数据问题`：校验发现的问题（级别、代码、字段、行号、说明）。
  - `规范化数据`：标准化后的逐行记录（含 `gender_normalized`）。

## 安装与运行

```powershell
uv sync
uv run personnel-mcp
```

服务默认使用项目内的 `data` 目录。通过环境变量 `PERSONNEL_DATA_DIR` 可指定另一个数据目录：

```powershell
$env:PERSONNEL_DATA_DIR = "D:\\HR\\approved-data"
uv run personnel-mcp
```

工具中的 `source_file` 与导出工具的 `output_file` 都必须是该目录内的相对路径。这避免 MCP Server 读取或写入目录外的任意文件。例如：

- 读取：`sample_personnel.csv`
- 导出：`reports/headcount.xlsx`

## 支持的数据列

服务按照统一数据契约自动识别列名，并统一为标准字段。缺少必填列会被报告为错误；缺少可选列不会阻止统计。

### 字段契约

| 标准字段 | 可识别列名示例 |
| --- | --- |
| `employee_id`（可选） | 工号、员工编号、员工ID、employee_id、employee id、id |
| `name`（必填） | 姓名、员工姓名、name、employee name |
| `department`（必填） | 部门、所属部门、部门名称、department、dept |
| `gender`（必填） | 性别、gender、sex |
| `job_title`（可选） | 岗位、职位、职务、job title、job_title、title |
| `hire_date`（可选） | 入职日期、入职时间、到岗日期、hire date、hire_date、start date |
| `level`（可选） | 职级、级别、职等、level、job level、job_level |

性别值会标准化为 `male`、`female` 或 `unknown`。其中 `男/male/m/man` 映射为 `male`，`女/female/f/woman` 映射为 `female`，空值、`未知`、`unknown`、`n/a` 等映射为 `unknown`。

### 文件契约

- 支持 `.xlsx`、`.csv`、`.tsv`。
- CSV/TSV 按 UTF-8（带 BOM）、GB18030、UTF-8 顺序尝试读取。
- Excel 默认使用第一个包含可识别表头的工作表，也可通过 `sheet_name` 指定。
- 表头允许出现在前 20 行；至少需要识别到 `name`，或同时识别到 `employee_id` 和 `department` 才会接受该表头。
- 报告导出仅支持 `.xlsx` 格式。

## MCP 客户端配置示例

```json
{
  "mcpServers": {
    "personnel-analytics": {
      "command": "uv",
      "args": ["--directory", "E:\\Projects  folder\\MCP_test_2026_7_31", "run", "personnel-mcp"]
    }
  }
}
```

## 验证

```powershell
uv run python -m unittest discover -s tests -v
```
