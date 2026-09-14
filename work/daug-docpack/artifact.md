# System Design 模板执行契约

## Reference

- Retained reference: `/Users/xbpd/.codex/plugins/cache/openai-curated-remote/openai-templates/0.1.1/skills/artifact-template-system-design/assets/reference.docx`
- SHA-256: `13504f6c221a42c1726460a9e865e563355539ff97d702d6c9b2267b4b261d76`
- Reference render: `work/daug-docpack/template-reference-render/page-1.png` through `page-7.png`
- Evidence: `work/daug-docpack/template-evidence/style.json` plus section, heading, image, field, footnote, and content-control audits captured in the task trace
- Page count: 7
- Section count: 1
- The retained file is read-only and must remain byte-for-byte unchanged.

## Page system

- Letter portrait, 8.50 by 11.00 inches.
- Margins: left 0.70, right 0.70, top 0.70, bottom 0.62 inches.
- One section with a first-page variant; header and footer are not linked to another section.
- The cover uses large top whitespace, a two-line title block, a three-column metadata row, and a two-column metadata table.
- Content pages use a wide single column and a centered recurring footer.
- The final document may exceed seven pages because the user requested a complete multi-part design package. It must retain the same page geometry, footer system, typography, table language, and section rhythm.

## Typography

- Embedded font family: Helvetica Neue and Helvetica Neue Light. Preserve the embedded font parts and relationships.
- Title role: 36 pt, left aligned, two lines; first line light weight, second line bold. The generated title text is black to satisfy the document creation standard while keeping the reference scale and spacing.
- Heading 1: 13.5 pt bold, black, keep with next, approximately 6.5 pt after.
- Heading 3 or subsection role: Helvetica Neue bold, approximately 11 pt, black, keep with next, approximately 4.5 pt after.
- Body: approximately 11 pt, color `233447`, 1.25 line spacing, approximately 5.5 pt after. Chinese runs may use a compatible CJK fallback while Latin text remains Helvetica Neue.
- Table header: dark navy fill `082A4A`, white bold text. Body rows alternate white and pale blue-gray. Borders remain light and visible.
- No decorative rule is placed directly under the title. No shaded callout boxes are introduced.

## Lists and tables

- Reuse the reference's bullet and alphabetic list numbering where practical.
- Tables use deliberate unequal column widths, vertically centered cells, expanding row heights, and repeating header rows when a table spans pages.
- Preserve the source's navy header, pale blue first-column or alternating-row treatment, white internal separators, and generous cell padding.
- Long explanatory material belongs in prose. Tables are reserved for comparable records, contracts, metrics, milestones, and risk matrices.

## Recurring components

- Cover title block and metadata table are editable.
- Footer text is editable and must read `Trace Derived Artifact Update Graph | Demo 技术方案` on content pages.
- The architecture figure slot is editable. Replace the source figure with a new diagram at the same approximate width, using the same navy and pale-blue visual language.
- Section headings, component tables, data-contract tables, operational-readiness tables, alternatives, and milestone tables may be cloned to support the requested content.
- Preserve first-page header/footer behavior, embedded fonts, style definitions, numbering, theme, and relationship structure unless an intentional body expansion requires a new relationship.

## Content flow

1. Cover and document control
2. Executive summary and decision boundary
3. Problem definition and related work
4. Goals, non-goals, and design principles
5. System architecture and lifecycle
6. Data model, scoring, APIs, and consistency guarantees
7. MVP and demo implementation plan
8. Evaluation and ablation plan
9. Risks, security, and governance
10. Research and paper roadmap
11. Demo runbook, acceptance checklist, open questions, and references

## Slot map

- `word/document.xml` cover title paragraphs using `Title`: rewrite.
- Cover status, owner, and date table: rewrite; do not invent personal names.
- Cover authors, reviewers, related docs, and scope table: rewrite with role labels and package filenames.
- Existing Heading 1 sections and body placeholders: replace and expand using cloned source patterns.
- Goals and non-goals table: rewrite.
- Architecture image relationship and caption: replace with the task-local generated diagram and caption.
- Core component, data contract, consistency, operational, alternatives, and milestone tables: rewrite; clone patterns as needed.
- Open questions: rewrite as explicit owner decisions, not unresolved implementation facts.
- `word/footer1.xml` and `word/footer2.xml`: rewrite organization placeholder only; preserve paragraph/run properties.
- Headers, embedded fonts, theme, styles, numbering, and footnote infrastructure: preserve-only.

## Package preservation

- Baseline package contains 24 parts, including two headers, two footers, footnotes, numbering, settings, font table and relationships, styles, document relationships, theme, one image, eight embedded font files, package relationships, and content types.
- Preserve-only classes: `word/fonts/*`, `word/theme/theme1.xml`, `word/fontTable.xml`, `word/_rels/fontTable.xml.rels`, `word/header*.xml`, `word/numbering.xml`, `word/styles.xml`, and package-level relationships unless required for a verified new body asset.
- Editable classes: `word/document.xml`, the architecture image part, footer text nodes, `word/_rels/document.xml.rels` only when adding the replacement image, and `[Content_Types].xml` only if a new supported media type is required.
- No comments or content controls exist. No field codes exist in the reference.
- The reference contains footnote infrastructure and a body footnote reference. The generated document may omit the sample footnote reference but must not silently delete unrelated package support if the save path preserves it.

## Fidelity gates

- Recheck the retained SHA-256 before and after authoring.
- Render the final DOCX and inspect every page at 100 percent zoom.
- Confirm Letter geometry, margin rhythm, title hierarchy, table colors, cell padding, footer position, and Chinese glyph coverage.
- Compare package-part inventories and investigate any missing preserved part.
- Confirm no placeholder brackets, citation tokens, clipped text, overlapping objects, broken tables, orphan headings, or large unexplained blank pages remain.
- Run section, style, heading, image, field, footnote, and content-control audits on the final file.
- The final deliverable is a proposal and implementation plan. It must not present suggested targets, synthetic fixtures, or future experiments as completed evidence.
