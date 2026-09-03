import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api } from "../api.js";
import { renderRadarChart } from "../charts/radarChart.js";

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

const TIP_BUBBLE_WIDTH = 235;
const TIP_MARGIN = 8;

// Player name with a hover/focus tooltip (price/position/predicted xP, plus 5-season history
// vs this week's opponent when the API included it) AND a click-to-open modal with their
// actual gameweek-by-gameweek points breakdown — fetched fresh every time it's opened (see
// PlayerBreakdownModal), never cached, so it always reflects the latest confirmed result.
//
// The tooltip bubble is rendered through a portal, positioned from the trigger's real
// on-screen coordinates, rather than as a normal `position: absolute` child. A plain absolute
// child gets silently clipped by any scrollable ancestor (e.g. a wide table's `.table-wrap`,
// which needs `overflow-x: auto` and — per the CSS spec — that forces `overflow-y` to clip too)
// — for a player in one of a table's top rows, that hid the bubble entirely when it tried to
// open upward. Portaling to <body> and positioning with `position: fixed` sidesteps every
// ancestor's overflow/stacking context, and flips to open downward when there isn't enough
// room above.
export function PlayerTip({ player }) {
  const [open, setOpen] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [bubblePos, setBubblePos] = useState(null);
  const ref = useRef(null);
  const stats = player.opponent_stats;

  const showTooltip = () => {
    const rect = ref.current?.getBoundingClientRect();
    if (!rect) return;
    const openUpward = rect.top > 180; // enough room above for a roughly ~150px-tall bubble
    const left = Math.min(Math.max(rect.left, TIP_MARGIN), window.innerWidth - TIP_BUBBLE_WIDTH - TIP_MARGIN);
    setBubblePos(
      openUpward
        ? { left, bottom: window.innerHeight - rect.top + TIP_MARGIN }
        : { left, top: rect.bottom + TIP_MARGIN }
    );
    setOpen(true);
  };
  const hideTooltip = () => setOpen(false);

  return (
    <>
      <span
        className="tip-wrap"
        tabIndex={0}
        role="button"
        aria-haspopup="dialog"
        ref={ref}
        onMouseEnter={showTooltip}
        onMouseLeave={hideTooltip}
        onFocus={showTooltip}
        onBlur={hideTooltip}
        onClick={() => setModalOpen(true)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setModalOpen(true);
          }
        }}
      >
        {player.name}
      </span>
      {open &&
        bubblePos &&
        createPortal(
          <span className="tip-bubble" style={{ position: "fixed", ...bubblePos }}>
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
            <hr className="tip-divider" />
            Click for their points breakdown
          </span>,
          document.body
        )}
      {modalOpen && <PlayerBreakdownModal player={player} onClose={() => setModalOpen(false)} />}
    </>
  );
}

const CARD_COLUMNS = [
  { key: "goals_scored", label: "G" },
  { key: "assists", label: "A" },
  { key: "clean_sheets", label: "CS" },
  { key: "bonus", label: "Bns" },
];

// The static-page generator (scripts/build-static-pages.mjs) publishes this alongside every
// build — a plain { playerId: slug } map so the popup can link to a player's real static page
// without trying to re-derive the slug client-side (which would need the whole player list
// anyway, just to detect the same rare name collisions the generator already resolved).
// Fetched once per session and cached in memory; in local dev (`vite dev`, no static build run
// yet) this 404s and the link just doesn't render — a graceful no-op, not an error.
let slugManifestPromise = null;
function fetchSlugManifest() {
  if (!slugManifestPromise) {
    slugManifestPromise = fetch("/fpl/players/slugs.json")
      .then((res) => (res.ok ? res.json() : {}))
      .catch(() => ({}));
  }
  return slugManifestPromise;
}

// Same manifest-fetched-once precedent as fetchSlugManifest above, publishing
// scripts/build-static-pages.mjs's own /fpl/players/radar.json so the popup shows the exact
// same percentile radar as that player's static page, without the browser ever hitting the
// (comparatively heavy) live /fpl/players/radar endpoint itself.
let radarManifestPromise = null;
function fetchRadarManifest() {
  if (!radarManifestPromise) {
    radarManifestPromise = fetch("/fpl/players/radar.json")
      .then((res) => (res.ok ? res.json() : {}))
      .catch(() => ({}));
  }
  return radarManifestPromise;
}

