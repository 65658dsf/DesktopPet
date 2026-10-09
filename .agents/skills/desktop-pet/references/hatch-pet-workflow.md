# Hatch-Pet Workflow Adapted For Desktop Pet Launcher

Use this reference when creating, repairing, or visually QA'ing pet art. It distills the parts of `hatch-pet` that matter for this launcher's high-DPI package contract.

## Generation Layer

Use the installed `$imagegen` skill for visual generation. Do not call image APIs, local image CLIs, or ad hoc image generation scripts directly.

For a full pet, generate a canonical base first, then generate row strips grounded by that base. Keep each row state-specific and preserve the same face, body proportions, palette, material, props, and silhouette.

When the pet is character-like or the user cares about recognizable identity, create a complete 1x hatch-pet action set first:

1. Generate or select a canonical base with all user-specified identity details.
2. Generate `idle` and `running-right` as quality gates.
3. Derive `running-left` only with a framewise mirror when it is visually safe; otherwise generate it normally.
4. Generate `waving`, `jumping`, `failed`, `waiting`, `running`, and `review` as separate state strips. Do not derive them from the base pose or another row.
5. Extract frames, compose the `1536x1872` 1x atlas, validate it, and inspect the contact sheet or GIF previews.
6. Only after the 1x action set passes should the workflow install the 1x package, create conservative variants, or redraw the same action storyboard at 4x.

For this launcher, prefer 4x production geometry:

- 4x cell: `768x832`
- 4x atlas: `6144x7488`
- 1x compatibility cell: `192x208`
- 1x compatibility atlas: `1536x1872`

Never generate only 1x art and upscale it to claim high-resolution support.

A 1x-only package is still acceptable when the user asks for hatch-pet compatibility, quick iteration, or a proven action baseline. Mark it as legacy-compatible by shipping only `pet.json` and `spritesheet.webp`; do not create fake `spritesheet@4x.webp` files.

## State Rows

The launcher uses the same 8-column by 9-row contract as `hatch-pet`:

| Row | State | Frames | Meaning |
| --- | --- | ---: | --- |
| 0 | `idle` | 6 | Quiet breathing, blinking, or small personality-preserving motion. |
| 1 | `running-right` | 8 | Directional drag movement facing right. |
| 2 | `running-left` | 8 | Directional drag movement facing left. |
| 3 | `waving` | 4 | Greeting gesture using a limb or prop already part of the pet. |
| 4 | `jumping` | 5 | Vertical body movement without floor marks or shadows. |
| 5 | `failed` | 8 | Small attached failure expression such as tears or smoke, if cleanly removable. |
| 6 | `waiting` | 6 | Expectant pose for user input or approval. |
| 7 | `running` | 6 | Focused task work; not literal directional running. |
| 8 | `review` | 6 | Checking, reading, or focused review pose. |

`running-left` may be derived by mirroring `running-right` only when the pet's identity, prop side, markings, and direction semantics remain correct. Preserve frame order so the gait timing is not reversed.

All other rows must be generated or redrawn with their own action semantics. Reject any row that is merely a static base pose shifted, squashed, rotated, recolored, or lightly warped unless the row is intentionally subtle `idle` and still shows visible micro-motion.

## Transparency And Effects

Generated strips should use a flat removable chroma background before deterministic transparency cleanup. Final atlases must have transparent unused cells.

Allow effects only when they are state-relevant, attached to the pet silhouette, inside the same cell, opaque enough to extract cleanly, and readable at small size.

Reject:

- visible text, labels, frame numbers, UI, guide marks, or speech bubbles
- detached stars, punctuation, smoke, dust, speed lines, motion trails, glows, floor shadows, and landing marks
- cropped body parts, overlapping cells, stray pixels, chroma-key halos, or nontransparent unused cells
- row identity drift: species, face, palette, outfit, material, prop, or silhouette changes
- missing user-specified identity details, including special pupils or iris marks, scars, accessories, asymmetries, or signature colors

## Visual QA

Deterministic validation is required but not enough. Inspect both:

- `spritesheet@4x.webp` for source crispness and true high-DPI detail
- `spritesheet.webp` for 1x readability and old-package compatibility

Check row previews or a contact sheet when available. Fail the package if a row is semantically wrong, visually inert, has wrong facing direction, shows size popping, or changes pet identity.

The 1x contact sheet is the first acceptance gate for character pets. A deterministic pass is not enough: verify that every row reads as its app state, `idle` is not completely static, `running` is task work rather than foot-running, and user-specified details remain visible wherever the pose allows.

## Repair Strategy

Repair the smallest failing scope:

- Manifest/path error: fix `pet.json`.
- Missing 2x/1x export from a valid 4x master: run `scripts/package_pet.py`.
- Bad unused cells or wrong size: regenerate or re-export the affected atlas scale.
- Visual row failure: regenerate only the failing row at 4x, recompose the 4x atlas, then downsample.
- 1x action failure: regenerate only the failing 1x row first, then re-run extraction, inspection, atlas validation, contact sheet, and previews before attempting any 4x redraw.

Keep `spritesheet.webp` as the compatibility path even when the launcher will choose `spritesheet@4x.webp` at runtime.

## Variant Guidance

After one full action set passes QA, variants may be created by conservative palette, contrast, or naming changes when the user asks for several versions. Keep the same atlas geometry and re-run validation for every variant. Do not call a variant complete if it changes identity, loses required details, breaks transparency, or hides the action readability.
