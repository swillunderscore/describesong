// describesong — page logic. Search; and "scan a folder": decode → fingerprint
// → ask the server if it's already in → (embed → submit) — all in the browser.
const MODEL_ID = "Xenova/larger_clap_music_and_speech@fp16";   // must equal the server's
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
es.onmessage = e => { try { const d = JSON.parse(e.data); if (d.rebuild) showRebuild(d.rebuild); else { renderStats(d); if (d.rebuild) showRebuild(d.rebuild); } } catch {} };
es.onerror = () => { if (lastN === null) $("#tTracks").textContent = "offline"; };

// ---- search -----------------------------------------------------------------
$("#f").addEventListener("submit", async e => {
  e.preventDefault();
  const q = $("#q").value.trim(); if (!q) return;
  $("#res").innerHTML = '<span class="blk">searching…</span>'; $("#hint").hidden = true;
  const r = await fetch("/api/search?q=" + encodeURIComponent(q)).then(r => r.json()).catch(() => null);
  if (!r) { $("#res").innerHTML = '<span class="blk b">server unreachable</span>'; return; }
  if (r.broad) { $("#hint").textContent = "No clear winner — that fits a lot of the music here about equally. Add an instrument, an era, or a mood."; $("#hint").hidden = false; }
  else if (r.small) { $("#hint").textContent = `Only ${r.count} track${r.count === 1 ? "" : "s"} in the database so far — confidences are rough until there are more.`; $("#hint").hidden = false; }
  if (!r.results.length) { $("#res").innerHTML = `<span class="blk">nothing in the database yet (${r.count} tracks) — add some below.</span>`; return; }
  renderResults(r.results);
  if (r.exact === false) {
    // the index answered from candidates; now check EVERY track, at low priority
    const more = document.createElement("div"); more.id = "more"; more.innerHTML = '<span class="spin"></span>Checking every track…'; $("#res").appendChild(more);
    const ex = await fetch("/api/search?q=" + encodeURIComponent(q) + "&exact=1").catch(() => null);
    if (ex && ex.ok) { const rr = await ex.json(); renderResults(rr.results); const d = document.createElement("div"); d.id = "more"; d.textContent = "Checked every track."; $("#res").appendChild(d); }
    else more.remove();                                    // 503 = the server was busy; the fast answer stands
  }
});
function renderResults(results) {
  $("#res").innerHTML = results.map((t, i) => `
    <article class="blk hit" style="--d:${i * 30}ms">
      <span class="ring" style="--p:${t.confidence}"><span>${t.confidence}</span></span>
      <div><div class="t"><span class="n">${String(i + 1).padStart(2, "0")}</span>${esc(t.title || "untitled")}</div>
        <div class="s">${esc(t.artist || "unknown artist")}${t.album ? ` · ${esc(t.album)}` : ""}</div></div>
      <span class="tag ${t.verified ? "v" : ""}">${t.verified ? "verified" : "unverified"}</span>
    </article>`).join("");
}

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

