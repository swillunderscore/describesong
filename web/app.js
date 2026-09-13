// describesong — page logic. Search; and "scan a folder": decode → fingerprint
// → ask the server if it's already in → (embed → submit) — all in the browser.
// THE EAR IS THE SERVER'S CHOICE, not a constant here. /api/stats says which
// model this database is built from; scanning with the other one would produce
// vectors nothing else can be compared to. Falls back to CLAP if stats is old.
let MODEL_ID = "Xenova/larger_clap_music_and_speech@fp16", EAR = "clap";
const $ = s => document.querySelector(s);

// A different example every load — the box should read like a real memory,
// not the same demo line forever.
const EXAMPLES = [
  "hard electro house with a massive bass drop and a chanted vocal hook",
  "slow acoustic guitar, a guy singing softly about leaving town, sounds like it was recorded in a bedroom",
  "nineties boom bap with a jazzy piano loop and scratching in the chorus",
  "dreamy shoegaze wall of guitars, female vocals buried in reverb",
  "aggressive dubstep with huge wobbling bass and screeching synths",
  "eighties synth pop with a gated snare and a saxophone solo",
  "solo nylon-string guitar, brazilian, intricate fingerpicking, no vocals",
  "big band swing with a brass section and a crooner",
  "lo-fi hip hop beat, warm pads, dusty drums, rain sounds at the start",
  "moody alternative r&b, soft male vocals, sparse 808s",
  "fast punk rock, shouted gang vocals, under two minutes",
  "ambient piano with long reverb tails and a string drone",
  "reggaeton beat with an autotuned hook and a spanish guitar intro",
  "psychedelic surf funk trio, reverb guitar, no vocals",
  "trap song with a flute melody and a whispered chorus",
  "drum and bass with a soulful female vocal and a liquid bassline",
  "the one that goes: we're up all night to get lucky",
  "female vocals, acoustic guitar, whistling in the intro, sounds like 2010",
  "early 2000s, norwegian, plucky synth riff, no vocals",
  "instrumental, plucked synth melody, slow hip hop drums, warm bass",
];
$("#q").placeholder = EXAMPLES[Math.floor(Math.random() * EXAMPLES.length)];
const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// ---- bar stats ---------------------------------------------------------------
// The counts are LIVE: the server pushes them whenever a track is added
// (Server-Sent Events, one idle connection, no polling). EventSource
// reconnects by itself, and the first message is the current state, so there
// is no separate fetch.
// Full numbers, never "1.3k": an odometer per count, one cell per digit, a
// thin gap every three, and a roll when a digit changes.
function odometer(el, n, prefix) {
  const digits = String(Math.max(0, Math.floor(n))).split("");
  const want = (prefix ? "p" : "") + digits.map((_, i) => ((digits.length - i) % 3 === 0 && i ? "g" : "") + "d").join("");
  if (el.dataset.shape !== want) {                       // digit count changed: rebuild without animation
    el.dataset.shape = want; el.innerHTML = "";
    if (prefix) { const p = document.createElement("span"); p.className = "sym"; p.textContent = prefix; el.appendChild(p); }
    digits.forEach((_, i) => {
      if ((digits.length - i) % 3 === 0 && i) { const g = document.createElement("span"); g.className = "gap"; el.appendChild(g); }
      const dg = document.createElement("span"); dg.className = "dg";
      const col = document.createElement("span"); col.className = "col"; col.style.transition = "none";
      for (let d = 9; d >= 0; d--) { const x = document.createElement("span"); x.textContent = d; col.appendChild(x); }   // 9 on top: a rising count rolls the digit DOWN, the next one arriving from above
      dg.appendChild(col); el.appendChild(dg);
    });
    requestAnimationFrame(() => { for (const c of el.querySelectorAll(".col")) c.style.transition = ""; });
  }
  el.querySelectorAll(".col").forEach((col, i) => { col.style.transform = `translateY(-${(9 - digits[i]) * 1.3}em)`; });
}
let lastN = null;
const renderStats = st => {
  if (st.model && st.ear) { MODEL_ID = st.model; EAR = st.ear; }
  const n = st.tracks || 0;
  odometer($("#odoTracks"), n); odometer($("#odoWeek"), st.week || 0, "+");
  $("#tTracks").textContent = "of ~200M ever released";
  lastN = n;
};
const es = new EventSource("/api/events");
let bannerTimer = null;
function banner(html, progress) {
  const b = $("#banner"); clearTimeout(bannerTimer);
  if (html == null) { b.hidden = true; return; }
  b.innerHTML = html + (progress == null ? "" : `<span class="bar"><i style="width:${Math.round(100 * progress)}%"></i></span>`); b.hidden = false;
}
const mmss = s => s == null ? "" : s < 60 ? `about ${Math.max(5, Math.round(s / 5) * 5)} s left` : `about ${Math.round(s / 60)} min left`;
// A rebuild is the server reorganising the index because the collection outgrew
// the fast exact path — i.e. the site got used. One line, then a short notice, then gone.
function showRebuild(r) {
  const n = (r.total || 0).toLocaleString();
  if (r.state === "running") banner(`<b>Reorganising the index</b> — ${n} tracks outgrew the fast path. ${r.note === "training" ? "Learning the layout…" : mmss(r.eta_s)} <a href="legal.html#scale">Why?</a>`, r.total ? r.done / r.total : 0);
  else if (r.state === "done") { banner(`<b>Index rebuilt:</b> ${n} tracks. Searches are very-nearly-exact, with a full check running after each one. <a href="legal.html#scale">What that means</a>`); bannerTimer = setTimeout(() => banner(null), 90000); }
  else if (r.state === "failed") { banner(`<b>Index rebuild failed</b> — searching continues on the previous index. (${esc(r.note || "")})`); bannerTimer = setTimeout(() => banner(null), 60000); }
}
es.onmessage = e => { try { const d = JSON.parse(e.data); if ("tracks" in d) renderStats(d); if (d.rebuild) showRebuild(d.rebuild); if (d.media) fillCover(d.media); } catch {} };
// a cover looked up while this page is open lands in its row (the store lookup runs on the Pi, results first)
function fillCover(m) {
  for (const row of document.querySelectorAll(`.hit[data-id="${m.id}"]`)) {
    const old = row.querySelector(".cover"); if (!old || old.classList.contains("play")) continue;
    const tpl = document.createElement("template"); tpl.innerHTML = coverHtml({ id: m.id, cover: m.cover, play: m.play }); old.replaceWith(tpl.content.firstElementChild);
    if (m.play && !row.querySelector(".src")) row.querySelector(".tagcol")?.insertAdjacentHTML("beforeend", `<a class="src" href="#" target="_blank" rel="noopener"></a>`);
  }
}
es.onerror = () => { if (lastN === null) $("#tTracks").textContent = "offline"; };

