---
name: Modern Editorial System
colors:
  surface: '#ffffff'
  surface-dim: '#dadada'
  surface-bright: '#ffffff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f3f3f4'
  surface-container: '#eeeeee'
  surface-container-high: '#e8e8e8'
  surface-container-highest: '#e2e2e2'
  on-surface: '#1a1c1c'
  on-surface-variant: '#45474b'
  inverse-surface: '#2f3131'
  inverse-on-surface: '#f0f1f1'
  outline: '#76777c'
  outline-variant: '#c6c6cb'
  surface-tint: '#5a5e68'
  primary: '#171b24'
  on-primary: '#ffffff'
  primary-container: '#2c3039'
  on-primary-container: '#9498a3'
  inverse-primary: '#c3c6d2'
  secondary: '#5d5f5f'
  on-secondary: '#ffffff'
  secondary-container: '#dfe0e0'
  on-secondary-container: '#616363'
  tertiary: '#22190e'
  on-tertiary: '#ffffff'
  tertiary-container: '#382e21'
  on-tertiary-container: '#a49584'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#dfe2ee'
  primary-fixed-dim: '#c3c6d2'
  on-primary-fixed: '#181c24'
  on-primary-fixed-variant: '#434750'
  secondary-fixed: '#e2e2e2'
  secondary-fixed-dim: '#c6c6c7'
  on-secondary-fixed: '#1a1c1c'
  on-secondary-fixed-variant: '#454747'
  tertiary-fixed: '#f1e0cc'
  tertiary-fixed-dim: '#d5c4b1'
  on-tertiary-fixed: '#231a0e'
  on-tertiary-fixed-variant: '#504537'
  background: '#ffffff'
  on-background: '#1a1c1c'
  surface-variant: '#e2e2e2'
  text-main: '#2C3039'
  text-muted: '#959595'
  border-light: '#EEEEEE'
  background-subtle: '#ffffff'
typography:
  display-lg:
    fontFamily: Pretendard
    fontSize: 48px
    fontWeight: '700'
    lineHeight: '1.2'
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Pretendard
    fontSize: 32px
    fontWeight: '600'
    lineHeight: '1.3'
    letterSpacing: -0.01em
  headline-md:
    fontFamily: Pretendard
    fontSize: 24px
    fontWeight: '600'
    lineHeight: '1.4'
  body-lg:
    fontFamily: Pretendard
    fontSize: 18px
    fontWeight: '400'
    lineHeight: '1.8'
  body-md:
    fontFamily: Pretendard
    fontSize: 16px
    fontWeight: '400'
    lineHeight: '1.7'
  label-md:
    fontFamily: Pretendard
    fontSize: 14px
    fontWeight: '500'
    lineHeight: '1.2'
    letterSpacing: 0.02em
  headline-lg-mobile:
    fontFamily: Pretendard
    fontSize: 28px
    fontWeight: '600'
    lineHeight: '1.3'
rounded:
  control: 0.5rem   # 8px - 버튼·입력창·카드 (모두 동일)
  surface: 0.75rem  # 12px - 히어로/큰 이미지
  pill: 9999px      # 칩·태그·탭·아바타
spacing:
  container-max-width: 1140px
  editorial-width: 720px
  gutter: 24px
  margin-mobile: 20px
  stack-sm: 8px
  stack-md: 24px
  stack-lg: 64px
---

## Brand & Style

The design system is centered on the concept of "Editorial Clarity." It is designed for content-heavy platforms where the reading experience is paramount. By removing all decorative gradients and vibrant hues, the focus shifts entirely to the structure of information and the rhythm of typography.

The style is **Minimalist** with a strong emphasis on whitespace as a functional element rather than just a void. It draws inspiration from premium digital publishing houses, evoking an emotional response of calm, intellectual focus, and modern sophistication. Every element serves a purpose; if an element does not contribute to readability or navigation, it is removed.

## Colors

The color palette is strictly functional. The primary color, `#2C3039`, serves as the anchor for all text, iconography, and primary interactive states, providing high contrast against the `#FFFFFF` background for maximum accessibility.

We utilize a "White-First" approach. Gradients are entirely prohibited to maintain a flat, paper-like aesthetic. Neutral shades are used sparingly to define hierarchy:
- **Surface:** Pure white (`#FFFFFF`) for every structural area - page, sections, cards, header, inputs. No grey background zones.
- **State grey:** `#F5F5F5` is reserved for interactive states only - hover, active, chip/tag fills. Never a structural background.
- **No accent:** the palette is fully neutral (ink to grey ramp). There is no brand accent color; high-priority actions use the darkest ink fill, secondary actions a thin ink outline. The only color on screen comes from webtoon artwork.

