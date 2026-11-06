---
name: Warm Growth Space
colors:
  surface: '#2E2821'
  surface-dim: '#17130f'
  surface-bright: '#3d3834'
  surface-container-lowest: '#110e0a'
  surface-container-low: '#1f1b17'
  surface-container: '#231f1b'
  surface-container-high: '#2e2925'
  surface-container-highest: '#39342f'
  on-surface: '#eae1da'
  on-surface-variant: '#dbc1b3'
  inverse-surface: '#eae1da'
  inverse-on-surface: '#34302b'
  outline: '#a38c7f'
  outline-variant: '#554338'
  surface-tint: '#ffb689'
  primary: '#ffb689'
  on-primary: '#512300'
  primary-container: '#f28c45'
  on-primary-container: '#622c00'
  inverse-primary: '#984800'
  secondary: '#9fd3a2'
  on-secondary: '#043916'
  secondary-container: '#23532c'
  on-secondary-container: '#91c594'
  tertiary: '#e7c362'
  on-tertiary: '#3d2e00'
  tertiary-container: '#c4a245'
  on-tertiary-container: '#4b3900'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#ffdbc8'
  primary-fixed-dim: '#ffb689'
  on-primary-fixed: '#311300'
  on-primary-fixed-variant: '#743500'
  secondary-fixed: '#baf0bc'
  secondary-fixed-dim: '#9fd3a2'
  on-secondary-fixed: '#002109'
  on-secondary-fixed-variant: '#20502a'
  tertiary-fixed: '#ffdf90'
  tertiary-fixed-dim: '#e7c362'
  on-tertiary-fixed: '#241a00'
  on-tertiary-fixed-variant: '#584400'
  background: '#17130f'
  on-background: '#eae1da'
  surface-variant: '#39342f'
  bg-elevated: '#241F1A'
  border: '#3E362C'
  text-primary: '#F3EDE3'
  text-secondary: '#B7AB9C'
  danger: '#D9604F'
  info: '#7FA8C9'
  accent-purple: '#A88BC4'
typography:
  display:
    fontFamily: Plus Jakarta Sans
    fontSize: 28px
    fontWeight: '700'
    lineHeight: 36px
  h1:
    fontFamily: Plus Jakarta Sans
    fontSize: 22px
    fontWeight: '700'
    lineHeight: 30px
  h2:
    fontFamily: Plus Jakarta Sans
    fontSize: 17px
    fontWeight: '600'
    lineHeight: 24px
  body-lg:
    fontFamily: Be Vietnam Pro
    fontSize: 15px
    fontWeight: '400'
    lineHeight: 22px
  caption:
    fontFamily: Be Vietnam Pro
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 18px
  micro:
    fontFamily: Be Vietnam Pro
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
  h1-mobile:
    fontFamily: Plus Jakarta Sans
    fontSize: 20px
    fontWeight: '700'
    lineHeight: 28px
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  base: 8px
  xs: 4px
  sm: 8px
  md: 12px
  lg: 16px
  xl: 24px
  xxl: 32px
  huge: 48px
  gutter-mobile: 12px
  gutter-desktop: 24px
---

## Brand & Style

The design system is built around the narrative of a **"Warm Growth Space."** It acknowledges the late-night, high-fatigue reality of parenting by providing a soothing, dark-mode baseline that reduces eye strain while maintaining a nurturing atmosphere. The brand personality is professional yet deeply empathetic—moving away from clinical, cold medical interfaces toward a cozy, supportive companion for early childhood development.

The visual style is a blend of **Modern Corporate** reliability and **Soft Minimalism**. It utilizes high-quality, localized typography and organic, rounded shapes to evoke safety and approachability. The design prioritizes "Data-Storytelling," transforming raw growth metrics into a visual diary of a child's milestones.

**Key Brand Pillars:**
- **Nurturing:** Warm tones and soft edges provide a sense of security.
- **Reliable:** High-contrast data visualization and tabular alignment ensure accuracy for health tracking.
- **Effortless:** One-handed ergonomics and high-contrast touch targets accommodate multitasking parents.

## Colors

The color palette is inspired by natural, organic food sources, specifically "Pumpkin Orange" and "Spinach Green." 