// ---- search -----------------------------------------------------------------
// One search = one query; pages of 30 arrive as you scroll (a sentinel at the
// bottom asks for the next page), so the list is as long as the index.
let cur = null;                                   // { q, exact, offset, done, seq }
let seqNo = 0;
const PAGE = 30;
$("#f").addEventListener("submit", async e => {
  e.preventDefault();
  const q = $("#q").value.trim(); if (!q) return;
  $("#res").innerHTML = '<span class="blk">searching…</span>'; $("#hint").hidden = true;
  const so = $("#soundOnly") && $("#soundOnly").checked ? "&sound_only=1" : "";
  const mine = ++seqNo; cur = { q, exact: false, offset: 0, done: false, seq: mine, so };
  const r = await fetch("/api/search?q=" + encodeURIComponent(q) + "&k=" + PAGE + so).then(r => r.json()).catch(() => null);
  if (mine !== seqNo) return;
  if (!r) { $("#res").innerHTML = '<span class="blk b">server unreachable</span>'; return; }
  if (r.quoted_miss) { $("#hint").textContent = "No song in the index has those quoted words in its lyrics. Showing the closest sounds instead."; $("#hint").hidden = false; }
  else if (r.broad) { $("#hint").textContent = "No clear winner — that fits a lot of the music here about equally. Add an instrument, an era, or a mood."; $("#hint").hidden = false; }
  else if (r.small) { $("#hint").textContent = `Only ${r.count} track${r.count === 1 ? "" : "s"} in the database so far — confidences are rough until there are more.`; $("#hint").hidden = false; }
  if (!r.results.length) { $("#res").innerHTML = `<span class="blk">nothing in the database yet (${r.count} tracks) — add some below.</span>`; return; }
  $("#res").innerHTML = ""; appendResults(r.results, 0); cur.offset = r.results.length; cur.done = r.results.length < PAGE; sentinel();
  if (r.exact === false) {
    // the index answered from candidates; now check EVERY track, at low priority
    const more = document.createElement("div"); more.id = "more"; more.innerHTML = '<span class="spin"></span>Checking every track…'; $("#res").appendChild(more);
    const ex = await fetch("/api/search?q=" + encodeURIComponent(q) + "&k=" + PAGE + "&exact=1" + so).catch(() => null);
    if (mine !== seqNo) return;
    if (ex && ex.ok) { const rr = await ex.json(); more.remove(); swapResults(rr.results); cur.exact = true; cur.offset = rr.results.length; cur.done = rr.results.length < PAGE; sentinel();
      const d = document.createElement("div"); d.id = "more"; d.textContent = "Checked every track."; $("#res").appendChild(d); }
    else more.remove();                                    // 503 = the server was busy; the fast answer stands
  }
});
const io = new IntersectionObserver(async ents => {
  if (!ents.some(x => x.isIntersecting) || !cur || cur.done || cur.loading) return;
  cur.loading = true; const mine = cur.seq;
  const r = await fetch(`/api/search?q=${encodeURIComponent(cur.q)}&k=${PAGE}&offset=${cur.offset}${cur.exact ? "&exact=1" : ""}${cur.so || ""}`).then(r => r.ok ? r.json() : null).catch(() => null);
  if (!cur || mine !== cur.seq) return;
  cur.loading = false;
  if (!r || !r.results.length) { cur.done = true; sentinel(); return; }
  appendResults(r.results, cur.offset); cur.offset += r.results.length; cur.done = r.results.length < PAGE; sentinel();
});
function sentinel() {
  let s = $("#sentinel"); if (s) s.remove();
  if (cur && !cur.done) { s = document.createElement("div"); s.id = "sentinel"; s.style.height = "1px"; $("#res").appendChild(s); io.observe(s); }
}
const coverHtml = t => t.play ? `<button type="button" class="cover play" data-id="${t.id}" title="30-second preview" aria-label="play a 30-second preview">${t.cover ? `<img src="${esc(t.cover)}" alt="" loading="lazy">` : ""}<svg viewBox="0 0 24 24" aria-hidden="true"><path class="tri" d="M8 5v14l11-7z"/><path class="bars" d="M7 5h4v14H7zM13 5h4v14h-4z"/></svg></button>`
  : t.cover ? `<span class="cover"><img src="${esc(t.cover)}" alt="" loading="lazy"></span>` : `<span class="cover ph"></span>`;
