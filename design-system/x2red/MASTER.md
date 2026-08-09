# X2RED Web Design System

> 全站网页端唯一视觉与交互来源。页面级规则如存在于 `pages/<page>.md`，只覆盖明确列出的差异，其余继续继承本文件。

- **Project:** X2RED
- **Updated:** 2026-08-06
- **Product:** 本地优先的内容研究、语料组织、多工作台创作与人工发布工具
- **Reference:** Claude 式暖白、低噪声、纸张感生产力界面
- **Design dials:** Variance 2/10 · Motion 2/10 · Density 4/10

## 1. Design intent

- 主工作台始终是视觉和尺寸中心；导航、来源选择与配置区可以收起，不能挤压核心编辑区。
- 暖白纸张背景、深墨文字、单一赤陶强调色；不使用紫蓝渐变、玻璃拟态、霓虹或装饰性光晕。
- 结构靠间距、细边框和文字层级区分，不靠大面积阴影或随机色块。
- 同类控件同高、同圆角、同字号、同状态反馈；正文控件最小字号 14px，默认正文 15px。
- 桌面、平板、手机都不能产生页面级横向滚动；表格或代码区仅允许自身局部滚动。
- 所有生成、审核和发布状态同时使用文字与颜色表达。

## 2. Foundations

### Color tokens

| Role | Value | Token |
|---|---:|---|
| App background | `#F7F6F2` | `--ui-bg` |
| Sidebar background | `#F0EEE7` | `--ui-sidebar` |
| Primary surface | `#FFFEFB` | `--ui-surface` |
| Subtle surface | `#F5F2EC` | `--ui-surface-subtle` |
| Raised surface | `#FFFFFF` | `--ui-surface-raised` |
| Primary text | `#2B2926` | `--ui-text` |
| Secondary text | `#6F6A63` | `--ui-text-muted` |
| Quiet text | `#8B857C` | `--ui-text-quiet` |
| Border | `#DEDAD2` | `--ui-border` |
| Strong border | `#CBC5BC` | `--ui-border-strong` |
| Primary action | `#B65D3C` | `--ui-accent` |
| Primary hover | `#9F4B2D` | `--ui-accent-hover` |
| Accent soft | `#F2E6DF` | `--ui-accent-soft` |
| Success | `#2F765C` | `--ui-success` |
| Success soft | `#E8F3EE` | `--ui-success-soft` |
| Warning | `#8A651B` | `--ui-warning` |
| Warning soft | `#F6EFD9` | `--ui-warning-soft` |
| Destructive | `#B44A4A` | `--ui-danger` |
| Destructive soft | `#F8E8E6` | `--ui-danger-soft` |
| Focus ring | `rgba(182, 93, 60, .28)` | `--ui-ring` |

`#B65D3C` with white text is reserved for primary actions and meets AA for normal text. Bright Claude-like terracotta may be used only as a border or decorative accent, never behind small white text.

### Typography

- UI/body: `ui-sans-serif, -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", "Microsoft YaHei", sans-serif`.
- Editorial headings only: `ui-serif, "Iowan Old Style", "Songti SC", "STSong", serif`.
- Monospace: `"SFMono-Regular", "Cascadia Code", Consolas, monospace`.
- Page title: 30px / 1.2 / 650; mobile 26px.
- Section title: 20px / 1.3 / 650.
- Panel title: 16px / 1.4 / 650.
- Body: 15px / 1.65 / 400.
- Label/control: 14px / 1.45 / 600.
- Metadata: never below 12px.
- English kicker is optional metadata, 11px, moderate tracking; it must not overpower the Chinese title.

### Spacing

| Token | Value |
|---|---:|
| `--space-1` | 4px |
| `--space-2` | 8px |
| `--space-3` | 12px |
| `--space-4` | 16px |
| `--space-5` | 20px |
| `--space-6` | 24px |
| `--space-8` | 32px |
| `--space-10` | 40px |
| `--space-12` | 48px |

### Shape and depth

- Control radius: 10px; small control: 8px.
- Card/panel radius: 14px; major workbench surface: 16px.
- Pill radius is only for status, tags and compact filters.
- Default panel uses a 1px border and at most `0 1px 2px rgba(43, 41, 38, .05)`.
- Floating drawer/modal may use `0 18px 50px rgba(43, 41, 38, .16)`.
- No gradients, colored glows or hover movement that changes layout.