const RADAR_WINDOW_LABELS = { last3: "Last 3 GWs", previous_season: "Previous Season", career: "Career" };
const RADAR_WINDOW_ORDER = ["last3", "previous_season", "career"];
const RADAR_POS_LABEL = { GK: "Goalkeepers", DEF: "Defenders", MID: "Midfielders", FWD: "Forwards" };

// renderRadarChart returns an SVG string (the same generator scripts/build-static-pages.mjs
// uses for the static pages) -- rendered here via dangerouslySetInnerHTML rather than ported to
// JSX, so the popup's radar can never quietly drift from what the static page shows.
function PlayerRadarSection({ radar, pos }) {
  if (!radar?.categoryLabels) return null;
  const keys = Object.keys(radar.categoryLabels);
  const labels = keys.map((k) => radar.categoryLabels[k]);
  const posLabel = `vs ${RADAR_POS_LABEL[pos] || pos}`;

  const charts = RADAR_WINDOW_ORDER.map((window) => {
    const entry = radar[window];
    if (!entry) return null;
    const allSeries = entry.all ? keys.map((k) => entry.all[k] ?? null) : null;
    const positionSeries = entry.position ? keys.map((k) => entry.position[k] ?? null) : null;
    const svg = renderRadarChart(labels, allSeries, positionSeries, { labelAll: "vs all players", labelPosition: posLabel });
    return svg ? { window, svg } : null;
  }).filter(Boolean);

  if (!charts.length) return null;

  return (
    <>
      <p className="section-heading" style={{ marginTop: 16 }}>
        Stat radar
      </p>
      <div className="radar-row">
        {charts.map(({ window, svg }) => (
          <figure className="radar-chart" key={window}>
            <figcaption>{RADAR_WINDOW_LABELS[window]}</figcaption>
            <div dangerouslySetInnerHTML={{ __html: svg }} />
          </figure>
        ))}
      </div>
    </>
  );
}

