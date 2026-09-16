# Zotero 文献管家 · Zotero Library Skill

通过 Codex 或配置了 GPT Actions 的 ChatGPT 管理 Zotero：导入与导出文献元数据、按内容整理分类、补充标签，并生成有依据的阅读顺序。

默认使用通用分类，再结合标题、摘要和可访问正文调整。保留已有标签、分类与书目信息；先形成具体计划，再按用户授权执行。个人库和群组库均通过 Zotero 官方 Web API 连接，需先完成云端同步。

## 功能与边界

| 功能 | 当前支持 |
| --- | --- |
| 检查连接 | 显示当前库、条目总数、密钥是否允许写入 |
| 列出分类 | 读取全部分类、父级关系和分类 key |
| 导入文献 | 导入经过核实的 Zotero API JSON；按 DOI 和标题检查重复 |
| 导出文献 | JSON 快照、BibTeX、BibLaTeX、RIS、CSL JSON、CSV |
| 分类与标签 | 复用或新建分类，追加成员关系和标签，保留原有内容 |
| 阅读顺序 | 编号分类、优先级标签及单独的阅读清单 |
| 变更保护 | 只读预检、版本冲突停止、逐项日志、写后读取核查 |

分类判断由模型完成，脚本负责读写。脚本不自动检索 DOI、不上传 PDF、不自动删除或合并重复文献，也不提供一键回滚。

## 选择使用方式

| 方式 | 适用情况 | 需要什么 |
| --- | --- | --- |
| Codex 技能 | 本地操作、批量整理、导出和保存变更日志 | Python，Zotero API Key |
| ChatGPT + GPT Actions | 在自定义 GPT 中直接读写云端库 | 支持 GPT Actions 的账号，自己的 API Key |
| 普通 ChatGPT 聊天 | 分析手动导出的文献并提出分类方案 | 上传导出文件；实际写入交给 Zotero 或 Codex |

**把技能文字粘贴到普通聊天，并不会自动获得 Zotero 访问能力。**

## Codex 快速开始（Windows）

### 1. 下载与安装技能

在本仓库选择 **Code → Download ZIP**，解压后进入项目文件夹。下面的命令均在项目根目录运行。准备 Python 3.11 或更新的受支持版本，确认 `python --version` 可用。脚本只用标准库，无需安装依赖。

也可以使用 Git 下载：

```powershell
git clone https://github.com/Sioloe/zotero-library-skill.git
cd zotero-library-skill
```

```powershell
python .\tools\install_skill.py
```

安装器默认使用 `$CODEX_HOME/skills`，没有设置时使用 `~/.codex/skills`。已有同名技能时会停止，不自动覆盖。对于使用通用技能目录的宿主，可明确指定：

```powershell
python .\tools\install_skill.py --skills-dir "$env:USERPROFILE\.agents\skills"
```

