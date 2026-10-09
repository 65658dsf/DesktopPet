# Launcher Contract

Application identifier: `top.nether.pet`.

The Tauri launcher has two windows:

- `pet`: transparent, borderless, always on top, skipped from taskbar, draggable when unlocked.
- `settings`: ordinary settings window opened from the tray menu.

## Settings

Persist settings to Tauri Store `settings.json`:

```json
{
  "activePetId": "pet-name",
  "width": 192,
  "height": 208,
  "x": 80,
  "y": 80,
  "alwaysOnTop": true,
  "dragEnabled": true,
  "locked": false,
  "clickThrough": false,
  "reducedMotion": false,
  "animationSpeed": 1,
  "manualState": "idle",
  "autostart": false,
  "showOnStartup": true,
  "pixelated": false,
  "idleVariety": true,
  "keepAspectRatio": true,
  "petFolders": []
}
```

## Tray Menu

Use these entries:

- Show / Hide
- Settings
- Lock / Unlock
- Refresh Pets
- Quit

## Asset Selection

When rendering, choose the smallest atlas scale that is at least:

```text
max(window_width / 192, window_height / 208) * devicePixelRatio
```

Fallback to 1x when a package has no high-resolution fields. Use smooth scaling by default and `image-rendering: pixelated` only when the manifest or setting requests it.

## Motion Behavior

When the manual state is `idle`, the launcher may occasionally preview other quiet rows such as `waving`, `jumping`, or `review` to make standby feel less static. During manual window dragging, switch temporarily to `running-left` or `running-right` based on drag direction, then return to the selected state after the drag ends.

## Import Paths

Scan:

- `%USERPROFILE%\.codex\pets\<pet-id>\`
- Tauri app data `%APPDATA%\top.nether.pet\pets\<pet-id>\`
- User-configured custom directories from `settings.json` `petFolders`

Custom directories may point either to a folder containing multiple pet package subfolders or directly to one pet package folder containing `pet.json`.

Use Tauri asset protocol scope for those directories and convert local spritesheet paths with `convertFileSrc`.
