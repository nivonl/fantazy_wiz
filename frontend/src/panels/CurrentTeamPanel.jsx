import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import {
  Button,
  Card,
  ErrorBanner,
  Field,
  PlayerTip,
  Reveal,
  SignedValue,
  SnapshotHint,
  Spinner,
  Tag,
  useCachedAsyncAction,
} from "../components/ui.jsx";
import { SquadTable } from "../components/SquadTable.jsx";

const CHIP_LABELS = {
  bench_boost: "Bench Boost",
  triple_captain: "Triple Captain",
  free_hit: "Free Hit",
  wildcard: "Wildcard",
};

// Only these two chips rebuild the whole squad, so only these have a squad worth showing.
const SQUAD_KEY_BY_CHIP = { free_hit: "free_hit_squad", wildcard: "wildcard_squad" };

// `squad` comes from useMySquadIdentity() in App.jsx — shared with the Overview tab so your
// entry ID / manual squad is entered once, not duplicated per screen.

function safeCacheKey(squad) {
  try {
    return squad.toParams().toString();
  } catch {
    return "unconfigured";
  }
}

export function CurrentTeamPanel({ squad }) {
  const squadCacheKey = safeCacheKey(squad);
  const [state, run] = useCachedAsyncAction("squad-full", squadCacheKey);
  const [expandedChip, setExpandedChip] = useState(null);
  const [tradeTarget, setTradeTarget] = useState("");
  const [tradeState, runTrade] = useCachedAsyncAction("squad-trade-for", `${squadCacheKey}|target=${tradeTarget}`);

  const submit = () => {
    run(async () => api.get(`/recommend/fpl/full?${squad.toParams().toString()}`));
  };

  const findTradeCombos = () => {
    runTrade(async () => {
      const params = squad.toParams();
      params.set("target", tradeTarget);
      return api.get(`/recommend/fpl/trade-for?${params.toString()}`);
    });
  };

  const rec = state.data;
  const trade = tradeState.data;

  return (
    <Card
      title="Current team & top recommendations"
      hint="Five kinds of advice, each over the horizon it actually needs: live status flags on your squad right now, this gameweek's captain/vice/bench, the single best transfer (evaluated a few gameweeks ahead, since it sticks around), and a quantified lift for each chip — Free Hit judged over just this gameweek, Wildcard over several. Hover any player name for their scoring history against this week's opponent, over the last 5 PL seasons."
    >
      <div className="mode-toggle">
        <button className={squad.mode === "entry" ? "active" : ""} onClick={() => squad.setMode("entry")}>
          From FPL entry ID
        </button>
        <button className={squad.mode === "manual" ? "active" : ""} onClick={() => squad.setMode("manual")}>
          Enter manually
        </button>
      </div>

      {squad.mode === "entry" ? (
        <>
          <div className="controls">
            <Field label="FPL entry ID">
              <input type="number" placeholder="e.g. 1234567" value={squad.entryId} onChange={(e) => squad.setEntryId(e.target.value)} />
            </Field>
            <Field label="Free transfers">
              <input type="number" min="0" value={squad.entryFreeTransfers} onChange={(e) => squad.setEntryFreeTransfers(e.target.value)} />
            </Field>
          </div>
          <p className="hint" style={{ marginTop: -8 }}>
            Only works <em>after</em> this gameweek's deadline has passed — FPL keeps everyone's picks private
            before lock. Use "Enter manually" before then.
          </p>
        </>
      ) : (
        <>
          <Field label="Your current 15, comma-separated">
            <textarea
              placeholder='e.g. Raya, Gabriel, Saliba, White, Saka, Haaland, ... (partial names like "Salah" work too)'
              value={squad.players}
              onChange={(e) => squad.setPlayers(e.target.value)}
            />
          </Field>
          <div className="controls">
            <Field label="Bank (£m)">
              <input type="number" step="0.1" value={squad.bank} onChange={(e) => squad.setBank(e.target.value)} />
            </Field>
            <Field label="Free transfers">
              <input type="number" min="0" value={squad.manualFreeTransfers} onChange={(e) => squad.setManualFreeTransfers(e.target.value)} />
            </Field>
          </div>
        </>
      )}

      <div className="controls">
        <Button onClick={submit} disabled={state.loading}>
          {state.loading ? "Working…" : "Get top recommendations"}
        </Button>
        <SnapshotHint savedAt={state.savedAt} />
      </div>

      <div className="output">
        {state.loading && <Spinner label="Fitting ratings, scoring your squad…" />}
        <ErrorBanner error={state.error} />
        {!state.loading && !state.error && !rec && <p className="empty">Nothing loaded yet.</p>}
        {rec && (
          <Reveal revealKey={JSON.stringify(rec.captain)}>
            {rec.unmatched_names?.length > 0 && (
              <p className="error-banner" style={{ marginBottom: 14 }}>
                Couldn't match: {rec.unmatched_names.join(", ")}.
              </p>
            )}

            <p className="section-heading">Check before deadline</p>
            {rec.risk_flags.length === 0 ? (
              <p className="summary-line">No live status concerns on your squad right now.</p>
            ) : (
              <ul className="flags">
                {rec.risk_flags.map((f) => (
                  <li key={f.player.id}>
                    <PlayerTip player={f.player} /> <Tag variant="hit">{f.status}</Tag> {f.news}
                    {f.suggested_replacement && (
                      <>
                        {" "}
                        &rarr; consider <PlayerTip player={f.suggested_replacement} />
                      </>
                    )}
                  </li>
                ))}
              </ul>
            )}

            <p className="section-heading">This gameweek</p>
            <p className="summary-line">
              Captain <b><PlayerTip player={rec.captain} /></b> · Vice <b><PlayerTip player={rec.vice_captain} /></b>
            </p>
            {rec.lineup_changes.length > 0 && (
              <ul className="flags">
                {rec.lineup_changes.map((c, i) => (
                  <li key={i}>{c}</li>
                ))}
              </ul>
            )}
            <SquadTable
              title="Your starting XI — predicted points this gameweek"
              players={[...rec.starters].sort((a, b) => b.xp - a.xp)}
              captainId={rec.captain.id}
              viceId={rec.vice_captain.id}
            />
            <SquadTable title="Your bench — predicted points this gameweek" players={rec.bench} />

            <p className="section-heading">Best trade target by position</p>
            <p className="hint" style={{ marginTop: -4 }}>
              Want the best affordable player at each position for a given budget? That's now its
              own tool: <Link to="/fpl-transfer-finder">Transfer Finder</Link> — it automatically
              excludes whoever's already in the squad you've entered here.
            </p>

            <p className="section-heading">Trade for a specific player</p>
            <p className="hint" style={{ marginTop: -4 }}>
              Want one particular player? The top 3 legal ways to reshuffle your squad (no chip)
              to afford and fit them in — including a second downgrade elsewhere if their price
              needs it — ranked by projected points over the next few gameweeks, net of any
              transfer hits.
            </p>
            <div className="controls">
              <Field label="Player you want">
                <input
                  type="text"
                  placeholder="e.g. Haaland"
                  value={tradeTarget}
                  onChange={(e) => setTradeTarget(e.target.value)}
                />
              </Field>
              <Button variant="ghost" onClick={findTradeCombos} disabled={tradeState.loading || !tradeTarget.trim()}>
                {tradeState.loading ? "Solving…" : "Find trade combos"}
              </Button>
              <SnapshotHint savedAt={tradeState.savedAt} />
            </div>
            {tradeState.loading && <Spinner label="Solving the best way to fit them in…" />}
            <ErrorBanner error={tradeState.error} />
            {trade && (
              <Reveal revealKey={JSON.stringify(trade.combos)}>
                {trade.combos.length === 0 ? (
                  <p className="empty">No legal combo found.</p>
                ) : (
                  <div className="chip-grid">
                    {trade.combos.map((c, i) => (
                      <div className="chip-card" key={i}>
                        {c.recommended && <Tag variant="captain">Recommended</Tag>}
                        <p className="summary-line" style={{ marginTop: 6 }}>
                          OUT{" "}
                          {c.players_out.map((p, j) => (
                            <span key={p.id}>
                              {j > 0 && ", "}
                              <PlayerTip player={p} />
                            </span>
                          ))}
                          {" "}&rarr; IN{" "}
                          {c.players_in.map((p, j) => (
                            <span key={p.id}>
                              {j > 0 && ", "}
                              <PlayerTip player={p} />
                            </span>
                          ))}
                        </p>
                        <div className="chip-lift">
                          <SignedValue value={c.xp_gain} suffix=" xP" />
                        </div>
                        <div className="chip-note">
                          {c.hits > 0 ? (
                            <Tag variant="hit">
                              {c.hits} hit{c.hits > 1 ? "s" : ""} (-{c.hit_cost})
                            </Tag>
                          ) : (
                            "No hit — within free transfers"
                          )}{" "}
                          · Bank after: {c.new_bank}m
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </Reveal>
            )}

            <p className="section-heading">Best transfer</p>
            {rec.best_transfer ? (
              <p className="summary-line">
                OUT <PlayerTip player={rec.best_transfer.out} /> &rarr; IN <PlayerTip player={rec.best_transfer.in} />{" "}
                <SignedValue value={rec.best_transfer.xp_gain} suffix=" xP" /> over the next {rec.transfer_horizon_gameweeks} gameweeks
                {rec.best_transfer.is_hit && <Tag variant="hit">-4 hit</Tag>}
              </p>
            ) : (
              <p className="empty">No transfer worth making over the next {rec.transfer_horizon_gameweeks} gameweeks.</p>
            )}

            <p className="section-heading">Chip lifts</p>
            <div className="chip-grid">
              {rec.chip_lifts.map((c) => {
                const squadKey = SQUAD_KEY_BY_CHIP[c.chip];
                const isOpen = expandedChip === c.chip;
                return (
                  <div className="chip-card" key={c.chip}>
                    <span className="chip-name">{CHIP_LABELS[c.chip] || c.chip}</span>
                    <span className="chip-horizon">
                      {c.horizon_gameweeks} GW{c.horizon_gameweeks > 1 ? "s" : ""}
                    </span>
                    <div className="chip-lift">
                      <SignedValue value={c.lift} />
                    </div>
                    <div className="chip-note">{c.note}</div>
                    {squadKey && (
                      <Button variant="ghost" onClick={() => setExpandedChip(isOpen ? null : c.chip)}>
                        {isOpen ? "Hide squad" : "Show squad"}
                      </Button>
                    )}
                  </div>
                );
              })}
            </div>

            {expandedChip && SQUAD_KEY_BY_CHIP[expandedChip] && (
              <Reveal revealKey={expandedChip}>
                {(() => {
                  const squad = rec[SQUAD_KEY_BY_CHIP[expandedChip]];
                  return (
                    <div style={{ marginTop: 16 }}>
                      <p className="summary-line">
                        {CHIP_LABELS[expandedChip]} squad · total <b>{squad.total_price}m</b> (100m budget) · Starting XI xP{" "}
                        <b>{squad.starting_xp}</b>
                      </p>
                      <SquadTable
                        title="Starting XI"
                        players={[...squad.starters].sort((a, b) => b.xp - a.xp)}
                        captainId={squad.captain.id}
                        viceId={squad.vice_captain.id}
                      />
                      <SquadTable title="Bench" players={squad.bench} />
                    </div>
                  );
                })()}
              </Reveal>
            )}
          </Reveal>
        )}
      </div>
    </Card>
  );
}
