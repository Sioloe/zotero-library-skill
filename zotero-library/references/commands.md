# 命令与计划格式

下文的 `python` 可换成Python 3.11+ 解释器，`<script>` 换成本技能 `scripts/zotero_library.py` 的绝对路径。无需 pip 依赖。工作文件放在当前任务 work 目录，交付文件放 outputs，不写入技能安装目录。

## 常用命令

```text
python <script> status
python <script> collections
python <script> collections --out outputs/collections.json
python <script> snapshot --out work/library.json
python <script> snapshot --collection ABCD2345 --out work/collection.json
python <script> export --format bibtex --out outputs/references.bib
python <script> export --format ris --collection ABCD2345 --out outputs/references.ris
python <script> export --format csljson --out outputs/references.csl.json
python <script> export --format csv --out outputs/references.csv
python <script> template --item-type journalArticle --out work/template.json
```

`status` 报告当前库、条目总数及 `key_allows_write`。它只核对密钥声明权限，不进行测试写入；群组实际写入还受成员角色和群组设置约束。`collections` 输出全部分类的 key、名称及父级，不修改分类或排序。

`snapshot` 和 `export --format json` 输出包含 library、items、collections 的快照。条目是 Zotero Web API JSON；它不是 Zotero 桌面“导出 Zotero RDF”格式，也不包含附件文件，不要把 JSON 快照当成完整备份导入桌面。所有输出命令拒绝覆盖同名文件。

`--collection` 只包含该分类直接所属的条目，不递归包含子分类。导入去重必须使用不带 `--collection` 的全库快照。

## 分类建议输入

由助手根据实际文献生成数组，示例如下（key 必须替换为真实快照中的 key）：

```json
[
  {
    "key": "ABCD2345",
    "collection_paths": [["10 研究主题", "医学影像"], ["20 综述与基础"]],
    "tags": ["主题/医学影像", "类型/综述"],
    "confidence": 0.93,
    "reason": "标题和摘要明确讨论医学影像领域的系统综述。"
  }
]
```

```text
python <script> plan-organize --snapshot work/library.json --input work/decisions.json --out outputs/organize-plan.json
python <script> apply --plan outputs/organize-plan.json
python <script> apply --plan outputs/organize-plan.json --execute --journal outputs/organize-journal.json
```

第一个 apply 只访问网络做预检，没有写入。第二个才执行；用户已明确授权实际整理时可以接着执行。低于 0.8 的判断留在 review；新分类使用随机 key，已存在同父级同名分类会被复用。

## 导入输入

输入必须是已核实的 Zotero API editable JSON 数组。先从模板保留适用字段，只填已确认的值。例如：

```json
[
  {
    "itemType": "journalArticle",
    "title": "在此填入已核实的论文标题",
    "creators": [],
    "date": "",
    "DOI": "",
    "tags": [],
    "collections": [],
    "relations": {}
  }
]
```

此例只说明格式，不能作为真实文献导入。脚本会清除来源库的 key、version、时间戳、分类及关系；目标分类通过参数指定，不保留跨库 key 引用。

```text
python <script> plan-import --snapshot work/library.json --input work/import-items.json --collection ABCD2345 --out outputs/import-plan.json
python <script> apply --plan outputs/import-plan.json
python <script> apply --plan outputs/import-plan.json --execute --journal outputs/import-journal.json
```

DOI 一致的候选跳过；标准化标题相同但 DOI 未确认一致的候选进入 review，再核对作者、年份与版本。即使没有 DOI，本次输入内部的同名候选也不会直接重复创建。

## 写入故障与恢复

- 401／403：确认库 ID、读写权限及密钥配置。不要输出密钥。
- 409／412：停止当前写入；同步完成后重新快照并生成计划。
- 429／503：遵守服务器要求的等待时间；不会自动重试写入。
- 日志 `pending`：请求可能已经成功，先 GET 其 key 确认。不要重放整个旧计划。
- 中途失败不是事务回滚。日志记录已确认和待确认操作；重建计划时根据当前库复用已创建目录／跳过已有文献。
- 撤销标签／成员关系：读取日志 before/after 及最新条目，计算“仅移除本次新增”的差异，保护后来的人工作业，再使用有版本保护的 API 更新。若本次后有人编辑了这些字段，应先解决冲突。新建分类／导入条目不自动删除。

脚本不提供删除、自动合并、PDF 文件上传或一键回滚；需要这些操作时应按用户明确的范围使用其他适当工具。
