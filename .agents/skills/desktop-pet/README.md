# Desktop Pet Skill

`desktop-pet` 是给 Codex 使用的桌宠制作与校验 skill，目标是为 **Desktop Pet Launcher** 生成、修复、验证、导入和打包高清宠物包。

## 适用场景

当用户要求以下任务时使用本 skill：

- 创建 Desktop Pet Launcher 可加载的桌宠包。
- 校验或修复 `pet.json`、`spritesheet.webp`、`spritesheet@4x.webp`。
- 将旧 `hatch-pet` 包升级或包装为 launcher 兼容格式。
- 生成高清 4x master，并导出 2x/1x 运行和兼容资源。
- 把宠物包安装到 `~/.codex/pets` 或 launcher 自定义宠物目录。
- 准备投稿到 `awesome-desktop-pets` 桌宠图鉴的包和 PR。

## 与 hatch-pet 的关系

本 skill 保留 `hatch-pet` 的核心动画契约：

- 8 列 x 9 行 atlas。
- 9 个状态：`idle`、`running-right`、`running-left`、`waving`、`jumping`、`failed`、`waiting`、`running`、`review`。
- 每行帧数、透明 unused cell、视觉 QA、状态语义与身份一致性规则。

不同点是本 skill 面向 Desktop Pet Launcher：

- 新包默认要求 4x master：`spritesheet@4x.webp`。
- 必须保留 1x 兼容版：`spritesheet.webp`。
- 可选推荐 2x：`spritesheet@2x.webp`。
- `pet.json` 扩展 `spritesheets`、`cellSize`、`sourceScale`、`pixelated`。
- 适配 launcher 的自定义扫描目录 `petFolders`。

为了避免每次触发 skill 时加载过长上下文，`hatch-pet` 的关键生成与 QA 规则被整理到 `references/hatch-pet-workflow.md`，不是整篇原样复制。

## 安装到 Codex

将本目录复制到 Codex skills 目录：

```powershell
Copy-Item -Recurse . "$env:USERPROFILE\.codex\skills\desktop-pet"
```

目录结构：

```text
desktop-pet/
├─ SKILL.md
├─ agents/openai.yaml
├─ references/
│  ├─ hatch-pet-workflow.md
│  ├─ gallery-contract.md
│  ├─ launcher-contract.md
│  └─ pet-package-contract.md
└─ scripts/
   ├─ package_pet.py
   └─ validate_pet_package.py
```

## 宠物包格式

最小兼容格式：

```text
<pet-id>/
├─ pet.json
└─ spritesheet.webp
```

高清推荐格式：

```text
<pet-id>/
├─ pet.json
├─ spritesheet.webp
├─ spritesheet@2x.webp
└─ spritesheet@4x.webp
```

`pet.json`：

```json
{
  "id": "my-pet",
  "displayName": "My Pet",
  "description": "A short pet description.",
  "spritesheetPath": "spritesheet.webp",
  "spritesheets": {
    "1x": "spritesheet.webp",
    "2x": "spritesheet@2x.webp",
    "4x": "spritesheet@4x.webp"
  },
  "cellSize": {
    "width": 192,
    "height": 208
  },
  "sourceScale": 4,
  "pixelated": false
}
```

## 脚本运行要求

Windows上，Python 辅助脚本固定使用 WSL `uv`：

```bash
wsl uv run --with pillow --with pydantic scripts/validate_pet_package.py <pet-dir>
wsl uv run --with pillow --with pydantic scripts/package_pet.py <pet-dir> --write-manifest
```

不要默认改用 Windows Python，除非用户明确改变约束。

## 校验宠物包

```bash
wsl uv run --with pillow --with pydantic scripts/validate_pet_package.py /mnt/c/path/to/my-pet
```

校验内容：

- `pet.json` 必填字段。
- 1x、2x、4x atlas 尺寸。
- `spritesheetPath` 必须指向 1x。
- `cellSize` 必须是 `192x208`。
- 已用 cell 不能空白。
- 未用 cell 应保持透明。
- 无 4x master 时会提示 legacy-compatible warning。

## 从 4x master 打包

```bash
wsl uv run --with pillow --with pydantic scripts/package_pet.py /mnt/c/path/to/my-pet --write-manifest
```

脚本会从 `spritesheet@4x.webp` 高质量下采样生成：

- `spritesheet@2x.webp`
- `spritesheet.webp`

并更新 manifest 的高清字段。

直接安装到 launcher 扫描根目录：

```bash
wsl uv run --with pillow --with pydantic scripts/package_pet.py /mnt/c/path/to/my-pet --write-manifest --install-root /mnt/c/Users/<you>/.codex/pets
```

`--install-root` 会复制为：

```text
<install-root>/<pet-id>/
```

## 生成工作流

1. 阅读 `references/pet-package-contract.md`。
2. 如果要生成或修复视觉素材，阅读 `references/hatch-pet-workflow.md`。
3. 先生成或取得 `spritesheet@4x.webp`，不要从 1x 放大。
4. 下采样导出 2x/1x。
5. 运行 `validate_pet_package.py`。
6. 进行视觉 QA：同时检查 4x 清晰度和 1x 可读性。
7. 安装到 `~/.codex/pets` 或用户在 launcher 设置页添加的自定义目录。

## 图鉴投稿工作流

当用户要把桌宠发布到社区图鉴时，目标仓库是：

```text
https://github.com/wangling-miao/awesome-desktop-pets
```

投稿包放在：

```text
pets/<pet-id>/
```

必须包含：

- `pet.json`
- `preview.png`
- `preview.gif`
- `README.md`
- `LICENSE`
- `spritesheet.webp`，以及可选高清 `spritesheet@2x.webp` / `spritesheet@4x.webp`

图鉴版 `pet.json` 在 launcher 兼容字段之外，还应包含 `name`、`version`、`author`、`tags`、`license`、`preview`、`format`、`resolution`、`createdAt`。提交前在图鉴仓库运行：

```bash
npm run build
```

## 关键拒绝条件

- 4x 是由 1x 放大得到，却声称高清。
- `spritesheet.webp` 缺失。
- `pet.json.spritesheetPath` 不指向 1x。
- used cells 空白。
- unused cells 残留图像。
- 行语义错误，例如 `running-left` 方向错、`running` 变成方向奔跑、`idle` 几乎静止。
- 角色身份、脸、颜色、材质、道具或轮廓在行之间漂移。
