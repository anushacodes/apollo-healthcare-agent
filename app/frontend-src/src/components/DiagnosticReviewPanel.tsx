import type { DiagnosticReview } from '../types'

const STAGES: Record<string, string> = {
  assessment_a: 'Broad differential assessment',
  assessment_b: 'Competing explanations assessment',
  critique: 'Evidence and assumptions check',
  synthesis: 'Combined differential',
}

export function DiagnosticReviewPanel({ review }: { review: DiagnosticReview }) {
  const issues = [...new Set([...review.disagreements, ...(review.concerns || []), ...review.missing_information])]
  return <section className="panel space-y-4" aria-labelledby="diagnostic-review-title">
    <div>
      <h3 id="diagnostic-review-title" className="font-serif text-xl font-semibold">Extended diagnostic review</h3>
      <p className="mt-1 max-w-[70ch] text-sm text-muted">{review.status === 'complete'
        ? `Four review steps completed${review.cached ? ' · Saved result reused' : ''}. Suggestions still require human review.`
        : 'The extended review could not complete. Record diagnoses shown below are a fallback. Review the record manually or run the analysis again.'}</p>
    </div>
    {review.status === 'unavailable' && <p role="status" className="text-sm text-caution">{review.failure_code === 'context_too_large'
      ? 'This record exceeds the extended review limit. Use standard analysis or review a smaller record.'
      : review.failure_code === 'review_disabled'
        ? 'Extended review is no longer enabled on this server. Use standard analysis.'
        : 'A provider request or evidence check failed. A completed diagnostic assessment is unavailable.'}</p>}
    {!!issues.length && <div>
      <h4 className="font-medium">Uncertainty and missing information</h4>
      <ul className="mt-2 list-disc space-y-2 pl-5 leading-7">{issues.map(issue => <li key={issue}>{issue}</li>)}</ul>
    </div>}
    {!!review.stages.length && <details className="border-t border-rule pt-4">
      <summary className="cursor-pointer text-sm text-muted">View assessment summaries{review.status !== 'complete' ? ' · Incomplete review' : ''}</summary>
      <ol className="mt-4 space-y-4">{review.stages.map(stage => <li key={stage.stage}>
        <h4 className="font-medium">{STAGES[stage.stage] || stage.stage}</h4>
        {stage.output.primary_diagnosis && <p className="mt-1">Suggested primary: {stage.output.primary_diagnosis}</p>}
        {stage.output.differential_notes && <p className="mt-1 max-w-[70ch] text-sm leading-6 text-muted">{stage.output.differential_notes}</p>}
        {!!stage.output.concerns?.length && <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">{stage.output.concerns.map(item => <li key={item}>{item}</li>)}</ul>}
      </li>)}</ol>
    </details>}
  </section>
}
