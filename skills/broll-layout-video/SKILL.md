---
name: broll-layout-video
description: Generate modular B-roll videos from an editable Remotion settled-layout component using grouped motion and explicit visual-focus flow. Use after a reference video's key settled frame has been reconstructed as real text, media, shape, and container elements; do not create black-white-gray framework images or flatten editable layouts into screenshots.
---

# B-roll Layout Video

Animate an editable Remotion layout whose default state already matches the reference video's key settled frame.

## Workflow

1. Start from the reference video and its selected settled frame, not from a generated framework image.
2. Reuse or create real editable text, media, shape, container, and group elements whose default state matches that settled frame.
3. Preserve normalized position, size, crop, anchor, z-order, overflow, and grouping from the settled layout.
4. Keep one or two focus targets whenever possible; three is the practical maximum.
5. Animate a group as one object when the reference moves or scales the group together, while keeping replaceable child content editable.
6. Treat language and source media as replaceable props. Preserve timing, easing, masking, and effects when the task is a recreation rather than an original variation.
7. Validate the editable component, render a preview, and inspect both the settled frame and resulting MP4 before handoff.

## Implementation route

Use Remotion code as the source of truth. Structure major elements with `Interactive.*`, expose replaceable content through props/schema, and drive time-varying properties from the Remotion frame. A compact record may configure an existing component, but it must not replace the editable component tree.

Read [references/layout-format.md](references/layout-format.md) when creating or editing a layout record. Read [references/remotion-rendering.md](references/remotion-rendering.md) only when rendering or extending the supplied renderer.

## Current renderer scope

The bundled renderer supports:

- `data-table`: staged table reveal followed by a result-row emphasis.
- `dialog-focus`: one dialogue group reframed from a local detail to the full group.
- `title-over-video`: a real source clip used as a blurred, darkened background for a centered three-level title reveal.
- `chapter-subject-media`: replaces a grayscale subject/title/media template with a real subject clip, editable chapter copy, and a real media image while preserving the template's reveal and handoff motion.
- `full-frame-aroll`: uses a real speaking clip as a full-frame replacement shot, with optional looping, source trim, framing, and short entry/exit fades.
- `kinetic-aroll-broll`: plays a clean speaking clip continuously while recreating a timed sequence of typography, metric, and cinematic title B-roll layers above it.

If another family is requested, extend the renderer with a new element type or motion preset without expanding the core record unnecessarily.

`structure-image-motion` remains in the renderer only for old demos. Do not create new records or outputs with it.

## Outputs

Use the layout `id` as the basename. Generate derived files only when needed:

- `<id>.mp4` for the preview.
- `<id>.tsx` only when the user requests standalone Remotion source.
- A temporary Remotion still only when needed to compare the settled layout with the source frame.

Do not persist redundant output paths in the layout record.
