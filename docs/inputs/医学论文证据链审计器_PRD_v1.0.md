# 医学论文证据链审计器 PRD v1.0

## 1. 产品定义

**产品名（暂定）**：Evidence Check

面向医学硕博生、规培医生和临床科研人员的自助式论文证据链审计工具。

用户提交论文的一个章节、该章节的参考文献及对应全文 PDF；系统逐条识别可核查论断（Claim），检查正文论断是否有引用、引用能否解析、引用文献中是否存在可定位的支持证据，以及正文是否将证据的范围或因果强度写得过大。

**一句话定位**：不替用户写论文，不判断论文好坏；只指出“这句话的证据在哪里、是否足以支持这句话”。

## 2. 目标与边界

### 2.1 首版目标

对一段医学论文正文生成可复核的证据审计报告，帮助作者在提交导师或期刊前发现：

1. 无引用的事实性/因果性论断；
2. 无法解析或无全文的引用；
3. 正文 Claim 与所引证据在人群、疾病、干预、结局、时间范围上的不一致；
4. 将观察性关联写成强因果结论的风险；
5. 文中数值与引用证据不一致的风险（仅限证据中可明确提取数值）。

### 2.2 明确非目标

- 不输出论文总分、深度分或“可发表”判断；
- 不生成、改写、润色论文；
- 不联网替用户寻找遗漏文献或反方文献；
- 不提供诊断、治疗、用药或临床决策建议；
- 不处理病历、影像、检验单、患者信息或病例报告；
- 不判定 AI 生成、抄袭或学术不端；
- 不支持全篇论文、系统综述或多用户协作。

## 3. 目标用户与使用场景

### 3.1 目标用户

- 正在写医学硕博论文、开题报告、文献综述或 SCI 初稿的学生；
- 需要自查论文引言、讨论章节的医生/科研人员。

### 3.2 首发场景

用户完成一章“引言”或“讨论”后，在发给导师前上传该章节与其引用文献，获得一份按句定位的问题清单。

### 3.3 输入限制

- 正文：中文或英文 Markdown / DOCX；最多 5,000 字或 3,000 English words；
- 引用格式：仅支持顺序编码制，如 `[1]`、`[1,2]`、`[1-3]`；
- 参考文献：最多 30 条；
- 证据文献：用户上传 PDF，或提供 DOI/PMID；
- 若无全文，只做书目信息核验，不能给出“支持/不支持”结论。

## 4. 核心用户流程

1. 用户创建一次审计任务，选择“医学论文证据审计”。
2. 上传正文 DOCX/Markdown、参考文献列表和已引用的 PDF；可补充 DOI/PMID。
3. 系统解析正文结构、句子和引用锚点；将引用锚点映射到参考文献。
4. 系统抽取候选 Claim，并仅从该 Claim 已引用的文献中检索候选 Evidence Span。
5. 系统执行确定性规则和受约束的 Claim–Evidence 比对。
6. 用户在页面查看问题，也可下载 Markdown/PDF 审计报告。
7. 任务完成后，原文件在设定保留期后自动删除。

## 5. 功能需求

### F1. 文档与引用解析

- 解析章节标题、段落、句子和字符位置；
- 识别数字引用锚点并解析区间引用；
- 建立 `citation_anchor -> reference_entry -> source_file` 映射；
- 标记以下解析问题：缺失参考文献、重复编号、无对应全文、PDF 不可读。

### F2. Claim 抽取

仅抽取可被外部证据验证的 Claim，不抽取研究计划、主观过渡句或作者自我说明。

医学 Claim 的最小结构：

```text
Claim = 文本 + ClaimType + 断言强度 + 引用锚点
      + Population/Disease/Intervention/Outcome/Time 等可得限定项
```

支持的 `ClaimType`：`prevalence`、`association`、`causality`、`effectiveness`、`safety`、`prognosis`、`diagnostic_accuracy`。

### F3. 证据定位

- 对每条 Claim，只在其文内已引用的 PDF 中检索证据；
- 候选 Evidence Span 必须保留文献名称、页码、段落、原文片段；
- 摘要、元数据或无法读取的全文只可作为“不可审计”的依据，不能作为细粒度支持证据。

### F4. 审计规则

| 规则 ID                  | 触发条件                | 输出等级    |
| ---------------------- | ------------------- | ------- |
| `missing_citation`     | 可核查 Claim 没有文内引用    | Warning |
| `unresolved_reference` | 引用编号找不到参考文献条目       | Error   |
| `source_unavailable`   | 有文献条目但无可审计全文        | Info    |
| `unsupported_claim`    | 已引用全文中找不到候选支持片段     | Warning |
| `scope_mismatch`       | 人群/疾病/干预/结局/时间范围不一致 | Warning |
| `causality_overclaim`  | 正文为强因果表述，证据仅显示观察性关联 | Warning |
| `direction_mismatch`   | 正文的效果方向与证据方向相反      | Error   |
| `numeric_mismatch`     | 可定位数值不一致            | Error   |

