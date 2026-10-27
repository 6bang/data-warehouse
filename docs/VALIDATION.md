# 开源副本独立验证

验证日期：2026-10-27。对象是独立开源副本，不是原私有项目。以下记录不包含原数据、凭据、个人目录或浏览器截图。

## 修复后复验（2026-10-27，最新）

独立审核后做了下列修复，本节结果以修复后的代码为准；下方各节是修复前的历史记录（当时为 92 个后端测试，其中包含已删除适配器的测试；6 个配置页签；旧版扫描器）。

| 修复 | 内容 |
| --- | --- |
| 删除第三方账号密码适配器 | 移除网页端账号密码登录、切换企业和内部查询接口的客户端，以及对应的模型、接口、命令、配置页签和测试；新增迁移 `0018` 删除该表。经营数据只通过 MCP 或本地导出文件进入；小时趋势在没有数据来源时显示不可用。 |
| 加强隐私扫描器 | 在 Git 仓库中只检查将被发布的文件；新增飞书文档/表格/用户/租户标识、手机号、身份证号、邮箱、公网 IP、非公开 URL 主机、配置与文档中的裸域名、JWT、Bearer、凭据赋值、高熵字符串、编码或拼接隐藏的密钥、锁文件私有源、店铺/企业名称（含英文品牌）等规则；支持放在仓库之外的私有词表，只输出位置与类别。 |
| 中性测试数据 | 后端测试夹具的商品与类目改为与演示目录一致的中性品类。 |
| 发布流程 | 发布副本放在私有项目之外单独初始化 Git；发布包只用 `git archive` 从 Git 生成，不压缩工作目录。 |
| 中性命名 | 月度 Excel 导入改用中性名称：模块 `services/monthly_export.py`、命令 `import_monthly_export`、来源标识 `excel` / `excel_export`；新增迁移 `0019` 更新默认值。MCP 经营数据适配器也改用中性名称：模块 `services/mcp_sync.py`、命令 `sync_mcp_data`、接口 `/api/v1/data-sync/mcp/`、来源标识 `mcp_sync`，前端页面、演示数据、测试和文档同步更新（无表结构变化，不需要迁移）。历史迁移文件保持原名，以免已有数据库无法升级。 |

| 检查 | 结果 |
| --- | --- |
| 后端 `pytest -p no:cacheprovider`（Python 3.11，断开外网） | 93/93 通过（含新命令、新接口路径与来源标识的回归测试） |
| `manage.py check` / `makemigrations --check --dry-run` | 无问题 / 无变更 |
| 新库迁移 0001–0019；旧版数据库升级 | 均成功；升级后适配器表已删除，默认来源已更新 |
| 用新命令导入一份生成的 Excel | 成功；同步记录、月度事实和商品档案的来源均为中性标识 |
| 未配置时运行全部管理命令 | 不联网、不同步、未设密码不建管理员；已删除和已改名的旧命令不再存在 |
| 根目录 `unittest`（扫描器与启动脚本自测） | Python 3.9：10/10；Python 3.11：9 通过、1 跳过（该解释器未装后端加密依赖） |
| 前端 `npm run build` / `npm run lint` / node 测试 | 构建通过；0 错误、2 条既有警告；28/28 |
| `python3 tests/privacy_audit.py`（Git 模式） | 0 findings |

## 总控最终集成验收

除下方独立验证之外，总控在另一份系统临时副本完成了下列检查：

| 检查 | 命令/执行方式 | 结果 |
| --- | --- | --- |
| 全新Python依赖 | Python 3.11.15创建独立venv，`python -m pip install -r backend/requirements.txt --no-cache-dir` | 退出0，实际下载安装成功；首次受网络沙箱限制失败，经授权重试成功 |
| 前端 | `npm run build && npm run lint && node --test tests/demo.test.mjs tests/demo-original.test.mjs` | 退出0，28/28；0 lint错误、2条既有warning；复用已有Node22依赖，未声称重新验证全新npm下载 |
| 后端最终回归 | 无.env临时副本中`python -m pytest -p no:cacheprovider -q` | Python3.11下92/92通过，退出0 |
| Django配置与迁移 | `python manage.py check`及`python manage.py makemigrations --check --dry-run` | 均退出0，No issues / No changes detected |
| 完整本地启动 | `python scripts/dev.py full --no-install --frontend-port 5185 --backend-port 8015` | 自动私有配置、迁移、初始管理员创建、后续不覆盖，前后端成功启动 |
| 本地MCP端到端 | 临时localhost模拟MCP，实际HTTP请求而非mock掉客户端 | 登录、匿名401、空月度看板、MCP配置加密、工具发现、店铺查询、单月导入和商品档案均通过；虚构销售额120、单条商品，无真实数据或凭据 |
| 原工程保护 | 对另存操作前后的167个原项目文件做SHA256对比 | 0个变化；未部署或访问原线上系统 |
| 纯源码检查 | `python3 tests/privacy_audit.py`及`python3 -m unittest discover -s tests -p 'test_*.py'`（禁用bytecode） | 0 findings，5/5通过，无依赖/数据库/凭据/符号链接残留 |

