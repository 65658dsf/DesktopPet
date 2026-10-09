# 秦彻 · 桌面宠物（Desktop Pet · QinChe）

《恋与深空》秦彻 Q 版桌面宠物程序：透明置顶桌宠窗口 + 交互反馈 + AI 对话 + 设置面板，
**核心功能完全离线运行**，AI 交互同时支持任意 OpenAI 兼容接口（含 Ollama 等本地模型）。

---

## 1. 交付物

| 路径 | 说明 |
| --- | --- |
| `app/` | 桌宠程序源码（Python + PySide6） |
| `pets/qinche-q/` | 秦彻宠物包（技能契约格式，实际加载、渲染及图集完整性检查通过） |
| `dist/QinChePet/QinChePet.exe` | 打包后的可执行程序（由 `build_exe.ps1` 生成） |
| `tools/gen_pet/` | 动作生成提示词、逐帧镜像、图集装配和实际播放预览工具 |
| `tools/verify_app.py`、`tools/verify_ai.py`、`tools/mock_openai.py` | 开发期自动化验证脚本 |
| `run.ps1` | 源码模式启动 |
| `build_exe.ps1` | 重新打包 exe |

## 2. 宠物包（技能契约）

项目技能已安装于 `.agents/skills/desktop-pet/`，来源：[Desktop Pet Launcher skill](https://github.com/wangling-miao/Desktop-Pet-Launcher-skill)。

1.3 版所有九个状态均采用独立绘制的动作帧，并重新装配完整 1x 和 2x 图集。
两档图集均来自原生动作素材的降采样；旧的程序化动作图集已替换。
本次使用应用自身的 Qt 渲染与集成测试验证包；技能自带 Python 校验脚本仍须在 WSL 中使用 `uv`：

```powershell
# 在配置好 uv 的 WSL 发行版中校验宠物包
wsl uv run --with pillow --with pydantic /mnt/d/Coding/LemonDev/DesktopPet/.agents/skills/desktop-pet/scripts/validate_pet_package.py /mnt/d/Coding/LemonDev/DesktopPet/pets/qinche-q
```

| 项 | 值 |
| --- | --- |
| 图集几何 | 8 列 × 9 行，单元格 `192×208`；1x `1536×1872` / 2x `3072×3744` |
| 状态行 | `idle(6)`、`running-right(8)`、`running-left(8)`、`waving(4)`、`jumping(5)`、`failed(8)`、`waiting(6)`、`running(6)`、`review(6)` |
| 未使用单元格 | 两档图集逐格回读，全部保持完全透明 |
| 分辨率策略 | 程序按 `max(宽/192, 高/208) × 屏幕缩放` 选择最小可用档位（遵循 launcher contract） |

动作通过内置 imagegen 参照同一角色独立绘制。`animationClips` 加载原生透明 PNG、逐帧时长、
明确的眨眼帧和跳跃位移；不支持扩展的外部启动器也能从新图集中播放完整九状态。
左移动是逐帧镜像右移动，保持步态顺序。原有托腮保留为 `chin-rest` 自动小动作，
戳一戳保留独立 `poke`；`review` 现在对应读书、思考和翻页。
提示词与验收记录见 `tools/gen_pet/all-states-prompts.md`、`review-prompt.md`、`all-states-qa.md`。

## 3. 快速开始

**方式 A：直接运行打包好的程序**

```
dist\QinChePet\QinChePet.exe
```

程序已运行时，再次启动 exe 会唤醒已有的对话窗口；也可运行
`dist\QinChePet\QinChePet.exe --chat`，在首次启动时直接打开对话。

**方式 B：源码运行**

在项目目录执行（首次运行先创建环境并安装依赖）：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r app\requirements.txt
powershell -ExecutionPolicy Bypass -File run.ps1
# 或： .\.venv\Scripts\python.exe app\main.py
```

依赖为 PySide6 / requests / Pillow。`run.ps1` 和 `build_exe.ps1` 优先使用项目的 `.venv`；重新打包前用 `.\.venv\Scripts\python.exe -m pip install pyinstaller` 安装打包工具。

程序启动后：桌宠出现在屏幕右下角，托盘出现"秦彻"图标。

## 4. 交互

| 操作 | 行为 |
| --- | --- |
| 单击桌宠 | 专属戳一戳反应（偏头眯眼 → 抬手眨眼 → 恢复待机）+ 气泡台词 |
| 连续戳桌宠 | 调侃台词；当前动作完整播完，最多再接一次，不会卡在第一帧 |
| 双击桌宠 | 打开 AI 对话窗口 |
| 对话最小化后再次打开 | 还原并激活已有对话，保留聊天内容 |
| 拖拽桌宠 | 移动窗口，并按拖拽方向切换 `running-left/right` 动画 |
| 右键桌宠 | 菜单：对话 / 设置 / 锁定 / 忽略鼠标 / 置顶 / 隐藏 / 退出 |
| 托盘双击 | 显示 / 隐藏桌宠 |
| 托盘单击 | 打开对话 |
| 托盘菜单 | 显示·隐藏 / 打开对话 / 设置 / 锁定·解锁 / 刷新宠物包 / 退出 |

对话窗口支持响应式排版：消息按窗口宽度自动换行，完整保留回复和段落；窄窗口下顶部操作和快捷提示会换行。
长输入会自动增高。流式回复期间向上翻阅历史不会被拉回底部，点击「回到最新」可继续跟随回复。

待机时约每 3～6 秒自然眨眼，并有幅度很小的呼吸起伏。自动模式约每 14～30 秒
轮换托腮、查看、等待或挥手，尽量避免连续重复。手动选择「待机 idle」只播放待机；
关闭「待机随机小动作」也可停止自动插入动作。
开启「减弱动效」会停在安静姿势，同时关闭呼吸。拖拽和回复状态优先，不会被待机动作打断。

动画验证：`python tools/verify_animation.py`、`python tools/verify_expression_assets.py`。
实际渲染预览：`pets/qinche-q/animations/preview.gif`；预览连续展示两段动作，运行时托腮间隔更长。

帧切换以 16ms 精确定时器和实际经过时间进行短过渡，保持透明边缘稳定；
播放使用绝对截止时间，避免绘制耗时逐帧累积。眨眼过渡更短，托腮动作和切换状态稍长。
`python tools/verify_frame_transition.py` 检查透明度、过渡中断、DPR 和缓存预算；
`python tools/preview_animation.py` 导出程序实际混合帧，再用 `tools/gen_pet/preview_expressions.cjs` 合成预览。
两条预览命令均加 `--poke` 可生成 `animations/poke-preview.gif`；加 `--all-states` 可生成
`animations/all-states-preview.gif` 与 `build/qa-animation/all-states/index.html`，后者逐个循环完整动作。
`tools/verify_poke.py` 与 `tools/verify_pet_input.py` 分别检查戳一戳行为与单双击、拖动输入。
`tools/verify_all_states.py` 验证九状态及真实设置预览。图片缓存采用 64 MiB LRU 上限，优先预热各动作首帧。
AI 等待首字时播放 `waiting`，开始流式输出后播放 `running`，后续内容不重启动画。

## 5. AI 交互

设置 → **AI 接入**：

- **本地离线模式（默认）**：使用内置的秦彻语气回复引擎，问时间/日期、切换显示、清空对话等指令均可直接使用，
  **不发起任何网络请求**——满足"完全离线运行"。
- **在线 AI**：填任意 OpenAI 兼容接口即可，内置预设：

| 预设 | 接口地址 | 模型示例 |
| --- | --- | --- |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| Moonshot | `https://api.moonshot.cn/v1` | `moonshot-v1-8k` |
| Ollama 本地 | `http://localhost:11434/v1` | `qwen2.5:7b`（**完全离线的本地大模型**） |

支持流式输出（逐字显示）、温度/最大 tokens 调节、人设 system prompt 编辑、**测试连接**按钮。
对话历史保存在配置目录，可一键清空。

> 离线兜底：即使未配置任何接口，程序的所有功能（动画、交互、托盘、设置、内置回复）都能正常工作；
> 连上本地大模型（Ollama）即可在无公网环境下获得完整 AI 对话。

## 6. 数据与配置

| 文件 | 位置 |
| --- | --- |
| 设置 | `%APPDATA%\top.nether.pet\settings.json`（契约同名字段 + `ai` 扩展段） |
| 宠物包扫描目录 | `%USERPROFILE%\.codex\pets\`、`%APPDATA%\top.nether.pet\pets\`、程序目录 `pets\`、自定义 `petFolders` |
| 便携模式 | 在 exe 同目录放一个空的 `portable.txt`，配置改存到程序目录 |

设置面板还可调整：宠物包切换、显示尺寸（60%~400%）、像素化渲染、动画速度、减弱动效、置顶、
拖拽开关、锁定位置、忽略鼠标（点击穿透）、手动状态指定、开机自启（注册表 `HKCU\...\Run`）、回到右下角等。

## 7. 已知限制

1. **外部启动器**：可读取完整新九状态图集；独立托腮、戳一戳、随机停留时长属于本程序的 `animationClips` 扩展。
2. **素材分辨率**：保留各 PNG 的生成原生分辨率，所有核心帧都足够降采样到 2x。
   未把 1x 放大为 4x；当前包不声明或附带旧 4x 图集。技能自带 Python 校验脚本仍按上文在 WSL `uv` 中运行。
3. **托盘图标**：由宠物包头部裁切生成（`app/assets/qinche.ico`）。

## 8. 声明

秦彻 Q 版形象为《恋与深空》角色的**同人二次创作**，仅限个人、非商业用途的欣赏与本地使用；
角色及相关知识产权归权利方所有。
