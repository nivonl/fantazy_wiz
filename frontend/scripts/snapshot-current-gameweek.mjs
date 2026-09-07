// Run on a schedule (.github/workflows/snapshot-gameweeks.yml, daily) to commit a point-in-
// time snapshot of the current gameweek's predictions -- the only way a later-generated
// gameweek page can honestly show "what was predicted beforehand" once that gameweek is in
// the past, since the live model always fits from whatever results exist *today* (no
// point-in-time capability anywhere in the backend). Idempotent: does nothing if this
// gameweek already has a snapshot, so running it daily just captures each new gameweek once,
// early in its cycle, and never touches it again.

import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { warmUpBackend, fetchJson } from "./lib/fetch-api.mjs";
import { seasonLabel } from "./lib/season.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const GAMEWEEKS_DIR = join(__dirname, "..", "data", "gameweeks");

async function main() {
  await warmUpBackend();
  const data = await fetchJson("/fpl/players/predicted");
  const path = join(GAMEWEEKS_DIR, `gw${data.event}.json`);

  if (existsSync(path)) {
    console.log(`Gameweek ${data.event} is already snapshotted -- nothing to do.`);
    return;
  }

  // Captured now, at the gameweek's own moment, rather than derived later from "today" at build
  // time -- once a season rolls over, a later build must not silently relabel an old gameweek's
  // URL as belonging to the new season just because "now" changed.
  const snapshot = { ...data, season: seasonLabel() };

  mkdirSync(GAMEWEEKS_DIR, { recursive: true });
  writeFileSync(path, JSON.stringify(snapshot, null, 2), "utf-8");
  console.log(`Snapshotted gameweek ${data.event} (${data.players.length} players, season ${snapshot.season}) to ${path}`);
}

main().catch((err) => {
  console.error("Gameweek snapshot failed:", err);
  process.exit(1);
});