规则结果只能为：`supported`、`partially_supported`、`contradicted`、`unverified`、`not_assessable`。

### F5. 审计报告

每个 Finding 必须包含：

- 严重等级和规则 ID；
- 正文 Claim 原文及其章节/段落/句子位置；
- 对应引用；
- 证据原文及页码/段落位置（若存在）；
- 为什么触发该规则；
- 面向作者的修改方向；
- 状态：`需复核`，不得显示为最终裁决。

报告汇总展示：审计 Claim 数、可审计 Claim 数、问题数、按规则分类数量、不可审计原因。

## 6. 技术方案

### 6.1 分层

```text
application / orchestration
  ├─ document parsing adapter      # DOCX、PDF、metadata
  ├─ candidate extraction adapter  # LLM，仅产生候选
  ├─ evidence retrieval adapter    # 仅检索用户提供的引用文献
  └─ report adapter

audit core（纯核心）
  ├─ Claim / Evidence / Finding 模型
  ├─ Citation resolution
  ├─ Entity / qualifier comparison
  ├─ Deterministic rule engine
  └─ Policy: severity / fail-closed

medical domain pack
  ├─ claim type schema
  ├─ qualifier schema
  └─ causal/scope audit rules
```

### 6.2 核心原则

- `audit core` 禁止文件、网络、数据库、系统时间和 LLM；
- LLM 只抽取候选 Claim、实体和候选证据段，不能直接生成最终 Finding；
- 无法找到充分证据时输出 `unverified` 或 `not_assessable`，绝不直接判为“错误”；
- 所有外部访问、文件解析、模型调用都在 adapter 层；
- 医学规则包仅定义证据表达语法，不维护疾病诊疗知识库。

### 6.3 最小技术选型

- 后端：Python + FastAPI；
- 文档：`python-docx`、PyMuPDF；
- 引用元数据：PubMed/Crossref（可选 effects adapter）；
- 检索：文献内 BM25，首版不需要向量库；
- 任务存储：SQLite 或 PostgreSQL；
- 模型：可替换 LLM adapter；支持关闭外部调用或用户自带 Key；
- 输出：HTML/Markdown，PDF 导出为后续能力。

## 7. 数据、安全与合规

- 只接受论文正文和公开/用户有权使用的文献；
- 前端明确禁止上传病历、患者信息、影像、检验单和病例报告；
- 上传文件加密存储；任务完成后默认 24 小时删除原文件与解析文本；
- 只保存经用户确认的匿名化审计汇总用于产品指标；
- 使用外部 LLM 前必须显示数据处理说明；用户可选择本地模型或关闭 LLM 增强；
- 对外文案固定为“学习与写作辅助，不构成医疗建议、发表保证或学术评价”。

## 8. MVP 验收标准

使用 100 条经人工标注的“Claim—引用—证据”样本验收：

1. 数字引用解析准确率 >= 98%；
2. `missing_citation` 和 `unresolved_reference` 的精确率 >= 95%；
3. 对范围夸大/因果夸大问题，呈现给用户的 Finding 精确率 >= 80%；
4. 每个 `Warning/Error` 均有正文定位；
5. 每个涉及证据判断的 Finding 均有证据定位，或明确标记为不可审计；
6. 不产生“治疗有效”“医学结论正确”“论文可发表”等越界结论；
7. 单章、30 篇以内文献的任务在 10 分钟内完成。

## 9. 开发阶段

### Phase 1：引用完整性检查

- DOCX/Markdown 解析；
- 数字引用解析；
- 缺引用、错引用、无全文报告；
- 不做 LLM 语义判断。

### Phase 2：证据对齐

- Claim 候选抽取；
- 文献内证据检索；
- `unsupported_claim`、`scope_mismatch`、`causality_overclaim`；
- Markdown 审计报告。

### Phase 3：医学产品化

- PubMed 元数据补全；
- 网页任务页与付费报告；
- 用户反馈闭环；
- 仅在真实付费成立后再加入 PDF 报告、更多格式和领域包。

## 10. 成功指标

- 用户完成一次审计后，能定位并修改至少一个具体问题；
- 用户愿意为一次完整审计支付 ¥99–199；
- 首批用户中，有人主动对下一章节或下一篇论文再次使用；
- 不以注册量、模型调用量或“论文评分”作为成功指标。
