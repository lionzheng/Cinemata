# Cinemata

> Stories, compiled into motion.

Cinemata is an open-source, reproducible production pipeline for episodic media. It turns a structured episode manifest into reviewable storyboards, subtitles, a timeline, and a provenance record. The first workflow is deliberately provider-neutral and deterministic, so the repository can be used in CI before connecting image, video, voice, or music providers.

## First end-to-end workflow

Requirements: Python 3.11+.

```powershell
py -3 -m cinemata build examples/episode-01.json --output dist/episode-01
```

Render the generated mock frames and dialogue into an MP4 (requires FFmpeg):

```powershell
py -3 -m cinemata render dist/episode-01 --output dist/episode-01.mp4
```

The command writes:

- `storyboard.md`: a reviewable shot list with dialogue and timing.
- `review.html`: a browser-ready visual review board for scenes and shots.
- `assets/*.svg`: deterministic mock frames generated through the provider interface.
- `assets/*.wav`: deterministic mock voice clips aligned to dialogue duration.
- `subtitles.srt`: subtitles derived from the dialogue timeline.
- `timeline.json`: normalized scene and shot timing.
- `provenance.json`: source, license, generation, and pipeline metadata.
- `episode-01.mp4`: optional rendered video with mock frames and dialogue audio.

Run the tests with:

```powershell
py -3 -m unittest discover -s tests -p "test_*.py" -v
```

See [docs/charter.md](docs/charter.md) for the project charter and [docs/data-model.md](docs/data-model.md) for the manifest model.

## Design principles

- Provider-neutral: model and media providers are adapters, not the data model.
- Reproducible: inputs, versions, parameters, and source assets are recorded.
- Reviewable: every generated artifact can be inspected before rendering or publishing.
- Rights-aware: asset provenance and licensing are first-class fields.
- Human-in-the-loop: automation produces drafts; creators approve the final cut.

## Status

The repository currently contains the manifest schema and a deterministic storyboard-to-subtitles pipeline. Media-provider adapters and video rendering are planned after the core format stabilizes.

The default image provider is `MockImageProvider`: it creates local SVG frames without network access, so the full workflow remains reproducible in CI. Real image, voice, music, and video providers can implement the interfaces in `src/cinemata/providers.py` without changing the episode manifest.

## License

Apache-2.0. See [LICENSE](LICENSE).
