# Public design system

Authority: **Rahil Design 3.3.0**, the canonical public learning identity, “A student trynna learn.” This file records its application to this project; it does not establish another design system. Agent routing is in [AGENTS.md](AGENTS.md).

## Scope

The reconciliation SVG and responsive HTML table are light quantitative artifacts. Keep unresolved gaps and the funding-versus-settlement distinction visible.

## Tokens and type

Use [the canonical token snapshot](design/tokens.json). Pages use charcoal `#111214`, surface `#202124`, warm-white ink `#F5F5EF`, muted ink `#B7B8B1` and yellow `#FFE500` for primary actions, selection and focus. Quantitative figures use a light `#F5F5EF` surface, charcoal labels, gray `#52545A` context and `#C6C7BF` rules. Yellow is one meaningful emphasis, with a charcoal outline on quantitative marks; it is optional when no comparison needs highlighting.

Anton carries large condensed display headlines; IBM Plex Sans carries explanations, figure labels and controls. Code alone uses monospace. A data table does not need an Anton headline to conform. Existing SVGs declare IBM Plex Sans but may use their documented system fallback in image viewers that cannot load fonts; do not claim embedded-font fidelity where it is absent. The Sunday tracker embeds its fonts. Include upstream licenses with redistributed fonts; project code's license status is separate.

## Composition and evidence

Start with the reader's task and one supported point. Keep evidence, date, units and one material limitation near the result. Use Build Notes/student language, not an expert persona or unsupported first-person success claim. Preserve illustrative/synthetic labels. Use open reading sections and breathing room; no decorative cards, gradients, shadows or extra categorical colors inside figures.

Use tables for small lookup sets, direct labels, shared scales and zero-baseline bars. Keep real data, missing values and hypothetical scenarios distinct. Run the present-data figure-brief check on quantitative changes and inspect the exact artifact at desktop and 400px. Existing findings and accepted narrow-width limitations remain in the project's verification/figure brief.

## Interactive surfaces

Keep controls in sentence case, use visible yellow focus on dark surfaces and dark focus on light figures, and preserve native keyboard operation. Essential reading is static. Honor reduced motion, wrap long hashes/URLs, and provide useful empty/error states. Success/error colors are semantic and require readable contextual contrast plus text; color alone never establishes a result. A browser mockup does not establish protocol or native behavior.

## Change discipline

The token JSON is copied unchanged from the canonical skill. Update its version and this contract together when the shared system changes. Use existing renderers, preserve numeric/protocol outputs, and compare regenerated assets before publishing. Documentation and CLI output can conform without a new website or invented visual content.
