# Theming

## The agent and customer app (/helpdesk)

`flux_helpdesk/public/css/flux-theme.css`, added to the page by `flux_helpdesk/theme.py`.

Helpdesk is built with frappe-ui, which takes every colour from CSS variables:

| Variables | Used for |
|---|---|
| `--surface-base`, `--surface-gray-1…10`, `--surface-sidebar`, `--surface-elevation-*` | backgrounds, panels, sidebar, popovers |
| `--ink-gray-1…9`, `--ink-base` | text |
| `--outline-gray-1…5`, `--outline-elevation-*` | borders |
| `--ink-blue-link`, `--focus-*` | links and focus rings |

Light values sit on `:root`, dark values on `[data-theme="dark"]`. The theme keeps Helpdesk's lightness steps and adds Flux's navy hue, so contrast stays as Helpdesk designed it. Primary buttons are frappe-ui's solid gray button (`bg-surface-gray-10`), which the theme turns Flux blue.

Settings: **Use the Flux theme** (on/off) and **Dark mode by default**. Default dark only applies to people who never chose a theme; the toggle in Helpdesk still works.

Fonts: Figtree for text and IBM Plex Mono for code, both open-licensed and served from this app. Inter stays as the fallback for scripts Figtree lacks.

## /support

`www/support/index.html`, `public/css/support.css` and `public/js/support.js`. It uses the same palette as runonflux.com: base `#0c0c18`, panels `#131320`, text `#d1d2db`, primary `#2656d7`, secondary `#5679ff`, and the cut-corner panel shape.

## Login and other Frappe pages

`public/css/flux-web.css`, loaded with `web_include_css`.

## Brand assets

`public/images`: the Flux icon and logo for dark and light backgrounds. The Flux name and logo are trademarks and are not covered by this repository's AGPL licence.
