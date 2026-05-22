# Catbox 图床

一个轻量的 Catbox.moe 上传面板，使用 FastAPI 提供后端接口，前端为原生 HTML/CSS/JavaScript。适合部署在自己的服务器上，通过浏览器完成批量上传、图片处理、历史管理和配置备份。

## 功能特性

- 批量上传图片、视频、音频等文件到 Catbox.moe。
- 支持拖拽上传、文件选择上传、剪贴板粘贴上传。
- 支持上传前将静态图片转换为 WebP，并可调整压缩质量。
- Catbox `userhash` 保存在浏览器本地，不会写入服务端配置。
- 本地上传历史展示、单条复制、批量复制、批量清除。
- 配置与历史记录导出/导入，支持浏览器端 AES-GCM 加密备份。
- 明暗主题切换，支持跟随系统主题。
- 毛玻璃 UI、移动端底部抽屉、桌面端浮层历史记录。
- 提供 `/api/health` 健康检查接口。

## 项目结构

```text
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
└── run.sh
```

## 环境要求

- Python 3.11 或更新版本
- 可以访问 `https://catbox.moe`
- 一个 Catbox 账号和 `userhash`

## 安装与启动

```bash
git clone https://github.com/uncat2310/catbox-imagehost.git
cd catbox-imagehost
python3.11 -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt
cp config/settings.example.json config/settings.json
./run.sh
```

默认监听 `0.0.0.0:7800`。如需修改端口：

```bash
PORT=8088 ./run.sh
```

启动后访问：

```text
http://服务器IP:7800/
```

## 使用方法

1. 打开页面，点击右上角设置按钮。
2. 在 Catbox 管理页获取 `userhash`，填入设置面板并保存。
3. 将文件拖入上传区域，或点击上传区域选择文件。
4. 上传完成后可复制直链或 Markdown。
5. 点击历史按钮查看本地上传记录，支持批量复制和清除。
6. 在设置面板的数据管理中导出或恢复备份。

## 配置说明

服务端配置位于 `config/settings.json`，该文件不会提交到 Git 仓库。示例：

```json
{
  "webp_enabled": true,
  "webp_quality": 80,
  "theme": "auto",
  "history": []
}
```

字段说明：

- `webp_enabled`: 是否默认启用 WebP 转换。
- `webp_quality`: WebP 压缩质量，范围 `1-100`。
- `theme`: `auto`、`light` 或 `dark`。
- `history`: 服务端保存的上传历史。

## API

- `GET /`: 返回前端页面。
- `GET /api/health`: 健康检查，返回版本号。
- `GET /api/config`: 获取服务端配置。
- `POST /api/config`: 更新服务端配置。
- `POST /api/upload`: 上传文件到 Catbox。
- `GET /api/history`: 获取上传历史。
- `POST /api/history/delete`: 删除本地历史记录。
- `GET /api/export`: 导出配置与历史。
- `POST /api/import`: 导入配置与历史。

## 反向代理

可以使用 Caddy、Nginx 或 Cloudflare Tunnel 暴露服务。示例 Caddy 配置：

```caddyfile
catbox.example.com {
    reverse_proxy 127.0.0.1:7800
}
```

## 安全说明

- 不要把 GitHub token、Catbox `userhash`、`.env` 或 `config/settings.json` 提交到仓库。
- `userhash` 默认只存在浏览器 `localStorage` 中。
- 导出的加密备份由浏览器端 Web Crypto API 完成加密，服务端不保存密码。
- 上传文件会被发送到 Catbox.moe，请确认文件内容适合公开托管。

## 开发检查

```bash
node --check frontend/app.js
venv/bin/python -m compileall backend
curl http://127.0.0.1:7800/api/health
```

## 许可证

MIT License
