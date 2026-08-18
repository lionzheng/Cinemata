# Cinemata 数据模型

第一版采用 JSON manifest，保持语言和 provider 无关。文件可以提交到 Git，用于审阅、复现和 CI。

## Episode manifest

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `project` | string | 是 | 项目或剧集名称 |
| `episode` | string | 是 | 分集标识 |
| `assets` | array | 否 | 素材来源和许可证 |
| `scenes` | array | 是 | 场景列表 |

每个 scene 包含 `id`、`location`、`characters`、`shots` 和可选的 `dialogue`。每个 shot 包含 `id`、`type`、`duration` 和 `prompt`。对白通过 `shot_id` 绑定镜头，并可声明角色和持续时间。

## Provenance

`provenance.json` 记录：

- schema 和 pipeline 版本
- 输入 manifest
- 生成时间
- 资产 URI、来源和许可证
- 后续 provider 的模型、参数、seed 和人工审核状态

第一版只写入已有资产和核心 pipeline 信息；provider 接入后必须扩展为可审计的逐资产记录。

## 兼容性规则

- 新增字段必须是可选字段，或提升 `schema_version`。
- 删除字段和修改字段类型属于破坏性变更。
- 未知字段应被读取端忽略，保证旧工具能够处理新 manifest。
- 时间统一使用秒，精度为浮点数；导出格式自行转换。
