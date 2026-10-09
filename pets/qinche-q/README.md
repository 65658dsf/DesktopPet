# 秦彻 · Q版桌面宠物

1.3.0：所有九个标准动作均有独立绘制的姿势，兼容 Desktop Pet Launcher 的 8×9 图集格式。

| 状态 | 帧数 | 动作 |
| --- | ---: | --- |
| idle | 6 | 呼吸、自然眨眼 |
| running-right | 8 | 朝右摆臂迈步、衣摆跟随 |
| running-left | 8 | 逐帧镜像朝左移动，顺序不变 |
| waving | 4 | 抬手挥动、眨眼、放下 |
| jumping | 5 | 蓄力、起跳、最高点、落地、恢复 |
| failed | 8 | 惊讶、扶额、无奈、恢复 |
| waiting | 6 | 抱臂、轻点袖子、左右看、眨眼 |
| running | 6 | 低头书写、停笔思考、继续记录 |
| review | 6 | 读书、托下巴思考、翻页 |

原有 chin-rest 托腮与 poke 戳一戳仍是独立扩展动作。自动模式会轮换安静的小动作；
手动待机只眨眼，不被随机动作打断。

## 文件与分辨率

- pet.json：状态时长、源图、显式取帧、眨眼帧及逻辑位移。
- spritesheet.webp：完整 1x 兼容图集，1536×1872。
- spritesheet@2x.webp：完整 2x 图集，3072×3744。
- animations/*.png：内置 imagegen 绘制的透明原生素材，未上采样。
- animations/all-states-preview.gif：程序实际渲染的九动作总览。
- animations/preview.gif：眨眼与原有托腮预览。
- animations/poke-preview.gif：戳一戳预览。
- preview.png / preview.gif：状态总览静态图和动图。

两档兼容图集都从原生动作帧导出。所有核心源帧均足够生成真实 2x，不附带放大的 4x。
无效扩展 clip 会回退到标准图集；无效位移不会静默裁切角色。未使用单元格完全透明。

## 安装与验证

复制本目录到 %USERPROFILE%\.codex\pets\，或在启动器设置中添加自定义宠物目录。
本项目打包脚本会将该目录完整放入 Windows 可执行程序。

项目验证：tools/verify_all_states.py、tools/verify_expression_assets.py。
生成与装配记录：tools/gen_pet/all-states-prompts.md、review-prompt.md、all-states-qa.md。
本程序通过 animationClips 使用原生帧和自然停留时长；外部启动器若不支持扩展，仍可播放全部九个标准动作。

## 声明

《恋与深空》秦彻的同人二次创作，仅供个人欣赏，角色版权归原权利方所有。