集成过程如实记录：本地端口首次被执行沙箱拒绝；授权后测试探针受本机连接环境影响超时，改为本机直连后继续。随后发现新空库显式月份看板500（空月份列表索引），已修复并增加4项独立回归，再次本地接入全流程退出0。启动器为子进程追加loopback NO_PROXY，保留已有代理绕过设置，并区分端口占用与权限错误。

主控曾在完整启动已生成.env的同一临时目录中再次运行默认配置测试，出现1条“缺生产密钥应拒绝”断言失败：测试实际读到了刚生成的有效配置。随后隔离该私有.env，按文档规定的无.env测试目录重跑，最终92/92通过；没有降低安全断言或改生产校验。

全部临时HTTP服务已停止。Windows启动、Docker镜像构建、全新npm安装及任何真实上游MCP授权不在本次实机验收范围。私有.env/SQLite/运行日志只在临时验证目录，不进入分发源码。仓库所有者已于2026-10-27确认MIT许可证；依赖漏洞与第三方授权仍需在正式公开/生产部署前复核。

## 环境与隔离

- 发布目录保持纯源码；测试在系统临时目录中的副本运行。
- 离线复用已安装的 Node 22 与 Python 3.9 依赖，未重新联网安装依赖。因此不等价于全新机器安装验收。
- 前端依赖仅链接到临时工作副本；构建产物、临时数据库、浏览器配置与截图均不进入发布目录。
- Python 使用 `PYTHONDONTWRITEBYTECODE=1`，pytest 使用 `-p no:cacheprovider`；测试数据库为 SQLite。
- 后端单元测试默认禁止未显式 mock 的 DNS、socket 连接和 urllib 请求。每条测试即时生成独立 Fernet 密钥，不发布可用密钥。
- 浏览器测试拦截并记录全部业务 API 请求和跨源请求，仅访问本机演示服务，不登录真实账户。

## 隐私与发布树检查

根目录执行：

```sh
PYTHONDONTWRITEBYTECODE=1 python3 tests/privacy_audit.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_*.py'
```

初次结果均为退出码 **0**：扫描 **0 findings**；扫描器自测 **2/2** 通过。

扫描覆盖整个发布目录（包括隐藏路径），检查 Git 历史、真实 `.env`、数据库、日志、依赖/缓存、构建目录、上传、截图、符号链接、个人绝对路径、常见密钥格式、URL 内嵌凭据、SVG 主动/外部内容和本地演示图白名单。扫描只打印文件位置与分类，不打印命中值。此工具是保守防线，不保证识别所有业务身份或所有秘密；新增业务样本仍须人工复核。

独立本地额外只读比对原项目的商品目录与根 `.env`：原目录 **60** 条商品，合计 **239** 个候选字符串。商品 ID、名称、货号、图片 URL 未发现精确残留；原生产主机、凭据与租户候选未发现残留。最初 18 个匹配位置均为通用项目标识、公开模型型号或 CLI 命令等非秘密值。原值与品牌字典未写入本发布树。

另逐文件检查 URL 主机：剩余地址为保留示例域、本机/容器服务、公开技术供应商/包仓库和电商公开链接模板。没有原用户生产域名或预填私有数据源。测试中的旧数据源示例已替换为 `source.example.invalid`。

## 前端回归

在 `frontend/` 执行：

```sh
node --test tests/demo.test.mjs tests/demo-original.test.mjs
npm run build
npm run lint
```

| 轮次 | 命令 | 退出码 | 实际结果 |
| --- | --- | --- | --- |
| 1 | Node 测试 | 1 | 27/28 通过；发现绝对示例域 URL 被 mock 地址解析误判为本地 |
| 1 | `npm run build` | 0 | TypeScript 与 Vite 构建成功；第三方 PURE 注释与大 chunk 警告 |
| 1 | `npm run lint` | 1 | 10 个历史未使用解构字段、构建生成配置的 1 个未定义变量错误；已反馈修复 |
| 2 | Node 测试（返工前确认） | 1 | 仍为 27/28；未把待修复状态记为通过 |
| 3 | Node 测试（返工后） | 0 | **28/28** 通过，含绝对 URL、协议相对 URL、显式端口 URL 拒绝 |
| 3 | `npm run build` | 0 | 构建通过；仍有第三方 PURE 注释和大 chunk 非阻断警告 |
| 3 | `npm run lint` | 0 | 0 errors，2 条已有 Vue 样式/prop 默认值警告 |

新增回归覆盖精确 60 个虚构产品、合成 ID/货号命名、每个本地 SVG 文件存在、无脚本/外部引用，以及路径穿越、编码绕过、空白、NUL、查询参数、fragment、外站、协议相对地址和非白名单文件拒绝。原 13 路由、金额聚合、模拟 CRUD、无凭据、无存储写入与失败关闭断言保留。

浏览器复跑方式（需预先安装 Playwright 和 Chromium，或用环境变量指定本地可执行文件）：

