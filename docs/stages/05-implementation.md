# 阶段 5：按领域实现 POC-A

生成顺序：共享 DTO/配置类型 → Document（解析及事实）→ Claim（人工候选校验）→ Audit（通用规则执行）→ Application（公开 API 编排）→ Infrastructure（文件/配置/报告）→ CLI/无持久化 FastAPI。

实现 Markdown/DOCX、数字单引/多引/区间、章节段句字符位置、编号解析、人工指定 Claim 无引用、错编号和全文未验证提示，JSON/Markdown 报告。CLI 示例实际返回三条 Finding，均有定位，未产生支持性判断。

安装：已创建独立 .venv 并安装本包及 dev 依赖。使用独立环境执行 `python -m unittest discover -s tests -v`：32 项通过，无失败/跳过。与预装环境结果一致。发现上游 TestClient/httpx 弃用警告，将在阶段 6 以直接 ASGITransport 请求消除测试适配器依赖。

## 【自检结果】

- R1: pass：业务规则/阈值/筛选/文案来自 JSON；配置阈值和映射变更测试证明结果随配置变化。静态词汇扫描不能证明全部 R1，阶段 6 仍需人工复核。
- R2: pass：实际扫描 src/package 根，无平铺业务文件，所有 init 为空。
- R3: pass：全量 Python 静态导入 DAG 无环，跨域只导入 api，领域与应用无 IO。
- R4: pass：contracts 无领域/应用/基础设施依赖，不存在 common。

未完成：POC-B 全文与语义能力、Web 前端、持久化任务/生产安全、人工金标和盲测。32 项合成测试不等于 PRD 的精度门槛达成。进入阶段 6 审计后只修改本切片发现的问题。
