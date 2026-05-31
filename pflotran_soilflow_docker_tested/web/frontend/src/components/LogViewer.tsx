interface LogViewerProps {
  text: string;
}

export function LogViewer({ text }: LogViewerProps) {
  return <pre className="log-viewer">{text || "Лог пока пуст."}</pre>;
}