// WHAT CAN FIND THIS TRACK. "unverified" only ever said one thing and it was
// the least useful one; these are the search paths that exist for this row.
const PATHS = [
  ["words", "lyrics", "no lyrics for this one, so a line you remember can't find it"],
  ["when", "year", "the year is unknown, so \u201cearly 2000s\u201d can't find it"],
  ["where", "country", "the country is unknown, so \u201cnorwegian\u201d can't find it"],
];
function knownHtml(t) {
  const h = t.has; if (!h) return "";
  // only what is MISSING. What the index has needs no announcement, and the
  // sound is always there — that is the whole point of the site.
  const miss = PATHS.filter(([k]) => !h[k] && !(k === "words" && h.instrumental));
  if (!miss.length) return "";
  return `<span class="known" title="the index has no ${miss.map(([, l]) => l).join(", no ")} for this track, so those words can't find it">`
    + miss.map(([, label, why]) => `<span class="pip off" title="${why}">no ${label}</span>`).join("") + `</span>`;
}
// CAN THIS BROWSER USE THE GRAPHICS CARD? Having a GPU is not enough — WebGPU
// is a browser feature, and which browser on which system decides. The
// difference is ~1.5 s a track against ~36 s, so say it plainly, before the
// scan rather than after, and say what would fix it.
async function gpuCheck() {
  const box = $("#gpu"); if (!box) return;
  const ua = navigator.userAgent;
  const firefox = /Firefox\//.test(ua), safari = /Safari\//.test(ua) && !/Chrome|Chromium|Edg\//.test(ua);
  const linux = /Linux/.test(ua) && !/Android/.test(ua);
  let adapter = null;
  try { adapter = navigator.gpu ? await navigator.gpu.requestAdapter() : null; } catch {}
  // SAY NOTHING WHEN IT IS FINE. The button already says what a GPU costs; a
  // banner underneath repeating it was the same fact twice, stacked.
  if (adapter) { box.hidden = true; return; }
  {
    const fix = firefox ? "Firefox only has it on Windows so far. Chrome or Edge will do the same scan about twenty times faster."
      : safari ? "Safari added it recently — updating macOS or iOS may be enough. Chrome or Edge will work today."
      : linux ? "On Linux this often needs enabling: open <code>chrome://flags</code>, turn on <b>Unsafe WebGPU Support</b>, and restart the browser."
      : "Chrome or Edge will do the same scan about twenty times faster.";
    box.className = "gpu no";
    box.innerHTML = `<b>This browser can't use your graphics card.</b> A scan would take about 36 seconds a track instead of 1.5. ${fix}`;
  }
  box.hidden = false;
}
gpuCheck();
const ordinal = n => n + (n % 100 >= 11 && n % 100 <= 13 ? "th" : ["th", "st", "nd", "rd", "th", "th", "th", "th", "th", "th"][n % 10]);
function rowHtml(t, i, start) {
  return `<article class="blk hit" style="--d:${(i % PAGE) * 20}ms" data-id="${t.id}">
      ${coverHtml(t)}
      <span class="ring" style="--p:${t.confidence}"><span>${t.confidence}</span></span>
      <div><div class="t"><span class="n">${String(start + i + 1).padStart(2, "0")}</span>${esc(t.title || "untitled")}</div>
        <div class="s">${esc(t.artist || "unknown artist")}${t.album ? ` · ${esc(t.album)}` : ""}${t.year || t.country ? ` <span class="facts">${[t.year, t.country_name || t.country].filter(Boolean).map(esc).join(" · ")}</span>` : ""}</div>
        <button type="button" class="hear" data-id="${t.id}">What the index hears ▾</button><div class="tags" hidden></div></div>
      <span class="tagcol">${t.via === "lyrics" ? '<span class="tag via">matched the words</span>' : t.via === "name" ? '<span class="tag via">matched the name</span>' : ""}${knownHtml(t)}${t.play ? `<a class="src" href="#" target="_blank" rel="noopener"></a>` : ""}</span>
    </article>`;
}
function appendResults(results, start) {
  const frag = document.createElement("template");
  frag.innerHTML = results.map((t, i) => rowHtml(t, i, start)).join("");
  const more = $("#more"); const anchor = $("#sentinel") || more;
  if (anchor) $("#res").insertBefore(frag.content, anchor); else $("#res").appendChild(frag.content);
}
// Replace the list with the exact one, animated: rows keep their identity by
// track id — the ones that stay slide to their new rank, newcomers fade in,
// the ones that fall off fade out. (FLIP: measure, swap, invert, play.)
function swapResults(results) {
  const res = $("#res"), before = new Map();
  for (const el of res.querySelectorAll(".hit")) before.set(el.dataset.id, el.getBoundingClientRect().top);
  const keep = new Set(results.map(t => String(t.id)));
  const leaving = [...res.querySelectorAll(".hit")].filter(el => !keep.has(el.dataset.id));
  for (const el of leaving) { el.style.transition = "opacity .35s, transform .35s"; el.style.opacity = "0"; el.style.transform = "scale(.98)"; el.style.pointerEvents = "none"; }
  setTimeout(() => {
    for (const el of leaving) el.remove();
    const old = new Map(); for (const el of res.querySelectorAll(".hit")) old.set(el.dataset.id, el);
    res.querySelectorAll(".hit, #sentinel").forEach(el => el.remove());
    results.forEach((t, i) => {
      let el = old.get(String(t.id));
      if (el) { el.querySelector(".n").textContent = String(i + 1).padStart(2, "0"); el.querySelector(".ring").style.setProperty("--p", t.confidence); el.querySelector(".ring span").textContent = t.confidence; el.style.animation = "none"; }
      else { const tpl = document.createElement("template"); tpl.innerHTML = rowHtml(t, i, 0); el = tpl.content.firstElementChild; el.style.opacity = "0"; }
      res.appendChild(el);
    });
    for (const el of res.querySelectorAll(".hit")) {
      const from = before.get(el.dataset.id);
      if (from != null) { const dy = from - el.getBoundingClientRect().top; if (dy) { el.style.transition = "none"; el.style.transform = `translateY(${dy}px)`; requestAnimationFrame(() => { el.style.transition = "transform .55s cubic-bezier(.2,.8,.2,1)"; el.style.transform = ""; }); } }
      else requestAnimationFrame(() => { el.style.transition = "opacity .45s"; el.style.opacity = "1"; });
    }
  }, leaving.length ? 350 : 0);
}
// PREVIEWS. One player for the page; the cover is the button. The audio is the
// store's own 30-second preview, streamed from Apple or Deezer, never from here.
const player = new Audio(); player.preload = "none"; player.hidden = true; document.body.appendChild(player); let playingId = null;   // in the document: Chrome aborts play() on a detached element
const setPlaying = id => {
  playingId = id;
  for (const el of document.querySelectorAll(".hit.playing")) el.classList.remove("playing");
  if (id != null) { const row = document.querySelector(`.hit[data-id="${id}"]`); if (row) row.classList.add("playing"); }
};
player.addEventListener("ended", () => setPlaying(null)); player.addEventListener("pause", () => { if (player.ended || player.currentTime === 0) setPlaying(null); });
player.addEventListener("timeupdate", () => { const row = playingId != null && document.querySelector(`.hit[data-id="${playingId}"]`); if (row && player.duration) row.style.setProperty("--played", (player.currentTime / player.duration).toFixed(3)); });
$("#res").addEventListener("click", async e => {
  const b = e.target.closest(".cover.play"); if (!b) return;
  const id = b.dataset.id;
  if (playingId === id) { if (player.paused) { player.play(); b.closest(".hit").classList.add("playing"); } else { player.pause(); b.closest(".hit").classList.remove("playing"); } return; }
  const r = await fetch("/api/play/" + id).then(r => r.ok ? r.json() : null).catch(() => null);
  if (!r) { b.classList.add("dead"); b.title = "no preview"; return; }
  player.src = r.url; setPlaying(id); player.play().catch(err => { console.warn("preview:", err.name, err.message); setPlaying(null); });
  const row = b.closest(".hit"), src = row.querySelector(".src");
  if (src) { src.href = r.link; src.textContent = r.source === "itunes" ? "on Apple Music" : "on Deezer"; }
});
// "More like this": the track's own vector as the query — browsing by sound.
$("#res").addEventListener("click", async e => {
  const b = e.target.closest(".morelike"); if (!b) return;
  const row = b.closest(".hit"), title = row.querySelector(".t").textContent.replace(/^\d+/, "").trim(), artist = row.querySelector(".s").textContent.trim();
  const r = await fetch("/api/similar/" + b.dataset.id).then(r => r.ok ? r.json() : null).catch(() => null);
  if (!r) return;
  cur = null; sentinel();
  $("#res").innerHTML = `<div class="similar-head"><span class="k">More like</span><b>${esc(title)}</b><span class="s">${esc(artist)}</span></div>`;
  appendResults(r.results, 0); window.scrollTo({ top: $("#res").getBoundingClientRect().top + scrollY - 90, behavior: "smooth" });
});
// "What the index hears": the track's vector read back as the phrases it sits
// closest to — the words that would find it. Fetched on demand, per track.
$("#res").addEventListener("click", async e => {
  const b = e.target.closest(".hear"); if (!b) return;
  const box = b.nextElementSibling;
  if (!box.hidden) { box.hidden = true; b.textContent = "What the index hears ▾"; return; }
  b.textContent = "What the index hears ▴";
  if (!box.dataset.loaded) {
    box.innerHTML = '<span class="spin"></span>'; box.hidden = false;
    const d = await fetch("/api/describe/" + b.dataset.id).then(r => r.ok ? r.json() : null).catch(() => null);
    box.innerHTML = d ? (d.events && d.events.length ? d.events.map(e => `<span class="chip ev" title="heard by the sound tagger, ${Math.round(e.prob * 100)}%">${esc(e.cls.toLowerCase())}</span>`).join("") + '<span class="chipnote">Heard in the track (sound tagger). Search these words directly.</span>' : "") + [...d.tags].sort((x, y) => (x.rank || 1e9) - (y.rank || 1e9)).map(t => `<span class="chip" title="${t.group}${t.rank ? ` — typing this word alone puts the track ${ordinal(t.rank)} of ${d.count}` : ""}">${esc(t.tag)} <small>${t.rank ? ordinal(t.rank) : t.pct}</small></span>`).join("") + `<span class="chipnote">${d.tags.some(t => t.rank) ? `Each word with where typing it alone would put this track, out of ${d.count.toLocaleString()}. The low numbers find it; the rest only land in the neighbourhood.` : "The words the model associates with this track — the closest it gets to describing the sound."} <button type="button" class="ghost morelike" data-id="${b.dataset.id}">More like this</button></span>` : "couldn't load"; box.dataset.loaded = "1";
  }
  box.hidden = false;
});


