# 本地使用教程

## 1. 准备与演示

安装 Node.js 22+（自带npm）和Python 3.11+。克隆仓库后在项目根目录运行：

```bash
python3 scripts/dev.py demo
```

Windows 可使用 `py -3.11` 替代 `python3`。打开终端输出的 `/demo` 地址，默认5173。五家店铺、60款商品和图表都是虚构数据；不需要管理员账户或外部服务。商品图片随源码存放，不从真实店铺加载。

脚本默认执行 `npm ci` 保证与锁文件一致。依赖已安装且不需重装时可加 `--no-install`。端口冲突时用 `--frontend-port 5183`，不要关闭其他项目的进程。

## 2. 完整本地系统

退出上一个演示进程后运行：

```bash
python3 scripts/dev.py full
```

脚本会：

1. 安装前端依赖，在本项目创建Python虚拟环境并安装 `backend/requirements.txt`。
2. 首次创建私有 `.env`，随机生成Django签名密钥、独立集成加密密钥、管理员和数据库密码；不覆盖已存在的文件。
3. 按本地配置迁移数据库并创建管理员。默认SQLite，数据库只在本地；没有导入任何原系统数据库。
4. 启动Django `127.0.0.1:8000` 与Vite `127.0.0.1:5173`。前端 `/api` 转发到本地后端。

打开 `/login`，在本机编辑器里查看 `.env` 中的用户名和管理员密码；不要将整个文件发送给智能体或上传Git。若手工复制 `.env.example` 后留空密钥，脚本不会覆盖你的文件；请补齐各随机密钥，或先把空文件移走再运行 `init`。生成新的加密密钥会导致已有密文不可读，不要在有数据的系统中随意轮换。

后端模式不会自动绑定公网，不会访问任何数据源，直到你登录并显式配置和调用接入。

```bash
# 只初始化配置，不运行服务
python3 scripts/dev.py init
# 自选两个不冲突的本地端口
python3 scripts/dev.py full --frontend-port 5183 --backend-port 8010
```

停止：在运行脚本的终端按Ctrl+C，脚本停止它自己启动的进程，不删除数据库与配置。再次启动保留本地业务数据；演示操作则始终刷新重置。

## 3. 接自己的 MCP

先使用完整模式、以本地管理员登录，进入配置中心，按[MCP教程](MCP.md)填写自己的端点和授权。不要在 `/demo` 中测试真实接入——演示页面有意禁止访问外部服务。

## 4. Docker + MySQL（可选）

需要已安装并启动Docker Compose。首次运行：

```bash
python3 scripts/dev.py init
docker compose up --build -d
```

打开 <http://127.0.0.1:8080/demo> 或 `/login`。Compose显式用MySQL；服务在本机8080，不映射MySQL/后端到公网。首次需下载镜像/依赖，持续等数据库健康。

停止使用 `docker compose down`；不要加 `-v`，否则会删除数据卷。本地SQLite与Docker MySQL是独立数据库，不自动迁移数据。正式外网部署必须自行配置域名、TLS、非DEBUG、安全hosts、备份和安全审查，不直接公开开发服务器。

## 5. 验证与排障

- 5173被占用：修改前端端口；8000被占用：同时修改后端端口，脚本自动更新API代理。
- Python或Node版本不符：换到所要求版本后重试，不通过删改业务代码绕过。
- MCP返回401/403：检查自己服务的授权与企业范围，不能改后端权限为匿名来绕过。
- 没有数据：演示和真实业务分开；真实看板需要成功同步，接入前为空是正常状态。
- MCP能列工具但不能同步：检查工具名称与返回协议，见接入说明，不是所有MCP提供同一格式。
- 商品图片：演示只认固定本地资源路径；真实商品图片另按用户授权来源处理。

前端构建/回归：

```bash
cd frontend
npm ci
npm run build
node --test tests/demo.test.mjs tests/demo-original.test.mjs
```

后端测试建议使用独立临时源码副本，不含 `.env`、数据库和上传文件。用已安装依赖的Python运行 `python -m pytest -p no:cacheprovider`，设置 `DJANGO_DEBUG=1`、`DB_ENGINE=sqlite`、虚构测试用 `DJANGO_SECRET_KEY` 及有效的临时 `INTEGRATION_ENCRYPTION_KEY`（可用Python标准库 `base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()`生成）。不要把本地管理员或集成凭据提供给测试。测试使用临时数据库，不连接实际MCP。

依赖版本沿用原型，为复现而固定；公开或生产使用前需独立评估依赖漏洞和维护状态。本文不承诺Windows/Docker在所有环境均已实机验证，以验证记录为准。
