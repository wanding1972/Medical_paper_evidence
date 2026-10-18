# 产品增量阶段 2：目录

目录 JSON 已更新。新增 Evidence 领域、产品契约/规则执行、PDF/模型/存储/Worker 适配器，以及 entrypoints/assets 静态界面。采用 FastAPI 同源静态页面，替代另起 Next.js 进程；产品没有 SSR/复杂路由需求，减少部署依赖，保留 HTTP 接口边界。

【自检结果】R1 pass（无业务值写入源码）；R2 pass（全部位于子包）；R3 pass（设计依赖未反向）；R4 pass（共享类型不依赖业务）。