// ---- scan a folder ------------------------------------------------------------
const worker = new Worker("worker.js", { type: "module" });
const pending = new Map(); let seq = 0;
worker.onmessage = ({ data }) => { const p = pending.get(data.id); if (!p) return; pending.delete(data.id); data.error ? p.reject(new Error(data.error)) : p.resolve(data); };
const ask = (msg, tr) => new Promise((resolve, reject) => { const id = ++seq; pending.set(id, { resolve, reject }); worker.postMessage({ id, ...msg }, tr || []); });

// Chrome's own folder prompt for <input webkitdirectory> says "upload", which
// is exactly the wrong word. The File System Access picker says "view files"
// and is used where it exists (Chrome/Edge desktop); the input is the fallback.
$("#pick").onclick = async () => {
  if (!window.showDirectoryPicker) return $("#folder").click();
  let dir; try { dir = await window.showDirectoryPicker({ mode: "read", id: "music", startIn: "music" }); } catch { return; }
  const files = []; const walk = async (d, depth) => { for await (const h of d.values()) { if (h.kind === "file") files.push(await h.getFile()); else if (depth < 8) await walk(h, depth + 1); } };
  $("#status").textContent = "reading folder…"; $("#prog").hidden = false; await walk(dir, 0); scan(files);
};
$("#folder").addEventListener("change", e => scan([...e.target.files]).finally(() => { e.target.value = ""; }));

$("#pickLyrics").onclick = async () => {
  if (!window.showDirectoryPicker) return $("#folderLyrics").click();
  let dir; try { dir = await window.showDirectoryPicker({ mode: "read", id: "music", startIn: "music" }); } catch { return; }
  const files = []; const walk = async (d, depth) => { for await (const h of d.values()) { if (h.kind === "file") files.push(await h.getFile()); else if (depth < 8) await walk(h, depth + 1); } };
  $("#status").textContent = "reading folder…"; $("#prog").hidden = false; await walk(dir, 0);
  lyricsOnly(files.filter(f => AUDIO_RE.test(f.name)));
};
$("#folderLyrics").addEventListener("change", e => lyricsOnly([...e.target.files].filter(f => AUDIO_RE.test(f.name))).finally(() => { e.target.value = ""; }));

