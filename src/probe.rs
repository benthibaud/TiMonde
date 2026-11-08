//! Sondage natif ultra-frugal de flux audio en Rust (sans dépendance lourde, sans bloquer le GIL Python).

use serde::{Deserialize, Serialize};
use std::time::Duration;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProbeMetadata {
    pub icy_name: String,
    pub icy_genre: String,
    pub icy_br: String,
    pub content_type: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProbeResult {
    pub ok: bool,
    pub is_geo: bool,
    pub status_code: u16,
    pub message: String,
    pub redirected_url: Option<String>,
    pub codec: String,
    pub meta: ProbeMetadata,
}

impl ProbeResult {
    pub fn error(msg: &str) -> Self {
        Self {
            ok: false,
            is_geo: false,
            status_code: 0,
            message: msg.to_string(),
            redirected_url: None,
            codec: String::new(),
            meta: ProbeMetadata {
                icy_name: String::new(),
                icy_genre: String::new(),
                icy_br: String::new(),
                content_type: String::new(),
            },
        }
    }
}

/// Sonde la disponibilité, le statut et les métadonnées d'un flux audio distant.
pub fn probe_stream_url(url: &str, timeout_secs: u64) -> ProbeResult {
    let clean = url.trim();
    if clean.is_empty() {
        return ProbeResult::error("URL vide");
    }

    let user_agent = concat!("TiMonde/", env!("CARGO_PKG_VERSION"), " (Linux; Audio Stream Prober)");
    let timeout = Duration::from_secs(timeout_secs.max(1));

    let response = ureq::get(clean)
        .set("User-Agent", user_agent)
        .set("Accept", "*/*")
        .set("Icy-MetaData", "1")
        .timeout(timeout)
        .call();

    match response {
        Ok(resp) => {
            let status_code = resp.status();
            let final_url = resp.get_url().to_string();
            let redirected_url = if final_url != clean {
                Some(final_url)
            } else {
                None
            };

            let ct = resp.header("Content-Type").unwrap_or_default().to_string();
            let raw_name = resp.header("icy-name")
                .or_else(|| resp.header("x-audiocast-name"))
                .unwrap_or_default()
                .trim()
                .to_string();
            let raw_genre = resp.header("icy-genre")
                .unwrap_or_default()
                .trim()
                .to_string();
            let raw_br = resp.header("icy-br")
                .unwrap_or_default()
                .trim()
                .to_string();

            let ct_low = ct.to_lowercase();
            // Rejet catégorique des pages web HTML retournant un faux code 200 (ex: radios éteintes)
            if ct_low.contains("text/html") || ct_low.contains("text/plain") {
                let clean_low = clean.to_lowercase();
                let is_playlist = clean_low.ends_with(".m3u")
                    || clean_low.ends_with(".m3u8")
                    || clean_low.ends_with(".pls")
                    || clean_low.ends_with(".asx");

                if !is_playlist {
                    return ProbeResult {
                        ok: false,
                        is_geo: false,
                        status_code,
                        message: "Hors ligne (page d'erreur HTML)".to_string(),
                        redirected_url,
                        codec: String::new(),
                        meta: ProbeMetadata {
                            icy_name: raw_name,
                            icy_genre: raw_genre,
                            icy_br: raw_br,
                            content_type: ct,
                        },
                    };
                }
            }

            let codec = if ct_low.contains("aac") {
                "AAC"
            } else if ct_low.contains("mpeg") || ct_low.contains("mp3") {
                "MP3"
            } else if ct_low.contains("ogg") {
                "OGG"
            } else if ct_low.contains("flac") {
                "FLAC"
            } else if ct_low.contains("vnd.apple.mpegurl") || ct_low.contains("m3u8") {
                "HLS"
            } else {
                "Audio"
            };

            ProbeResult {
                ok: true,
                is_geo: false,
                status_code,
                message: format!("En direct ({})", codec),
                redirected_url,
                codec: codec.to_string(),
                meta: ProbeMetadata {
                    icy_name: raw_name,
                    icy_genre: raw_genre,
                    icy_br: raw_br,
                    content_type: ct,
                },
            }
        }
        Err(ureq::Error::Status(code, resp)) => {
            let is_geo = code == 403 || code == 451 || (code == 503 && {
                let c_low = clean.to_lowercase();
                c_low.contains("amperwave")
                    || c_low.contains("audacy")
                    || c_low.contains("streamtheworld")
                    || c_low.contains("akamai")
                    || c_low.contains("geoblock")
                    || c_low.contains("leanstream")
            });

            let message = if is_geo {
                "Géobloqué (VPN)".to_string()
            } else {
                format!("Erreur HTTP {}", code)
            };

            let ct = resp.header("Content-Type").unwrap_or_default().to_string();

            ProbeResult {
                ok: false,
                is_geo,
                status_code: code,
                message,
                redirected_url: None,
                codec: String::new(),
                meta: ProbeMetadata {
                    icy_name: String::new(),
                    icy_genre: String::new(),
                    icy_br: String::new(),
                    content_type: ct,
                },
            }
        }
        Err(ureq::Error::Transport(t)) => {
            let desc = t.to_string();
            // Prise en charge des vieux serveurs SHOUTcast v1 (qui renvoient ICY 200 OK non standard)
            if desc.contains("ICY 200") || desc.contains("200 OK") {
                return ProbeResult {
                    ok: true,
                    is_geo: false,
                    status_code: 200,
                    message: "En direct (Shoutcast)".to_string(),
                    redirected_url: None,
                    codec: "MP3".to_string(),
                    meta: ProbeMetadata {
                        icy_name: String::new(),
                        icy_genre: String::new(),
                        icy_br: String::new(),
                        content_type: "audio/mpeg".to_string(),
                    },
                };
            }

            let message = if desc.to_lowercase().contains("timeout") || desc.to_lowercase().contains("timed out") {
                "Délai d'attente dépassé".to_string()
            } else {
                "Serveur inaccessible".to_string()
            };

            ProbeResult {
                ok: false,
                is_geo: false,
                status_code: 0,
                message,
                redirected_url: None,
                codec: String::new(),
                meta: ProbeMetadata {
                    icy_name: String::new(),
                    icy_genre: String::new(),
                    icy_br: String::new(),
                    content_type: String::new(),
                },
            }
        }
    }
}

/// Sérialise le résultat de sondage en JSON lisible
pub fn probe_stream_json(url: &str, timeout_secs: u64) -> String {
    let result = probe_stream_url(url, timeout_secs);
    serde_json::to_string(&result).unwrap_or_else(|_| r#"{"ok":false,"message":"Erreur sérialisation"}"#.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_probe_empty_url() {
        let res = probe_stream_url("", 1);
        assert!(!res.ok);
        assert_eq!(res.message, "URL vide");

        let json = probe_stream_json("   ", 1);
        assert!(json.contains("\"ok\":false"));
        assert!(json.contains("URL vide"));
    }

    #[test]
    fn test_probe_unreachable_host() {
        let res = probe_stream_url("http://127.0.0.1:59999/nonexistent", 1);
        assert!(!res.ok);
        assert_eq!(res.message, "Serveur inaccessible");
    }
}
