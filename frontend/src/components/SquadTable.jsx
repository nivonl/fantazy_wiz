import { Fragment } from "react";
import { PlayerTip, Tag } from "./ui.jsx";

export function SquadTable({ title, players, captainId, viceId, injuryNotes }) {
  return (
    <>
      {title && <p className="section-heading">{title}</p>}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Pos</th>
              <th>Name</th>
              <th>Team</th>
              <th>Price</th>
              <th>xP</th>
            </tr>
          </thead>
          <tbody>
            {players.map((p) => {
              const note = injuryNotes?.[p.id];
              return (
                <Fragment key={p.id}>
                  <tr>
                    <td>{p.pos}</td>
                    <td>
                      <PlayerTip player={p} />
                      {p.id === captainId && <Tag variant="captain">C</Tag>}
                      {p.id === viceId && <Tag variant="vice">VC</Tag>}
                      {note && <Tag variant="hit">{note.status.toUpperCase()}</Tag>}
                    </td>
                    <td>{p.team}</td>
                    <td>{p.price.toFixed(1)}m</td>
                    <td>{p.xp.toFixed(2)}</td>
                  </tr>
                  {note?.news && (
                    <tr>
                      <td></td>
                      <td colSpan={4} style={{ color: "var(--warn)", fontSize: "0.78rem", paddingTop: 0 }}>
                        {note.news}
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}
