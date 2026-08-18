# Provider 接口

Cinemata 将内容数据和外部生成服务分开。provider 只接收规范化后的业务对象，返回一个带 provenance 的资产记录；它不负责修改 episode manifest，也不负责发布内容。

## 当前接口

`ImageProvider.generate(shot, output_path)` 接收一个标准化镜头，写出图片文件并返回资产记录。内置 `MockImageProvider`：

- 不访问网络或 API Key
- 根据 prompt 生成确定性的 SVG 占位帧
- 记录 provider 名称、版本和 prompt SHA-256
- 可在 CI 和本地审阅流程中使用

## 接入真实 provider 的约束

实现真实图片、配音、音乐或视频 provider 时：

1. 不改变 episode manifest 的字段含义。
2. 将模型、版本、参数、seed、耗时和外部任务 ID 写入 provenance。
3. 失败时抛出可分类的异常，不返回伪成功资产。
4. 由调用方决定重试和缓存策略，避免 provider 内部产生不可见副作用。
5. 明确记录素材的来源、许可证和使用限制。

后续会提供官方适配器包和离线 fixture，核心仓库保持无外部依赖。