```sh
npm run dev -- --host 127.0.0.1 --port 5184 --strictPort
DEMO_ORIGIN=http://127.0.0.1:5184 node tests/demo.browser.mjs
```

首次 Chrome 启动退出 **1**：受执行沙箱限制，在页面测试前 SIGABRT。经批准启动隔离的无头浏览器后继续复测。截图仅保留在系统临时目录，不随项目分发。

完整浏览器复测退出 **0**：13 个原页面、五店/月筛选、图表、商品 SVG 实际加载、搜索/生命周期、商品建计划、任务闭环、模拟 AI 建任务、6 个配置 tab、角色、同步/导入拒绝、主题切换、390px 手机、登录/退出入口、重载、13 个私有路由保护、遗留 token、空/失败目录均通过。业务 API 请求 **0**、跨源请求 **0**、页面异常 **0**。人工检查商品档案与手机页面截图，本地图形正确显示，未见页面横向溢出。

绝对 URL 与策略 payload 返工后再次从头运行完整浏览器流程：退出 **0**，上述全部检查仍通过，业务 API/跨源请求/页面异常仍均为 **0**。完成后停止本次验证启动的本地 Vite 服务。

## 后端回归

在 `backend/` 执行：

```sh
DB_ENGINE=sqlite DJANGO_DEBUG=1 PYTHONDONTWRITEBYTECODE=1 python -m pytest -p no:cacheprovider -q --tb=short
DB_ENGINE=sqlite DJANGO_DEBUG=1 PYTHONDONTWRITEBYTECODE=1 python manage.py check
DB_ENGINE=sqlite DJANGO_DEBUG=1 PYTHONDONTWRITEBYTECODE=1 python manage.py makemigrations --check --dry-run
```

| 轮次 | 命令 | 退出码 | 实际结果 |
| --- | --- | --- | --- |
| 1 | pytest | 1 | 75/81 通过；5 个测试暴露旧 dashboard 未定义变量，1 个历史 MCP 工具数量断言过期 |
| 2 | pytest | 0 | 修复 dashboard 后 81/81 通过；MCP 仍严格断言当前 3 个工具 |
| 3 | pytest | 0 | 补充网络禁止与连接安全测试后 **88/88** 通过 |
| 3 | Django check | 0 | No issues |
| 3 | migration drift | 0 | No changes detected |
| 4 | pytest（测试显示名通用化后） | 0 | **88/88** 再次通过 |

新增安全覆盖：无密码不创建管理员、弱密码拒绝、强密码创建但不打印、现有管理员不重置、普通用户不提权、空用户名拒绝、显式有效 Fernet 密钥、错误密钥拒绝解密、缺加密密钥 API 返回 400 且不遗留配置、可选连接默认关闭且无地址、私网 DNS 拒绝、生产模式拒绝弱签名密钥与通配主机。

## 初始化脚本

补充独立回归（主控新安装 smoke 发现问题后）：空数据库显式请求有效月份曾因读取空月份数组抛出 500。后端仅为最新月份判断增加空列表保护，未改变已有数据的统计口径。新增 `backend/apps/warehouse/tests/test_dashboard_empty.py` 覆盖空库显式月份 200/零统计、未指定月份的既有空响应，以及两种没有可见数据的权限范围（未分配店铺、仅分配无数据店铺），确认不可见店铺的月份、指标、异常不泄露，显式请求未授权店铺返回 403。未知利润仍保持 `null`。

在同一独立临时副本重跑全部后端测试：退出 **0**，**92/92** 通过。主控更新启动脚本的本机代理绕过逻辑后，根目录初始化/扫描器测试复跑仍 **5/5**、退出 **0**；干净发布树隐私扫描 **0 findings**、退出 **0**。新 Python 3.11 完整启动与 MCP 本地 stub 结果由主控另行记录，不混记为本轮独立执行。

根目录执行 `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_*.py'`：退出码 **0**，首次 **4/4** 通过；补充通用 live-token 前缀扫描自测后，最终 **5/5** 通过（隐私扫描器 3 条、初始化脚本 2 条，未跳过）。仅复制 `scripts/dev.py` 与 `.env.example` 到临时目录运行 `init`，验证不同安装的所有密钥/密码不同、Unix 文件权限 0600、输出不含秘密、第二次运行不覆盖、Fernet 实际加解密成功。未调用 npm、未安装依赖、未启动后端服务。

最终干净发布树再次执行 `python3 tests/privacy_audit.py`：退出码 **0**、**0 findings**。通用 live-token 检测使用规则与临时构造测试值，不保存原凭据、其可逆片段或私有品牌字典。

## 验证边界

未连接任何真实飞书/MCP/电商/AI 数据源，未使用原账户、生产数据库或真实密钥，未运行云端部署或上传代码。外部集成只能认定本地协议与安全边界回归通过，不能据此宣称真实服务端到端可用。容器构建、全新机器依赖安装和真实集成接入需在单独授权环境继续验收。
