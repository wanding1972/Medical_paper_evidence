# Windows 启动修复

## 阶段1：边界与依赖

问题是 Windows 虚拟环境路径不同，以及基础设施 Worker 直接导入 POSIX-only fcntl。无需新增业务域/实体；替换基础设施排他锁，依赖仍为 infrastructure → contracts，DAG不增加反向边。

【自检结果】R1 pass；R2 pass；R3 pass；R4 pass（设计层）。

## 阶段2：目录

修改现有 infrastructure/worker.py、对应测试、README、依赖文件和 CI；不新增平铺业务源码。

【自检结果】R1 pass；R2 pass；R3 pass；R4 pass（目录层）。

## 阶段3：接口

Worker start/stop 与效果回调不变。锁须跨进程排他，并允许 FastAPI shutdown 在另一线程调用 stop；启动恢复失败须释放锁。锁竞争返回 worker_already_running，其他锁 IO 故障转换稳定错误并记录。

【自检结果】R1 pass；R2 pass；R3 pass；R4 pass（契约层）。

## 阶段4：配置

业务策略不变。采用跨平台 filelock 技术依赖并固定安装版本；不引入业务条件/阈值。文档区分 CMD 与 POSIX 路径；Windows 文件权限由 NTFS ACL 管理，不把 chmod0600 误称为已设置Windows ACL。

【自检结果】R1 pass；R2 pass；R3 pass；R4 pass（配置层）。

## 阶段5：实现与测试

filelock 取代 fcntl，thread_local=False 支持应用关闭时在其他线程释放；补充竞争、跨线程释放、恢复失败释放、锁IO错误测试。浏览器脚本根据平台选择 Python 路径；POSIX mode 位断言仅适用于POSIX，Windows须检查用户目录ACL。

【自检结果】R1 pass；R2 pass；R3 pass；R4 pass（实际代码及架构测试）。

## 阶段6：审计

- Linux/Python3.12 本地74项测试通过，含原71项回归；真实浏览器完整流程通过。
- pip 针对 win_amd64/cp314 成功解析并下载全部锁定依赖的预编译wheel。此结果证明依赖可获取，不等于在Windows上执行应用。
- 增加 windows-latest / Python3.12及3.14 后端CI，托管Windows运行结果尚未验证，不冒称Windows实机通过。
- 未修改业务规则/数据/金标，未加入生成的虚拟环境或密钥。

【自检结果】R1 pass；R2 pass；R3 pass；R4 pass。当前修复未解决的代码fail为0，Windows实机运行须由CI/用户环境继续确认。
