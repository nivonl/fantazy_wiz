import { normalizePersonName } from "./normalize-person-name.mjs";

// Player-page slugs are derived from `web_name` (the only name field the /fpl/players/predicted
// candidate pool carries -- CandidatePlayer doesn't expose first/second name separately, that
// dataclass is shared by every squad-building endpoint). web_name is usually distinctive enough
// on its own ("Saka", "Haaland", "M.Salah"); the element id disambiguates the rare real
// collision, detected once across the whole player list rather than guessed at per-player.
function baseSlug(webName) {
  return normalizePersonName(webName).replace(/[^a-z0-9\s-]/g, "").trim().replace(/\s+/g, "-");
}

// Returns a Map<player.id, slug>. The element id is always the real join key; the slug is a
// presentation layer over it, never re-derived from a name that could change later.
export function buildSlugMap(players) {
  const bySlug = new Map();
  for (const p of players) {
    const slug = baseSlug(p.name) || `player-${p.id}`;
    if (!bySlug.has(slug)) bySlug.set(slug, []);
    bySlug.get(slug).push(p);
  }

  const slugById = new Map();
  for (const [slug, group] of bySlug) {
    if (group.length === 1) {
      slugById.set(group[0].id, slug);
    } else {
      for (const p of group) slugById.set(p.id, `${slug}-${p.id}`);
    }
  }
  return slugById;
}
