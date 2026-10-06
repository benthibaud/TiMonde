//! Module DAB+ (Digital Audio Broadcasting) pour TiMonde
//! Gère la réception hertzienne numérique DAB/DAB+ via radio logicielle (SDR / welle-cli)
//! et la cohabitation fluide avec les webradios traditionnelles.

use std::path::PathBuf;
use std::process::Command;

/// Informations extraites d'une URL de type dab://canal/nom_service
#[derive(Debug, Clone, PartialEq)]
pub struct DabStationInfo {
    pub channel: String,
    pub service_name: String,
    pub frequency_mhz: f64,
}

/// Fréquences officielles DAB+ Bande III (VHF 174-240 MHz) en Europe et en France
pub fn channel_to_frequency(channel: &str) -> Option<f64> {
    match channel.to_ascii_uppercase().as_str() {
        "5A" => Some(174.928),
        "5B" => Some(176.640),
        "5C" => Some(178.352),
        "5D" => Some(180.064),
        "6A" => Some(181.936),
        "6B" => Some(183.648),
        "6C" => Some(185.360),
        "6D" => Some(187.072),
        "7A" => Some(188.928), // Métropolitain M1 (France)
        "7B" => Some(190.640), // Métropolitain M2 (France)
        "7C" => Some(192.352),
        "7D" => Some(194.064),
        "8A" => Some(195.936),
        "8B" => Some(197.648), // Local / Régional
        "8C" => Some(199.360),
        "8D" => Some(201.072),
        "9A" => Some(202.928),
        "9B" => Some(204.640),
        "9C" => Some(206.352),
        "9D" => Some(208.064),
        "10A" => Some(209.936),
        "10B" => Some(211.648),
        "10C" => Some(213.360),
        "10D" => Some(215.072),
        "11A" => Some(216.928),
        "11B" => Some(218.640),
        "11C" => Some(220.352),
        "11D" => Some(222.064),
        "12A" => Some(223.936),
        "12B" => Some(225.648),
        "12C" => Some(227.360),
        "12D" => Some(229.072),
        _ => None,
    }
}

/// Vérifie si l'URL est un flux DAB hertzien
pub fn is_dab_url(url: &str) -> bool {
    url.starts_with("dab://")
}

/// Parse une URL dab://<channel>/<service>
pub fn parse_dab_url(url: &str) -> Option<DabStationInfo> {
    if !is_dab_url(url) {
        return None;
    }
    let trimmed = &url[6..];
    let parts: Vec<&str> = trimmed.splitn(2, '/').collect();
    if parts.len() < 2 {
        return None;
    }
    let channel = parts[0].trim().to_ascii_uppercase();
    let service_name = parts[1].trim().to_string();
    if channel.is_empty() || service_name.is_empty() {
        return None;
    }
    let frequency_mhz = channel_to_frequency(&channel).unwrap_or(0.0);
    Some(DabStationInfo {
        channel,
        service_name,
        frequency_mhz,
    })
}

/// Formate une URL DAB
pub fn format_dab_url(channel: &str, service: &str) -> String {
    format!("dab://{}/{}", channel.trim().to_ascii_uppercase(), service.trim())
}

/// Détecte si une clé USB SDR (RTL-SDR, Airspy, HackRF) est connectée
pub fn is_sdr_hardware_connected() -> bool {
    if let Ok(out) = Command::new("lsusb").output() {
        let text = String::from_utf8_lossy(&out.stdout).to_lowercase();
        // Identifiants matériels classiques RTL2832U (0bda:2838, 0bda:2832), Airspy, HackRF
        text.contains("rtl2832")
            || text.contains("0bda:2838")
            || text.contains("0bda:2832")
            || text.contains("airspy")
            || text.contains("hackrf")
    } else {
        false
    }
}

/// Vérifie si le décodeur welle-cli ou un outil DAB est disponible
pub fn find_dab_decoder() -> Option<PathBuf> {
    let candidates = ["welle-cli", "dablin", "rtl_fm"];
    for cand in &candidates {
        if let Ok(out) = Command::new("which").arg(cand).output() {
            if out.status.success() {
                let path = String::from_utf8_lossy(&out.stdout).trim().to_string();
                if !path.is_empty() {
                    return Some(PathBuf::from(path));
                }
            }
        }
    }
    None
}

