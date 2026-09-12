//! Chromaprint in the browser.
//!
//! The one thing a submission has to get right is WHICH track it is, and a
//! user's tags cannot be trusted for that. Chromaprint derives a fingerprint
//! from the waveform itself; AcoustID maps it to a MusicBrainz recording ID.
//! Running it here means the audio never leaves the machine — only a few
//! hundred bytes of fingerprint do.
//!
//! Output is exactly what `fpcalc` emits and AcoustID's lookup accepts: the
//! compressed fingerprint, base64 (URL-safe alphabet, no padding).
use base64::Engine;
use rusty_chromaprint::{Configuration, FingerprintCompressor, Fingerprinter};
use wasm_bindgen::prelude::*;

/// `samples` are interleaved signed 16-bit PCM. Returns the AcoustID
/// fingerprint string. Chromaprint only looks at the first ~2 minutes, so
/// callers may truncate before handing audio over.
#[wasm_bindgen]
pub fn fingerprint(samples: &[i16], sample_rate: u32, channels: u32) -> Result<String, JsValue> {
    // preset_test2 is the algorithm AcoustID's database is built on.
    let cfg = Configuration::preset_test2();
    let mut fp = Fingerprinter::new(&cfg);
    fp.start(sample_rate, channels)
        .map_err(|e| JsValue::from_str(&format!("chromaprint start: {e:?}")))?;
    fp.consume(samples);
    fp.finish();
    let raw = fp.fingerprint();
    if raw.is_empty() {
        return Err(JsValue::from_str("audio too short to fingerprint"));
    }
    let compressed = FingerprintCompressor::from(&cfg).compress(raw);
    Ok(base64::engine::general_purpose::URL_SAFE_NO_PAD.encode(compressed))
}

/// The uncompressed fingerprint, for tests that compare against fpcalc -raw.
#[wasm_bindgen]
pub fn fingerprint_raw(samples: &[i16], sample_rate: u32, channels: u32) -> Result<Vec<u32>, JsValue> {
    let cfg = Configuration::preset_test2();
    let mut fp = Fingerprinter::new(&cfg);
    fp.start(sample_rate, channels)
        .map_err(|e| JsValue::from_str(&format!("chromaprint start: {e:?}")))?;
    fp.consume(samples);
    fp.finish();
    Ok(fp.fingerprint().to_vec())
}