let scanning = false, stopRequested = false;
$("#stop").onclick = () => { stopRequested = true; $("#stop").textContent = "stopping after the current file…"; };
// Closing or leaving the tab kills the worker mid-scan. Finished tracks are
// already on the server (and skipped next time), but ask before losing the rest.
window.addEventListener("beforeunload", ev => { if (scanning) { ev.preventDefault(); ev.returnValue = ""; } });
const DONE_KEY = "describesong.done.v1";
const doneKey = f => `${f.name}|${f.size}|${f.lastModified}`;
function loadDone() { try { return new Set(JSON.parse(localStorage.getItem(DONE_KEY) || "[]")); } catch { return new Set(); } }
function saveDone(set) { try { localStorage.setItem(DONE_KEY, JSON.stringify([...set])); } catch {} }
const fmt = s => { s = Math.round(s); const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), x = s % 60; return h ? `${h}:${String(m).padStart(2, "0")}:${String(x).padStart(2, "0")}` : `${m}:${String(x).padStart(2, "0")}`; };
// A 429 from the server means "slow down", not "this file failed": wait and retry,
// and say so in the status line. Any other error carries the server's reason.
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function post(url, body) {
  for (let i = 0; ; i++) {
    const r = await fetch(url, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
    if (r.status === 429 && i < 6) { const wait = 20 * (i + 1); $("#status").textContent += `\nserver asked us to slow down — retrying in ${wait} s`; await sleep(wait * 1000); continue; }
    let j = null; try { j = await r.json(); } catch {}
    if (!r.ok) throw new Error((j && j.detail) || `HTTP ${r.status}`);
    return j;
  }
}

async function scan(all) {
  if (scanning) return;
  const audio = all.filter(f => /\.(mp3|flac|wav|m4a|ogg|opus)$/i.test(f.name));
  $("#prog").hidden = false;
  const log = m => { $("#log").textContent = (m + "\n" + $("#log").textContent).slice(0, 6000); };
  if (!audio.length) { $("#status").textContent = `No audio files in that folder (${all.length} files looked at). MP3, FLAC, WAV, M4A, OGG or Opus.`; return; }
  // RESUME, two layers: this browser remembers files it finished (name+size+
  // mtime); and the server is asked, by fingerprint, before every embed — so a
  // scan resumed in another browser, or of a renamed file, skips too.
  const doneSet = loadDone();
  const files = audio.filter(f => !doneSet.has(doneKey(f)));
  const skipped = audio.length - files.length;
  if (skipped) log(`↷ ${skipped} file${skipped === 1 ? "" : "s"} finished earlier — skipped`);
  if (!files.length) { $("#status").textContent = `Nothing new — all ${audio.length} audio files here were added earlier.`; return; }
  $("#bar").max = files.length; $("#bar").value = 0;
  let done = 0, sent = 0, ident = 0, failed = 0, known = 0, current = "";
  scanning = true; stopRequested = false; $("#stop").hidden = false; $("#stop").textContent = "Stop";
  document.documentElement.dataset.scanning = "1";   // water.js pauses the simulation: the GPU belongs to CLAP now
  const t0 = performance.now();
  $("#status").textContent = "loading model… (the first time downloads 143 MB)";
  let initr; try { initr = await ask({ type: "init" }); } catch (err) { $("#status").textContent = "model failed to load: " + err.message; scanning = false; $("#stop").hidden = true; delete document.documentElement.dataset.scanning; return; }
  const backend = initr.device === "webgpu" ? "GPU" : "CPU — no WebGPU in this browser, slower";
  const progress = () => {
    const el = (performance.now() - t0) / 1000, left = done ? el / done * (files.length - done) : 0;
    $("#status").textContent = `${done} of ${files.length} · ${sent} added (${ident} identified, ${sent - ident} unverified)${known ? ` · ${known} already in` : ""}${failed ? ` · ${failed} failed` : ""} · ${backend} · ${fmt(el)} elapsed${done ? ` · about ${fmt(left)} left` : ""}${current ? `\n${current}` : ""}`;
  };
  const finishOne = f => { doneSet.add(doneKey(f)); saveDone(doneSet); $("#bar").value = ++done; progress(); const pct = Math.round(100 * done / files.length); $("#rScan").style.setProperty("--p", pct); $("#nScan").textContent = pct + "%"; };
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
  const finish = async (f, a, r) => {
    const { fpr, idr } = a;
    try {
      // AcoustID can know the recording but hand back an empty title/artist;
      // keep its id, but never store a blank label when the file has tags.
      const tags = (await readTags(f)) || guessFromName(f.name);
      let label = idr.mbid && (idr.title || idr.artist) ? { artist: idr.artist || tags.artist, title: idr.title || tags.title, album: idr.album || tags.album } : tags;
      if (!idr.mbid && idr.prior && (idr.prior.artist || idr.prior.title)) {
        if (normL(idr.prior) === normL(label)) {
          if (!r) { log(`= ${label.artist || "?"} — ${label.title || f.name} (already in, same label)`); return; }   // nothing new to say
        } else {
          const ok = await confirmSerial(idr.prior, label);
          if (ok) label = { artist: idr.prior.artist, title: idr.prior.title, album: idr.prior.album };
        }
      }
      const sub = await post("/api/submit", { model: MODEL_ID, fp_hash: idr.fp_hash, mbid: idr.mbid || null, duration: fpr.duration, ...label, mean: r ? r.mean : null, moments: r ? r.moments : [] });
      if (sub.ok) { if (r) { sent++; if (idr.mbid) ident++; log(`${idr.mbid ? "✓" : "?"} ${label.artist || "?"} — ${label.title || f.name}`); } else log(`= ${label.artist || "?"} — ${label.title || f.name} (already in — label confirmed)`); }
      else { failed++; log(`✗ ${f.name}: ${sub.detail || "rejected"}`); }
    } catch (err) { failed++; log(`✗ ${f.name}: ${err.message}`); }
    finally { finishOne(f); }
  };
  let nextA = stageA(files[0]).catch(e => e);
  for (let i = 0; i < files.length; i++) {
    const f = files[i];
    if (stopRequested) break;
    current = f.name; progress();
    const a = await nextA;
    if (i + 1 < files.length) nextA = stageA(files[i + 1]).catch(e => e);
    if (a instanceof Error) { failed++; log(`✗ ${f.name}: ${a.message}`); finishOne(f); continue; }
    if (a.idr.known) {
      // Already in. Verified: nothing to add, skip the embed entirely. Unverified:
      // still skip the embed, but offer our tags as a label vote.
      known++; await ask({ type: "drop", ref: a.fpr.ref }).catch(() => {});
      if (a.idr.mbid) { log(`= ${a.idr.artist || "?"} — ${a.idr.title || f.name} (already in)`); finishOne(f); }
      else { const p = finish(f, a, null); net.add(p); p.finally(() => net.delete(p)); }
      continue;
    }
    let r;
    try { r = await ask({ type: "embed", ref: a.fpr.ref }); }
    catch (err) { failed++; log(`✗ ${f.name}: ${err.message}`); finishOne(f); continue; }
    const p = finish(f, a, r); net.add(p); p.finally(() => net.delete(p));
    if (net.size >= 4) await Promise.race(net);
  }
  await Promise.all(net);
  scanning = false; $("#stop").hidden = true; current = "";
  delete document.documentElement.dataset.scanning;
  $("#status").textContent = `${stopRequested ? "stopped" : "done"} — ${sent} added (${ident} identified by fingerprint, ${sent - ident} unverified)${known ? `, ${known} already in` : ""}${failed ? `, ${failed} failed` : ""}${skipped ? `, ${skipped} skipped` : ""} in ${fmt((performance.now() - t0) / 1000)}`;
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
  const want = ver === 2 ? { TP1: "artist", TT2: "title", TAL: "album" } : { TPE1: "artist", TIT2: "title", TALB: "album" };
  const out = {}; const idLen = ver === 2 ? 3 : 4, hdr = ver === 2 ? 6 : 10;
  while (o + hdr <= b.length) {
    const id = String.fromCharCode(...b.subarray(o, o + idLen)); if (!/^[A-Z0-9]+$/.test(id)) break;
    const len = ver === 2 ? (b[o + 3] << 16) | (b[o + 4] << 8) | b[o + 5] : ver === 4 ? syncsafe(b, o + 4) : u32be(b, o + 4);
    if (want[id]) out[want[id]] = id3text(b.subarray(o + hdr, o + hdr + len));
    o += hdr + len;
  }
  return out.title || out.artist ? { artist: out.artist || null, title: out.title || null, album: out.album || null } : null;
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
        if (k === "ARTIST" && !out.artist) out.artist = v; else if (k === "TITLE") out.title = v; else if (k === "ALBUM") out.album = v;
      }
      return out.title || out.artist ? { artist: out.artist || null, title: out.title || null, album: out.album || null } : null;
    }
    if (last) return null; o += 4 + len;
  }
}