## Typography

This design system employs **Pretendard** across all levels - one Korean-capable family that also carries full Latin glyphs, so Korean and English share the same rhythm without a font swap. The typography scale is aggressive in its use of line height (1.7 to 1.8 for body text) to ensure a comfortable reading experience similar to a physical book.

**Hierarchy Rules:**
- **Headlines:** Use tighter letter spacing and heavier weights to create a strong visual anchor.
- **Body:** Use regular weight with generous line-height. Never use pure black; stick to `#2C3039` to reduce eye strain.
- **Labels:** Small caps or medium weights are used for metadata and labels to differentiate them from body prose without needing color accents.

## 다국어 (i18n: 한 / 영)

The system targets at least Korean and English. Routing and message catalogs live in the app layer, not here; the design system owns only the typographic and layout consequences:

- **One family covers both:** Pretendard carries Hangul and full Latin glyphs, so there is no per-language font swap and the rhythm stays consistent across languages.
- **Tolerate text expansion:** the same label is often longer in English. Never size buttons or labels to fit Korean exactly - allow flex/wrapping and keep a min touch target (>= 44px).
- **Wrapping:** `word-break: keep-all` (Korean breaks between words, not mid-word) plus `overflow-wrap: break-word` (long Latin strings/URLs wrap). Set globally on `body`.
- **Numbers & prices:** tabular numerals (`font-feature-settings: "tnum"`) on prices, counts, and dates so figures align - important for a payment surface. Apply per-component, not globally.

## Layout & Spacing

The layout follows a **Fixed Grid** philosophy for desktop to control line lengths, which is critical for an editorial aesthetic. 

- **Desktop:** A 12-column grid with a 1140px max-width for general browsing, but a narrowed 720px central column for long-form reading.
- **Whitespace:** Use "Stack" units to create clear separation. A `stack-lg` (64px) should be used between major sections to allow the layout to "breathe."
- **Mobile:** Transition to a fluid single-column layout with 20px side margins. Horizontal padding should be generous to maintain the feeling of a premium margin.

## Elevation & Depth

To maintain the minimalist and flat aesthetic requested, the design system eschews traditional shadows entirely. Depth is communicated through:

1.  **Low-Contrast Outlines:** Instead of shadows, use 1px solid borders in `#EEEEEE` to define the boundaries of cards and input fields. This is the primary depth device.
2.  **Negative Space:** Separate and elevate elements with white space rather than visual weight; backgrounds stay pure white.
3.  **No tonal background zones:** depth never comes from grey fills behind content. `#F5F5F5` appears only as a transient interactive state (hover/active/chip), not as a layout layer.

## Shapes

The shape language is **uniformly rounded** - soft corners everywhere to match the friendly, comic-adjacent feel of a webtoon site, and to never mix sharp and round corners in one view. 

- **Controls (buttons · inputs · cards):** all use `control` (8px), the single most-used radius. **0px is not allowed** on any button, input, or card.
- **Large surfaces:** hero sections and large image containers use `surface` (12px).
- **Chips · tags · tabs · avatars:** use `pill` (fully rounded).
- **Dividers:** 1px hair-lines rather than thick blocks.

## Components

### Buttons
- **Primary:** Solid `#171B24` fill, white text, no border, `control` (8px) radius. Hover to `#2C3039`. No accent color, the primary action is simply the darkest thing on the page.
- **Secondary:** 1px `#2C3039` border, transparent fill, `control` (8px) radius.
- **Ghost:** No border, fill, or box - a text link that underlines on hover. Not rounded (it is not a box).

### Input Fields
- **Default:** white fill, 1px solid `#EEEEEE` border, `control` (8px) radius. Applies to every input - search box, login/signup fields, etc.
- **Focus:** border changes to 1px `#2C3039`. No outer glow or shadow.

### Cards
- White background, 1px `#EEEEEE` border, `control` (8px) radius. No shadow.
- Padding should be generous (typically 32px) to ensure content doesn't feel cramped.

### Lists & Navigation
- **Navigation:** Simple text links in `label-md`. Use ample tracking (letter spacing) for a premium feel.
- **List Items:** Separated by a 1px border-top in `#EEEEEE`. Remove the border for the first item in a set.

### Chips & Tags
- Small text, `pill` (fully rounded).
- Light grey fill (`#F5F5F5`, the state token) with no border. This distinguishes them from interactive buttons.