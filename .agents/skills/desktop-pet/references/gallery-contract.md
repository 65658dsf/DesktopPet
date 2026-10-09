# Community Gallery Contract

Use this reference when preparing a desktop pet for the `awesome-desktop-pets` community gallery.

The gallery is intentionally static:

- GitHub repository handles Pull Requests, validation, packaging, and version history.
- GitHub Pages hosts `public/index.json`, previews, and downloadable zip packages.
- The website and Desktop Pet Launcher browse this index and download zip packages.
- Do not add a backend, login system, comments, likes, or accounts unless the user explicitly changes the product scope.

## Repository

```text
https://github.com/wangling-miao/awesome-desktop-pets
```

Recommended generated index URL:

```text
https://wangling-miao.github.io/awesome-desktop-pets/index.json
```

The website may expose this as `pet.nether.top/gallery/`.

## Directory Shape

```text
pets/
  <pet-id>/
    pet.json
    preview.png
    preview.gif
    README.md
    LICENSE
    spritesheet.webp
    spritesheet@2x.webp       # optional
    spritesheet@4x.webp       # recommended for new high-resolution packages
schemas/
  pet.schema.json
scripts/
  validate-pets.ts
  package-pets.ts
  build-index.ts
public/
  index.json
```

## Gallery Manifest Fields

Gallery `pet.json` extends the launcher pet manifest. Keep the launcher-compatible fields, and add gallery metadata:

```json
{
  "id": "cat-black",
  "name": "黑猫桌宠",
  "displayName": "黑猫桌宠",
  "version": "1.0.0",
  "author": "example-user",
  "description": "一只会在桌面上闲逛的黑猫。",
  "tags": ["cat", "cute", "pixel"],
  "license": "CC-BY-4.0",
  "preview": "preview.gif",
  "previewImage": "preview.png",
  "format": "hatch-pet-compatible",
  "resolution": "4x",
  "createdAt": "2026-06-10",
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

Rules:

- `id` must match the directory name and use lowercase kebab-case.
- `preview` must be `preview.gif`.
- `previewImage` should be `preview.png`.
- `format` is `desktop-pet` or `hatch-pet-compatible`.
- `resolution` is the best shipped runtime asset: `1x`, `2x`, or `4x`.
- `spritesheetPath` must still point to the 1x compatibility atlas.

## Preview Requirements

Create real previews from the pet, not unrelated placeholder art:

- `preview.png`: static representative pose, transparent or clean simple background.
- `preview.gif`: short loop from `idle` or another personality-preserving row.
- Keep previews small enough for a gallery page, but readable.

## Commands

In the gallery repository:

```bash
npm install
npm run new-pet my-cute-cat
npm run build
```

`npm run build` must:

1. Validate all `pets/*/pet.json` files and required files.
2. Package each pet as `public/downloads/<pet-id>-v<version>.zip`.
3. Generate `public/index.json`.

## Submission Workflow

1. Fork `awesome-desktop-pets`.
2. Add `pets/<pet-id>/`.
3. Include `pet.json`, previews, README, LICENSE, and spritesheets.
4. Run `npm run build`.
5. Open a Pull Request.

Do not submit pets without a clear license. Fan-art or branded characters need explicit notes about source and rights; if rights are uncertain, mark them as examples only or ask the user before publishing.

