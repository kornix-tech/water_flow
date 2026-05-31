import type { JobStatus } from "../types";
import { jobStatusLabel } from "../labels";

export function JobStatusBadge({ status }: { status: JobStatus | string }) {
  return <span className={`badge badge-${status}`}>{jobStatusLabel(status)}</span>;
}
