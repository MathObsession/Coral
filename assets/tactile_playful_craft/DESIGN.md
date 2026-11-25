---
name: Tactile Playful Craft
colors:
  surface: '#fbf9f8'
  surface-dim: '#dbd9d9'
  surface-bright: '#fbf9f8'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f5f3f3'
  surface-container: '#efeded'
  surface-container-high: '#eae8e7'
  surface-container-highest: '#e4e2e2'
  on-surface: '#1b1c1c'
  on-surface-variant: '#3f4a36'
  inverse-surface: '#303030'
  inverse-on-surface: '#f2f0f0'
  outline: '#6f7b64'
  outline-variant: '#becbb1'
  surface-tint: '#2b6c00'
  primary: '#2b6c00'
  on-primary: '#ffffff'
  primary-container: '#58cc02'
  on-primary-container: '#1e5000'
  inverse-primary: '#6be026'
  secondary: '#8c5000'
  on-secondary: '#ffffff'
  secondary-container: '#fd9500'
  on-secondary-container: '#633700'
  tertiary: '#006590'
  on-tertiary: '#ffffff'
  tertiary-container: '#4abdff'
  on-tertiary-container: '#004a6b'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#87fe45'
  primary-fixed-dim: '#6be026'
  on-primary-fixed: '#082100'
  on-primary-fixed-variant: '#1f5100'
  secondary-fixed: '#ffdcbf'
  secondary-fixed-dim: '#ffb872'
  on-secondary-fixed: '#2d1600'
  on-secondary-fixed-variant: '#6a3b00'
  tertiary-fixed: '#c8e6ff'
  tertiary-fixed-dim: '#88ceff'
  on-tertiary-fixed: '#001e2e'
  on-tertiary-fixed-variant: '#004c6e'
  background: '#fbf9f8'
  on-background: '#1b1c1c'
  surface-variant: '#e4e2e2'
  primary-shade: '#46A302'
  secondary-shade: '#E07800'
  tertiary-shade: '#1899D6'
  accent-yellow: '#FFC800'
  accent-yellow-shade: '#E5A500'
  accent-red: '#FF4B4B'
  accent-red-shade: '#D33131'
  surface-canvas: '#F7F7F7'
  surface-card: '#FFFFFF'
  border-subtle: '#E5E5E5'
  border-bold: '#CECECE'
  text-muted: '#777777'
  text-disabled: '#AFAFAF'
typography:
  display-hero:
    fontFamily: Plus Jakarta Sans
    fontSize: 48px
    fontWeight: '800'
    lineHeight: 56px
    letterSpacing: -0.03em
  display-hero-mobile:
    fontFamily: Plus Jakarta Sans
    fontSize: 36px
    fontWeight: '800'
    lineHeight: 44px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Plus Jakarta Sans
    fontSize: 32px
    fontWeight: '800'
    lineHeight: 40px
    letterSpacing: -0.02em
  headline-lg-mobile:
    fontFamily: Plus Jakarta Sans
    fontSize: 26px
    fontWeight: '800'
    lineHeight: 34px
    letterSpacing: -0.01em
  headline-md:
    fontFamily: Plus Jakarta Sans
    fontSize: 24px
    fontWeight: '700'
    lineHeight: 32px
    letterSpacing: -0.01em
  headline-sm:
    fontFamily: Plus Jakarta Sans
    fontSize: 20px
    fontWeight: '700'
    lineHeight: 28px
  title-md:
    fontFamily: Plus Jakarta Sans
    fontSize: 17px
    fontWeight: '700'
    lineHeight: 24px
  body-lg:
    fontFamily: Plus Jakarta Sans
    fontSize: 17px
    fontWeight: '600'
    lineHeight: 26px
  body-md:
    fontFamily: Plus Jakarta Sans
    fontSize: 15px
    fontWeight: '500'
    lineHeight: 22px
  body-sm:
    fontFamily: Plus Jakarta Sans
    fontSize: 13px
    fontWeight: '500'
    lineHeight: 18px
  label-lg:
    fontFamily: Plus Jakarta Sans
    fontSize: 14px
    fontWeight: '800'
    lineHeight: 18px
    letterSpacing: 0.04em
  label-md:
    fontFamily: Plus Jakarta Sans
    fontSize: 12px
    fontWeight: '800'
    lineHeight: 16px
    letterSpacing: 0.05em
  label-sm:
    fontFamily: Plus Jakarta Sans
    fontSize: 11px
    fontWeight: '700'
    lineHeight: 14px
    letterSpacing: 0.04em
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  gutter: 1.5rem
  gutter-mobile: 1rem
  margin: 2rem
  margin-mobile: 1rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 1rem
  space-lg: 1.5rem
  space-xl: 2rem
  space-2xl: 3rem
---

## Brand & Style

The design system establishes a high-energy, friendly, and physically grounded workspace experience. It rejects sterile SaaS minimalism, generic AI gradients, and floaty glassmorphism in favor of deliberate tactility, thick structural outlines, and expressive warmth.

