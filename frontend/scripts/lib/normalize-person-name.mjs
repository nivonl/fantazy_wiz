// Ports fpl_history.py's normalize_person_name exactly, so player-name handling here matches
// the backend precisely. Plain NFKD + strip-non-ASCII silently DROPS letters with no
// base+combining-mark decomposition (letters like the Danish O-slash or AE ligature) rather
// than transliterating them -- this explicit table handles those first, same as the Python
// original.
const EXTRA_TRANSLATIONS = {
  "Ø": "O", "ø": "o", // O with stroke (upper/lower)
  "Æ": "AE", "æ": "ae", // AE ligature (upper/lower)
  "Đ": "D", "đ": "d", // D with stroke (upper/lower)
  "ß": "ss", // sharp s
  "Ł": "L", "ł": "l", // L with stroke (upper/lower)
};

const COMBINING_MARKS = /[̀-ͯ]/g; // combining diacritical marks block
const NON_ASCII = /[^\x00-\x7F]/g;

export function normalizePersonName(name) {
  let translated = "";
  for (const ch of String(name)) {
    translated += EXTRA_TRANSLATIONS[ch] ?? ch;
  }
  const stripped = translated
    .normalize("NFKD")
    .replace(COMBINING_MARKS, "") // combining marks left behind by NFKD decomposition
    .replace(NON_ASCII, ""); // anything else non-ASCII, matching Python's ascii-ignore
  return stripped.toLowerCase().split(/\s+/).filter(Boolean).join(" ");
}
