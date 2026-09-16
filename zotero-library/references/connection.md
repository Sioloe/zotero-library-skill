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

按当前账号的实际界面确认支持情况，不仅凭套餐或“技能”页面标题判断。若进入编辑器后看到“新 GPT / 草稿”以及“创建 / 配置”，点击“配置”，向下找到“操作 → 创建新操作”。能打开草稿不等于能保存或调用接口；这些步骤应分别验证。已有 GPT 则检查是否有编辑权限及 Actions 入口。

如果当前账号提供可用的 Actions 配置：

1. 名称填“Zotero 文献管家”，将 [GPT 指令](chatgpt-instructions.md) 全文填入“指令 / Instructions”。
2. 在“操作 → 创建新操作”中，将 [接口定义](../assets/chatgpt-actions.json) 的原始 JSON 全文粘贴到“Schema / 架构”。GitHub 上可用 Raw 查看原文，不能复制整个网页；此文件应放在操作架构中，而非“知识”上传区。
3. Authentication 选择 API Key，认证类型选 Bearer，只在认证窗口输入完整 Zotero API Key，不手动加 `Bearer ` 前缀。Zotero 支持 `Authorization: Bearer`。不将密钥放进指令、Schema 或聊天。
4. 在 GPT 的 Instructions 末尾补充 `libraryType=users` 和 `libraryID=<自己的数字 User ID>`；群组用 `groups` 和 Group ID。将占位符替换为真实数字。Actions 使用复数，本机 Python 配置使用单数 `user/group`。
5. 开启可用的数据分析／文件生成功能，以便把导出响应合并成下载文件。需要核实 DOI 或链接时，使用可用检索能力。
6. 在预览中发送“检查 Zotero 连接，列出我的分类，不修改任何文献”，再请求最多 5 篇文献的标题与 key。以真实工具调用和返回内容验证，不凭模型口头声称判定成功。空库可合法返回空数组。连接检查只用 `listCollections`、`listTopItems` 等读取操作，不调用写入操作测试连通性。
7. 验证后按界面保存或创建 GPT，访问范围选“仅自己 / Only me”。手机使用同一账号及工作区打开已保存 GPT，再测试读取。是否能保存和调用仍受当前权限限制。

这个配置直接访问 Zotero 云端，不需要额外架设服务器或让电脑一直运行。Windows 中保存的密钥和库配置不会自动转移到 GPT；本机配置与 GPT 认证分别维护。导出为文本元数据，不包含 PDF 文件，也未实现自动获取 PDF 全文。每次读取默认 25 条；大库分页并分批处理。没有 Actions 或受工作区限制时，可在 ChatGPT 分析导出文件，再交给 Codex 执行计划。

不要公开共享带有个人 Zotero 密钥的 GPT：该 GPT 的访问者可能使用它的库权限。共享给别人时应让对方自行创建 GPT 和自己的密钥。

Actions 平台可能要求确认写入；这是平台交互，不代表需要额外逐条口头审批。本包没有绕过它。

## 手机与 Remote

阅读文献可使用 Zotero 官方 iOS / Android App 或手机网页。元数据同步不包含 PDF 文件，阅读附件需另行完成文件同步。只有标题或摘要时，不声称已经读取全文。

若手机希望沿用电脑上的 Codex 技能，可在桌面应用支持时使用 Remote：电脑端“设置 → Connections / 连接 → Control this Mac or PC / 控制此电脑”开始配对，用手机扫描二维码，登录同一账号及工作区，再从手机 Remote 打开该电脑上的任务。此方式使用电脑的技能、凭据和权限，电脑必须保持唤醒、联网且应用运行；入口可能受功能开放或工作区权限限制。

Actions 配置成功后可直接从手机请求 Zotero 云端，无需电脑常开；Remote 则依赖电脑。上传技能 ZIP 本身不建立云端连接。本包尚未提供独立部署的云端 MCP 服务。

## 本地模式边界

本包仅实现 Zotero Web API，不依赖桌面版本的本地写入能力。本地授权与云端密钥、版本号体系不同，不应混用。扩展本地 API 前先核对当前官方文档。

## 官方依据

- [Zotero API 基础、认证、导出和分页](https://www.zotero.org/support/dev/web_api/v3/basics)
- [Zotero 写入、版本保护和数组替换语义](https://www.zotero.org/support/dev/web_api/v3/write_requests)
- [Zotero 本地 API](https://www.zotero.org/support/dev/web_api/v3/local_api)
- [Zotero 排序](https://www.zotero.org/support/sorting)
- [OpenAI Skills](https://learn.chatgpt.com/docs/build-skills)
- [GPT Actions 配置与测试](https://developers.openai.com/api/docs/actions/getting-started)
- [GPT Actions 认证](https://developers.openai.com/api/docs/actions/authentication)
- [GPT Actions 限制](https://developers.openai.com/api/docs/actions/production)
- [GPT 使用与编辑](https://help.openai.com/en/articles/8554397-creating-a-gpt)
- [OpenAI Remote](https://learn.chatgpt.com/docs/remote-connections)
- [Zotero 手机端](https://www.zotero.org/support/mobile)
- [Zotero 数据与附件同步](https://www.zotero.org/support/sync)

核对日期：2026-09-16。平台界面及功能可用性可能变化，遇到入口不同先核对当前官方说明。
