# 阶段 6：全量审计与修复

范围：本轮 POC-A 的全部源码、配置、契约、测试和运行说明。POC-B/生产服务未实现，不纳入“已完成”声明。

## 违规／缺陷清单及修复

审计先补充 8 个回归用例，初次运行 6 FAIL、2 ERROR；对应问题全部修正后重跑全套。

| 项 | 初次结果 | 修复 | 复检 |
|---|---|---|---|
| 超长编号触发 Python int 原始异常 | ERROR | 配置数字长度限制，转换前拦截；技术转换异常稳定化 | pass |
| DOCX 表格内容静默遗漏 | FAIL | 配置 XPath 检测未支持结构及拒绝门禁，表格/图片/文本框/修订等不静默跳过 | pass |
| 配置 eq 操作数 bool/int 混用 | FAIL | 根据 DTO 字段精确类型验证，不依赖 Python bool==int 行为 | pass |
| 配置移除候选位置门禁仍被接受 | FAIL | 加载时要求各准入事实契约完整覆盖 | pass |
| 分句配置未覆盖全部正文 | FAIL | 计算非空白字符覆盖事实，以配置门禁拒绝遗漏 | pass |
| JSON 重复键被最后一个值覆盖 | FAIL | 配置与 CLI context 检测重复键并稳定报错 | pass |
| 仅规则版本不能区分配置内容变化 | ERROR | 增加整个不可变策略快照的 policy_sha256 | pass |
| 参考文献标题未参与初步 PII 拦截 | FAIL | 批量扫描正文及全部参考标题，错误不回显内容 | pass |

额外修复：测试使用直接 httpx ASGITransport，消除上游 TestClient 弃用适配；DOCX XPath 加载时校验，解析 IO 异常在 adapter 转换为稳定错误。未支持的运行能力通过 DTO 的技术能力类型拒绝，不维护隐藏业务判定表。

## 【自检结果】

| 规则 | 结果 | 证据 |
|---|---|---|
| R1 | pass | 所有业务条件、标签、严重程度、阈值、准入筛选、语法策略及提示在 JSON。通用有限比较器不含规则词汇；配置阈值/严重级别/文案/启用状态变更测试通过。人工检查领域和应用中分支均为语法事实计算、集合/坐标运算、配置执行或技术结构校验；未发现隐藏业务映射。 |
| R2 | pass | 全部实际 Python 路径扫描；src 无直接 .py，包根仅空 __init__.py，业务代码均为子包。 |
| R3 | pass | 全量静态导入 DAG（22 模块，含空包）无环；跨域只调用 api，领域依赖 contracts 及域内模块，application 无 IO/adapters 依赖。见 import-graph.json。 |
| R4 | pass | contracts 的全部导入扫描，无业务域/应用/基础设施依赖；没有 common。 |

R1 的自动策略词汇扫描是有限检测，不是任意未来业务硬编码的形式化证明。以上结论由本次源码检查、自动结构检查和行为变更测试共同支持。

## 实际验证

- 独立 Python 3.12 .venv 可编辑安装成功；固定开发依赖见 backend/requirements-dev.lock；按 README 重复安装通过。
- 最终 unittest：40 tests，40 passed，0 failed，0 errors，0 skipped；本次机器记录见 validation-results.json。
- `pip check`：No broken requirements found。
- 真实 Uvicorn 启动，HTTP POST /audits 返回 200：示例准确产生 missing_citation、unresolved_reference、source_unavailable 三条 Finding，均带原文定位；报告含配置内容哈希。测试启动的进程已停止。
- 已安装 evidence-check CLI 的 JSON 和 Markdown 示例运行成功。
- 七份原始材料逐字节比对一致；LICENSE 未变；无密钥、上传原文件或虚拟环境被纳入版本管理。git diff --check 通过。

## 不属于已通过验收的项目

- 当前只验证引用完整性 POC-A。无自动医学 Claim 抽取、PDF 全文/BM25、语义事实与证据关系判断；不宣称完成整个 PRD。
- 所有已映射来源均未验证全文；source_unavailable 不是全文缺失的事实裁决，也不是 unsupported_claim。
- DOCX 仅支持普通段落；页眉页脚不属规范正文，章节由调用者确认。复杂缩写分句仍需人工复核。
- 初步 PII 正则存在漏检风险；未实现生产鉴权、上传加密、任务持久化、24h 删除与失败重试，不对外部署。
- annotation-template 是 pending 模板，不是金标；PRD 的 98%/95%/80% 指标、真实人工用户测试和付费指标未运行。

当前切片未修复 fail：0。下一实现阶段是自动候选 Claim 的受约束输入与校验，再进入 PDF 原文定位和封闭检索；不能越过人工盲测直接宣称医学证据结论可靠。
