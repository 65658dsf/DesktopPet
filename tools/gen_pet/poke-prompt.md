# Poke reaction artwork

Created with the built-in `image_gen` tool, transparent background enabled.
Reference: `pets/qinche-q/animations/blink.png`.
Output: `pets/qinche-q/animations/poke.png`, preserved at its generated native resolution.
The grid is 3 columns by 3 rows. This is an optional runtime `poke` clip;
the original compatibility atlas is unchanged.

Actual source size: **1205×1305 RGBA**. Visual QA selected eight frames using
explicit source rectangles in `pet.json`: source indices 0, 1, 2, 3, 5, 6, 7, 8.
The center open-palm frame is excluded because it switches the responding hand.
An imagegen correction was attempted (see `poke-repair-prompt.md`) but did not
correct that continuity issue; its output is not shipped. The final gesture
keeps the same responding arm: surprised blink, hand rising, a playful raised
finger and wink, then settling back to idle. No source artwork was upscaled.

## Exact generation prompt

undefined
