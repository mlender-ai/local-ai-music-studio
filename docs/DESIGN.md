# DESIGN.md — AI-Native DAW Design System

## Design Direction

**Professional · Dark · Functional · Precise**

Inspired by the density and ergonomics of Ableton Live (Arrangement/Clip workflow), Logic Pro (Track hierarchy & Mixer), and Bitwig Studio (modular dock layout), while establishing a restrained, independent studio identity.

### Explicit Anti-Patterns (Forbidden)
- Card-based SaaS/AI dashboards or hero banners
- Oversized marketing headings or instructional empty-state walls
- Heavy gradients, glassmorphism, or decorative animations
- Fake/unwired controls or synthetic waveform/meter animations
- Full-screen chat layouts

## Layout Architecture

Validated at `1440×900` and `1280×800` desktop viewports. Timeline always claims the largest area.

```text
+-------------------------------------------------------------------+
| Top Transport Bar (48px): Brand | Project | Transport | LCD | Exp |
+------------+----------------------------------------+-------------+
| Browser    | Section Markers (24px) & Bar Ruler     | AI Producer |
| (220px,    +--------------+-------------------------+ (260px,     |
| resizable/ | Track Headers| Arrangement Timeline    | resizable/  |
| collaps.)  | (188px)      | (Audio / Stem / MIDI)   | collaps.)   |
|            +--------------+-------------------------+             |
|            | Bottom Dock (220px, resizable/collaps.)|             |
|            | Tabs: Clip Editor | Piano Roll | Mixer | FX Rack     |
+------------+----------------------------------------+-------------+
```

## Color Tokens (`apps/daw/src/styles/tokens.css`)

### Surfaces
- `--bg-app`: `#141518` (outer shell)
- `--bg-panel`: `#1a1c20` (sidebars, transport, headers)
- `--bg-surface`: `#202328` (controls, inputs, clip editor canvas)
- `--bg-elevated`: `#272b32` (hover states, dropdowns)
- `--bg-timeline`: `#17191d` (arrangement grid)
- `--bg-timeline-alt`: `#1b1e23` (alternating bar shading)

### Borders & Lines
- `--border-subtle`: `#262a31`
- `--border-default`: `#30353e`
- `--border-strong`: `#424956`
- `--grid-bar`: `#343943`
- `--grid-beat`: `#23272e`
- `--grid-sub`: `#1d2026`

### Typography & Ink
- `--text-primary`: `#e4e7ec`
- `--text-secondary`: `#9aa2b1`
- `--text-muted`: `#6c7484`
- `--font-ui`: `'Inter', -apple-system, BlinkMacSystemFont, 'SF Pro Text', sans-serif`
- `--font-mono`: `'JetBrains Mono', 'SF Mono', ui-monospace, monospace` (used for BPM, Bar.Beat.Tick, dB, ms, Hz)

### Semantic Accents
- `--accent-play`: `#63b47c` (play active, loop toggle active)
- `--accent-playhead`: `#e5b84b` (playhead triangle & vertical line, selected clip outline)
- `--accent-mute`: `#c87a4b` (mute active)
- `--accent-solo`: `#d6b24d` (solo active)
- `--accent-danger`: `#d95c5c` (clipping indicator, destructive actions)
- `--accent-focus`: `#6899c4` (selection & keyboard focus ring)

### Restrained Track Palette
- Drums (`audio`): `#6a997c` (sage green)
- Bass (`stem` / `audio`): `#867ca8` (slate lavender)
- Guitar / Keys (`stem` / `audio`): `#b89458` (warm ochre)
- Synth (`midi`): `#648ea8` (steel blue)
- Texture / FX (`audio`): `#9e7389` (dusty mauve)
- Additional tracks: `#6a9999` (muted teal), `#9c8568` (sandstone)

## Interaction Rules

- **Direct Studio Entry:** Launch directly into the workspace (auto-loading the most recent or demo project).
- **Clear States:** Selected clips use a `1.5px` high-contrast `#e5b84b` border and elevated header tint; dragging clips show snap guides; unimplemented controls (`Record`, `FX Rack`, `AI Prompt`) are explicitly labeled as coming in later phases.
- **Keyboard Focus Safety:** Global DAW shortcuts (`Space`, `Delete`, `Cmd+Z/D/E/S`, arrows) are suppressed whenever focus is inside `<input>`, `<textarea>`, `<select>`, or `contentEditable`.
