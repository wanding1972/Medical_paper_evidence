# Evidence Check 标注集包

该包用于构建医学论文 Claim—Citation—Evidence 审计的人工金标集。

## 使用边界

- `annotation-template.jsonl` 是待填充的任务模板，不包含虚构医学事实或证据，不能直接作为验收集。
- 每一条最终金标必须来自已获得处理授权的正文与全文 PDF，并保留原始 Claim 与 Evidence Span 的页码定位。
- 仅允许在 `supported`、`partially_supported`、`contradicted`、`unverified`、`not_assessable` 中选择一个最终标签。
- 所有语义判断均应由人工确认；自动生成的候选内容只可作为预标注。

## 建议的最小样本设计

每个语言模式 100 条独立 Claim，总计 300 条：

| 语言模式 | 数量 | 最低覆盖 |
|---|---:|---|
| `zh-zh` | 100 | association、causality、effectiveness、safety |
| `zh-en` | 100 | association、causality、effectiveness、prognosis |
| `en-en` | 100 | association、causality、effectiveness、diagnostic_accuracy |

每种模式应刻意抽样：至少 20 条无引用或无法解析、至少 20 条可明确支持、至少 20 条范围/因果/方向/数值存在风险的 Claim。不能只抽取容易判断的正例。

## 文件

- `annotation-schema.json`：单条标注记录的 JSON Schema。
- `labeling-guide.md`：标注规则与冲突处理。
- `annotation-template.jsonl`：三种语言模式的可复制任务模板。

## 生成真实候选记录

导入一份正文、参考文献表及对应 PDF 后，系统应先填充：`claim_text`、`citation_ids`、`source_document_id`、`evidence_candidates` 与 `language_mode`。标注者随后确认最终标签和规则，不应以模型生成结果直接填入 `final_label`。
