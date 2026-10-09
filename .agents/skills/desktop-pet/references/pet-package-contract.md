# Pet Package Contract

## Atlas Geometry

| Scale | Cell | Atlas |
| --- | --- | --- |
| 1x | `192x208` | `1536x1872` |
| 2x | `384x416` | `3072x3744` |
| 4x | `768x832` | `6144x7488` |

The atlas is always 8 columns by 9 rows. Unused cells after the row's final used frame must be transparent.
Used cells must contain visible sprite pixels; blank used frames are invalid even when the atlas dimensions are correct.

## Rows

| Row | State | Used columns | Durations |
| --- | --- | ---: | --- |
| 0 | `idle` | 0-5 | 280, 110, 110, 140, 140, 320 ms |
| 1 | `running-right` | 0-7 | 120 ms each, final 220 ms |
| 2 | `running-left` | 0-7 | 120 ms each, final 220 ms |
| 3 | `waving` | 0-3 | 140 ms each, final 280 ms |
| 4 | `jumping` | 0-4 | 140 ms each, final 280 ms |
| 5 | `failed` | 0-7 | 140 ms each, final 240 ms |
| 6 | `waiting` | 0-5 | 150 ms each, final 260 ms |
| 7 | `running` | 0-5 | 120 ms each, final 220 ms |
| 8 | `review` | 0-5 | 150 ms each, final 280 ms |

## Manifest

Legacy-compatible minimum:

```json
{
  "id": "pet-name",
  "displayName": "Pet Name",
  "description": "One short sentence.",
  "spritesheetPath": "spritesheet.webp"
}
```

High-resolution manifest:

```json
{
  "id": "pet-name",
  "displayName": "Pet Name",
  "description": "One short sentence.",
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

`spritesheetPath` always points to the 1x compatibility file so older consumers can still load the package.

The launcher resolves `spritesheets` paths relative to the package root and chooses the smallest scale that satisfies the current window size and device pixel ratio.

## Source Quality

A 4x atlas must be generated, drawn, or exported at 4x. Do not create 4x by resizing a 1x atlas upward. If the source is only 1x, mark the package as legacy-compatible and ask for or generate a true high-resolution source before claiming high-DPI support.