const AUDIO_RE = /\.(mp3|flac|wav|m4a|ogg|opus)$/i;   // one definition, used by both pickers
let scanning = false, stopRequested = false;
$("#stop").onclick = () => { stopRequested = true; $("#stop").textContent = "stopping after the current file…"; };
// Closing or leaving the tab kills the worker mid-scan. Finished tracks are
// already on the server (and skipped next time), but ask before losing the rest.
window.addEventListener("beforeunload", ev => { if (scanning) { ev.preventDefault(); ev.returnValue = ""; } });
const DONE_KEY = "describesong.done.v3";   // v2: files finished before the sound tagger existed are looked at again (identify is cheap; known tracks with events skip)
const doneKey = f => `${f.name}|${f.size}|${f.lastModified}`;
// key -> fp_hash. It used to be a bare list of keys, so a file the sound scan
// skipped had no known fingerprint and could never be offered to the lyrics
// pass — which is why a folder of 564 tracks needing words only ever showed a
// fraction of them. Old lists load as keys with a null hash and gain one the
// next time that file is seen.
function loadDone() {
  try {
    const raw = JSON.parse(localStorage.getItem(DONE_KEY) || "[]");
    return new Map(Array.isArray(raw) ? raw.map(x => Array.isArray(x) ? x : [x, null]) : Object.entries(raw));
  } catch { return new Map(); }
}
function saveDone(m) { try { localStorage.setItem(DONE_KEY, JSON.stringify([...m])); } catch {} }
const fmt = s => { s = Math.round(s); const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), x = s % 60; return h ? `${h}:${String(m).padStart(2, "0")}:${String(x).padStart(2, "0")}` : `${m}:${String(x).padStart(2, "0")}`; };
// A 429 from the server means "slow down", not "this file failed": wait and retry,
// and say so in the status line. Any other error carries the server's reason.
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function post(url, body) {
  for (let i = 0; ; i++) {
    // A server restart (a deploy) is a few seconds of refused connections or
    // 502s from the tunnel; that is not "this file failed" either.
    let r;
    try { r = await fetch(url, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) }); }
    catch (e) { if (i < 6) { const wait = 5 * (i + 1); $("#status").textContent += `\nserver unreachable — retrying in ${wait} s`; await sleep(wait * 1000); continue; } throw e; }
    if ((r.status === 502 || r.status === 503 || r.status === 504) && i < 6) { const wait = 5 * (i + 1); $("#status").textContent += `\nserver restarting — retrying in ${wait} s`; await sleep(wait * 1000); continue; }
    if (r.status === 429 && i < 6) { const wait = 20 * (i + 1); $("#status").textContent += `\nserver asked us to slow down — retrying in ${wait} s`; await sleep(wait * 1000); continue; }
    let j = null; try { j = await r.json(); } catch {}
    if (!r.ok) throw new Error((j && j.detail) || `HTTP ${r.status}`);
    return j;
  }
}

