# 1.3.0 complete state animation QA

All new raster artwork was created with the built-in `image_gen` tool, with true transparency.
The canonical character reference is `pets/qinche-q/animations/blink.png`.
Prompts: `all-states-prompts.md`, `review-prompt.md`, `running-layout-repair-prompt.md`,
and `failed-layout-repair-prompt.md` in this folder. Final sources live in `pets/qinche-q/animations/`.

| Source | Native pixels | Extraction |
| --- | --- | --- |
| blink.png | 1476×1066 | 3×2, six approved existing frames |
| chin-rest.png | 1476×1066 | 3×2, six approved existing frames, separate automatic gesture |
| running-right.png | 852×1847 | 2×4, eight chronological frames |
| running-left.png | 852×1847 | framewise horizontal mirror of right; order unchanged |
| waving.png | 1206×1305 | 2×2, explicit row boundary y=646 inside transparent gutter |
| jumping.png | 1477×1065 | 3×2, five frames, sixth cell unused |
| failed.png | 852×1846 | 2×4, explicit row boundaries y=493,953,1403 inside gutters |
| waiting.png | 1476×1066 | 3×2, six frames |
| running.png | 1475×1067 | 3×2, six writing/thinking frames |
| review.png | 1476×1066 | 3×2, six reading/thinking/page-turn frames |
| poke.png | 1205×1305 | eight approved existing frames selected from 3×3 |

Initial running-right and failed 4×2 drafts were rejected because characters crossed equal cell
boundaries. Their replacements separate poses into 2×4 layouts. Failed and waving use explicit
rectangles to preserve small differences in generated row spacing; source artwork was not rescaled.
The generated native files are retained without claiming they are 4x masters.

The nine core clips have the contract's 57 frames. All native clip canvases exceed 384×416;
the real Qt renderer exports 2x keyframes, then `assemble_states.cjs` builds a lossless 1x atlas.
After its contact-sheet acceptance, `assemble_states.cjs --2x` builds a true 2x atlas from the
same 2x keyframes, never by enlarging 1x. Both atlases have transparent unused cells.
Obsolete original atlases are archived in `build/qa-animation/legacy-atlas-1.2.0/`;
the pet package no longer ships or declares the previous 4x atlas.

Jump offsets use logical 192×208 units and preserve the visible character inside its cell.
Character articulation is authored in each source pose; offsets only add the airborne trajectory.
Left/right gait timing is identical. Short eye-closure blends are declared by `blinkFrames`.

Visual review covered source art, every actual Qt keyframe, the 1x atlas on a dark background,
the labeled contact sheet, action identity, frame separation, facing direction, and loop endpoints.
No obvious identity drift, cross-cell fragments or new clipping was found. Static frame review
does not assert a measured desktop refresh rate.

Verification passed: all-state integration 6; clip loading/offsets 10; animation/priority/config 33;
alpha transitions/cache 14; pointer input 13; poke behavior 13; window activation 6.
These tests use isolated in-memory or temporary settings and do not contact AI services.

Reproduce previews with `tools/preview_animation.py --all-states`, followed by
`tools/gen_pet/preview_expressions.cjs --all-states`. The HTML at
`build/qa-animation/all-states/index.html` loops each action at its own duration;
`animations/all-states-preview.gif` is a compact 3×3 overview. The normal preview still shows
blink plus chin-rest, and `--poke` still shows the existing touch reaction.

Application behavior: automatic mode chooses quiet gestures without consecutive repeats;
explicit idle only blinks. AI waits in waiting, writes in running after its first content chunk,
and uses failed on an error. Preview cycles return to standby, and automatic gestures cannot
interrupt an active manual preview. The scaled-pixmap LRU cache is capped at 64 MiB.
