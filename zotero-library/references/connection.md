# 连接设置

## Codex：当前 Windows 用户

1. 在 Zotero 桌面端登录并完成同步。
2. 打开 [Zotero API Keys](https://www.zotero.org/settings/keys)，为此技能创建专用密钥。读取需要 library access，导入和标签／分类更新还需要写权限。记录页面显示的数字 User ID，它不是登录名。群组库使用 Group ID。
3. 在用户自己的 PowerShell 窗口运行 `powershell.exe -NoProfile -ExecutionPolicy Bypass -File "<技能路径>\scripts\setup.ps1"`。此参数只影响本次进程，解决默认禁止脚本的问题，不改变永久策略，也不能覆盖组织组策略。输入库类型、数字 ID 和密钥；密钥隐藏输入，使用 Windows 当前用户的 DPAPI 加密后保存至 `%LOCALAPPDATA%\ZoteroCodex\config.json`。这个文件不能直接搬到另一台电脑／另一用户解密。不要将密钥发到聊天。
4. 让 Codex 运行 `python <技能路径>/scripts/zotero_library.py status`。如果工具需要网络访问，按当前主机的授权机制处理。

个人“我的文库”选 `user`，群组文库选 `group`。Group ID 为群组网页 `/groups/` 后的数字。新建空群组不会自动包含个人库的文献。切换库后重新获取快照，不复用旧库计划。

个人库需要在当前密钥的 **Personal Library** 下开启 **Allow library access**；实际修改还需 **Allow write access**，点击 **Save Key** 保存。群组写权限不能代替个人库写权限。API Key 是创建结果中的完整密钥，不是 Key Name 或编辑网页的编号。遗失完整密钥时创建新密钥并重新配置；只修改原密钥权限时不用重新配置。

`status` 显示库范围及 `key_allows_write`，只核对密钥声明权限，不做测试写入。群组实际写入还受成员角色限制。`collections` 列出全部分类及父级。解密失败时先确认使用同一 Windows 用户；若仅代理沙盒失败，按宿主机制授权该用户环境访问，不要因此反复重建密钥。

也支持环境变量 `ZOTERO_LIBRARY_TYPE=user|group`、`ZOTERO_LIBRARY_ID`、`ZOTERO_API_KEY`。设置了 API_KEY 时只用这一组环境配置，不与加密文件混用。非 Windows 使用环境变量。`ZOTERO_CONFIG` 可指定其他加密配置路径。

本脚本使用 `https://api.zotero.org`，连接前不会扫描密钥或直接读写 `zotero.sqlite`。首次实库验证先读少量条目。写入成功后在 Zotero 同步以查看结果。

## ChatGPT：个人自定义 GPT 的 Actions

如果当前账号提供创建 GPT 和 Actions 的入口：

1. 创建一个仅自己使用的 GPT，把 `references/chatgpt-instructions.md` 内容填入 Instructions。
2. 新建 Action，把 `assets/chatgpt-actions.json` 全文粘贴到 Schema。
3. Authentication 选择 API Key，认证类型选 Bearer，输入 Zotero 专用 API Key。Zotero 支持 `Authorization: Bearer`；不需要不受 Actions 支持的自定义头。
4. 在 GPT 的 Instructions 末尾补充你的 `libraryType=users` 和数字 `libraryID`；群组则用 `groups`。库 ID 不是密钥。
5. 开启可用的数据分析／文件生成功能，以便把导出响应合并成下载文件。首先测试列出分类和少量文献，再测试用户指定的小范围写入。

这个配置直接访问 Zotero 云端，不需要额外架设服务器。导出为文本元数据，不包含 PDF 文件。每次读取默认 25 条；大库分页并分批处理。没有 Actions 或受工作区限制时，在 ChatGPT 分析导出文件，再交给 Codex 执行计划。

不要公开共享带有个人 Zotero 密钥的 GPT：该 GPT 的访问者可能使用它的库权限。共享给别人时应让对方自行创建 GPT 和自己的密钥。

Actions 平台可能要求确认写入；这是平台交互，不代表需要额外逐条口头审批。本包没有绕过它。

## 本地模式边界

本包仅实现 Zotero Web API，不依赖桌面版本的本地写入能力。本地授权与云端密钥、版本号体系不同，不应混用。扩展本地 API 前先核对当前官方文档。

## 官方依据

- [Zotero API 基础、认证、导出和分页](https://www.zotero.org/support/dev/web_api/v3/basics)
- [Zotero 写入、版本保护和数组替换语义](https://www.zotero.org/support/dev/web_api/v3/write_requests)
- [Zotero 本地 API](https://www.zotero.org/support/dev/web_api/v3/local_api)
- [Zotero 排序](https://www.zotero.org/support/sorting)
- [OpenAI Skills](https://learn.chatgpt.com/docs/build-skills)
- [GPT Actions 认证](https://developers.openai.com/api/docs/actions/authentication)
- [GPT Actions 限制](https://developers.openai.com/api/docs/actions/production)

核对日期：2026-09-16。平台界面及功能可用性可能变化，遇到入口不同先核对当前官方说明。
