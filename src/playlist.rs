use log::{info, warn};
use std::time::Duration;

/// Décode une playlist M3U et extrait la première URL de flux audio direct
pub fn parse_m3u(content: &str) -> Option<String> {
    for line in content.lines() {
        let trimmed = line.trim();
        if !trimmed.is_empty() && !trimmed.starts_with('#') && (trimmed.starts_with("http://") || trimmed.starts_with("https://")) {
            return Some(trimmed.to_string());
        }
    }
    None
}

/// Décode une playlist PLS (format INI Shoutcast) et extrait l'URL du premier flux (File1=...)
pub fn parse_pls(content: &str) -> Option<String> {
    for line in content.lines() {
        let trimmed = line.trim();
        if trimmed.to_ascii_lowercase().starts_with("file") {
            if let Some(pos) = trimmed.find('=') {
                let url = trimmed[pos + 1..].trim();
                if url.starts_with("http://") || url.starts_with("https://") {
                    return Some(url.to_string());
                }
            }
        }
    }
    None
}

/// Décode une playlist ASX (format XML Windows Media) et extrait l'attribut href
pub fn parse_asx(content: &str) -> Option<String> {
    let lower = content.to_ascii_lowercase();
    if let Some(ref_pos) = lower.find("href") {
        let after_href = &content[ref_pos + 4..];
        if let Some(quote_start) = after_href.find(['"', '\'']) {
            let quote_char = after_href.chars().nth(quote_start).unwrap();
            let remainder = &after_href[quote_start + 1..];
            if let Some(quote_end) = remainder.find(quote_char) {
                let url = remainder[..quote_end].trim();
                if url.starts_with("http://") || url.starts_with("https://") {
                    return Some(url.to_string());
                }
            }
        }
    }
    None
}

/// Détecte si l'URL pointe vers un fichier de playlist et résout le flux audio direct sous-jacent
pub fn resolve_stream_url(url: &str) -> String {
    let url_clean = url.trim();
    let lower = url_clean.to_ascii_lowercase();

    // Vérifie si l'URL se termine par une extension de playlist connue
    let is_m3u = lower.ends_with(".m3u") || lower.contains(".m3u?");
    let is_pls = lower.ends_with(".pls") || lower.contains(".pls?");
    let is_asx = lower.ends_with(".asx") || lower.contains(".asx?");

    if !is_m3u && !is_pls && !is_asx {
        return url_clean.to_string();
    }

    info!("Résolution de la playlist réseau : {}", url_clean);

    let resp = match ureq::get(url_clean)
        .set("User-Agent", "TiMonde/0.1.0")
        .timeout(Duration::from_secs(3))
        .call()
    {
        Ok(r) => r,
        Err(e) => {
            warn!("Impossible de télécharger la playlist ({}) : {}", url_clean, e);
            return url_clean.to_string();
        }
    };

    let mut body = String::new();
    if let Ok(reader) = resp.into_reader().take(16 * 1024).read_to_string(&mut body) {
        if reader > 0 {
            if is_m3u {
                if let Some(direct_url) = parse_m3u(&body) {
                    info!("Playlist M3U résolue vers le flux direct : {}", direct_url);
                    return direct_url;
                }
            } else if is_pls {
                if let Some(direct_url) = parse_pls(&body) {
                    info!("Playlist PLS résolue vers le flux direct : {}", direct_url);
                    return direct_url;
                }
            } else if is_asx {
                if let Some(direct_url) = parse_asx(&body) {
                    info!("Playlist ASX résolue vers le flux direct : {}", direct_url);
                    return direct_url;
                }
            }
        }
    }

    url_clean.to_string()
}

use std::io::Read;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_m3u() {
        let sample = "#EXTM3U\n#EXTINF: TOP MUSIC\nhttp://sc.creacast.com/topmusic_strasbourg\n";
        assert_eq!(
            parse_m3u(sample),
            Some("http://sc.creacast.com/topmusic_strasbourg".to_string())
        );
    }

    #[test]
    fn test_parse_pls() {
        let sample = "[playlist]\nNumberOfEntries=1\nFile1=http://stream01.warm.fm:9002/live\nTitle1=Warm\n";
        assert_eq!(
            parse_pls(sample),
            Some("http://stream01.warm.fm:9002/live".to_string())
        );
    }

    #[test]
    fn test_parse_asx() {
        let sample = "<asx version=\"3.0\"><entry><ref href=\"http://stream.example.com/live.asf\"/></entry></asx>";
        assert_eq!(
            parse_asx(sample),
            Some("http://stream.example.com/live.asf".to_string())
        );
    }
}
