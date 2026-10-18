# 阶段 3：公开接口契约

## 调用与依赖

所有跨业务域调用只导入 `evidence_check.domains.<domain>.api`。共享类型只能从 contracts 引入。Application 只依赖领域公开 API 和 DTO，不依赖 adapters。entrypoints 装配配置和 IO；infrastructure 不依赖业务域。模块内可静态导入内部实现。禁止动态 import、eval、exec。

## DTO 与验证

使用 frozen Pydantic DTO，extra=forbid、strict=True；集合用 tuple，禁止上层把数据库或 SDK 对象传入。HTTP JSON 在边界转换 tuple，未知字段拒绝。语法和类型校验在 DTO 层；格式、语言、长度、编号、来源、规则映射等业务限制由配置驱动。

- DocumentInput(document_id:str, text:str, references:tuple[Reference], claims:tuple[ClaimCandidate], language_mode:str, authorized:bool, single_section:bool)。authorized 和 single_section 必须显式提供。references / claims 可为空。
- Reference(reference_id:int, title:str)。本轮不接受用户提供的全文已验证标志；未执行 PDF parser 就不能证明全文可审计。
- ClaimCandidate(start:int, end:int, text:str)。start/end 是规范正文的半开 Unicode 字符偏移。只允许覆盖同一个句子且逐字匹配；重叠候选拒绝。人工选择的候选不代表语义已验证。
- Location(paragraph_index:int, sentence_index:int, char_start:int, char_end:int)。段落/句序从 0 起，位置区间半开，全部基于返回的规范文本。句界算法处理引用紧随句末标点和英文小数；不承诺复杂缩写句界正确。
- Citation(reference_ids:tuple[int], location:Location)。保留每个原文锚点；区间按升序展开，拒绝倒序、非法数字引用和超限展开。
- Sentence(text:str, location:Location, citations:tuple[Citation])。
- DocumentBundle(document_id:str, text:str, sentences:tuple[Sentence], references:tuple[Reference])。
- ClaimRecord(text:str, location:Location, citation_ids:tuple[int])。候选必须包含同一句的全部引用锚点；拒绝截取造成的漏引文。
- Finding(rule_id, severity, label, location, claim_text, citation_ids, message, guidance, review_status)。所有展示值由规则配置产生，需复核，不能是医学裁决。
- AuditReport(document_id, normalized_text, input_sha256, policy_version, policy_sha256, findings, summary)。报告标明 audit_scope、未验证能力；返回 issues 和人工 Claim 计数。input_sha256 对完整规范输入（正文、文献、候选及声明）计算，非只对正文。

## 函数

| 公开 API | 输入 → 输出 | 边界 |
|---|---|---|
| document.api.parse_document | DocumentInput, Policy → DocumentBundle | 纯函数；验证配置门禁、编号和长度，解析语法/位置 |
| claim.api.normalize_claims | DocumentBundle, tuple[ClaimCandidate], Policy → tuple[ClaimRecord] | 纯函数；拒绝编造、越界、跨句、重叠、遗漏句内引用 |
| audit.api.evaluate_audit | DocumentBundle, tuple[ClaimRecord], Policy → tuple[Finding] | 纯函数；通过声明式 when 条件执行规则，不读取文件 |
| application.api.audit_document | DocumentInput, Policy → AuditReport | 纯编排；只依赖上述公开 API，保留全部规则命中 |
| infrastructure.api.load_policy | config_dir:Path → Policy | 批量读取 JSON，验证配置结构、有限运算符、事实字段、规则和版本一致性；失败转 PolicyError 并日志记录 |
| infrastructure.api.read_document | path:Path, Policy → str | Markdown UTF-8 / DOCX 按段换行；先限制文件大小及 DOCX 解压大小；IO/解析失败稳定错误，不记录论文内容 |
| infrastructure.api.render_markdown | AuditReport → str | 文本转义、每条定位和修改方向；不输出医学支持结论 |
| entrypoints CLI | --input PATH --context PATH [--config-dir PATH] [--format json/markdown] | context 是除 text 以外的 DocumentInput；stdout 报告，stderr 稳定错误码；退出非零 |
| POST /audits | DocumentInput JSON → AuditReport JSON | 无文件上传、无后台任务、无持久化、无外部模型。错误 422；真实服务上传/PII/加密/删除未实现，不公开部署 |
| GET /health | none → {status} | 仅进程健康，不代表业务通过；集成测试实际调用 /audits |

## 错误语义

稳定异常：InputError(code, message)、PolicyError、DocumentReadError。所有外部输入的类型错误和 IO 故障在入口/adapter 转换，日志仅记录错误码，不记录路径、正文、密钥。领域错误不得伪装成 unverified。重复文献编号、恶意/畸形区间、配置冲突拒绝整项输入；未知引用号产生 Finding。

## 策略执行边界

事实计算只提供计数、成员集合差、字符匹配、位置比较。通用规则引擎支持显式有限的 eq/ne/gt/ge/lt/le/in/not_in/truthy/falsy 运算；运算符、字段名校验，禁止表达式语言。Python 不维护最终标签/严重等级/规则 ID/阈值映射。

本轮来源状态：全部全文未验证，映射成功的引用触发配置中的 source_unavailable；无引用只检查人工 Claim。重复问题按规则/正文位置合并，保留相应引用号。多引用的语义合并未实现，不输出 supported/contradicted。全部报告显示“引用完整性 POC-A，非语义证据审计”。

## 后续接口（本轮不生成实现）

Evidence.retrieve_evidence(ClaimRecord[], DocumentBundle, EvidenceRetrieverPort)；仅引用内全文候选，必须返回原始页码与原文。
LLM.extract_claims / compare_evidence 只能返回候选；禁止 final_label/Finding 字段。
Audit 的 ComparisonFacts 合并表、数值单位/分母/窗口需在 POC-B 前冻结，不能挪用本轮无全文策略作为未来聚合策略。
人工金标和预测始终使用独立数据路径，原 annotation-schema 和模板原样保留。

## 阶段 6 契约补强

配置加载额外校验重复键、比较操作数的精确类型、全部准入事实字段覆盖及 DOCX XPath 语法。解析后检查全部非空白字符覆盖；DOCX 未支持结构按配置拒绝。报告增加完整不可变策略快照的 policy_sha256。引文数字长度在 int 转换前受配置限制。
