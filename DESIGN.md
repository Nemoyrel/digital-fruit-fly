# Digital Fruit Fly Design System

## 1. Atmosphere & Identity

Digital Fruit Fly uses a technical field-report language: precise, skeptical, and readable under long-form study. The signature is an annotated systems map, where evidence, assumptions, and implementation gaps are visually separated so readers can distinguish published biology, Eon claims, and this repository's engineering work.

## 2. Color

### Palette

| Role | Token | Light | Dark | Usage |
|------|-------|-------|------|-------|
| Surface/primary | --surface-primary | #F7F8F4 | #121417 | Main report background |
| Surface/secondary | --surface-secondary | #FFFFFF | #1A1D20 | Content panels and tables |
| Surface/elevated | --surface-elevated | #EEF3EF | #20262A | Emphasis blocks |
| Surface/ink | --surface-ink | #171A1D | #F5F7F2 | Inverted callouts |
| Text/primary | --text-primary | #171A1D | #F5F7F2 | Headlines and body |
| Text/secondary | --text-secondary | #58605B | #BAC4BE | Captions and supporting text |
| Text/tertiary | --text-tertiary | #7B847E | #8D9891 | Metadata |
| Border/default | --border-default | #D8DED8 | #38413B | Panels and dividers |
| Border/subtle | --border-subtle | #E7ECE6 | #2B332E | Soft separations |
| Accent/primary | --accent-primary | #00796B | #35C0A8 | Links, marks, focus |
| Accent/secondary | --accent-secondary | #C44A1C | #FF8658 | Warnings and uncertainty |
| Accent/tertiary | --accent-tertiary | #6F58C9 | #A696FF | Research-method markers |
| Status/success | --status-success | #147A3A | #58D68D | Ready or validated |
| Status/warning | --status-warning | #9B6500 | #F6C453 | Needs calibration |
| Status/error | --status-error | #B3261E | #FF7B72 | Missing or not reproducible |
| Status/info | --status-info | #1E6EA8 | #78C2FF | Informational notes |

### Rules

- Accent/primary is for evidence links and system connectors.
- Accent/secondary is reserved for limitations, caveats, and approximation warnings.
- Use neutral surfaces for long reading; do not turn the report into a single-hue theme.

## 3. Typography

### Scale

| Level | Size | Weight | Line Height | Tracking | Usage |
|-------|------|--------|-------------|----------|-------|
| Display | 48px mobile / 72px desktop | 760 | 1.04 | 0 | Report title |
| H1 | 34px mobile / 46px desktop | 720 | 1.12 | 0 | Major sections |
| H2 | 26px mobile / 34px desktop | 700 | 1.2 | 0 | Section headers |
| H3 | 20px | 680 | 1.35 | 0 | Card titles |
| Body/lg | 18px | 430 | 1.65 | 0 | Lead paragraphs |
| Body | 16px | 420 | 1.65 | 0 | Default text |
| Body/sm | 14px | 430 | 1.55 | 0 | Notes and captions |
| Caption | 12px | 620 | 1.45 | 0 | Labels and metadata |
| Overline | 11px | 700 | 1.4 | 0 | Section labels |

### Font Stack

- Primary: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif
- Mono: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace
- Serif: not used

### Rules

- Body text never drops below 14px.
- Chinese headings use constrained widths and normal letter spacing to avoid awkward wrapping.
- Monospace is used only for source IDs, timings, and implementation labels.

## 4. Spacing & Layout

### Base Unit

All spacing derives from a base of 4px.

| Token | Value | Usage |
|-------|-------|-------|
| --space-1 | 4px | Tight inline pairing |
| --space-2 | 8px | Small chips and metadata |
| --space-3 | 12px | Compact groups |
| --space-4 | 16px | Default inner spacing |
| --space-5 | 20px | Comfortable stack spacing |
| --space-6 | 24px | Panel padding |
| --space-8 | 32px | Grid gaps |
| --space-10 | 40px | Section internal breaks |
| --space-12 | 48px | Major grouping |
| --space-16 | 64px | Section rhythm |
| --space-20 | 80px | Opening block rhythm |
| --space-24 | 96px | Maximum separation |

### Grid

- Max content width: 1240px
- Column system: 12-column desktop grid with 24px gutters; single-column mobile with 20px margins
- Breakpoints: sm 640px, md 768px, lg 1024px, xl 1280px

### Rules

- Repeated report objects use grid/flex primitives with stable dimensions.
- Avoid nested cards; use full-width bands, tables, and single-level panels.

## 5. Components

### Evidence Tag
- **Structure**: inline anchor with source number and short label.
- **Variants**: primary, local, caveat.
- **Spacing**: --space-1 horizontal padding, --space-2 gap when grouped.
- **States**: default, hover, focus.
- **Accessibility**: visible focus ring and descriptive link text.
- **Motion**: color transition only.

### System Node
- **Structure**: labeled block inside a process map.
- **Variants**: source, transform, interface, output.
- **Spacing**: --space-4 padding, --space-3 internal label gap.
- **States**: static in report.
- **Accessibility**: text-first layout, no color-only meaning.
- **Motion**: none.

### Claim Matrix
- **Structure**: responsive table with claim, evidence, reproducibility status, and project implication.
- **Variants**: verified, partial, missing.
- **Spacing**: --space-4 cell padding.
- **States**: static in report.
- **Accessibility**: semantic table and high contrast status labels.
- **Motion**: none.

## 6. Motion & Interaction

### Timing

| Type | Duration | Easing | Usage |
|------|----------|--------|-------|
| Micro | 120ms | ease-out | Link and chip hover |
| Standard | 220ms | ease-in-out | Details open state |
| Emphasis | 420ms | cubic-bezier(0.16, 1, 0.3, 1) | Initial content reveal if used |
| Scroll-driven | none | linear | Not used |

### Rules

- Report remains readable with JavaScript disabled.
- Use `prefers-reduced-motion` to disable non-essential transitions.
- Focus states must be visible on every link.

## 7. Depth & Surface

### Strategy

Use borders-only with tonal-shift emphasis. Shadows are not part of this report language.

| Type | Value | Usage |
|------|-------|-------|
| Default | 1px solid var(--border-default) | Panels, tables, diagrams |
| Subtle | 1px solid var(--border-subtle) | Internal dividers |
| Strong | 2px solid var(--text-primary) | Key conclusion blocks |
