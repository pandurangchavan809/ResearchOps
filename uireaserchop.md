# ResearchOps UI handoff

Use [reference.md](./reference.md) as the visual reference. Preserve its quiet, ChatGPT-style conversation layout, neutral surfaces, compact controls, restrained accent use, and responsive behavior. Adapt all content and interactions to ResearchOps; do not copy DataPilot or RAGDocs branding, database concepts, or unsupported behaviors.

## Product experience

- **Normal mode:** show a clear answer with inline citations and expandable source evidence.
- **Report mode:** the user explicitly clicks **Generate Report** after receiving an answer. Show progress and a download action only when the backend supports those states.
- Do not auto-create a PDF, imply background research is complete before the API says so, or invent model names, source counts, trace steps, or timings.

## Layout

- Full-height two-column workspace: collapsible ~280px history/sidebar and a flexible main column.
- On narrow screens, use a slide-in sidebar drawer with an overlay.
- Main column has a compact header, scrollable conversation, and composer anchored at the bottom.
- Center the conversation and composer in a readable column (around `max-width: 48rem`).
- Empty state includes a simple ResearchOps mark, short headline, and a few example technical research questions.

## Visual system

- Minimal, professional chat UI inspired by the reference. Use white and zinc-like neutral surfaces, thin borders, subtle shadows, and generous whitespace.
- Use one restrained indigo/cyan accent family for the app UI. Reserve pink and sky-blue accents for generated PDF reports, as specified in [project.md](./project.md).
- Rounded controls and cards; avoid dense dashboard chrome and decorative gradients beyond a small brand mark or highlight.
- Body copy should be comfortable to read, citations secondary but legible, and code/comparison details use clear technical typography.
- Support light and dark themes, keyboard navigation, visible focus states, and phone widths without horizontal scrolling.

## Conversation components

1. **Research question:** right-aligned, compact user message.
2. **Answer:** unboxed assistant content with readable Markdown, headings, lists, code, and tables.
3. **Evidence citations:** inline numbered or linked references. An expandable source card shows title, publisher/domain, URL, date when available, and the excerpt supporting the claim.
4. **Research status:** show only real backend progress events. If there is no streaming/progress API, use a simple pending state and render the answer when complete.
5. **Composer:** auto-growing input, submit button, and a short scope hint. Disable submission only during real request constraints.
6. **Generate Report:** visible with a completed answer. It must remain a user-triggered action. Handle generating, ready/download, and error states from actual API responses.
7. **History/sidebar:** start a new research question and list saved sessions only after persistence exists. Do not show fake history.

## Answer structure

Let content follow the question, but favor:

- Direct answer
- Key findings
- Comparison table when useful
- Limitations or conflicting evidence
- Recommendation when the evidence supports one
- Sources

The UI should distinguish supported claims from uncertainty. Include a source panel and clear external-link affordances. Do not treat a model confidence score as proof.

## PDF report appearance

PDF pages use a separate fixed editorial system: white background, pink and sky-blue accents, professional typography, consistent margins, and repeated headers/footers with page numbers. Use a stable section sequence: Title, Executive Summary, Key Findings, Comparison Tables, Detailed Analysis, Recommendation, Sources. ReportLab Platypus handles flow and page breaks; tables must repeat header rows and split safely. Content may vary by research topic while the template controls spacing and page design.

## Reference adaptation checklist

- [ ] Keep the reference's simple chat-first composition and responsive sidebar behavior.
- [ ] Replace model picker behavior with only provider/model options the backend actually supports; omit the picker if selection is not implemented.
- [ ] Show source evidence instead of database/schema/result panels.
- [ ] Do not show a reasoning trace unless real progress events are returned.
- [ ] Keep PDF creation explicit and separate from the normal answer flow.
- [ ] Verify empty, loading, answer, source expansion, report-ready, and error states against real API behavior.
