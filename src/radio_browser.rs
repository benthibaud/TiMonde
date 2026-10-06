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

#[derive(Debug, Deserialize, Clone)]
pub struct SearchResult {
    pub name: String,
    pub url_resolved: String,
    #[serde(default)]
    pub country: String,
    #[serde(default)]
    pub codec: String,
    #[serde(default)]
    pub bitrate: u32,
    #[serde(default)]
    pub votes: u32,
    #[serde(default)]
    pub lastcheckok: u32,
}

/// Envoie une notification discrète sur le bureau via notify-send
pub fn notify(title: &str, body: &str) {
    let _ = Command::new("notify-send")
        .arg("-a")
        .arg("TiMonde")
        .arg("-i")
        .arg("audio-speakers")
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

const ENDPOINTS: [&str; 3] = [
    "https://de1.api.radio-browser.info",
    "https://nl1.api.radio-browser.info",
    "https://at1.api.radio-browser.info",
];

/// Recherche un flux de secours actif sur l'annuaire communautaire Radio-Browser
pub fn find_backup_stream(station_name: &str) -> Option<(String, String)> {
    let queries = extract_search_terms(station_name);
    if queries.is_empty() {
        return None;
    }

    for query in &queries {
        info!("Recherche Radio-Browser avec la requête : {:?}", query);
        for endpoint in ENDPOINTS {
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

/// Recherche en ligne des stations sur Radio-Browser par mot-clé avec tri par popularité
pub fn search_online(query: &str, limit: usize) -> Vec<SearchResult> {
    let clean_query = query.trim();
    if clean_query.is_empty() {
        return Vec::new();
    }

    for endpoint in ENDPOINTS {
        let url = format!(
            "{}/json/stations/byname/{}?limit={}&order=votes&reverse=true",
            endpoint,
            urlencoding(clean_query),
            limit
        );

        match ureq::get(&url)
            .set("User-Agent", "TiMonde/0.1.0")
            .timeout(Duration::from_secs(4))
            .call()
        {
            Ok(response) => {
                if let Ok(stations) = response.into_json::<Vec<SearchResult>>() {
                    let valid_stations: Vec<SearchResult> = stations
                        .into_iter()
                        .filter(|s| !s.url_resolved.is_empty() && s.lastcheckok == 1)
                        .collect();

                    if !valid_stations.is_empty() {
                        return valid_stations;
                    }
                }
            }
            Err(e) => {
                warn!("Échec recherche Radio-Browser sur {} : {}", endpoint, e);
            }
        }
    }

    Vec::new()
}

/// Encodage URL minimal
pub fn urlencoding(s: &str) -> String {
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

    #[test]
    fn test_search_online() {
        let results = search_online("FIP", 5);
        assert!(!results.is_empty(), "La recherche en ligne pour 'FIP' doit renvoyer des résultats");
        assert!(results.iter().any(|r| r.name.to_lowercase().contains("fip")));
    }
}