安装的只有 `zotero-library` 文件夹。重新打开会话或刷新技能列表后，在 Codex 中说“使用 Zotero 文献管家”。不同宿主的发现目录参见 [OpenAI 技能说明](https://learn.chatgpt.com/docs/build-skills)。

### 2. 选对文献库并找到 ID

| 你要管理的库 | 配置中输入 | ID 从哪里找 |
| --- | --- | --- |
| 桌面左侧“我的文库 / My Library” | `user` | [Zotero API Keys 页面](https://www.zotero.org/settings/keys)显示的数字 User ID |
| “群组文库 / Group Libraries”中的某个库 | `group` | 打开该群组，网页地址 `/groups/` 后面的数字 |

例如 `https://www.zotero.org/groups/1234567/example` 的 Group ID 是 `1234567`（仅作示例）。User ID 不是用户名或邮件地址；Group ID 不是群组名称。

**原有文献在“我的文库”时，请选 `user`。新建群组不会自动把个人库文献复制过去。**

### 3. 创建 API Key 并设置权限

打开 [Zotero API Keys](https://www.zotero.org/settings/keys)，选择 **Create new private key**。Key Name 可以填 `Zotero Library Skill`。

个人库权限：

- 勾选 **Personal Library → Allow library access**，用于读取文献与分类。
- 如需导入、创建分类或添加标签，再勾选 **Allow write access**。
- 按实际需求选择其他权限；本脚本不整理笔记和附件。

群组库需要单独选择相应群组的读写权限，且成员角色必须允许相应操作。**群组写权限不能代替个人库的 Allow write access。**

保存后，在创建结果中复制完整 API Key。它不是 Key Name，也不是编辑网址 `/settings/keys/edit/...` 中的编号。密钥编辑页通常只显示名称和权限；没有保存完整密钥时，请创建新专用密钥并重新配置。

完整密钥只输入本机配置窗口或 GPT 的认证设置，**不要发到聊天、Issue、README 或 Git 仓库中**。认证机制见 [Zotero 官方文档](https://www.zotero.org/support/dev/web_api/v3/basics)。

### 4. 在自己的 PowerShell 中配置

在项目根目录打开 PowerShell，完整复制运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\zotero-library\scripts\setup.ps1"
```

依次输入：

1. 库类型：`user` 或 `group`，直接回车默认为 `user`。
2. 对应库的数字 ID。
3. 完整 API Key：隐藏输入，不显示字符是正常现象。

密钥使用当前 Windows 用户加密，默认保存在 `%LOCALAPPDATA%\ZoteroCodex\config.json`，不会放入项目。每次配置替换当前连接设置，不会移动、复制或删除文献。

`-ExecutionPolicy Bypass` 只对本次启动的 PowerShell 进程生效，不更改永久执行策略，无需全局启用脚本。组织强制的组策略仍可能阻止执行，见 [Microsoft 执行策略说明](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_execution_policies)。

### 5. 检查连接并列出分类

```powershell
python .\zotero-library\scripts\zotero_library.py status
python .\zotero-library\scripts\zotero_library.py collections
```

重点检查：

- `library.type` 与 `library.id`：当前是否是目标个人库或群组库。
- `connected: true`：已成功读取目标库。
- `key_allows_write: true`：当前密钥声明允许写入该库。

这些命令不会修改文献。写权限检查不是实际写入测试；群组权限还受成员角色和设置约束。空库返回零条分类也可能是连接成功，不等于密钥失效。

之后可直接对 Codex 说：

> 使用 Zotero 文献管家，检查连接并列出我的分类。

## 实际使用示例

### 先预览，再按范围执行

> 使用 Zotero 文献管家，按通用分类分析我的文献。保留已有分类和标签，结合标题与摘要给出新增分类、标签和阅读顺序。先输出计划，不执行写入。

通用分类与标签示例见 [分类规则](zotero-library/references/taxonomy.md)。资料不足的判断列为待复核，不把低置信度推测写成确定标签。

> 执行刚才确认的整理计划，只追加分类与标签，保存变更日志，并核查执行结果。

已明确授权的范围内可以执行；“预览”请求不会写入。分类成员关系不等于复制文献，同一篇文献可属于多个分类。

### 导入与导出

> 核实这些 DOI 对应的标题、作者与年份，检查重复后导入我的个人库，并汇报跳过和待复核条目。

> 把“研究方法”分类的文献导出成 BibTeX，再生成带优先级与理由的阅读清单。

Python 直接导入的是 Zotero API 可编辑 JSON 数组。RIS/BibTeX 请先用 Zotero 原生导入，或通过可信转换器转为 API JSON 后核对；不能把 RIS 文件直接交给 `plan-import`。导出和快照均不包含 PDF 文件。

### 命令行工作流

```powershell
# 保存元数据快照
python .\zotero-library\scripts\zotero_library.py snapshot --out work/library.json

# 导出文献
python .\zotero-library\scripts\zotero_library.py export --format bibtex --out outputs/references.bib

# decisions.json 由助手根据真实快照生成，格式见命令文档
python .\zotero-library\scripts\zotero_library.py plan-organize --snapshot work/library.json --input work/decisions.json --out outputs/organize-plan.json

# 只读预检
python .\zotero-library\scripts\zotero_library.py apply --plan outputs/organize-plan.json

# 实际执行，须在用户授权范围内使用
python .\zotero-library\scripts\zotero_library.py apply --plan outputs/organize-plan.json --execute --journal outputs/organize-journal.json
```

完整参数、导入格式和恢复方式见 [命令与计划格式](zotero-library/references/commands.md)。输出拒绝覆盖同名文件，再次操作请换新文件名。`--collection` 仅包括直接属于该分类的条目，不递归包含子分类；导入查重要求全库快照。

## ChatGPT + GPT Actions

当账号提供自定义 GPT 与 Actions 时：

1. 创建仅自己使用的 GPT。
2. 将 [chatgpt-instructions.md](zotero-library/references/chatgpt-instructions.md) 放入 Instructions。
3. 添加 Action，粘贴 [chatgpt-actions.json](zotero-library/assets/chatgpt-actions.json)。
4. Authentication 选择 **API Key → Bearer**，在认证设置中输入 Zotero 专用密钥。
5. Instructions 中写明 `libraryType=users` 与自己的 `libraryID`；群组用 `groups`。这里是复数，与 Python 配置的 `user/group` 不同。
6. 先测试“列出分类”，再按授权测试小范围写入。需要下载文件时开启可用的文件生成功能。

Actions 直接请求 Zotero 云端，无需自建服务器。没有 Actions 或受工作区限制的账号，可先分析导出文件，再交给 Codex 执行。

**不要公开共享保存了个人 Zotero 密钥的 GPT。** 其使用者可能通过它访问同一文献库。分享本项目时，让每个人配置自己的密钥。Actions 可能要求额外确认写入，按平台提示操作。参见 [GPT Actions 认证](https://developers.openai.com/api/docs/actions/authentication)。

## 常见问题

### Group ID 在哪里？我应该用个人库还是群组库？

打开目标群组网页，取 `/groups/` 后的数字。如果文献原本在桌面“我的文库”，应选 `user` 并使用 API Keys 页的 User ID，无需新建群组。

### “此系统上禁止运行脚本”怎么办？

使用快速开始中的完整命令，即 `powershell.exe -NoProfile -ExecutionPolicy Bypass -File ...`。不要只双击或输入脚本路径。含空格的路径必须加双引号；若仍被组织策略拦截，联系管理员或采用环境变量配置，不修改组织安全策略。

### API Key 在哪里？编辑页只有名称和权限。

完整密钥在创建结果中显示。`Codex` 一类 Key Name 和编辑 URL 的编号都不是密钥。没有保留完整密钥时创建新密钥，在本机配置窗口输入，不要贴到聊天中排查。

### 连上了，但分类为空或文献不对？

先看 `status` 的库类型与 ID，再确认 Zotero 已同步。个人库和群组库独立，新建群组通常为空。仅修改类型而沿用错误的 ID 也会连接失败。

### 怎样切换回个人库？

重新运行 `setup.ps1`，选择 `user`，输入 User ID 和有个人库权限的完整密钥，再运行 `status` 与 `collections`。如果由助手切换，可以只更新本机配置中的库类型和 ID，保留加密密钥字段，不输出完整配置。切换后重新快照，不使用原库的旧计划。

### 怎样开启个人库 Allow write access？

打开 [API Keys](https://www.zotero.org/settings/keys)，编辑本机正在使用的那一把密钥，在 **Personal Library** 下勾选 **Allow library access** 和 **Allow write access**，然后点击 **Save Key**。再次运行 `status`，确认 `key_allows_write` 为 `true`。

只勾选群组写权限没有作用。只修改同一密钥权限，无需重新配置；如果创建了另一把新密钥，则必须重新配置。不要为了检查权限创建测试文献。

### 提示无法解密，但我已正确配置？

配置依赖同一 Windows 用户的加密环境。先在创建配置的同一用户终端检查。若普通终端成功、代理沙盒失败，应按宿主授权机制允许在该用户环境中解密和联网，这不等于密钥错误。换用户或换电脑需要重新配置，不能直接复制加密配置使用。

### 为什么仍报 401 / 403？

确认正在使用预期密钥、目标库 ID 正确、权限已保存。设置了 `ZOTERO_API_KEY` 环境变量时，它会覆盖加密文件，需连同 `ZOTERO_LIBRARY_TYPE`、`ZOTERO_LIBRARY_ID` 一起检查。群组还需检查成员角色。错误信息不要附带密钥。

### 能永久调整 Zotero 列表的任意顺序吗？

项目生成阅读清单，并使用编号分类与优先级标签辅助组织。Zotero 列表按字段排序；API 排序参数只控制返回结果，不会保存任意拖动顺序。项目不会为排序改动标题、作者或日期。参见 [Zotero 排序说明](https://www.zotero.org/support/sorting)。

### 写入冲突、断网或桌面没更新怎么办？

412 等版本冲突会停止写入，重新读取并生成计划。断网时请求可能已成功，先按日志中的 key 核实，再决定后续操作；不要盲目重放整个旧计划。云端写入后，桌面需要同步才会显示。

日志保存操作前后的元数据，但不是事务回滚或完整数据库/PDF 备份。删除、替换旧标签、自动合并和完整恢复不在脚本范围内。

## macOS / Linux 与环境变量

Python 脚本可在其他平台运行；`setup.ps1` 的加密配置仅适用于 Windows。在本地终端通过隐藏输入设置环境变量，例如 Bash：

```bash
export ZOTERO_LIBRARY_TYPE=user
export ZOTERO_LIBRARY_ID=1234567  # 替换为自己的数字 ID
read -r -s -p 'Zotero API key: ' ZOTERO_API_KEY; printf '\n'
export ZOTERO_API_KEY
python3 zotero-library/scripts/zotero_library.py status
```

该例不将密钥直接写入命令历史。让代理访问变量时，应由同一环境启动代理或使用宿主凭据管理方式。测试后可 `unset ZOTERO_API_KEY`。

## 项目结构与验证

```text
zotero-library/             可独立安装的技能
  SKILL.md                 触发范围与执行规则
  agents/openai.yaml       Codex 显示信息
  scripts/                 配置与 API 操作
  references/              分类规则、连接和命令说明
  assets/                  GPT Actions OpenAPI 定义
tests/                     离线测试，虚构条目与模拟 API
tools/                     安装器与 Actions Schema 生成器
```

从根目录运行：

```powershell
python -X utf8 -B -m unittest discover -s tests -v
python -X utf8 -B tools/build_actions.py
```

测试覆盖分类复用、原标签保留、导入去重、分页、版本冲突、部分失败日志、导出分批合并与权限范围。测试不连接真实 Zotero，不代表每个账号均可写入；真实环境先检查连接，再在授权范围内操作。

不要提交本机配置、密钥、文献快照、导出和变更日志。`.gitignore` 已排除常用输出位置。示例 ID 和文献均为演示用途。

## 许可

[MIT License](LICENSE)。本项目为独立社区工具，与 Zotero 或 OpenAI 无隶属关系。
