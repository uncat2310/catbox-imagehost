# 个人 Catbox 图床

单人自用的 Catbox 上传面板。Userhash 在部署时配置，浏览器不再接收、填写、保存或导出它。页面、静态文件和管理 API 都需要访问密码；仅 `/api/health` 公开。

**面板私有不代表文件私有：上传后的文件由 Catbox 公开托管，持有文件直链的人仍可访问。**

## Docker Compose 部署

```sh
git clone https://github.com/uncat2310/catbox-imagehost.git
cd catbox-imagehost
cp .env.example .env
chmod 600 .env
# 在服务器编辑 .env，填入 CATBOX_USERHASH 和独立的 APP_PASSWORD
docker compose up -d --build
```

必填环境变量：

| 变量 | 用途 |
| --- | --- |
| `CATBOX_USERHASH` | 你自己的 Catbox Userhash，仅供服务端向 Catbox 认证 |
| `APP_PASSWORD` | 登录面板的独立密码，至少 8 位，推荐随机生成 32 位以上 |

可选：`MAX_FILE_SIZE_MB`（1–200，默认 200）、`CONFIG_DIR`（默认项目的 config 目录）、`PORT`（默认 7800）。不要把真实凭证写进 Compose 文件、构建参数、Git 或聊天记录。环境变量对有权限管理宿主机或容器的人可见。

浏览器打开 `http://localhost:7800`，在原生登录提示中输入用户名 **admin** 和 APP_PASSWORD。浏览器会在当前会话中缓存 HTTP Basic 凭证；公共设备上请使用独立的隐私窗口并在用完后关闭。修改 APP_PASSWORD 并重启可使旧凭证失效。

默认只发布到 `127.0.0.1:7800`。远程访问使用 HTTPS 反向代理或 Cloudflare Tunnel，不要直接把 7800 发布到公网。示例 Caddy：

```caddy
catbox.example.com {
    request_body {
        max_size 201MB
    }
    reverse_proxy 127.0.0.1:7800
}
```

反向代理必须保留 Host、Origin 和 Authorization，不要缓存页面或 API。Cloudflare 等入口可能另有更低的请求大小限制，以实际入口为准。跨站修改会被拒绝；没有开放 CORS。

## 源码运行

Python 3.11+：

```sh
python3 -m venv venv
venv/bin/pip install -r backend/requirements.lock
cp .env.example .env
chmod 600 .env
# 编辑 .env
./run.sh
```

Windows 可使用 `venv\Scripts\python -m uvicorn backend.main:app --host 127.0.0.1 --port 7800 --workers 1 --env-file .env`。

保持 **1 个 worker、1 个实例**：进程内的全局上传上限为设置中的并发数，最多 6。多进程/多副本部署必须另加共享队列和统一配额，不能直接扩容绕过上限。达到并发上限时返回 503，不无限排队。批量请求中的文件按顺序上传；前端可并发发送单文件请求。

## 数据、升级与备份

- 设置和最多 500 条历史保存在 `config/settings.db`（SQLite 事务）。文件操作在线程中执行，上传结果批量保存。
- 首次启动自动读取原来的 `config/settings.json`，迁移合法的设置和 Catbox 历史；不会修改旧文件。重复或不安全的历史地址会被过滤。
- 旧 JSON 的 Userhash 不会自动作为新版运行凭证。升级时须明确设置 CATBOX_USERHASH，并将包含凭证的旧文件移到受保护的备份目录。
- 升级前停止写入并备份 config 目录、旧源码版本和服务配置。恢复旧版时同时恢复旧配置，避免丢失升级后新增的数据。
- 设置与历史由服务端统一保存，其他设备刷新或重新打开面板即可读取。设置面板只保留账号绑定状态、图片处理与上传速度。
- v4.1 已移除浏览器备份/恢复、加密代码与 `/api/export`、`/api/import` 接口；日常使用不需要手动同步。
- 浏览器中旧的 catbox-userhash 本地存储会在打开新版页面时清理。
- 服务器备份由运维执行：停止服务后备份整个 config 目录，或使用 SQLite backup API 创建一致性快照；环境文件独立备份并限制权限。恢复时停止服务，再恢复数据库和所需环境配置。
- 清除历史只删除面板记录，不删除 Catbox 上的文件。

## 上传与图片处理

单文件与单次请求的文件总大小默认均为 200MiB，单次最多 20 个文件。接收请求时按实际字节数限制，文件使用受控临时文件向上游发送，不先将大文件完整读入内存。

图片最多 2000 万像素；20MiB 以内的静态图片可在服务端压缩或转 WebP。超过转码大小的图片保留原文件并返回提示。关闭 WebP 时保留原格式，处理后更大的同格式文件保留原文件。动图保留原文件。处理失败的回退会明确提示，超出像素上限则拒绝。取消上传会停止浏览器当前请求和后续任务；已被 Catbox 接收的文件可能仍然存在。

## 开发验证

```sh
venv/bin/pip install -r requirements-dev.txt
venv/bin/python -m unittest discover -s tests -v
node --check frontend/app.js
venv/bin/python scripts/check_secrets.py --history
```

测试使用临时数据目录和模拟 Catbox，不使用实际凭证或真实上传。依赖完整锁定在 backend/requirements.lock；CI 执行历史凭证检查、回归测试、依赖审计、实际容器启动及重启验证后构建多架构镜像。更新依赖时同时更新直接依赖清单和锁文件，并通过测试及依赖审计。

合并到 main 后自动发布 GHCR 的 latest、main 和完整提交 SHA 标签；版本标签发布对应版本镜像。PR 只检查和构建，不登录或推送镜像。Actions 不连接 VPS、不接收运行凭证，也不自动部署服务器。按需更新时选择通过检查的版本或不可变镜像 digest，并继续挂载原数据目录。

本项目不提供多用户注册、访客上传或客户端指定 Catbox 账号功能。
