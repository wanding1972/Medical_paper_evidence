# Evidence Check · 医学论文证据链审计

一个可运行的**单机、单用户审计工作台**：上传单章节 Markdown/DOCX 和已引用 PDF → 提取候选论断 → 仅在已引全文内检索 → 查看原文页码 → 人工/可选模型比对 → 下载审计报告。默认不外发文本。

本轮已补齐软件工作流；**不是已经通过医学盲测或公开生产验收的服务**。真实模型尚未联调，独立医学金标、真实用户试用和隐私审查仍待完成。不得用合成测试宣称达到 PRD 的 98%/95%/80% 指标。

## 启动

Linux、Python 3.12+，在仓库根目录执行：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-dev.lock
.venv/bin/python -m pip install --no-deps -e backend
.venv/bin/evidence-server
```

默认绑定本机 127.0.0.1 的 8000 端口；启动控制台告知访问口令文件位置。浏览器进入服务首页，使用 `.evidence-data/access-password` 中的口令登录。通过本地终端自行读取该文件；不要把口令或密钥贴到聊天、日志或 Git。

可选参数：`--port`、`--host`、`--config-dir`、`--data-dir`。默认数据目录 `.evidence-data/` 已加入忽略规则。只支持一个服务进程/Worker 使用同一数据目录，第二个实例会明确拒绝启动。

## 使用流程

1. 选择正文文件，填写任务名称与正文/文献语言模式。
2. 参考文献逐行输入，如 `[1] Author. Article title. Year.`；为每个 PDF 选择对应编号。没有全文的引用仍可检查编号，但不能判断支持性。
3. 确认处理授权、无患者信息、单章节范围。默认不勾选外部模型。
4. 等待任务完成，查看候选论断、引用问题、候选证据和原始 PDF。每段证据可定位到页码、段落与页内字符区间。
5. 逐条确认候选；可去掉不属于可核查论断的句子，也可在正文中选中完整句子补充。选择证据、填写各项关系及复核依据，然后重新审计。
6. 原预测任务保留，人工复核生成新任务；JSON/Markdown 报告可下载，原 PDF 可下载核对。可主动删除任务及所有关联材料。

“支持候选”“相反证据候选”等均为**需复核预测**，不构成医学结论。没有 Finding 不等于证据支持；未知、冲突和不完整来源保守呈现。人工复核不修改 evaluation 内的金标。

## 已实现的边界

- 单章节、中/英文、数字单引/多引/区间引用，参考文献最多30条。中文字符和英文词分别受配置限制。
- DOCX 普通段落及 Markdown；DOCX 表格、图片、文本框、修订等未支持结构会被拒绝，避免静默漏内容。页眉页脚不是规范正文，章节范围仍需用户确认。
- 文本型 PDF 页内原文定位；扫描/加密/损坏 PDF 标明不可审计。摘要/参考文献区和表格文本不作为细粒度证据，不提供 OCR，不以元数据替代证据。
- BM25 与小型配置同义词表，仅限当前 Claim 的已引文献；**跨语言召回未通过独立验证**，没有候选不代表全文没有证据。
- 配置化八规则、五标签；来源不完整、关系未知、未逐来源比对或支持/反证冲突时保守降级。数值比较必须由人工/模型确认单位、分母、时间窗口可比，不做字符串数值相等的伪判定。
- 候选类型、断言强度与限定项保留为结构化 DTO；本地规则提供有限候选，不会凭常识补医学事实。
- 持久化队列、启动恢复、重试上限、任务时间预算；步骤故障为任务失败，不伪装成 unverified。
- 请求、原文件、解析文本、报告、模型响应加密保存在 SQLite BLOB；上传/正文解析走内存，不生成解密正文临时文件。来源 ID 包含原 PDF 内容哈希，防止跨文件套用旧观察。
- 本地登录、HttpOnly/SameSite cookie、写请求同源检查、体积限制、最小日志与安全响应头。到期任务即时不可访问，后台按配置周期物理删除；清理失败记录并重试。默认每任务24小时，清理周期30秒。

PII 正则仍是初步拦截，不能保证检出所有患者信息。不得用于处理病历、病例报告或患者数据。公开部署前须完成独立安全、版权、隐私和模型服务适用性审查。

## 可选外部模型

默认 `backend/config/product.json` 的 `model.enabled=false`，即使客户端声明同意也不能绕过。要启用：

- 在运行环境安全配置 `EVIDENCE_MODEL_URL`（HTTPS chat-completions 完整地址）、`EVIDENCE_MODEL_NAME`、`EVIDENCE_MODEL_KEY`；不把值写进配置文件或仓库。
- 将 `product.json` 的 `model.enabled` 改为 true，并重启服务。
- 用户每项任务仍须勾选明确同意，页面才允许外发。正文/PDF 的门禁和 PII 检查先执行。

适配器只允许 `extract` 和 `compare` 的严格 JSON Schema 候选响应，禁止 Finding/最终标签字段；原文/坐标/关系枚举/证据 ID 再由域验证。TLS 验证保留，禁止重定向携带密钥；网络或响应失败会明确使任务失败。真实供应商需通过环境网络设置允许对应域名。本轮只验证了受控 HTTP 响应，**没有调用真实模型服务**。

## 数据与运行维护

默认本地生成 `data.key`、`session.key` 和访问口令，文件0600、目录0700；也可通过 `EVIDENCE_DATA_KEY` 注入 Fernet 数据密钥、`EVIDENCE_ACCESS_PASSWORD` 注入访问口令。密钥不会回显。已有数据密钥不匹配时拒绝启动，不覆盖数据。

备份须同时考虑加密数据库与数据密钥，分开保管；丢失数据密钥无法恢复。默认密钥与数据库同机，**不能抵御整机/整个目录被窃取**；正式环境应由独立密钥管理或受保护挂载注入。恢复时保留 session.key，可保持本地用户归属；更换它会使旧会话失效并改变用户归属。

SIGTERM 停止接新任务；当前模型请求受配置超时限制，下一检查点退出，未完成 running 任务在重启后恢复。异常重复超过配置重试次数后明确失败。不要以多个 Uvicorn workers 共享本目录。外部访问需 HTTPS 反向代理和防火墙；默认本机绑定不等同于互联网发布。本仓库没有自动发布或收费；PRD 将付费服务放在真实用户验证后。

## 测试

```bash
cd backend
../.venv/bin/python -m unittest discover -s tests -v
```

真实 Chromium 端到端（自动启动/停止测试服务，使用临时合成 PDF，不访问外部模型）：

```bash
cd browser
npm ci
npx playwright install chromium
npm test
```

已有系统 Chromium 时可设置 `EVIDENCE_CHROMIUM=/usr/bin/chromium`；Python 不在根目录 `.venv` 时设置 `EVIDENCE_TEST_PYTHON`。可用 `EVIDENCE_SCREENSHOT_DIR` 保存合成测试截图。CI 配置见 `.github/workflows/checks.yml`；本地已验证同等命令，GitHub 托管 CI 本轮尚未执行。

## 独立盲测入口

```bash
.venv/bin/evidence-evaluate --gold /path/gold.jsonl --predictions /path/predictions.jsonl --split-manifest /path/split.json
```

Gold 使用原 `evaluation/annotation-schema.json`，仅接受 confirmed/adjudicated，禁止待填模板和占位文字。Prediction 每行仅含 record_id、predicted_label、rule_ids、citation_ids。split.json 为 `{"development_documents":["dev-id"],"blind_documents":["blind-id"]}`；文档集合不得重叠，金标文档必须完全匹配盲测清单。人工负责清单真实性与防止内容重复；程序不能证明真实独立性。

输出各规则 TP/FP/FN、precision/recall、引用解析准确率和语言覆盖。无预测的 precision 是 null，不能判通过；样本不足同样失败。退出码0=全部门槛通过，2=指标/覆盖未通过，1=输入无效。门槛引用 acceptance.json，不硬编码到 Python。当前没有真实金标，医学效果验收仍未执行。

## 开发约束与资料

[AGENTS.md](AGENTS.md)、[约束本体](docs/constraint-ontology.json)、[目录 JSON](docs/directory-tree.json)、[产品分阶段产物](docs/product)、[原 POC-A 自检](docs/stages)。R1–R4 检查包含导入 DAG、目录、跨域接口、策略扫描及配置变更测试；R1 仍需人工检查，不能把字符串扫描当作完备证明。

原始需求保存在 docs/inputs，七份附件逐字节保留；人工标注模板在 evaluation，不能当验收金标。没有引入通用知识库、联网补文献、论文评分或医学决策。CLI `evidence-check` 和 `/audits` 的 POC-A 兼容入口仍保留，产品网页请用 `evidence-server`。

学习与写作辅助，不构成医疗建议、发表保证或学术评价。
