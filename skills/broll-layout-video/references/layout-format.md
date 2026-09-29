# Compact layout format

Use one JSON object per template. A library may store multiple objects under a shared `templates` array with global defaults for `ratio` and `unit`.

## Required fields

```json
{
  "id": "example-id",
  "type": "data-table",
  "elements": []
}
```

- `id`: Stable ASCII basename for generated outputs.
- `type`: Supported renderer family.
- `elements`: Composition-bearing elements only.
- `src`: Optional source-image path when the record came from image analysis.

## Element shape

```json
{
  "id": "table",
  "type": "table",
  "role": "comparison",
  "box": [12, 20, 76, 60]
}
```

`box` is `[x, y, width, height]` in percentages. Omit elements that do not change the reusable composition.

## Optional fields

- `focus`: Ordered element IDs. One or two is preferred; do not exceed three without a clear reason.
- `groups`: Object whose keys are group IDs and values are child element IDs.
- `motion`: Short preset records only when the scene changes over time.
- `must`: Layout relationships that must survive regeneration.
- `prefer`: Replaceable implementation preferences.
- `content`: Replaceable text or data used for the current render.
- `theme`: Replaceable surface palette.
- `durationInFrames`, `fps`, `width`, `height`: Render overrides.

Anything not recorded is free. Do not list every freedom explicitly.

## Supported families

### `data-table`

Include one `table` element with `box`, `columns`, and `rows`. Mark one row with `result: true`. Use `focus: ["table", "result_row"]`.

### `dialog-focus`

Include one `dialog` element with a `box`, `title`, and `lines`. Use one group ID for the dialog and its text. Add a `local-to-full` motion preset targeting the group.

### `title-over-video`

Include one `title-video` element with `videoSrc`, `kicker`, `title`, `subtitle`, and optional `playbackRate`. The referenced clip must live in the renderer's `public/` directory. Use this family when real footage is the full-frame background and the reusable composition is a centered three-level title group.

### Legacy `structure-image-motion`

This family exists only so historical demos continue to render. Do not create new `structure-image-motion` records. New work must reconstruct the settled frame as real editable Remotion elements instead of flattening it into a black-white-gray PNG.

### `chapter-subject-media`

Include one `chapter-media` element with `subjectVideoSrc`, `mediaImageSrc`, `titleLines`, and optional `eyebrow`. Both referenced assets must live in the renderer's `public/` directory. Use this family when a grayscale template defines three replaceable slots—subject footage, chapter title, and next media—and the finished output must preserve the template's subject move, title reveal, and rotating media takeover.

### `full-frame-aroll`

Include one `full-frame-aroll` element with `videoSrc` and `loopDurationInFrames`. Use optional `trimBefore`, `objectPosition`, `scaleFrom`, `scaleTo`, `volume`, `fadeInFrames`, and `fadeOutFrames` only when the reference shot requires them. The source clip must live in the renderer's `public/` directory. This family is for full-canvas speaking footage with no independent overlay elements; setting `loopDurationInFrames` allows a short user clip to repeat when the requested preview is longer.

### `kinetic-aroll-broll`

Include one `kinetic-aroll-broll` element with a clean `videoSrc`, `loopDurationInFrames`, two moon assets, the four lead-title strings, metric content, and product-title content. The speaking video remains continuous underneath the full sequence so its audio continues through opaque B-roll scenes. Use this family for a timed A-roll/B-roll recreation containing an opening typography overlay, a full-screen metric callout, a cinematic product title, and a dissolve back to A-roll.
