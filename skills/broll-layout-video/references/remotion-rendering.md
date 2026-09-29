# Remotion rendering

The reusable renderer lives in `assets/remotion-renderer`.

Render with:

```bash
scripts/render-video.sh <layout.json> <output.mp4>
```

The script installs matching Remotion dependencies on first use, then renders composition `BrollLayout` with the JSON as input props.

Before handoff:

1. Confirm the layout ID and output basename agree.
2. Confirm the MP4 is non-empty and decodable with `ffprobe`.
3. Render the selected settled frame for comparison when layout changed; this still is a temporary verification artifact, not a framework image.
4. Keep the editable Remotion component as the source of truth. A layout JSON may configure it, but must not replace its element tree.
