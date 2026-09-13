// The SAME hashing the server does to lyrics from LRCLIB (server/lyrics.py).
// A transcription made in this browser must produce byte-identical hashes, or
// a line typed into the search would never match a track transcribed here.
// Nothing but these numbers ever leaves the machine — the words themselves are
// discarded the moment they are hashed, and a hash cannot be turned back.

// norm_words(): NFKD, lowercase, drop combining marks, drop [bracketed] and
// (parenthesised) stage directions, normalise curly apostrophes, keep only
// letters/digits/apostrophe, split, strip leading and trailing apostrophes.
export function normWords(text) {
  let t = (text || "").normalize("NFKD").toLowerCase();
  t = t.replace(/\p{M}+/gu, "");
  t = t.replace(/\[[^\]]*\]|\([^)]*\)/g, " ");
  t = t.replace(/[’`]/g, "'");
  t = t.replace(/[^a-z0-9' \n]+/g, " ");
  return t.split(/\s+/).map(w => w.replace(/^'+|'+$/g, "")).filter(Boolean);
}

// grams(): sha1 of n words joined by spaces, first 8 bytes big-endian, masked
// to 63 bits so it fits SQLite's signed INTEGER exactly as Python does it.
const MASK = (1n << 63n) - 1n;
export async function grams(words, n = 3) {
  const enc = new TextEncoder(), out = new Set();
  for (let i = 0; i + n <= words.length; i++) {
    const buf = await crypto.subtle.digest("SHA-1", enc.encode(words.slice(i, i + n).join(" ")));
    const b = new Uint8Array(buf, 0, 8);
    let v = 0n;
    for (let k = 0; k < 8; k++) v = (v << 8n) | BigInt(b[k]);
    out.add((v & MASK).toString());          // string: JSON has no 64-bit ints
  }
  return [...out];
}