### Emotional Target & Audience
- **Feeling:** Joyful productivity, momentum, tangibility, and immediate satisfaction upon interaction.
- **Audience:** Collaborative teams and modern knowledge workers who value approachable, punchy tools over clinical enterprise dashboards.
- **Core Aesthetic:** Tactile Pop Brutalism meets modern character-driven craft. Elements look and behave like real physical plastic tokens, physical punch-cards, and mechanical keys.

### Design Principles
- **Extruded Physics:** Every interactive element has physical depth. Buttons have solid underside bevels (`box-shadow: 0 4px 0 [shade]` or `border-b-4`) that physically depress on click (`translate-y-1` with 0px offset).
- **Sturdy Geometry:** UI components use thick, confident 2px borders, large corner radiuses (`rounded-2xl` to `rounded-3xl`), and generous interior cushioning.
- **Punchy Contrast:** Clean milky-white paper surfaces rest on warm cream or soft stone canvases, punctuated by saturated primary hues (Lime Green, Hermes Fox Orange, Vivid Sky Blue, and Canary Yellow).
- **Human Microcopy:** Direct, active verbs and playful clarity. No buzzwords, no decorative sparkles, and no ambiguous icon-only interfaces without clear labels.

## Colors

The color palette is built on high-saturation comic-book vibrancy balanced against milk-white cards and warm stone backgrounds. 

### Color Strategy
- **Primary (`#58CC02` / Shade `#46A302`):** Reserved for primary success milestones, main action confirmations, and positive progress tracking. Always paired with its darker shade for the extruded 3D base.
- **Secondary (`#FF9600` / Shade `#E07800`):** The signature Hermes Fox accent used for primary workspace conversions, urgency, high-priority notifications, and energetic calls-to-action.
- **Tertiary (`#1CB0F6` / Shade `#1899D6`):** Information badges, interactive links, secondary flows, and live presence indicators.
- **Accents:**
  - **Canary Yellow (`#FFC800` / Shade `#E5A500`):** Streak meters, attention alerts, and achievements.
  - **Punch Red (`#FF4B4B` / Shade `#D33131`):** Destructive actions, system errors, and critical task warnings.
- **Neutrals & Structural Borders:**
  - Canvas surface is set to `#F7F7F7` to let pure `#FFFFFF` cards pop with dimension.
  - Structural borders use `#E5E5E5` for standard division and `#CECECE` for active containers, maintaining high visibility without muddying the interface.
  - Primary text is deep charcoal (`#4B4B4B`), avoiding clinical jet black for a warmer, friendlier print-like quality.

## Typography

The typography leverages `Plus Jakarta Sans` across all styles to deliver a chunky, muscular geometric grotesque with human warmth. Weights are skewed heavier than traditional enterprise systems: titles command attention at weight `800` (ExtraBold), while body and utility labels anchor at weights `600` and `800`.

### Type Guidance
- **Uppercase Labels:** System badges, button labels, and milestone trackers use uppercase tracking with `label-lg` or `label-md` to maintain legibility and emphasize punchy game-like micro-interactions.
- **Rhythm & Weight:** Never drop below weight `500` (Medium) for body copy. Thin or light font weights are strictly prohibited to prevent washed-out readability against bold containers.
- **Display Numbers:** Numeric counters, task points, and sprint metrics utilize display weights with tight letter-spacing for high visual impact.

## Layout & Spacing

The layout is built upon a sturdy 12-column fluid grid on desktop and a continuous 4-column block layout on mobile. Spacing leans generous and modular, mirroring toy brick assemblies.

### Grid & Breakpoints
- **Mobile (< 768px):** 4-column layout with `margin-mobile` (1rem / 16px) and `gutter-mobile` (1rem / 16px). All full-width action drawers and persistent bottom navbars span edge-to-edge with 16px internal padding.
- **Tablet (768px - 1024px):** 8-column layout with 24px margins and gutters. Sidebars collapse to icon-and-label compact vertical trays.
- **Desktop (> 1024px):** 12-column grid constrained to a maximum content container width of 1280px to prevent interface stretching. Left navigation rail is fixed at 256px.

### Spacing Philosophy
- Elements never float in empty void; they nest inside grounded containers with deliberate internal padding (`space-lg` for cards, `space-md` for form fields).
- Vertical margins between distinct modules are locked to `space-xl` (32px) or `space-2xl` (48px) to establish clean, confident rhythm.

## Elevation & Depth

This design system completely replaces fuzzy, blurred, or ambient shadows with physical, mechanical offsets. Depth is established through hard bevels, distinct container borders, and physical compression.