async function scan(all) {
  if (scanning) return;
  const audio = all.filter(f => AUDIO_RE.test(f.name));
  $("#prog").hidden = false;
  // (log lives at module scope — the lyrics pass runs outside this function)
  if (!audio.length) { $("#status").textContent = `No audio files in that folder (${all.length} files looked at). MP3, FLAC, WAV, M4A, OGG or Opus.`; return; }
  // RESUME, two layers: this browser remembers files it finished (name+size+
  // mtime); and the server is asked, by fingerprint, before every embed — so a
  // scan resumed in another browser, or of a renamed file, skips too.
  const doneSet = loadDone();
  const files = audio.filter(f => !doneSet.has(doneKey(f)));
  const skippedKnown = audio.filter(f => doneSet.get(doneKey(f)));   // skipped by sound, may still need words
  const skipped = audio.length - files.length;
  if (skipped) log(`↷ ${skipped} file${skipped === 1 ? "" : "s"} finished earlier — skipped`);
  // NOT A DEAD END. Every file may already be indexed by sound and still have no
  // words anywhere, so the lyrics pass runs on its own from the fingerprints
  // remembered last time. Returning here is what made a fully scanned folder
  // say "nothing new" and do nothing.
  if (!files.length) return lyricsOnly(audio);
  $("#bar").max = files.length; $("#bar").value = 0;
  let done = 0, sent = 0, ident = 0, failed = 0, known = 0, noEv = 0, current = "";
  const byHash = new Map();          // fp_hash -> File, for the lyrics pass
  scanning = true; stopRequested = false; $("#stop").hidden = false; $("#stop").textContent = "Stop";
  document.documentElement.dataset.scanning = "1";   // water.js pauses the simulation: the GPU belongs to the model now
  const t0 = performance.now();
  // the size is the ACTIVE ear's, not a constant: this said 143 MB (CLAP's)
  // for hours after the switch to MuLan, which downloads 606 MB.
  $("#status").textContent = `loading the model… (downloads ${EAR === "mulan" ? "about 600 MB" : "143 MB"} the first time, then it is cached)`;
  // ask the server directly rather than trusting whatever the live-stats
  // stream has sent so far: scanning with the wrong ear wastes the whole run
  try { const st = await fetch("/api/stats").then(r => r.json()); if (st.model && st.ear) { MODEL_ID = st.model; EAR = st.ear; } } catch {}
  let initr; try { initr = await ask({ type: "init", ear: EAR }); } catch (err) { $("#status").textContent = "model failed to load: " + err.message; scanning = false; $("#stop").hidden = true; delete document.documentElement.dataset.scanning; return; }
  const backend = initr.device === "webgpu" ? "GPU" : "CPU — no WebGPU in this browser, slower";
  // say what actually happened, not what was available. The banner above is a
  // capability check made before any model loads; this is the truth.
  const gbox = $("#gpu");
  if (gbox) {
    if (initr.device === "webgpu") gbox.hidden = true;      // working as advertised: no need to say so
    else {
      gbox.className = "gpu no";
      gbox.innerHTML = "<b>Running on the processor, not your graphics card.</b> The model could not start on the GPU here, so this will be far slower. Chrome or Edge usually manage it.";
      gbox.hidden = false;
    }
  }
  const progress = () => {
    const el = (performance.now() - t0) / 1000, left = done ? el / done * (files.length - done) : 0;
    $("#status").textContent = `${done} of ${files.length} · ${sent} added (${ident} identified, ${sent - ident} unverified)${known ? ` · ${known} already in` : ""}${failed ? ` · ${failed} failed` : ""} · ${backend} · ${fmt(el)} elapsed${done ? ` · about ${fmt(left)} left` : ""}${current ? `\n${current}` : ""}`;
  };
  // ok=false: the file is finished for this run but NOT remembered as done, so the next pick tries it again
  const finishOne = (f, ok = true, hash = null) => { if (ok) { doneSet.set(doneKey(f), hash || doneSet.get(doneKey(f)) || null); saveDone(doneSet); } $("#bar").value = ++done; progress(); const pct = Math.round(100 * done / files.length); $("#rScan").style.setProperty("--p", pct); $("#nScan").textContent = pct + "%"; };
  let confirmChain = Promise.resolve();                       // one dialog at a time
  const confirmSerial = (...a) => (confirmChain = confirmChain.then(() => confirmPrior(...a)));

  // STAGE A (cheap, runs one file ahead): decode → fingerprint → ask the server.
  const stageA = async f => {
    const pcm = await decode(f);
    const fpr = await ask({ type: "fingerprint", pcm, sampleRate: 48000 }, [pcm.buffer]);
    const idr = await post("/api/identify", { fingerprint: fpr.fingerprint, duration: fpr.duration });
    return { fpr, idr };
  };
  // STAGE B (the GPU, the only serial cost): embed → submit, overlapped with the next A.
  const net = new Set();
  const finish = async (f, a, r, ev) => {
    const { fpr, idr } = a; let good = false;
    try {
      // AcoustID can know the recording but hand back an empty title/artist;
      // keep its id, but never store a blank label when the file has tags.
      const tags = (await readTags(f)) || guessFromName(f.name);
      let label = idr.mbid && (idr.title || idr.artist) ? { artist: idr.artist || tags.artist, title: idr.title || tags.title, album: idr.album || tags.album } : { artist: tags.artist, title: tags.title, album: tags.album };
      const facts = { year: tags.year || null, genre: tags.genre || null };
      if (!idr.mbid && idr.prior && (idr.prior.artist || idr.prior.title)) {
        if (normL(idr.prior) === normL(label)) {
          if (!r && !ev) { log(`= ${label.artist || "?"} — ${label.title || f.name} (already in, same label)`); good = true; return; }   // nothing new to say (with sounds tagged there is)
        } else {
          const ok = await confirmSerial(idr.prior, label);
          if (ok) label = { artist: idr.prior.artist, title: idr.prior.title, album: idr.prior.album };
        }
      }
      const sub = await post("/api/submit", { model: MODEL_ID, fp_hash: idr.fp_hash, mbid: idr.mbid || null, acoustid: idr.acoustid || null, duration: fpr.duration, ...label, ...facts, events: ev || null, mean: r ? r.mean : null, moments: r ? r.moments : [] });
      const heard = ev ? Object.entries(ev).filter(([, p]) => p >= 0.3).sort((x, y) => y[1] - x[1]).slice(0, 3).map(([k]) => k.toLowerCase()).join(", ") : "";
      if (sub.ok) { good = true; if (r) { sent++; if (idr.mbid) ident++; log(`${idr.mbid ? "✓" : "?"} ${label.artist || "?"} — ${label.title || f.name}${heard ? "  · " + heard : ""}`); } else log(`= ${label.artist || "?"} — ${label.title || f.name} (already in${ev ? " — sounds added" + (heard ? ": " + heard : "") : " — label confirmed"})`); }
      else { failed++; log(`✗ ${f.name}: ${sub.detail || "rejected"}`); }
    } catch (err) { failed++; log(`✗ ${f.name}: ${err.message}`); }
    finally { finishOne(f, good, idr && idr.fp_hash); }
  };
  let nextA = stageA(files[0]).catch(e => e);
  for (let i = 0; i < files.length; i++) {
    const f = files[i];
    if (stopRequested) break;
    current = f.name; progress();
    const a = await nextA;
    if (i + 1 < files.length) nextA = stageA(files[i + 1]).catch(e => e);
    if (a instanceof Error) { failed++; log(`✗ ${f.name}: ${a.message}`); finishOne(f, false); continue; }
    if (a.idr && a.idr.fp_hash) byHash.set(a.idr.fp_hash, f);
    // has_vector false means this database has switched ears since the track
    // went in: it has no vector in the active model's space, so it must be
    // embedded again like a new one. Without this a switch would quietly leave
    // every known track unsearchable.
    if (a.idr.known && a.idr.has_vector !== false) {
      // Already in. Skip the embed. If the index has no sound events for it yet
      // (scanned before the tagger existed), tag it now and send only that;
      // unverified tracks also offer our tags as a label vote.
      known++;
      let ev = null;
      if (!a.idr.has_events) { try { ev = (await ask({ type: "events", ref: a.fpr.ref })).events; } catch (err) { noEv++; log(`✗ ${f.name}: sounds not tagged — ${err.message}`); } }
      else await ask({ type: "drop", ref: a.fpr.ref }).catch(() => {});
      if (a.idr.mbid && !ev) { log(`= ${a.idr.artist || "?"} — ${a.idr.title || f.name} (already in${a.idr.has_events ? ", sounds known" : ""})`); finishOne(f, !!a.idr.has_events); }
      else { const p = finish(f, a, null, ev); net.add(p); p.finally(() => net.delete(p)); }
      continue;
    }
    let r, ev = null;
    try { ev = (await ask({ type: "events", ref: a.fpr.ref, keepHeld: true })).events; } catch (err) { noEv++; log(`✗ ${f.name}: sounds not tagged — ${err.message}`); }
    try { r = await ask({ type: "embed", ref: a.fpr.ref }); }
    catch (err) { failed++; log(`✗ ${f.name}: ${err.message}`); finishOne(f, false); continue; }
    const p = finish(f, a, r, ev); net.add(p); p.finally(() => net.delete(p));
    if (net.size >= 4) await Promise.race(net);
  }
  await Promise.all(net);
  // The flag STAYS SET across the gap below. Dropping it here left a window —
  // a network round trip wide — where closing the tab warned about nothing and
  // a second scan could start on top of this one. It is released once, at the
  // end, after the lyrics pass has had its turn.
  $("#stop").hidden = true; current = "";
  delete document.documentElement.dataset.scanning;
  // Ask BEFORE wording the finish line: saying "done" and then starting more
  // work is the thing he objected to, and it needs the answer first.
  for (const f of skippedKnown) byHash.set(doneSet.get(doneKey(f)), f);   // whole folder, not just this run
  const todo = stopRequested ? [] : await lyricsTodo(byHash);
  $("#status").textContent = `${stopRequested ? "stopped" : (todo.length ? "sounds indexed" : "done")} — ${sent} added (${ident} identified by fingerprint, ${sent - ident} unverified)${known ? `, ${known} already in` : ""}${failed ? `, ${failed} failed` : ""}${noEv ? `, ${noEv} without sounds` : ""}${skipped ? `, ${skipped} skipped` : ""} in ${fmt((performance.now() - t0) / 1000)}`;
  // PHASE TWO. The index is complete and searchable at this point; everything
  // below is extra. Only tracks LRCLIB has NO words for — never an instrumental,
  // never one it answered. Closing the tab here costs nothing.
  try { if (todo.length) await hearLyricsPass(byHash, todo); }
  finally { scanning = false; $("#stop").hidden = true; }
}

