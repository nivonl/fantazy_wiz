// Approximate primary shirt colors for Premier League / recently-promoted-or-relegated clubs —
// plain colors only, no crests/logos/wordmarks, deliberately (see the methodology page and the
// project's own conversation history: official photos/crests need a license the data itself
// doesn't grant; a color swatch does not carry the same risk — colors alone are very hard to
// trademark-protect in this context, and tinting a team name is common practice on fan/stats
// sites). No official "team color" field exists in FPL's API, so this is hand-maintained —
// rarely changes, at most once a year with promotion/relegation.
//
// Plain ES module (no React/JSX) so both the frontend components and the Node static-page
// generator (frontend/scripts/) can import the same file without duplicating the list.
export const TEAM_COLORS = {
  Arsenal: "#EF0107",
  "Aston Villa": "#670E36",
  Bournemouth: "#DA291C",
  Brentford: "#E30613",
  Brighton: "#0057B8",
  Burnley: "#6C1D45",
  Chelsea: "#034694",
  "Crystal Palace": "#1B458F",
  Everton: "#003399",
  Fulham: "#000000",
  "Ipswich Town": "#0044A9",
  "Leeds United": "#1D428A",
  "Leicester City": "#003090",
  Liverpool: "#C8102E",
  "Luton Town": "#F78F1E",
  "Man City": "#6CABDD",
  "Manchester City": "#6CABDD",
  "Man Utd": "#DA291C",
  "Manchester United": "#DA291C",
  Newcastle: "#241F20",
  "Newcastle United": "#241F20",
  "Norwich City": "#FFF200",
  "Nott'm Forest": "#DD0000",
  "Nottingham Forest": "#DD0000",
  "Sheffield United": "#EE2737",
  Southampton: "#D71920",
  Sunderland: "#EB172B",
  Spurs: "#132257",
  "Tottenham Hotspur": "#132257",
  Watford: "#FBEE23",
  "West Brom": "#122F67",
  "West Bromwich Albion": "#122F67",
  "West Ham": "#7A263A",
  "West Ham United": "#7A263A",
  Wolves: "#FDB913",
  "Wolverhampton Wanderers": "#FDB913",
  "Coventry City": "#78D0F7",
  "Hull City": "#F18A00",
  Middlesbrough: "#DC1B1B",
};

// A muted neutral for any club not in the map above, rather than guessing a color that could
// be wrong — matches the app's own --text-dim tone so it doesn't look broken either way.
export const FALLBACK_TEAM_COLOR = "#8A7F99";

export function teamColor(teamName) {
  return TEAM_COLORS[teamName] || FALLBACK_TEAM_COLOR;
}
