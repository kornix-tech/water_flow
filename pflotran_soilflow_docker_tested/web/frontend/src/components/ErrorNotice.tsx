export function ErrorNotice({ message }: { message: string }) {
  if (!message) {
    return null;
  }
  return <div className="error-notice">{message}</div>;
}
