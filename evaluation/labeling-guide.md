# 标注判定指南

## 标签

| 标签 | 使用条件 |
|---|---|
| `supported` | 已引用、可读取的全文中有可定位片段，且人群、疾病、干预/暴露、结局、时间和断言强度均足以支持 Claim。 |
| `partially_supported` | 有直接相关证据，但至少一个重要限定项或断言强度不能完全支持。 |
| `contradicted` | 可定位证据明确与 Claim 的方向、数值或结论相反。 |
| `unverified` | 资料可审计，但在已引用全文中未找到足以支持或反驳的候选证据。 |
| `not_assessable` | 无引用、引用未解析、无全文、PDF 不可读，或无法可靠定位证据。 |

## 规则映射

- Claim 没有数字引用：`missing_citation` + `not_assessable`。
- 引用号无法映射到参考文献：`unresolved_reference` + `not_assessable`。
- 有条目但无可审计全文：`source_unavailable` + `not_assessable`。
- 全文可读但未找到支持性证据：`unsupported_claim` + `unverified`。
- 人群、疾病、干预、结局或时间范围不一致：`scope_mismatch`，通常为 `partially_supported`。
- 正文使用“导致、证明、显著降低风险”等强因果表达，而证据为观察性关联：`causality_overclaim` + `partially_supported`。
- 原文方向相反或可定位数值不一致：`direction_mismatch` / `numeric_mismatch` + `contradicted`。

## 强制原则

1. 只查看该 Claim 已经引用的文献；不能补找外部文献。
2. 摘要和元数据不能构成细粒度 Evidence Span。
3. 中文 Claim 对英文 Evidence 的译文仅可帮助理解；最终证据字段必须保存英文原文。
4. 不能依据常识、临床指南或标注者专业意见补足证据。
5. 有分歧时保留双方理由，进入 `adjudicated` 前不覆盖原记录。
