import { useState } from "react";
import { api } from "../api.js";
import {
  Button,
  Card,
  ErrorBanner,
  Field,
  PlayerTip,
  Reveal,
  SignedValue,
  Spinner,
  Tag,
  useAsyncAction,
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
const POSITION_ORDER = ["GK", "DEF", "MID", "FWD"];

export function CurrentTeamPanel({ squad }) {
  const [state, run] = useAsyncAction();
  const [expandedChip, setExpandedChip] = useState(null);
  const [budget, setBudget] = useState(8.0);
  const [targetsState, runTargets] = useAsyncAction();

  const submit = () => {
    run(async () => api.get(`/recommend/fpl/full?${squad.toParams().toString()}`));
  };

  const findTargets = () => {
    runTargets(async () => {
      const params = squad.toParams();
      params.set("budget", budget);
      return api.get(`/recommend/fpl/targets?${params.toString()}`);
    });
  };

  const rec = state.data;
  const targets = targetsState.data;

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
              For a given spend on a single incoming player, the best player NOT already in your squad at each
              position, ranked by predicted points summed over the next few gameweeks.
            </p>
            <div className="controls">
              <Field label="Budget for the incoming player (£m)">
                <input type="number" step="0.1" min="0" value={budget} onChange={(e) => setBudget(e.target.value)} />
              </Field>
              <Button variant="ghost" onClick={findTargets} disabled={targetsState.loading}>
                {targetsState.loading ? "Searching…" : "Find targets"}
              </Button>
            </div>
            {targetsState.loading && <Spinner label="Scoring the market…" />}
            <ErrorBanner error={targetsState.error} />
            {targets && (
              <Reveal revealKey={JSON.stringify(targets.targets)}>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Pos</th>
                        <th>Best target</th>
                        <th>Team</th>
                        <th>Price</th>
                        <th>Predicted pts ({targets.horizon_gameweeks} GWs)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {POSITION_ORDER.map((pos) => {
                        const p = targets.targets[pos];
                        return (
                          <tr key={pos}>
                            <td>{pos}</td>
                            {p ? (
                              <>
                                <td><PlayerTip player={p} /></td>
                                <td>{p.team}</td>
                                <td>{p.price.toFixed(1)}m</td>
                                <td>{p.xp.toFixed(2)}</td>
                              </>
                            ) : (
                              <td colSpan={4} className="empty">
                                Nothing affordable at £{Number(budget).toFixed(1)}m
                              </td>
                            )}
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
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
