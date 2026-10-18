# 产品增量阶段 3：接口契约

## 纯业务 API

- claim.api.extract_candidates(DocumentBundle, ProductPolicy) -> ClaimCandidate[]：从配置匹配句子；是候选，需人工确认，保留原文与引用，不会生成医学事实。
- evidence.api.retrieve(ClaimRecord, SourceDocument[], ProductPolicy) -> EvidenceSpan[]：BM25 内存检索；先按 Claim 引用号筛选全文，页/段偏移与原文逐字核验；不查摘要/网络。跨语言同义词表配置化，效果待盲测。
- audit.api.assess(ClaimRecord, SourceDocument[], EvidenceSpan[], Observation[], Policy, ProductPolicy) -> ClaimAssessment：先验证观察的原文证据 ID、关系枚举和来源集合，再运行配置规则与保守决策表。模型未返回观察的已读全文只能为未核验；部分来源缺失不等同整条反证。
- application.product.run_audit(ProductRequest, Policy, ProductPolicy, ModelPort|None) -> ProductReport：无 IO。模型通过协议注入，只提供候选/关系，任务级 consent 必须满足配置门禁。

稳定 DTO 在 contracts/product.py；source page 坐标为页内 Unicode 半开字符区间，页码从 1 起，paragraph 从 0 起。source_file_id 与 reference_id 分开。Observation 使用 support_relation/scope_relation/causal_relation/direction_relation/numeric_relation、evidence_ids 和 rationale；禁止最终标签/Finding 字段。每条观察必须指向本 Claim 已取回的 span，且不得重复同组 evidence_ids。

默认本地模式：配置模式匹配抽出候选，不自动制造语义观察；用户可通过页面逐条选择证据并填写关系后重新审计。模型模式：同意后由可替换 HTTPS JSON-schema 适配器一次批量抽取、逐 Claim 比较（网络调用在 port）；存储模型/提示词/规则版本与加密原始响应，不把服务故障伪装成未核验。

## 持久化与 IO

SQLite 只存无正文元数据；请求、原文件、解析文本、报告和复核均加密为 BLOB。一个本地持久化数据密钥（0600、目录0700）；可用 EVIDENCE_DATA_KEY 绑定运维密钥，不打印。备份必须包含密钥；丢失密钥不能恢复。

Store：create(owner,payload,now) / acquire(now) / finish(task_id,lease,result) / fail / list/get(owner) / delete(owner) / recover / expire(now)。状态、保留期、重试/清理间隔来自 product.json。后台单 worker，实例通过 advisory file lock 排他运行；启动时恢复未完成 running，队列保存在 SQLite。任务删除/过期后已在运行的 worker 不得重建记录。到期内容即使清理失败也不返回；删除错误记录并在下一轮重试。

原文 PDF 由 PyMuPDF 解析；扫描/加密/损坏/表格或图片等无法稳定读取的页面只标明不可审计，不把 OCR 或元数据当证据。提取页内原文、段落定位和输入哈希。原文 PII 初步扫描命中则拒绝整个任务，且禁止外发。上传总大小、数量、单文件大小、解压/PDF页数/文本长度、候选数上限均来自配置。

## HTTP（单机单用户）

- GET /：静态网页；GET /api/config：非敏感配置、声明及模型可用性。
- POST /api/session：以本地启动生成的访问口令建立 HttpOnly SameSite=Strict cookie；禁止无身份读取任务。
- POST /api/tasks：multipart context + manuscript + evidence PDF（文件名仅用于展示与编号映射，不写路径）；context 显式绑定 reference_id 到上传文件索引，确认授权和单章节，默认本地模型。
- GET /api/tasks / /api/tasks/{id}：进度/结果；GET /api/tasks/{id}/report?format=json|markdown；GET /api/tasks/{id}/source/{reference_id}：任务内原 PDF，页码用于复核。
- POST /api/tasks/{id}/review：保存人工证据关系/注释并创建新审计任务；原预测保留；标注金标不受影响。
- DELETE /api/tasks/{id}：删除请求、原文件、结果和人工记录；UI 显示到期时间。

所有写请求检查自定义 X-Evidence-Request 头与同源 Origin；身份失败401、任务不存在404、输入422、体积413。错误与日志不含论文正文、密钥、模型响应或栈。内容不被缓存，PDF attachment + nosniff。外网部署需 HTTPS 反向代理，口令/会话密钥与数据密钥不能默认示例值。不开启支付，PRD 把付款定义为真实用户验证后的商业化能力。

【自检结果】R1 pass（规则/聚合/状态转移值由配置驱动）；R2 pass（契约和端口属子包）；R3 pass（跨域仅 api，模型/仓储端口无基础设施依赖）；R4 pass（contracts 叶节点）。实际实现待下一阶段。

## 最终实现补充

- ClaimCandidate/ClaimRecord 增加可空 claim_type、assertion_strength 及固定字段 Qualifiers；本地仅候选，模型/人工元数据不构成医学事实。
- EvidenceSpan ID 包含原文文件SHA256、来源标识与页内区间，禁止跨文件沿用观察。
- 成功/失败诊断包含步骤与耗时、输入/策略哈希及版本；私有诊断加密存储，不在普通任务响应回显。
- 评测为独立验证入口：读取原 Schema、人工确认状态及 split 清单，输出按规则 precision/recall 和引用解析准确率，不改金标；无数据不判通过。