- **Primary (Pumpkin Orange):** Used for critical calls-to-action, active states, and primary growth chart lines. It provides warmth and high visibility against the dark background.
- **Secondary (Spinach Green):** Reserved for success states, healthy growth indicators, and "safe" food labels.
- **Tertiary (Custard Yellow):** Used for warnings, attention-required notifications, and intermediate milestones.
- **Neutral (Warm Charcoal):** The foundation of the "Growth Space." Unlike pure black, this warm charcoal prevents harsh contrast, making the UI feel more like an organic environment than a digital tool.

The system supports a switchable light mode where the primary orange remains constant, but the background shifts to a warm parchment white (`#FBF7F0`).

## Typography

The typography system prioritizes clarity and legibility for parents who may be viewing the screen under low-light conditions or while multi-tasking. 

- **Headlines:** Use **Plus Jakarta Sans** (mapping to Alibaba PuHuiTi for localized contexts) for a modern, slightly rounded, and friendly feel. 
- **Body & Labels:** Use **Be Vietnam Pro** (mapping to PingFang SC) for its exceptional legibility and neutral tone.
- **Tabular Data:** All numeric values—such as weight (kg), milk volume (ml), and age—must utilize `font-variant-numeric: tabular-nums`. This ensures that growth data aligns vertically in dashboards and lists for easy comparison.
- **Hierarchy:** Display sizes are reserved for "Growth Imprints" (milestone numbers), while H1 and H2 define page and module structures.

## Layout & Spacing

The system follows an **8px base unit** rhythm, creating a predictable and harmonious vertical flow. 

- **Layout Model:** A 12-column fluid grid system is used.
- **Mobile (<768px):** Single column layout. Components use a 12px gutter and 16px side margins to maximize screen real estate while maintaining touch safety.
- **Tablet (768px - 1199px):** Two-column grid for dashboard modules and recipe lists.
- **Desktop (≥1200px):** Three to four columns depending on content density.
- **Ergonomics:** All primary interactive elements (navigation, "+" quick action) are anchored to the bottom 30% of the screen to facilitate one-handed mobile use.

## Elevation & Depth

In alignment with the dark-mode primary theme, this design system avoids traditional heavy drop shadows, which can appear "dirty" on dark surfaces. 

Instead, depth is conveyed through **Tonal Layering** and **Highlight Borders**:
- **Level 0 (Background):** `#1B1713` - The deepest layer.
- **Level 1 (Cards/Surfaces):** `#241F1A` - Uses a 1px top-aligned stroke (`--color-border`) to create a "shelf" effect, simulating light hitting the top edge of a physical card.
- **Level 2 (Modals/Popovers):** These use a slightly lighter surface (`#2E2821`) and a very soft, low-opacity ambient glow (0px 8px 24px rgba(0,0,0,0.4)) to separate them from the content beneath.

Visual hierarchy is reinforced by Z-index management: Modals > Popovers > Floating Action Buttons > Standard Content.

## Shapes

The shape language is consistently **Rounded**, reinforcing the "nurturing" brand personality. 

- **Standard Radius (12px):** Applied to primary buttons, content cards, and recipe images. This provides a soft, friendly appearance without appearing juvenile.
- **Large Radius (20px):** Reserved for containers that "hold" the user, such as Modals, bottom sheets, and large image-focused cards.
- **Small Radius (6px):** Used for micro-elements like input fields and status tags (badges) to maintain internal structural integrity.
- **Iconography:** All custom icons use a 1.5px stroke width with rounded end-caps and joins to match the component curvature.

## Components

- **Buttons:** Primary buttons use a full-color fill (`--color-primary`) with rounded-md (12px) corners. Secondary buttons use an outlined style with a 1.5px stroke.
- **Chips & Tags:** Small, low-profile elements used for dietary labels (e.g., "Iron-rich"). Use `--radius-sm` (6px) and subtle background tints derived from status colors.
- **Cards:** The primary container for records and recipes. Should have 16px internal padding and a subtle highlight border. Aspect ratios for recipe images are fixed at 4:3.
- **Inputs:** Fields use the `#2E2821` surface color to appear "sunken" into the card. They feature a 6px corner radius and a clear focus state using the primary orange stroke.
- **Checkboxes/Radios:** Highly rounded (Radios) or softly rounded (Checkboxes) with a generous 44px touch target area for easy interaction.
- **Growth Imprint:** A specialized circular progress component used for age and milestone tracking. It uses a high-contrast stroke and large `Display` typography for the central data point.
- **Feedback:** Toasts should slide from the top, appearing for exactly 2 seconds, while Skeleton Screens are required for all chart and list loading states to maintain perceived performance.