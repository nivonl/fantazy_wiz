// Mirrors fantasy_app/providers/fpl_history.py's current_season_label() exactly (July
// rollover), so a URL's season token always agrees with what the backend and every on-page
// "Season" column already call that same period -- never invent a second convention for the
// same fact.
export function seasonLabel(date = new Date()) {
  const startYear = date.getUTCMonth() >= 6 ? date.getUTCFullYear() : date.getUTCFullYear() - 1;
  return `${startYear}-${String(startYear + 1).slice(-2)}`;
}
