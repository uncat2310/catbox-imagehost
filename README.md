# Catbox 图床

一个轻量的 [Catbox.moe](https://catbox.moe) 上传面板，使用 FastAPI 提供后端接口，前端为原生 HTML/CSS/JavaScript。适合部署在自己的服务器上，通过浏览器完成批量上传、图片处理、历史管理和配置备份。

## 功能特性

- 批量上传图片、视频、音频等文件到 Catbox.moe
- 前端和后端均支持受控并发上传，默认 3 个并发，最高 6 个
- 支持拖拽上传、文件选择上传、剪贴板粘贴上传
- 支持上传前将静态图片转换为 WebP 并可调整压缩质量
- Catbox `userhash` 保存在浏览器本地，不写入服务端配置
- 本地上传历史展示、单条复制、批量复制、批量清除
- 配置与历史记录导出/导入，支持浏览器端 AES-GCM 加密备份
- 明暗主题切换，支持跟随系统主题
- 毛玻璃 UI、移动端底部抽屉、桌面端浮层历史记录
- 提供 `/api/health` 健康检查接口

## 项目结构

```
catbox-imagehost/
├── backend/
│   ├── main.py              # FastAPI 入口与 API 路由
│   ├── catbox_client.py     # Catbox API 客户端
│   ├── config.py            # JSON 配置与历史记录持久化
│   ├── image_processor.py   # Pillow 图片处理
│   └── requirements.txt
├── config/
│   └── settings.example.json
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── app.js
├── Dockerfile
├── docker-compose.yml
├── docker-entrypoint.sh
└── run.sh
```

## 快速开始

### Docker Compose 部署（推荐）

**1. 创建项目目录并进入**

```bash
mkdir catbox-imagehost && cd catbox-imagehost
```

**2. 创建 `docker-compose.yml`**

```yaml
services:
  catbox-imagehost:
    image: honkai/catbox-imagehost:latest
    container_name: catbox-imagehost
    restart: unless-stopped
    ports:
      - "7800:7800"
    volumes:
      - ./catbox-imagehost:/app/config
```

**3. 创建配置目录并启动**

```bash
mkdir -p catbox-imagehost
docker compose up -d
```

> `settings.json` 可选，缺失时自动使用内置默认值（WebP 关闭、质量 80、并发 3、主题跟随系统）。如需自定义，下载 [settings.example.json](https://raw.githubusercontent.com/uncat2310/catbox-imagehost/main/config/settings.example.json) 放入 `catbox-imagehost/` 目录即可。

**4. 访问**

打开浏览器访问 `http://服务器IP:7800/`。

### 源码部署

```bash
git clone https://github.com/uncat2310/catbox-imagehost.git
cd catbox-imagehost
python3.11 -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt
cp config/settings.example.json config/settings.json
./run.sh
```

默认监听 `0.0.0.0:7800`，可通过 `PORT=8088 ./run.sh` 修改端口。

## 使用方法

1. 打开页面，点击右上角 **设置** 按钮
2. 在 [Catbox 管理页](https://catbox.moe/user/manage.php) 获取 `userhash`，填入设置面板并保存
3. 将文件拖入上传区域，或点击上传区域选择文件
4. 如需提速，可在设置面板中调整上传并发。推荐 `2-4`，网络较好可提高到 `6`
5. 上传完成后可复制直链或 Markdown
6. 点击 **历史** 按钮查看本地上传记录，支持批量复制和清除
7. 在设置面板的 **数据管理** 中导出或恢复备份

## 配置说明

服务端配置位于 `config/settings.json`，该文件不会被提交到 Git 仓库。示例：

```json
{
  "webp_enabled": true,
  "webp_quality": 80,
  "upload_concurrency": 3,
  "theme": "auto",
  "history": []
}
```

| 字段 | 说明 | 范围 |
|------|------|------|
| `webp_enabled` | 是否默认启用 WebP 转换 | `true` / `false` |
| `webp_quality` | WebP 压缩质量 | `1-100` |
| `upload_concurrency` | 上传并发数 | `1-6` |
| `theme` | 主题 | `auto` / `light` / `dark` |
| `history` | 服务端保存的上传历史 | 自动维护 |

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 返回前端页面 |
| GET | `/api/health` | 健康检查，返回版本号 |
| GET | `/api/config` | 获取服务端配置 |
| POST | `/api/config` | 更新服务端配置 |
| POST | `/api/upload` | 上传文件到 Catbox |
| GET | `/api/history` | 获取上传历史 |
| POST | `/api/history/delete` | 删除本地历史记录 |
| GET | `/api/export` | 导出配置与历史 |
| POST | `/api/import` | 导入配置与历史 |

## 反向代理

可以使用 Caddy、Nginx 或 Cloudflare Tunnel 暴露服务。示例 Caddy 配置：

```caddyfile
catbox.example.com {
    reverse_proxy 127.0.0.1:7800
}
```

## 安全说明

- 不要把 GitHub token、Catbox `userhash`、`.env` 或 `config/settings.json` 提交到仓库
- `userhash` 默认只存在浏览器 `localStorage` 中，不上传服务端
- 导出的加密备份由浏览器端 Web Crypto API 完成加密，服务端不保存密码
- 上传文件会被发送到 Catbox.moe，请确认文件内容适合公开托管

## 开发检查

```bash
node --check frontend/app.js
venv/bin/python -m compileall backend
curl http://127.0.0.1:7800/api/health
```

## 许可证

MIT License
