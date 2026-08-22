function pct(x) {
  return `${(x * 100).toFixed(0)}%`;
}

export function PredictionsTable({ predictions }) {
  if (!predictions.length) return <p className="empty">No fixtures found.</p>;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Home</th>
            <th>Away</th>
            <th>Exp. goals</th>
            <th>Likely score</th>
            <th>Home / draw / away</th>
            <th>Clean sheet (H/A)</th>
            <th>BTTS</th>
            <th>O2.5</th>
          </tr>
        </thead>
        <tbody>
          {predictions.map((p, i) => (
            <tr key={i}>
              <td>{p.home_team}</td>
              <td>{p.away_team}</td>
              <td>
                {p.lam_home.toFixed(2)} – {p.lam_away.toFixed(2)}
              </td>
              <td>
                {p.most_likely_score[0]}-{p.most_likely_score[1]} ({pct(p.most_likely_score_prob)})
              </td>
              <td>
                {pct(p.p_home_win)} / {pct(p.p_draw)} / {pct(p.p_away_win)}
              </td>
              <td>
                {pct(p.p_home_clean_sheet)} / {pct(p.p_away_clean_sheet)}
              </td>
              <td>{pct(p.p_btts)}</td>
              <td>{pct(p.p_over_2_5)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