## 3. Layout contract

- Desktop shell rail: 256px; compact rail: 76px.
- Top bar: 64px.
- Content maximum: 1680px, centered; desktop horizontal padding 28px.
- From 861px through 1360px, the shell rail automatically becomes icon-only so the workbench keeps its width; users may temporarily reopen it.
- At 860px and below, navigation becomes an off-canvas drawer; the page stays full width.
- Workspace columns always use `minmax(0, 1fr)`; every grid child has `min-width: 0`.
- Auxiliary source/configuration regions offer an explicit collapse control. When width is constrained, they default to compact while preserving a visible reopen control.
- Empty states must size to their panel, not force an arbitrary 500–700px blank canvas.

Required viewport checks: 320, 375, 414, 768, 1024, 1440 and 1600px.

## 4. Components

### Buttons

- Minimum target: 44×44px.
- Primary: solid `--ui-accent`, white text, no gradient.
- Secondary: warm subtle surface with strong text.
- Ghost/tool: transparent or white with a 1px border.
- Destructive: danger text and soft danger hover; destructive confirmation remains explicit.
- Loading keeps the button width stable, sets `aria-busy`, and never shifts surrounding controls.
- Hover/focus duration: 160–200ms; no translate/scale animation.

### Inputs

- Default height: 44px; horizontal padding 12px.
- Visible label is required; placeholder is supporting copy only.
- Border uses `--ui-border-strong`; focus uses accent border plus a 3px ring.
- Selects and long option labels use `min-width: 0` and `text-overflow: ellipsis`.
- Checkbox and radio targets are wrapped in a clickable 44px minimum row.
- Textarea line-height is 1.65 and can resize vertically.

### Panels and cards

- Major panels share the same border, radius and header padding.
- Lists use 12–16px row padding and 12px gaps; metadata stays at 12px or larger.
- Active rows use accent-soft background plus accent border, not a purple glow.
- Empty states use a quiet outline icon, a direct title and one sentence of guidance.

### Navigation

- One consistent Lucide-style outline SVG set, 18–20px; no emoji or arbitrary text glyph icons.
- Active navigation uses subtle warm fill and a 3px accent indicator.
- Group headings are collapsible buttons with `aria-expanded`.
- Mobile drawer traps no content behind it and closes after route selection or Escape.

### Progress and workflow

- A workflow card has the same height within its row.
- Current, completed, optional and error states always include textual labels.
- Dense stage maps collapse descriptions progressively; they do not create one tall card beside an empty canvas.

## 5. Motion and accessibility

- Functional transitions only: color, border, background and opacity; 160–220ms.
- Respect `prefers-reduced-motion: reduce`; disable smooth scroll and nonessential animation.
- Keyboard focus must always remain visible.
- Normal text contrast ≥ 4.5:1; large text ≥ 3:1.
- Icon-only controls require an accessible name and tooltip/title.
- All images need useful alt text unless purely decorative.
- Do not disable browser zoom.

## 6. Forbidden patterns

- Purple/blue gradients, neon, glass blur and decorative radial backgrounds.
- Emoji as interface icons.
- Body or metadata text below 12px.
- Fixed pixel content widths that exceed the viewport.
- Whole-page horizontal scrolling.
- Cards with mismatched heights in the same workflow row.
- Configuration rails that permanently consume the main editor width.
- Placeholder-only fields, hidden focus rings, hover-only actions or color-only status.
- Animating width/height or moving controls on hover.

## 7. Pre-delivery checklist

- [ ] All active pages use the shared warm tokens and one icon family.
- [ ] All buttons/inputs meet 44px targets and share radii/typography.
- [ ] Sidebar, source rail and configuration regions collapse and reopen correctly.
- [ ] No page-level horizontal overflow at required viewports.
- [ ] Workflow rows have aligned heights and readable state text.
- [ ] Keyboard navigation, focus and Escape behavior work.
- [ ] Reduced-motion mode is respected.
- [ ] Console has no errors or warnings while switching every view.
- [ ] Long labels, empty data, populated data and loading states are all usable.
- [ ] 375px, 768px, 1024px and 1440px screenshots pass visual review.
