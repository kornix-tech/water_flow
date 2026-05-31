import { useMemo } from "react";
import { visualizationHtmlUrl } from "../api/client";

export function PlotFrame({ runName }: { runName: string }) {
  const url = useMemo(() => (runName ? visualizationHtmlUrl(runName, Date.now()) : ""), [runName]);
  if (!runName) {
    return <div className="empty-panel">Выберите расчёт.</div>;
  }
  return <iframe className="plot-frame" title={`Графики ${runName}`} src={url} sandbox="allow-scripts" />;
}
