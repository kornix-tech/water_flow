import { useState } from "react";
import { clearApiToken, getHealth, setApiToken } from "../api/client";
import { ErrorNotice } from "./ErrorNotice";

interface AuthPanelProps {
  visible: boolean;
  onVerified: () => void;
}

export function AuthPanel({ visible, onVerified }: AuthPanelProps) {
  const [token, setToken] = useState("");
  const [error, setError] = useState("");
  const [checking, setChecking] = useState(false);

  if (!visible) {
    return null;
  }

  async function verifyToken() {
    setChecking(true);
    setError("");
    try {
      setApiToken(token);
      await getHealth();
      onVerified();
    } catch (caught) {
      clearApiToken();
      setError(caught instanceof Error ? caught.message : "Токен не принят сервером");
    } finally {
      setChecking(false);
    }
  }

  async function continueWithoutToken() {
    setChecking(true);
    setError("");
    try {
      clearApiToken();
      await getHealth();
      onVerified();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Сервер требует API-токен");
    } finally {
      setChecking(false);
    }
  }

  return (
    <div className="auth-backdrop" role="presentation">
      <section className="auth-panel" aria-labelledby="auth-title">
        <h1 id="auth-title">Доступ к данным</h1>
        <p className="muted">Введите API-токен для защищённого режима сервера.</p>
        <ErrorNotice message={error} />
        <label className="field">
          <span>API-токен</span>
          <input
            type="password"
            autoComplete="current-password"
            value={token}
            onChange={(event) => setToken(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                verifyToken();
              }
            }}
          />
        </label>
        <div className="toolbar">
          <button className="primary" type="button" disabled={!token.trim() || checking} onClick={verifyToken}>
            {checking ? "Проверка..." : "Войти"}
          </button>
          <button type="button" disabled={checking} onClick={continueWithoutToken}>
            Без токена
          </button>
        </div>
      </section>
    </div>
  );
}