// ---- lyrics for the songs no database has words for -----------------------
const log = m => { $("#log").textContent = (m + "\n" + $("#log").textContent).slice(0, 6000); };
// WORDS WITHOUT RE-SCANNING. Matching on TAGS — a few hundred header bytes per
// file — finds which tracks still have no words anywhere without decoding a
// single one. That means this can run on its own, skipping the sound pass
// entirely, which is what you want when a library is already indexed.
async function lyricsOnly(audio) {
  // claim the flag BEFORE the slow tag-reading phase, or two quick clicks both
  // get past the guard and fight over the worker and the progress bar
  if (scanning) { $("#status").textContent = "Already working — press Stop first."; return; }
  if (!audio.length) { $("#status").textContent = "No audio files in that folder."; return; }
  scanning = true; stopRequested = false;
  try { await lyricsOnlyInner(audio); } finally { scanning = false; $("#stop").hidden = true; }
}
async function lyricsOnlyInner(audio) {
  $("#prog").hidden = false;
  $("#status").textContent = `Reading tags from ${audio.length} files to see which have no words…`;
  const tagged = [];
  for (const f of audio) { const t = (await readTags(f)) || guessFromName(f.name); tagged.push({ artist: t.artist, title: t.title }); }
  const byIndex = new Map();
  for (let i = 0; i < tagged.length; i += 2000) {
    const r = await post("/api/needs_lyrics_by_name", { tracks: tagged.slice(i, i + 2000) }).catch(() => null);
    for (const n of (r && r.need) || []) byIndex.set(n.i + i, n.fp_hash);
  }
  const heard = loadHeard();
  const only = new Map(), todo = [];
  for (const [i, h] of byIndex) { if (!heard.has(h)) { only.set(h, audio[i]); todo.push(h); } }
  if (!todo.length) { $("#status").textContent = `Nothing to do — every one of those ${audio.length} files either has words already or has none to find.`; return; }
  // the fingerprint module must exist before anything is fingerprinted
  try { await ask({ type: "init_fp" }); }
  catch (err) { $("#status").textContent = "could not start: " + err.message; return; }
  await hearLyricsPass(only, todo);
}

const LYR_KEY = "describesong.heard.v1";
const loadHeard = () => { try { return new Set(JSON.parse(localStorage.getItem(LYR_KEY) || "[]")); } catch { return new Set(); } };
const saveHeard = s => { try { localStorage.setItem(LYR_KEY, JSON.stringify([...s])); } catch {} };

async function lyricsTodo(byHash) {
  if (!byHash.size) return [];
  const hashes = [...byHash.keys()], need = [];
  for (let i = 0; i < hashes.length; i += 500) {
    const r = await post("/api/needs_lyrics", { fp_hashes: hashes.slice(i, i + 500) }).catch(() => null);
    if (r && r.need) need.push(...r.need);
  }
  const heard = loadHeard();
  return need.filter(h => !heard.has(h));
}

async function hearLyricsPass(byHash, todo) {
  if (!todo || !todo.length) return;
  // The water pauses on this flag. The scan clears it when the sound pass ends,
  // which is BEFORE this runs, and the tag-matching path never set it at all —
  // so the animation was competing with transcription for the GPU both ways.
  document.documentElement.dataset.scanning = "1";
  try { return await hearLyricsPassInner(byHash, todo); }
  finally { delete document.documentElement.dataset.scanning; }
}
async function hearLyricsPassInner(byHash, todo) {
  const heard = loadHeard();
  const base = $("#status").textContent;
  $("#stop").hidden = false; $("#stop").textContent = "Stop"; scanning = true;
  let n = 0, got = 0, t0 = performance.now();
  $("#bar").max = todo.length; $("#bar").value = 0;
  const tick = () => { $("#bar").value = n; const pct = Math.round(100 * n / todo.length);
    $("#rScan").style.setProperty("--p", pct); $("#nScan").textContent = pct + "%"; };
  tick();
  const say = extra => { $("#status").textContent = `${base}\n\nNo lyrics exist online for ${todo.length} of these. Listening for the words so they can be found by a line you remember — ${n} of ${todo.length}${got ? `, ${got} now searchable` : ""}. ${extra || "Close the tab whenever; nothing is lost."}`; };
  say("The model downloads once, then it's about ten seconds a track.");
  for (const h of todo) {
    if (stopRequested) break;
    const f = byHash.get(h); n++;
    try {
      const pcm = await decode(f);
      const fpr = await ask({ type: "fingerprint", pcm, sampleRate: 48000 }, [pcm.buffer]);
      const res = await ask({ type: "lyrics", ref: fpr.ref });
      if (res.grams && res.grams.length) {
        // WHICH RECORDING IS THIS, REALLY. `h` came from matching TAGS, and two
        // different recordings can share an artist and title — a live cut, a
        // remaster, someone else's upload. Sending the FINGERPRINT instead lets
        // the server decide from the audio actually in hand, in one request
        // rather than a separate identify per track.
        const r = await post("/api/submit_lyrics", { fingerprint: fpr.fingerprint, grams: res.grams, bigrams: res.bigrams, model: "whisper-large-v3-turbo" })
          .catch(() => null);
        if (r && r.ok && r.grams) { got++; log(`♪ ${f.name}: ${res.words} words heard`); }
        else if (r && r.skipped) log(`· ${f.name}: already has words, left alone`);
        else if (!r) log(`· ${f.name}: not a recording the index knows, skipped`);
      } else log(`· ${f.name}: nothing audible to transcribe`);
      heard.add(h); saveHeard(heard);
    } catch (err) {
      log(`✗ ${f.name}: lyrics — ${err.message}`);
      if (/could not load/i.test(err.message)) break;      // no model: stop, do not grind through every track
    }
    tick(); say(`about ${fmt((performance.now() - t0) / 1000 / Math.max(n, 1) * (todo.length - n))} left`);
  }
  scanning = false; $("#stop").hidden = true;
  $("#status").textContent = `${base}\n\nLyrics: ${got} of ${todo.length} tracks can now be found by their words.`;
}

async function decode(file) {
  const buf = await file.arrayBuffer();
  const probe = new OfflineAudioContext(1, 1, 48000);
  const audio = await probe.decodeAudioData(buf);              // decodes at the file's own rate
  const ctx = new OfflineAudioContext(1, Math.ceil(audio.duration * 48000), 48000);
  const src = ctx.createBufferSource(); src.buffer = audio; src.connect(ctx.destination); src.start();
  const out = await ctx.startRendering();                       // mono, 48 kHz — exactly what CLAP wants
  return out.getChannelData(0).slice();
}

