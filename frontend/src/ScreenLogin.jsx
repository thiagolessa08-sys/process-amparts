import { useState } from "react";
import { Icon } from "./icons.jsx";
import { login as apiLogin, setAuthToken } from "./api.js";

/* Login real contra o backend (POST /api/login) — ver app/auth.py. */

/* Lê/escreve a sessão no localStorage para sobreviver a reloads. */
const AUTH_KEY = "pm-auth";
export function readAuth() {
  try {
    const raw = localStorage.getItem(AUTH_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}
export function saveAuth(user) {
  localStorage.setItem(AUTH_KEY, JSON.stringify(user));
}
export function clearAuth() {
  localStorage.removeItem(AUTH_KEY);
}

export function LoginScreen({ onLogin, dark, onToggleTheme }) {
  const [email, setEmail] = useState("");
  const [pass, setPass] = useState("");
  const [show, setShow] = useState(false);
  const [remember, setRemember] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setError("");
    if (!email.trim() || !pass) {
      setError("Preencha e-mail e senha.");
      return;
    }
    setBusy(true);
    try {
      const user = await apiLogin(email.trim().toLowerCase(), pass);
      setAuthToken(user.token);          // disponível na sessão, mesmo sem "Lembrar"
      if (remember) saveAuth(user);
      onLogin(user);
    } catch (err) {
      setBusy(false);
      setError(err.status === 401 ? "E-mail ou senha incorretos." : (err.message || "Falha no login."));
    }
  }


  return (
    <div className={"auth-shell" + (dark ? " dark" : "")}>
      <button
        className="auth-theme"
        onClick={onToggleTheme}
        title="Alternar tema"
        type="button"
      >
        <Icon name={dark ? "sun" : "moon"} size={18} />
      </button>

      {/* Painel lateral — marca */}
      <aside className="auth-aside">
        <div className="auth-brand">
          <span className="auth-logo">
            <Icon name="activity" size={22} strokeWidth={2.4} />
          </span>
          <span className="auth-brand-name">
            Process<span className="dim"> Intelligence</span>
          </span>
        </div>

        <div className="auth-pitch">
          <h2>Inteligência de processos para o seu financeiro.</h2>
          <p>
            Descubra o fluxo real dos seus processos P2P e O2C, encontre
            gargalos, retrabalho e desvios — tudo em um só lugar.
          </p>
          <ul className="auth-feats">
            <li>
              <Icon name="explorer" size={16} /> Descoberta automática do processo
            </li>
            <li>
              <Icon name="loop" size={16} /> Análise de retrabalho e loops
            </li>
            <li>
              <Icon name="bolt" size={16} /> Assistente de IA em linguagem natural
            </li>
          </ul>
        </div>

        <div className="auth-aside-foot">© {new Date().getFullYear()} Process Intelligence</div>
      </aside>

      {/* Formulário */}
      <main className="auth-main">
        <form className="auth-card" onSubmit={submit}>
          <div className="auth-card-head">
            <h1>Entrar</h1>
            <p>Acesse a plataforma de Process Intelligence.</p>
          </div>

          <label className="auth-field">
            <span className="auth-label">E-mail</span>
            <div className="auth-input">
              <span className="auth-lead">
                <Icon name="mail" size={16} />
              </span>
              <input
                type="email"
                autoComplete="username"
                placeholder="voce@empresa.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoFocus
              />
            </div>
          </label>

          <label className="auth-field">
            <span className="auth-label">Senha</span>
            <div className="auth-input">
              <span className="auth-lead">
                <Icon name="lock" size={16} />
              </span>
              <input
                type={show ? "text" : "password"}
                autoComplete="current-password"
                placeholder="••••••••"
                value={pass}
                onChange={(e) => setPass(e.target.value)}
              />
              <button
                type="button"
                className="auth-eye"
                onClick={() => setShow((s) => !s)}
                title={show ? "Ocultar senha" : "Mostrar senha"}
                tabIndex={-1}
              >
                <Icon name={show ? "eyeOff" : "eye"} size={16} />
              </button>
            </div>
          </label>

          <div className="auth-row">
            <label className="auth-check">
              <input
                type="checkbox"
                checked={remember}
                onChange={(e) => setRemember(e.target.checked)}
              />
              <span>Manter conectado</span>
            </label>
            <button
              type="button"
              className="auth-link"
              onClick={() => setError("Recuperação de senha não disponível na demo.")}
            >
              Esqueceu a senha?
            </button>
          </div>

          {error && (
            <div className="auth-error">
              <Icon name="alert" size={15} />
              {error}
            </div>
          )}

          <button className="auth-submit" type="submit" disabled={busy}>
            {busy ? (
              <>
                <Icon name="activity" size={17} className="spin" />
                Entrando…
              </>
            ) : (
              <>
                <Icon name="lock" size={16} />
                Entrar
              </>
            )}
          </button>
        </form>
      </main>
    </div>
  );
}
