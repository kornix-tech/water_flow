import type { StrictReadinessPlan, StrictReadinessTarget } from "../types";

function textValue(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  return String(value);
}

function isGateAllowed(target: StrictReadinessTarget): string {
  const value = target.strict_candidate_can_gate_suite;
  if (value === true || value === "true") {
    return "да";
  }
  if (value === false || value === "false") {
    return "нет";
  }
  return "-";
}

export function StrictReadinessPlanPanel({ plan }: { plan: StrictReadinessPlan | null }) {
  if (!plan) {
    return null;
  }

  const targets = plan.next_targets ?? [];
  const counts = plan.stage_counts ?? {};

  return (
    <section className="strict-plan-panel">
      <div className="suite-summary-header">
        <h3>Strict-readiness plan</h3>
        {plan.artifact_readiness && <span className="status-pill status-pill-unknown">{plan.artifact_readiness}</span>}
      </div>
      <div className="strict-plan-metrics">
        <div>
          <span>Следующий блок</span>
          <strong>{textValue(plan.next_stage)}</strong>
        </div>
        <div>
          <span>Targets</span>
          <strong>{targets.length}</strong>
        </div>
        {Object.entries(counts).map(([stage, count]) => (
          <div key={stage}>
            <span>{stage}</span>
            <strong>{count}</strong>
          </div>
        ))}
      </div>
      {plan.plan_error && <p className="muted">{plan.plan_error}</p>}
      {targets.length > 0 && (
        <div className="suite-results-table-wrap">
          <table className="suite-results-table strict-plan-table">
            <thead>
              <tr>
                <th>Target</th>
                <th>Stage</th>
                <th>Gate</th>
                <th>Deck</th>
                <th>Builder</th>
                <th>Blocker</th>
              </tr>
            </thead>
            <tbody>
              {targets.map((target) => (
                <tr key={`${target.test_id}-${target.strict_readiness_stage}`}>
                  <td className="mono">{textValue(target.test_id)}</td>
                  <td>{textValue(target.strict_readiness_stage)}</td>
                  <td>{isGateAllowed(target)}</td>
                  <td>{textValue(target.profile_deck_kind)}</td>
                  <td>{textValue(target.profile_case_builder_status)}</td>
                  <td>{textValue(target.strict_profile_evaluator_blocker)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
