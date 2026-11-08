# Apollo UI refinement

Operate mode. Existing product, clinical meaning, text, functionality and typography remain the authority. This pass amplifies the existing identity rather than introducing a separate brand or new workflow.

Palette: record paper #f4f6f5, sheet #ffffff, ink #17221e, clinical teal #0b6e64, muted #52635c, rule #dbe3de. Existing caution and critical colors retain their meanings.

Type: IBM Plex Sans for controls and reading; Source Serif 4 for patient identity and section headings; IBM Plex Mono remains for actual logs/code. Fixed rem scale, body 16px, prose at most 68ch, numeric results tabular.

Layout A, selected:

    patient rail | patient name + age
    search       | section navigation
    case names   | patient brief     key concerns
                 | clinical record sections

Layout B, declined: a full-width patient ribbon above a tiled dashboard. It would make patient switching less immediate and introduce additional metrics/chrome without helping the existing workflow.

The sidebar carries the bold visual move through ink background and a clearly selected patient. Patient initials help scanning, without stock photos or fabricated status. The overview groups the brief and concerns, then presents diagnoses, medications and labs as a continuous record. Shared controls and restrained native SVG icons clarify navigation. No decorative graphs, new claims, simulated status, or clinical-data changes.

The initial concept's metric strip and a new cobalt palette were dropped: the strip repeated existing information; retaining teal keeps the already-established semantic and visual system coherent. Navigation, typography and grouping provide the extra character.

Verify all tabs, source dialogs, review/edit/finalize, keyboard focus, long names, 390/768/1440 layouts, contrast, reduced motion, and horizontal overflow. Use a single batched visual inspection, one fix batch and at most one confirmation round. Run the Impeccable detector once after the UI is complete.

## Verification

The initial batched inspection covers overview at 390, 768 and 1440 pixels, the Ask empty state and composer, tab navigation at 1024 pixels, patient search/switching, details disclosure, keyboard focus and reduced-motion behavior. Computed visible-text contrast passed on the overview. The correction batch makes the entire sidebar search surface a native label target.

Impeccable's manual detector was run once across `app/frontend-src/src`. It reported one existing `side-tab` warning at the Markdown blockquote's 3px quotation rule. This is a semantic quotation marker, not an accent on a generic card; retained as a narrow intentional exception. No detector scan was repeated.

The palette, patient data, clinical status meanings, endpoint behavior, review rules and source evidence remain unchanged. No new packages, fabricated clinical values, status badges or decorative charts were added by this UI pass.

Final confirmation: frontend lint/typecheck/build pass; analysis-review and extraction-review browser flows pass, including evidence dialogs, corrections, finalization, record refresh and persistence. Desktop/mobile/tablet renders were inspected in two bounded rounds. The README workspace screenshot reflects the refreshed UI.
