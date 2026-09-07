# Top Ten Sports UI/UX Standards

These are persistent project instructions for all UI work in this repository.

## Product standard

The interface must feel sharp, polished, modern, simple, intentional, responsive,
easy to understand, and visually consistent. Favor clarity over decoration. Every
visual choice should improve comprehension, hierarchy, navigation, usability,
feedback, discoverability, consistency, or visual quality.

Treat the application as one design system rather than a collection of separately
styled pages. Inspect existing tokens, components, and patterns before creating new
ones. Centralize shared decisions and avoid page-specific hacks, duplicated markup,
scattered hard-coded values, and unexplained magic numbers.

## System foundations

- Express recurring colors, typography, spacing, radii, shadows, transitions,
  breakpoints, and icon sizes as reusable tokens whenever practical.
- Give colors semantic roles: background, surface, text, border, action, selected,
  disabled, success, warning, error, and focus. Avoid near-duplicate shades.
- Maintain accessible contrast and never rely on color alone for critical meaning.
- Use a restrained type scale with clear roles for page titles, section titles,
  card headings, body text, labels, metadata, buttons, statistics, and ranks.
- Treat numeric sports data as first-class UI: use tabular numerals, consistent
  alignment, and predictable formatting for rankings, scores, records, and rates.
- Use a small, deliberate spacing scale. Related elements sit closer together;
  separate sections receive more space. Repeated components must align precisely.
- Maintain one coherent shape language, border treatment, and elevation model.
  Reserve strong shadows for elements that genuinely sit above the interface.

## Components and interaction

- Reuse primitives for buttons, cards, inputs, search, dropdowns, tabs, badges,
  tables, lists, dialogs, menus, loading states, empty states, and errors.
- Create named component variants instead of accumulating one-off overrides.
- Maintain clear action hierarchy: primary, secondary, tertiary, and destructive
  controls must not compete visually.
- Account for default, hover, active, selected, focus-visible, disabled, loading,
  success, and error states where relevant. Respect reduced-motion preferences.
- Forms need persistent labels, consistent control sizes, clear validation, and
  visible focus. Filters must expose active state and an understandable reset path.
- Loading, empty, and error states must explain what is happening and what the user
  can do next; never show raw technical errors to normal users.

## Icons and media

- Use a consistent icon family with matching stroke weight, fill behavior,
  proportions, corner treatment, visual weight, sizing, and alignment.
- Icons should improve recognition or comprehension, not add decoration.
- Custom icons must be reusable vectors, inherit colors when appropriate, and
  remain recognizable at their intended rendered size. Avoid duplicate SVG markup.
- Define predictable image and logo behavior for aspect ratio, cropping, fallbacks,
  sizing, and alignment. Branding complements the product system rather than
  replacing it.

## Layout and sports data

- Organize screens by information priority, not request order. Avoid card soup,
  excessive borders, repeated labels, unnecessary gradients, and empty decoration.
- Use tables for precise column comparison and cards/lists when identity or visual
  content is primary. Establish shared patterns for teams, players, rankings,
  scores, records, statistics, schedules, trends, and status.
- Balance information density: keep primary information visible, group related
  details, and reveal secondary information when useful.
- Selected navigation, tabs, filters, teams, and items must be immediately clear
  through more than a subtle color shift.

## Responsive behavior

Design desktop and mobile behavior together. Decide what wraps, stacks, shrinks,
hides, or changes presentation at each breakpoint. Preserve readable text,
important actions, touch-friendly controls, and information priority. Avoid
horizontal overflow and do not treat mobile as a scaled-down desktop page.

## Implementation workflow

For every visual request:

1. Decide whether it is local or system-wide.
2. Identify the token, primitive, or component that should control it.
3. Check equivalent components and responsive/accessibility implications.
4. Prefer a clean extension of the system over a one-off override.
5. Implement appropriate interaction states, not only the static screenshot.
6. Visually inspect the rendered result at its intended size and on mobile.
7. Fix adjacent obvious alignment, wrapping, contrast, and consistency problems.
8. Run relevant automated tests before considering the work complete.

Translate subjective requests such as “sharp,” “clean,” “modern,” “premium,” or
“subtle” into concrete improvements to hierarchy, spacing, contrast, geometry,
density, and icon weight. Do not invent major branding preferences when none were
specified; follow the established system.

Prioritize decisions in this order: usability, clarity, consistency, hierarchy,
accessibility, responsiveness, polish, maintainability, performance, then novelty.

Before completion, confirm that hierarchy, spacing, typography, semantic colors,
icons, component reuse, interactive states, responsive behavior, accessibility,
visual restraint, and implementation quality all feel intentionally designed as
part of the same sports application.
