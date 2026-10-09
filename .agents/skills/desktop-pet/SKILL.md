---
name: desktop-pet
description: Create, validate, repair, import, and package high-resolution Tauri desktop pet packages for the Desktop Pet Launcher. Use when the user asks for a desktop pet, Tauri pet launcher assets, hatch-pet-compatible pet packages, tray pet packaging, high-DPI spritesheets, or pet.json/spritesheet.webp validation. Prefer 4x master spritesheets and export 1x compatibility assets instead of upscaling small hatch-pet output.
---

# Desktop Pet

Use this skill to create, repair, validate, import, and package pets for the Tauri Desktop Pet Launcher. The launcher is compatible with old `hatch-pet` packages, but this skill should produce high-resolution launcher-native packages by default.

For character pets, first prove the pet works as a complete 1x action set before producing high-DPI assets. A complete 1x action set means all 9 rows are authored with distinct state semantics, validated as a `1536x1872` atlas, and visually QA'd through a contact sheet or GIF previews. Do not replace this step with a single base sprite plus local transforms.

## Core Contract

Read these references only when they apply:

- `references/pet-package-contract.md`: required for every package creation, repair, validation, or import.
- `references/launcher-contract.md`: read when launcher behavior, settings, tray behavior, import paths, or custom pet folders matter.
- `references/hatch-pet-workflow.md`: read when generating, repairing, or visually QA'ing pet art. It carries the essential `hatch-pet` workflow without loading the entire upstream skill into every task.
- `references/gallery-contract.md`: read when publishing or preparing a package for the `awesome-desktop-pets` community gallery.

Package root:

```text
<pet-id>/
  pet.json
  spritesheet.webp
  spritesheet@4x.webp
  spritesheet@2x.webp        # optional but recommended
```

Always keep `spritesheet.webp` as the 1x compatibility atlas. New work should preserve or create `spritesheet@4x.webp` as the runtime-quality master.

The package can be installed into any folder the launcher scans. The default Codex-compatible location is `~/.codex/pets/<pet-id>/`, and the launcher also supports user-configured custom folders.

## High-Resolution Rule

Do not treat a `192x208` cell or `1536x1872` atlas as a source-quality master. If only a 1x hatch-pet atlas exists, it is legacy-compatible but not high-resolution.

For new character or mascot generation:

- Build and accept a full 1x hatch-pet package first when action quality, identity fidelity, or state semantics matter.
- Generate each normal row as its own state-specific strip grounded by the canonical base; only `running-left` may be derived from `running-right`, and only through framewise mirror preserving order.
- Never synthesize `waving`, `jumping`, `failed`, `waiting`, `running`, or `review` by affine-transforming one base pose, moving a static sprite, or recoloring another state.
- Capture user-specified identity details, such as special eye shapes, markings, props, or asymmetries, in the base prompt and every row prompt. Treat missing or wrong identity details as visual QA failures even when deterministic validation passes.
- After the 1x action set passes, either install it as a legacy-compatible package or use it as the approved action storyboard for a true 4x redraw. Do not upscale the accepted 1x atlas to claim high-DPI support.

For new visual generation:

- Generate or obtain a 4x master atlas first: `6144x7488`, cell `768x832`.
- Downsample from 4x to 2x and 1x with a high-quality filter.
- Do not upscale 1x output to create `spritesheet@4x.webp`.
- QA both the 4x master and 1x compatibility export.

When using `$imagegen`, prompt for row strips or atlas assets at 4x slot geometry. Keep the same 9 states and frame counts as hatch-pet, but make the master cells `768x832`. Read `references/hatch-pet-workflow.md` for state semantics, transparency rules, repair strategy, and visual QA blockers.

## Validation

Use the bundled validator for deterministic checks:

```bash
wsl uv run --with pillow --with pydantic scripts/validate_pet_package.py /mnt/c/path/to/pet-dir
```

If `uv` is missing in WSL, ask the user to install it before running Python helpers. Do not fall back to Windows Python unless the user explicitly changes that requirement.

Validator expectations:

- `pet.json` has `id`, `displayName`, `description`, and `spritesheetPath`.
- `spritesheet.webp` exists and is exactly `1536x1872`.
- `spritesheet@4x.webp`, when present, is exactly `6144x7488`.
- `spritesheet@2x.webp`, when present, is exactly `3072x3744`.
- `pet.json.spritesheets` points to all shipped scale assets.
- Used frame cells are non-empty.
- Unused cells after each row's final frame are transparent.

## Packaging

Use the bundled packager when a valid 4x master exists:

```bash
wsl uv run --with pillow --with pydantic scripts/package_pet.py /mnt/c/path/to/pet-dir --write-manifest
```

The packager creates or refreshes `spritesheet@2x.webp`, `spritesheet.webp`, and manifest scale fields from `spritesheet@4x.webp`.

For accepted 1x-only hatch-pet output, install the legacy-compatible package directly:

```text
<pet-id>/
  pet.json
  spritesheet.webp
```

The manifest should keep `spritesheetPath` as `spritesheet.webp`. Do not add `spritesheets` scale fields unless the corresponding files actually exist.

Variants are allowed after one action set passes QA. Keep variants derived from the accepted atlas to conservative palette, contrast, scale, or naming changes unless the user requests a new visual identity. Re-validate every variant.

To copy the finished package into a launcher scan root, pass `--install-root`:

```bash
wsl uv run --with pillow --with pydantic scripts/package_pet.py /mnt/c/path/to/pet-dir --write-manifest --install-root /mnt/c/Users/<you>/.codex/pets
```

## Launcher Import Guidance

The launcher scans:

- Windows `%USERPROFILE%\.codex\pets\<pet-id>\`
- Tauri app data `%APPDATA%\top.nether.pet\pets\`
- Custom folders saved in launcher settings as `petFolders`

For Codex-compatible sharing, stage finished packages under `~/.codex/pets/<pet-id>/`. For app-local installs, copy the package into the launcher's app data `pets/` directory. For user-managed libraries, install into any folder and add that folder in the launcher settings page.

## Community Gallery Guidance

When the user asks to publish, submit, share, or add a pet to the community/gallery, use the `awesome-desktop-pets` index repository instead of inventing a backend. Read `references/gallery-contract.md`.

Gallery-ready packages must add:

- `preview.png`
- `preview.gif`
- `README.md`
- `LICENSE`
- gallery metadata fields in `pet.json`: `name`, `version`, `author`, `tags`, `license`, `preview`, `format`, `resolution`, and `createdAt`

The gallery repository validates and builds with:

```bash
npm run build
```

The launcher imports gallery pets from zip download URLs and installs them into `%APPDATA%\top.nether.pet\pets\<pet-id>\`.

## Visual QA

After deterministic validation, inspect:

- The 1x contact sheet and GIF previews for complete, distinct row semantics.
- 4x atlas for crisp source details.
- 1x atlas for readable small-size animation.
- All 9 animation rows for identity consistency and correct state semantics.
- Scaling in the launcher at small, native, and enlarged window sizes.

Reject packages with identity drift, cropped frames, blank used cells, copied guide marks, detached effects, inert rows, repeated base-pose rows, missing user-specified details, or a 4x atlas that is merely an upscaled 1x image.
