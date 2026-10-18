# 产品增量阶段 1：建模

沿用四域，新增 Evidence 的全文来源与页内坐标、Observation 候选、ClaimAssessment 和持久化 Task。任务持久化、文件加解密、模型和时钟均在基础设施；应用只编排端口。单机单用户，用户以持久化本地会话访问，无跨用户协作或付款功能（PRD 后续商业化项）。

语义事实必须绑定实际取回的证据 ID，观察记录保存 origin 和 rationale；无证据不允许语义推断。来源缺失与已检索但无命中分开。多来源不完备/冲突按配置表保守输出，保留每项 Finding。人工复核记录不覆盖原预测或金标。

默认本地候选提取+人工逐条复核；可选 HTTPS OpenAI-compatible 两操作适配，须配置且每次任务明确同意，不允许模型输出 Finding/最终标签。没有实际密钥时继续完整离线流程，不编造调用结果。

业务规则补入 constraint-ontology。对更新依赖 DAG 执行 DFS：无环。

【自检结果】R1 pass（策略在配置）；R2 pass（新增领域子包）；R3 pass（设计 DAG 无环）；R4 pass（contracts 叶节点）。这是设计自检，新增代码待实现。