/// Génère les bouquets officiels DAB+ métropolitains et locaux pour tests et usage quotidien
pub fn get_default_dab_groups() -> Vec<crate::models::Group> {
    let mut groups = Vec::new();

    // 1. Multiplex Métropolitain M1 (Canal 7A - 188.928 MHz)
    let mut m1 = crate::models::Group::new("📻 DAB+ Métropolitain M1 (7A)");
    let stations_m1 = [
        ("AirZen Radio", "dab://7A/AirZen"),
        ("Chérie FM", "dab://7A/Cherie FM"),
        ("Fun Radio", "dab://7A/Fun Radio"),
        ("Latina", "dab://7A/Latina"),
        ("M Radio", "dab://7A/M Radio"),
        ("Nostalgie", "dab://7A/Nostalgie"),
        ("NRJ", "dab://7A/NRJ"),
        ("Radio Classique", "dab://7A/Radio Classique"),
        ("Rire et Chansons", "dab://7A/Rire et Chansons"),
        ("RTL", "dab://7A/RTL"),
        ("RTL2", "dab://7A/RTL2"),
        ("Skyrock", "dab://7A/Skyrock"),
        ("Skyrock Klassiks", "dab://7A/Skyrock Klassiks"),
    ];
    for (name, url) in &stations_m1 {
        m1.stations.push(crate::models::Station {
            name: name.to_string(),
            url: url.to_string(),
        });
    }
    groups.push(m1);

    // 2. Multiplex Métropolitain M2 (Canal 7B - 190.640 MHz)
    let mut m2 = crate::models::Group::new("📻 DAB+ Métropolitain M2 (7B)");
    let stations_m2 = [
        ("BFM Business", "dab://7B/BFM Business"),
        ("BFM Radio", "dab://7B/BFM Radio"),
        ("Europe 1", "dab://7B/Europe 1"),
        ("Europe 2", "dab://7B/Europe 2"),
        ("FIP", "dab://7B/FIP"),
        ("France Culture", "dab://7B/France Culture"),
        ("France Info", "dab://7B/France Info"),
        ("France Inter", "dab://7B/France Inter"),
        ("France Musique", "dab://7B/France Musique"),
        ("KTO Radio", "dab://7B/KTO"),
        ("Mon Paris FM", "dab://7B/Mon Paris FM"),
        ("RFI", "dab://7B/RFI"),
        ("RMC", "dab://7B/RMC"),
    ];
    for (name, url) in &stations_m2 {
        m2.stations.push(crate::models::Station {
            name: name.to_string(),
            url: url.to_string(),
        });
    }
    groups.push(m2);

    // 3. Multiplex Local (Canal 8B)
    let mut local = crate::models::Group::new("📻 DAB+ Local & Régional (8B)");
    let stations_local = [
        ("Radio FG", "dab://8B/Radio FG"),
        ("Generations", "dab://8B/Generations"),
        ("Jazz Radio", "dab://8B/Jazz Radio"),
        ("Radio Nova", "dab://8B/Radio Nova"),
        ("OUI FM", "dab://8B/OUI FM"),
        ("TSF Jazz", "dab://8B/TSF Jazz"),
    ];
    for (name, url) in &stations_local {
        local.stations.push(crate::models::Station {
            name: name.to_string(),
            url: url.to_string(),
        });
    }
    groups.push(local);

    groups
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_dab_url() {
        let url = "dab://8B/FIP";
        assert!(is_dab_url(url));
        let info = parse_dab_url(url).expect("Parsing réussi");
        assert_eq!(info.channel, "8B");
        assert_eq!(info.service_name, "FIP");
        assert_eq!(info.frequency_mhz, 197.648);
    }

    #[test]
    fn test_invalid_dab_url() {
        assert!(!is_dab_url("http://stream.example/live"));
        assert!(parse_dab_url("dab://").is_none());
        assert!(parse_dab_url("dab://7A").is_none());
    }

    #[test]
    fn test_format_dab_url() {
        let formatted = format_dab_url("7a", "France Inter");
        assert_eq!(formatted, "dab://7A/France Inter");
    }

    #[test]
    fn test_default_dab_groups() {
        let groups = get_default_dab_groups();
        assert_eq!(groups.len(), 3);
        assert_eq!(groups[0].name, "📻 DAB+ Métropolitain M1 (7A)");
        assert!(groups[0].stations.len() >= 10);
        assert!(is_dab_url(&groups[0].stations[0].url));
    }
}
