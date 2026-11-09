# 技术设计记录

本目录保留仍有参考价值的需求映射、模块设计与技术取舍。实现完成后，设计记录可继续解释决策；其中当时的待办、代码片段和运行状态不自动成为当前事实或新任务。

日常开发入口：

- [当前后端结构与数据来源](../../architecture/backend-overview.md)
- [API 契约](../../api/voteable-api-contract.md)及对应源码
- [当前 BACKLOG](../../BACKLOG.md)

主题设计索引见 [文档索引](../../README.md)。已明确被替代的旧 ILIKE autocomplete、单文件 admin panel、旧固定槽问卷前端设计已经移入 [设计归档](../../archive/superpowers/specs/)。官方需求原文仍在 [requirements](../../requirements/)。

2026-11-09 问卷四阶段设计均已实施并提交：

- [定义来源统一](2026-11-09-questionnaire-backend-source-design.md)：填写/结果共用后端定义，id/code分工及管理台维护。
- [答案规则](2026-11-09-questionnaire-answer-rules-design.md)：合法性、单份完成及分支评估；当时required-only及空配置兼容为历史范围，后续已调整。
- [整体完成闸门](2026-11-09-questionnaire-completion-gate-design.md)：全部必填＋至少一份extra，退出旧数据放行。
- [独立定义检查脚本](2026-11-09-questionnaire-check-design.md)：只读命令、错误/警告和发布前调用，无新增后台模块。

当前提交、核验边界和下一步统一查[问卷现状](../../migration/questionnaire-audit-2026-11-09.md)，不从旧设计的历史约束重新安排实现。

只有准备实施的新需求才进入 [实施计划](../plans/README.md)；旧设计记录不按“未执行计划”管理。
