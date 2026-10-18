# 阶段 2：目录树

完整 JSON 见 `../directory-tree.json`。JSON 已解析并执行 src/package 根层文件检查。当前阶段只保存目录设计，不生成业务源码。未实现的 Evidence、LLM、存储、前端不创建空模块。

## 【自检结果】

- R1: pass（设计层）：未增加 Python 业务策略。
- R2: pass（设计层）：src 只含 evidence_check 包，包根只允许空 __init__.py；业务文件全属子包。
- R3: pass（设计层）：沿用阶段 1 的无环依赖；未增加导入。
- R4: pass（设计层）：contracts 为叶节点，无 common。
