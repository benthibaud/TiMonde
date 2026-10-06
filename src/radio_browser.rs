use log::{info, warn};
use serde::Deserialize;
use std::process::Command;
use std::time::Duration;

#[derive(Debug, Deserialize)]
pub struct StationResult {
    pub name: String,
    pub url_resolved: String,
    #[serde(default)]
    pub lastcheckok: u32,
    #[serde(default)]
    pub bitrate: u32,
}

/// Envoie une notification discrète sur le bureau via notify-send
pub fn notify(title: &str, body: &str) {
    let _ = Command::new("notify-send")
        .arg("-a")
        .arg("TiMonde")
        .arg("-i")
        .arg("radiotray")
        .arg(title)
        .arg(body)
        .spawn();
}

/// Nettoie un nom de station pour optimiser la recherche dans Radio-Browser
fn extract_search_terms(name: &str) -> Vec<String> {
    // Si le nom contient un tiret (ex: "Kickin' Country - 181 fm"), tester d'abord la partie gauche
    let parts: Vec<&str> = name.split('-').collect();
    let mut queries = Vec::new();

    if parts.len() > 1 {
        let first_part = parts[0].trim().replace(['\'', '’', ':'], " ");
        let cleaned: Vec<&str> = first_part.split_whitespace().collect();
        if !cleaned.is_empty() {
            queries.push(cleaned.join(" "));
        }
    }

    let whole = name.replace(['-', '\'', '’', ':'], " ");
    let words: Vec<&str> = whole
        .split_whitespace()
        .filter(|w| !w.is_empty() && w.len() > 1)
        .take(2)
        .collect();
    if !words.is_empty() {
        queries.push(words.join(" "));
    }

    queries
}

/// Recherche un flux de secours actif sur l'annuaire communautaire Radio-Browser
pub fn find_backup_stream(station_name: &str) -> Option<(String, String)> {
    let queries = extract_search_terms(station_name);
    if queries.is_empty() {
        return None;
    }

    let endpoints = [
        "https://de1.api.radio-browser.info",
        "https://nl1.api.radio-browser.info",
        "https://at1.api.radio-browser.info",
    ];

    for query in &queries {
        info!("Recherche Radio-Browser avec la requête : {:?}", query);
        for endpoint in endpoints {
            let url = format!("{}/json/stations/byname/{}", endpoint, urlencoding(query));
            match ureq::get(&url)
                .set("User-Agent", "TiMonde/0.1.0")
                .timeout(Duration::from_secs(3))
                .call()
            {
                Ok(response) => {
                    if let Ok(stations) = response.into_json::<Vec<StationResult>>() {
                        let valid_station = stations
                            .into_iter()
                            .filter(|s| s.lastcheckok == 1 && !s.url_resolved.is_empty())
                            .max_by_key(|s| s.bitrate);

                        if let Some(s) = valid_station {
                            info!("Flux de secours trouvé : {} -> {}", s.name, s.url_resolved);
                            return Some((s.name, s.url_resolved));
                        }
                    }
                }
                Err(e) => {
                    warn!("Échec interrogation Radio-Browser sur {} : {}", endpoint, e);
                }
            }
        }
    }

    None
}

/// Encodage URL minimal
fn urlencoding(s: &str) -> String {
    let mut encoded = String::new();
    for b in s.bytes() {
        match b {
            b'a'..=b'z' | b'A'..=b'Z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => {
                encoded.push(b as char);
            }
            b' ' => encoded.push_str("%20"),
            _ => encoded.push_str(&format!("%{:02X}", b)),
        }
    }
    encoded
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_find_kickin_country_backup() {
        let res = find_backup_stream("Kickin' Country - 181 fm");
        assert!(res.is_some(), "Radio-Browser doit trouver un flux de secours pour Kickin' Country");
        let (name, url) = res.unwrap();
        println!("Test trouvé avec succès : {} -> {}", name, url);
        assert!(!url.is_empty());
    }
}