function guessFromName(name) {
  const base = name.replace(/\.[^.]+$/, "").replace(/^\d+\s*[-.]\s*/, "");
  const m = base.split(/\s+-\s+/);
  return m.length >= 2 ? { artist: m[0], title: m.slice(1).join(" - "), album: null } : { artist: null, title: base, album: null };
}

const normL = l => `${(l.artist || "").trim().toLowerCase()}|${(l.title || "").trim().toLowerCase()}`;
const showL = l => `<b>${esc(l.title || "untitled")}</b> — ${esc(l.artist || "unknown artist")}${l.album ? ` <span class="s">· ${esc(l.album)}</span>` : ""}`;
// The recording is already in the index with a typed label (no fingerprint
// match) and the file's own tags say something DIFFERENT. Ask which is right.
// Resolves true = keep the existing label, false = use this file's tags.
function confirmPrior(prior, mine) {
  return new Promise(res => {
    $("#confirmText").innerHTML = `<p style="margin:0 0 10px">This recording is already in the index with a typed label (it isn't in the fingerprint database), and your file's tags disagree.</p>
      <div class="lbl"><span class="k">Existing label</span><span>${showL(prior)}</span><span class="k">Your label</span><span>${showL(mine)}</span></div>
      <p class="s" style="margin:0">Labelled this way by ${prior.submissions || 1} earlier scan${prior.submissions === 1 ? "" : "s"}.</p>`;
    const d = $("#confirm"); d.showModal();
    $("#cYes").onclick = () => { d.close(); res(true); }; $("#cNo").onclick = () => { d.close(); res(false); };
  });
}

// ---- tags -------------------------------------------------------------------
// Unidentified tracks (not in AcoustID — the obscure ones this exists for) are
// labelled from the file's OWN tags. The filename is the last resort: "06 -
// Outernational.mp3" carries no artist at all. Reads only the tag bytes, never
// the audio. ID3v2.2/2.3/2.4 and FLAC Vorbis comments; M4A/Ogg fall through.
async function readTags(file) {
  try {
    const head = new Uint8Array(await file.slice(0, 10).arrayBuffer());
    const s = String.fromCharCode(...head.subarray(0, 4));
    if (s.startsWith("ID3")) return id3v2(file, head);
    if (s === "fLaC") return flacTags(file);
  } catch (e) { console.warn("tags:", e.message); }
  return null;
}
const syncsafe = (b, o) => ((b[o] & 0x7f) << 21) | ((b[o + 1] & 0x7f) << 14) | ((b[o + 2] & 0x7f) << 7) | (b[o + 3] & 0x7f);
const u32be = (b, o) => ((b[o] << 24) | (b[o + 1] << 16) | (b[o + 2] << 8) | b[o + 3]) >>> 0;
const u32le = (b, o) => (b[o] | (b[o + 1] << 8) | (b[o + 2] << 16) | (b[o + 3] << 24)) >>> 0;
function id3text(b) {                       // first byte = encoding
  const enc = b[0], t = b.subarray(1);
  const dec = enc === 0 ? "latin1" : enc === 3 ? "utf-8" : enc === 2 ? "utf-16be" : "utf-16";
  return new TextDecoder(dec).decode(t).replace(/\0.*$/s, "").trim();
}
async function id3v2(file, head) {
  const ver = head[3], size = syncsafe(head, 6);
  const b = new Uint8Array(await file.slice(10, 10 + size).arrayBuffer());
  let o = (head[5] & 0x40) ? (ver === 4 ? syncsafe(b, 0) : u32be(b, 0) + 4) : 0;   // skip extended header
  const want = ver === 2 ? { TP1: "artist", TT2: "title", TAL: "album", TYE: "year", TCO: "genre" } : { TPE1: "artist", TIT2: "title", TALB: "album", TYER: "year", TDRC: "year", TDRL: "year", TCON: "genre" };
  const out = {}; const idLen = ver === 2 ? 3 : 4, hdr = ver === 2 ? 6 : 10;
  while (o + hdr <= b.length) {
    const id = String.fromCharCode(...b.subarray(o, o + idLen)); if (!/^[A-Z0-9]+$/.test(id)) break;
    const len = ver === 2 ? (b[o + 3] << 16) | (b[o + 4] << 8) | b[o + 5] : ver === 4 ? syncsafe(b, o + 4) : u32be(b, o + 4);
    if (want[id]) out[want[id]] = id3text(b.subarray(o + hdr, o + hdr + len));
    o += hdr + len;
  }
  const year = out.year ? parseInt(String(out.year).slice(0, 4), 10) : null;
  return out.title || out.artist ? { artist: out.artist || null, title: out.title || null, album: out.album || null, year: year && year > 1900 ? year : null, genre: out.genre ? out.genre.replace(/^\(\d+\)/, "").trim() || null : null } : null;
}
async function flacTags(file) {
  let o = 4;
  for (;;) {
    const h = new Uint8Array(await file.slice(o, o + 4).arrayBuffer()); if (h.length < 4) return null;
    const last = h[0] & 0x80, type = h[0] & 0x7f, len = (h[1] << 16) | (h[2] << 8) | h[3];
    if (type === 4) {
      const b = new Uint8Array(await file.slice(o + 4, o + 4 + len).arrayBuffer()), td = new TextDecoder();
      let p = 4 + u32le(b, 0); const n = u32le(b, p); p += 4; const out = {};
      for (let i = 0; i < n && p + 4 <= b.length; i++) {
        const l = u32le(b, p); p += 4; const kv = td.decode(b.subarray(p, p + l)); p += l;
        const eq = kv.indexOf("="); const k = kv.slice(0, eq).toUpperCase(), v = kv.slice(eq + 1).trim();
        if (k === "ARTIST" && !out.artist) out.artist = v; else if (k === "TITLE") out.title = v; else if (k === "ALBUM") out.album = v; else if (k === "DATE" || k === "YEAR") out.year = v; else if (k === "GENRE" && !out.genre) out.genre = v;
      }
      const year = out.year ? parseInt(String(out.year).slice(0, 4), 10) : null;
      return out.title || out.artist ? { artist: out.artist || null, title: out.title || null, album: out.album || null, year: year && year > 1900 ? year : null, genre: out.genre || null } : null;
    }
    if (last) return null; o += 4 + len;
  }
}