// Fetched fresh every time it opens (plain useAsyncAction, not the localStorage-cached hook
// used elsewhere) — a stale points breakdown would defeat the entire point of showing it.
function PlayerBreakdownModal({ player, onClose }) {
  const [state, run] = useAsyncAction();
  const [profileSlug, setProfileSlug] = useState(null);
  const [radar, setRadar] = useState(null);

  useEffect(() => {
    let cancelled = false;
    fetchSlugManifest().then((manifest) => {
      if (!cancelled) setProfileSlug(manifest[player.id] || null);
    });
    return () => {
      cancelled = true;
    };
  }, [player.id]);

  useEffect(() => {
    let cancelled = false;
    fetchRadarManifest().then((manifest) => {
      if (!cancelled) setRadar(manifest[player.id] || null);
    });
    return () => {
      cancelled = true;
    };
  }, [player.id]);

  useEffect(() => {
    run(async () => api.get(`/fpl/player/${player.id}/breakdown`));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [player.id]);

  useEffect(() => {
    const onKeyDown = (e) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  const rows = state.data?.recent ?? [];
  const hasDetailedStats = rows.some((r) => r.clean_sheets !== null || r.bonus !== null);

  return createPortal(
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-card" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <span>
            {player.name} <span className="modal-subhead">points breakdown</span>
          </span>
          <button className="modal-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>

        {state.loading && <Spinner label="Fetching the latest gameweek data…" />}
        <ErrorBanner error={state.error} />

        {state.data && (
          <>
            {state.data.note && (
              <p className="hint" style={{ marginTop: 0 }}>
                {state.data.note}
              </p>
            )}
            {rows.length === 0 ? (
              <p className="empty">No gameweek history available yet.</p>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Season</th>
                      <th>GW</th>
                      <th>Opponent</th>
                      <th>Min</th>
                      {hasDetailedStats && CARD_COLUMNS.map((c) => <th key={c.key}>{c.label}</th>)}
                      <th>Pts</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r, i) => (
                      <tr key={i}>
                        <td>{r.season}</td>
                        <td>{r.gameweek}</td>
                        <td>
                          {r.opponent ? (r.was_home ? r.opponent : `@ ${r.opponent}`) : "—"}
                        </td>
                        <td>{r.minutes}</td>
                        {hasDetailedStats &&
                          CARD_COLUMNS.map((c) => (
                            <td key={c.key}>{r[c.key] ?? "—"}</td>
                          ))}
                        <td>
                          <b>{r.total_points}</b>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {profileSlug && (
              <p style={{ marginTop: 12, marginBottom: 0 }}>
                <a href={`/fpl/player/${profileSlug}`}>View {player.name}'s full profile &amp; stats chart &rarr;</a>
              </p>
            )}
            <PlayerRadarSection radar={radar} pos={player.pos} />
          </>
        )}
      </div>
    </div>,
    document.body
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

function cacheStorageKey(slot) {
  return STORAGE_PREFIX + "snapshot:" + slot;
}

function readCachedSnapshot(slot, cacheKey) {
  try {
    const stored = window.localStorage.getItem(cacheStorageKey(slot));
    if (!stored) return null;
    const parsed = JSON.parse(stored);
    return parsed.cacheKey === cacheKey ? parsed : null;
  } catch {
    return null;
  }
}

// Same shape as useAsyncAction, but the last successful result is kept as a "snapshot" in
// localStorage under `slot`, tagged with `cacheKey` (e.g. the exact query params used) so a
// mismatched key (a different squad, a different budget) never shows someone else's stale
// result. On mount — and whenever `cacheKey` changes — this immediately shows whatever
// snapshot is on file for that exact key, with no loading spinner and no network call, until
// the caller explicitly calls `run()` again (a button click, or an effect that only fires
// when `hasSnapshot()` says there's nothing to show yet). Solves two things: switching tabs
// no longer re-triggers an expensive rebuild (ratings fit + ILP solve) just to redraw the
// same result, and a full page reload restores the last view instead of going in blank.
export function useCachedAsyncAction(slot, cacheKey) {
  const [state, setState] = useState(() => {
    const cached = readCachedSnapshot(slot, cacheKey);
    return cached
      ? { loading: false, error: null, data: cached.data, savedAt: cached.savedAt }
      : { loading: false, error: null, data: null, savedAt: null };
  });

  useEffect(() => {
    const cached = readCachedSnapshot(slot, cacheKey);
    setState(
      cached
        ? { loading: false, error: null, data: cached.data, savedAt: cached.savedAt }
        : { loading: false, error: null, data: null, savedAt: null }
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slot, cacheKey]);

  const run = async (fn) => {
    setState((prev) => ({ ...prev, loading: true, error: null }));
    try {
      const data = await fn();
      const savedAt = Date.now();
      setState({ loading: false, error: null, data, savedAt });
      try {
        window.localStorage.setItem(cacheStorageKey(slot), JSON.stringify({ cacheKey, data, savedAt }));
      } catch {
        // localStorage unavailable (private browsing, quota) — snapshot just won't persist
      }
      return data;
    } catch (err) {
      setState((prev) => ({ ...prev, loading: false, error: err.message || String(err) }));
      return null;
    }
  };

  // Synchronous, direct-from-storage check (deliberately not derived from `state`, which only
  // updates on the next render) — safe to call from an effect reacting to the same key change
  // that also drives this hook's own cache-sync effect above, with no ordering race.
  const hasSnapshot = (key = cacheKey) => readCachedSnapshot(slot, key) !== null;

  return [state, run, hasSnapshot];
}

// Renders nothing until a snapshot exists, then a small "as of HH:MM:SS" hint — the visible
// cue that what's on screen might not be freshly fetched.
export function SnapshotHint({ savedAt }) {
  if (!savedAt) return null;
  return <span className="snapshot-hint">Snapshot from {new Date(savedAt).toLocaleTimeString()}</span>;
}
