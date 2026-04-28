# Browser Sandbox — 有头浏览器自动化工具箱

基于 CDP（Chrome DevTools Protocol）驱动**真实有头 Chrome** 的自动化工具集。运行在 Xvfb 虚拟显示器中，专门用于那些会检测无头浏览器、或会触发"打开 App"弹窗的网站。

## 快速开始

```bash
# 安装依赖
sudo apt-get install -y xvfb google-chrome-stable python3-pip
pip3 install websocket-client requests

# 启动 Chrome 并打开目标网站
python3 scripts/browser.py start "https://www.xiaohongshu.com"

# 等待页面加载
sleep 3

# 截图查看当前状态
python3 scripts/interact.py --screenshot /tmp/xhs.png

# 完成后停止浏览器
python3 scripts/browser.py stop
```

## 项目结构

| 脚本 | 作用 |
|------|------|
| `scripts/browser.py` | 启动 / 停止 Chrome + Xvfb |
| `scripts/interact.py` | 元素查找、点击、输入、截图 |
| `scripts/interact_frame.py` | 在 `<iframe>` 内执行操作 |
| `scripts/protocol_guard.js` | 注入脚本，拦截外部 URI 协议唤起 |
| `scenarios/*.md` | 各平台经验文档与避坑指南 |

## 为什么不用 Playwright / Selenium？

- **无头检测** — 小红书、抖音等平台会在 `navigator.webdriver` 为 true 时返回不同页面或触发验证码。真实 Chrome 更难被检测。
- **App 唤起弹窗** — 这些网站会尝试通过 `weixin://`、`taobao://` 等自定义协议打开 native App。`protocol_guard.js` 在页面加载前注入，拦截这些请求，避免弹窗打断自动化流程。
- **可视化验证** — 浏览器是真实运行的，每一步都可以截图确认，肉眼可见。

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `CDP_PORT` | `18800` | Chrome 远程调试端口 |
| `DISPLAY_NUM` | `99` | Xvfb 虚拟显示编号 |
| `SCREEN_WIDTH` | `1920` | 虚拟屏幕宽度 |
| `SCREEN_HEIGHT` | `1080` | 虚拟屏幕高度 |
| `CHROME_PATH` | 自动探测 | Chrome 或 Chromium 可执行文件路径 |

## 常见操作

### 截图

```bash
python3 scripts/interact.py --screenshot /tmp/page.png
```

### 查找并点击元素

```bash
python3 scripts/interact.py --find "登录"
python3 scripts/interact.py --click-text "登录" --js-click
```

### 在已聚焦的输入框中输入文字

```bash
python3 scripts/interact.py --click 960 540
python3 scripts/interact.py --type "hello world"
```

### 查看 iframe 内容

```bash
python3 scripts/interact_frame.py --list-frames
python3 scripts/interact_frame.py --iframe "login" --find-elements
python3 scripts/interact_frame.py --iframe "login" --click-text "提交"
```

## 架构

```
┌─────────────────┐     WebSocket      ┌──────────────┐
│  interact.py    │ ◄────────────────► │ Chrome + CDP │
│  interact_frame │                    │  (port 18800)│
└─────────────────┘                    └──────────────┘
       ▲                                      │
       │      HTTP (json/list)                │
       └──────────────────────────────────────┘

Chrome 运行在 Xvfb (:99) 中，无需物理显示器。
```

## 协议拦截原理

`protocol_guard.js` 通过 Chrome 的 `--inject-js` 参数在页面加载前注入，拦截以下外部协议：

- `weixin://` / `wechat://`
- `taobao://`
- `alipay://`
- `jd://` / `tmall://`
- `meituan://` / `dianping://`
- `openapp://`

拦截手段包括：
- `window.location` Proxy / descriptor 劫持
- `window.open` 包装
- `history.pushState` / `replaceState` 拦截
- `<a>` 标签点击事件捕获
- `MutationObserver` 动态清理注入的恶意锚点

## 适用平台

| 平台 | 状态 | 注意事项 |
|------|------|---------|
| 小红书 (xiaohongshu.com) | 已验证 | 必须先勾选协议复选框再获取验证码 |
| 抖音 (douyin.com) | 已验证 | Canvas 渲染为主，建议用截图；登录需"诱饵标签页"策略 |
| 知乎 (zhihu.com) | 已验证 | 标准 DOM，浏览一段时间后可能弹出登录墙 |
| B站 (bilibili.com) | 已验证 | 登录按钮建议用 `--js-click` |

详细操作经验见 `scenarios/` 目录下的各平台文档。

## License

MIT