### The Bevel Depth Hierarchy
- **Level 0 (Flat / Inset):** Subtle background panels, progress bar tracks, and disabled states. Set flat on `#F7F7F7` or `#E5E5E5` with an optional 2px interior solid border.
- **Level 1 (Grounded Cards):** Pure white `#FFFFFF` cards framed by a solid `2px solid #E5E5E5` border and a solid lower offset `box-shadow: 0 4px 0 #E5E5E5`.
- **Level 2 (Interactive Elements & Buttons):** Colored interactive buttons use an extruded 4px physical bottom shade: `box-shadow: 0 4px 0 [darker-shade-color]`. Hover states produce micro-lift (`translate-y-[-1px]`, 5px shade), while the active click state physically drops the element (`translate-y-[4px]` with `box-shadow: 0 0 0 transparent`).
- **Level 3 (Modals & Popovers):** Elevated dialogs feature a `3px solid #CECECE` border with a crisp, non-diffuse hard offset shadow: `box-shadow: 0 8px 0 rgba(75, 75, 75, 0.15)`. No gradient mesh or backdrop-blur glow is permitted.

## Shapes

The shape system is friendly, soft, and approachable, featuring rounded forms without losing architectural structure.

### Radius Rules
- **Base Components (`roundedness: 2` = 0.5rem / 8px):** Checkboxes, utility tags, small input icons, and micro tooltips.
- **Standard Cards & Form Inputs (`rounded-2xl` = 1rem / 16px):** Core container cards, text entry fields, modular widgets, and contextual flyouts.
- **Interactive Action Buttons & Hero Cards (`rounded-2xl` to `rounded-3xl` = 16px to 24px):** Primary interactive targets have extra-rounded corners for an organic, tactile aesthetic.
- **Pills (`rounded-full`):** Badges, chip filters, status meters, user presence avatars, and count indicators always take a pill shape.

## Components

### Buttons
- **Primary (Green Milestone Action):** Background `#58CC02`, text `#FFFFFF`, border-radius 16px, `border-2 border-[#46A302]`, `box-shadow: 0 4px 0 #46A302`.
  - *Active:* `translate-y-1`, `box-shadow: 0 0 0 #46A302`.
- **Secondary (Hermes Orange Action):** Background `#FF9600`, text `#FFFFFF`, border-radius 16px, `border-2 border-[#E07800]`, `box-shadow: 0 4px 0 #E07800`.
  - *Active:* `translate-y-1`, `box-shadow: 0 0 0 #E07800`.
- **Tertiary / Utility (Sky Blue):** Background `#1CB0F6`, text `#FFFFFF`, border-radius 16px, `border-2 border-[#1899D6]`, `box-shadow: 0 4px 0 #1899D6`.
- **Ghost / Outline Button:** Background `#FFFFFF`, text `#4B4B4B`, `border-2 border-[#E5E5E5]`, `box-shadow: 0 4px 0 #E5E5E5`.
  - *Hover:* Background `#F7F7F7`, `border-color: #CECECE`, `box-shadow: 0 4px 0 #CECECE`.
  - *Active:* `translate-y-1`, `box-shadow: 0 0 0 transparent`.

### Cards & Panels
- **Standard Card:** Milky white `#FFFFFF` surface, `2px solid #E5E5E5` border, `rounded-2xl`, padded with `space-lg`. Bottom offset `box-shadow: 0 4px 0 #E5E5E5`.
- **Selected / Active Card:** `#FFFFFF` surface with `2px solid #58CC02` or `#1CB0F6`, `box-shadow: 0 4px 0 [border-color]`, background lightly tinted with 4% hue overlay.

### Input Fields & Controls
- **Text Inputs:** Background `#F7F7F7`, text `#4B4B4B`, font weight 600, `2px solid #E5E5E5`, rounded 16px, padded with 14px 16px.
  - *Focus:* Background `#FFFFFF`, `border-2 border-[#1CB0F6]`, `box-shadow: 0 3px 0 #1CB0F6`, outline none.
- **Checkboxes & Radios:** Chunky 24px x 24px box, `2px solid #CECECE`, rounded 8px (checkbox) or full pill (radio). On checked state: background `#58CC02`, border `#46A302`, displaying a bold white checkmark with `box-shadow: 0 2px 0 #46A302`.

### Chips & Badges
- **Pill Badge:** Bold uppercase font (`label-md`), height 28px, padding 4px 12px, rounded-full.
  - *Sprint Active:* Background `#1CB0F6`, text `#FFFFFF`, `border-b-2 border-[#1899D6]`.
  - *Milestone Completed:* Background `#58CC02`, text `#FFFFFF`, `border-b-2 border-[#46A302]`.
  - *Urgent Fox Alert:* Background `#FF9600`, text `#FFFFFF`, `border-b-2 border-[#E07800]`.

### Lists & Activity Feeds
- List items are separated by `2px solid #E5E5E5` dividers or organized as individual pill-shaped floating rows with `space-sm` gaps between them. Hovering an item applies a tactile push right (`translate-x-1`) and reveals a crisp border highlight.

### Progress Bars (Streak & Task Meters)
- Track is recessed: background `#E5E5E5`, height 16px, rounded-full with an inner shadow or inset feel.
- Fill bar: Vibrant `#58CC02` or `#FFC800` with rounded-full cap and a bright top highlight stroke creating a cylindrical, gummy look.