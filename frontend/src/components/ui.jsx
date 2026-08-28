import { useEffect, useRef, useState } from "react";

// Remembers a value in this browser (localStorage) across visits — e.g. your FPL entry ID or
// current squad, so you don't retype it every time you open the site on your phone. No
// backend/account needed: it's purely on-device, per browser.
const STORAGE_PREFIX = "pitchmetric:";

export function usePersistentState(key, initialValue) {
  const storageKey = STORAGE_PREFIX + key;
  const [value, setValue] = useState(() => {
    try {
      const stored = window.localStorage.getItem(storageKey);
      return stored !== null ? JSON.parse(stored) : initialValue;
    } catch {
      return initialValue;
    }
  });

  const setAndStore = (next) => {
    setValue((prev) => {
      const resolved = typeof next === "function" ? next(prev) : next;
      try {
        window.localStorage.setItem(storageKey, JSON.stringify(resolved));
      } catch {
        // localStorage unavailable (private browsing, quota) — the app still works, just
        // won't remember between visits.
      }
      return resolved;
    });
  };

  return [value, setAndStore];
}

// Persisted light/dark choice (not prefers-color-scheme — an explicit toggle per the user's
// request). Applies data-theme to <html> so index.css's [data-theme="light"] override kicks in.
export function useTheme() {
  const [theme, setTheme] = usePersistentState("theme", "dark");
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);
  return [theme, setTheme];
}

export function ThemeToggle() {
  const [theme, setTheme] = useTheme();
  const isLight = theme === "light";
  return (
    <button
      className="theme-toggle"
      onClick={() => setTheme(isLight ? "dark" : "light")}
      aria-label="Toggle light/dark mode"
      title={isLight ? "Switch to dark mode" : "Switch to light mode"}
    >
      {isLight ? "🌙" : "☀️"}
    </button>
  );
}

// Shared "who am I" squad identity (FPL entry ID or a manually-typed 15), used by both the
// Overview dashboard and the Squad tab so it's entered once, not duplicated per screen.
// Persisted per-device via usePersistentState, same as before — just lifted to one place.
export function useMySquadIdentity() {
  const [mode, setMode] = usePersistentState("ct-mode", "entry");
  const [entryId, setEntryId] = usePersistentState("ct-entry-id", "");
  const [entryFreeTransfers, setEntryFreeTransfers] = usePersistentState("ct-entry-ft", 1);
  const [players, setPlayers] = usePersistentState("ct-players", "");
  const [bank, setBank] = usePersistentState("ct-bank", 0);
  const [manualFreeTransfers, setManualFreeTransfers] = usePersistentState("ct-manual-ft", 1);

  const isConfigured = mode === "entry" ? Boolean(entryId) : Boolean(players.trim());

  function toParams() {
    const params = new URLSearchParams();
    if (mode === "entry") {
      if (!entryId) throw new Error("Enter your FPL entry ID first (Squad tab).");
      params.set("entry_id", entryId);
      params.set("free_transfers", entryFreeTransfers);
    } else {
      if (!players.trim()) throw new Error("Enter your current 15 players first (Squad tab).");
      params.set("players", players.trim());
      params.set("bank", bank);
      params.set("free_transfers", manualFreeTransfers);
    }
    return params;
  }

  return {
    mode, setMode,
    entryId, setEntryId,
    entryFreeTransfers, setEntryFreeTransfers,
    players, setPlayers,
    bank, setBank,
    manualFreeTransfers, setManualFreeTransfers,
    isConfigured,
    toParams,
  };
}

export function Card({ title, hint, children }) {
  return (
    <section className="card">
      <h2>{title}</h2>
      {hint && <p className="hint">{hint}</p>}
      {children}
    </section>
  );
}

export function Field({ label, children }) {
  return (
    <div className="field">
      <label>{label}</label>
      {children}
    </div>
  );
}

export function Button({ children, onClick, disabled, variant = "primary" }) {
  return (
    <button className={`btn btn-${variant}`} onClick={onClick} disabled={disabled}>
      {disabled && <span className="btn-spinner" />}
      {children}
    </button>
  );
}

export function Spinner({ label = "Loading…" }) {
  return (
    <div className="spinner-row">
      <span className="spinner-ring" />
      <span>{label}</span>
    </div>
  );
}

export function ErrorBanner({ error }) {
  if (!error) return null;
  return <div className="error-banner">{error}</div>;
}

export function Empty({ children }) {
  return <p className="empty">{children}</p>;
}

export function SignedValue({ value, decimals = 2, suffix = "" }) {
  const cls = value >= 0 ? "value-positive" : "value-negative";
  const sign = value >= 0 ? "+" : "";
  return (
    <span className={cls}>
      {sign}
      {value.toFixed(decimals)}
      {suffix}
    </span>
  );
}

export function Tag({ children, variant = "default" }) {
  return <span className={`tag tag-${variant}`}>{children}</span>;
}

// Player name with a hover/focus tooltip: price/position/predicted xP for this fixture
// always, plus 5-season history vs this week's opponent when the API included it.
export function PlayerTip({ player }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const stats = player.opponent_stats;

  return (
    <span
      className="tip-wrap"
      tabIndex={0}
      ref={ref}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
    >
      {player.name}
      {open && (
        <span className="tip-bubble">
          <span className="tip-header">
            {player.pos} · {player.team} · {player.price.toFixed(1)}m
          </span>
          <span className="tip-xp">
            Predicted {player.xp.toFixed(2)} pts{stats ? ` vs ${stats.opponent}` : ""}
          </span>
          {stats && (
            <>
              <hr className="tip-divider" />
              {stats.games_overall === 0 ? (
                <>No PL history vs {stats.opponent} in the last 5 seasons.</>
              ) : (
                <>
                  Overall: {stats.games_overall} apps, avg {stats.avg_points_overall} pts, {stats.goals_overall}G/
                  {stats.assists_overall}A
                  <br />
                  {stats.games_current_team ? (
                    <>
                      At current club: {stats.games_current_team} apps, avg {stats.avg_points_current_team} pts
                    </>
                  ) : (
                    <>No appearances vs {stats.opponent} yet at their current club.</>
                  )}
                </>
              )}
            </>
          )}
        </span>
      )}
    </span>
  );
}

// Fades/slides content in once it's ready — used to give newly-loaded results a soft entrance
// instead of popping in instantly.
export function Reveal({ children, revealKey }) {
  return (
    <div className="reveal" key={revealKey}>
      {children}
    </div>
  );
}

// Small helper: run an async loader on demand, tracking loading/error/data state.
export function useAsyncAction() {
  const [state, setState] = useState({ loading: false, error: null, data: null });
  const run = async (fn) => {
    setState({ loading: true, error: null, data: null });
    try {
      const data = await fn();
      setState({ loading: false, error: null, data });
      return data;
    } catch (err) {
      setState({ loading: false, error: err.message || String(err), data: null });
      return null;
    }
  };
  return [state, run];
}
