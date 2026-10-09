use crate::models::Station;
use quick_xml::events::Event;
use quick_xml::Reader;
use std::fs::File;
use std::io::{BufReader, Read};
use std::path::{Path, PathBuf};
use std::sync::OnceLock;

/// Cache en mémoire pour éviter de relire le disque à chaque tirage aléatoire
static CACHED_BOUQUET_STATIONS: OnceLock<Vec<Station>> = OnceLock::new();

/// Recherche l'emplacement du répertoire des bouquets DAB+/mondiaux
pub fn find_bouquets_dir() -> Option<PathBuf> {
    let home = std::env::var("HOME").unwrap_or_else(|_| ".".to_string());
    let candidate1 = PathBuf::from(&home).join(".local/share/timonde/bouquets");
    if candidate1.is_dir() {
        return Some(candidate1);
    }

    let candidate2 = PathBuf::from("data/bouquets");
    if candidate2.is_dir() {
        return Some(candidate2);
    }

    let candidate3 = PathBuf::from("/usr/share/timonde/bouquets");
    if candidate3.is_dir() {
        return Some(candidate3);
    }

    None
}

/// Recherche l'emplacement du répertoire des fichiers exemples thématiques & musicaux
pub fn find_examples_dir() -> Option<PathBuf> {
    let home = std::env::var("HOME").unwrap_or_else(|_| ".".to_string());
    let candidate1 = PathBuf::from(&home).join(".local/share/timonde/examples");
    if candidate1.is_dir() {
        return Some(candidate1);
    }

    let candidate2 = PathBuf::from("data/examples");
    if candidate2.is_dir() {
        return Some(candidate2);
    }

    let candidate3 = PathBuf::from("/usr/share/timonde/examples");
    if candidate3.is_dir() {
        return Some(candidate3);
    }

    None
}

/// Analyse un contenu XML de bouquet et extrait les stations associées à leur pays
pub fn parse_bouquet_xml_str(content: &str) -> Vec<Station> {
    let mut reader = Reader::from_str(content);
    reader.config_mut().trim_text(true);

    let mut stations = Vec::new();
    let mut country_code = None;
    let mut buf = Vec::new();

    loop {
        match reader.read_event_into(&mut buf) {
            Ok(Event::Start(ref e)) | Ok(Event::Empty(ref e)) => {
                let tag_name = e.name();
                if tag_name.as_ref() == b"bouquet" {
                    for attr in e.attributes().flatten() {
                        if attr.key.as_ref() == b"country" {
                            if let Ok(val) = std::str::from_utf8(&attr.value) {
                                country_code = Some(val.trim().to_uppercase());
                            }
                        }
                    }
                } else if tag_name.as_ref() == b"station" {
                    let mut name = String::new();
                    let mut url = String::new();
                    let mut is_offline = false;

                    for attr in e.attributes().flatten() {
                        match attr.key.as_ref() {
                            b"name" => {
                                if let Ok(val) = std::str::from_utf8(&attr.value) {
                                    name = val.trim().to_string();
                                }
                            }
                            b"url" => {
                                if let Ok(val) = std::str::from_utf8(&attr.value) {
                                    url = val.trim().to_string();
                                }
                            }
                            b"status" => {
                                if let Ok(val) = std::str::from_utf8(&attr.value) {
                                    if val.trim().eq_ignore_ascii_case("offline") {
                                        is_offline = true;
                                    }
                                }
                            }
                            _ => {}
                        }
                    }

                    if !is_offline && !name.is_empty() && !url.is_empty() {
                        let st = match &country_code {
                            Some(c) if !c.is_empty() => Station::with_country(name, url, c),
                            _ => Station::new(name, url),
                        };
                        stations.push(st);
                    }
                }
            }
            Ok(Event::Eof) => break,
            Err(e) => {
                log::warn!("Erreur lors de l'analyse d'un fragment de bouquet XML : {}", e);
                break;
            }
            _ => {}
        }
        buf.clear();
    }

    stations
}

/// Analyse un fichier bouquet individuel sur le disque
pub fn parse_bouquet_file(path: &Path) -> Vec<Station> {
    let file = match File::open(path) {
        Ok(f) => f,
        Err(e) => {
            log::warn!("Impossible d'ouvrir le fichier bouquet {:?} : {}", path, e);
            return Vec::new();
        }
    };

    let mut reader = Reader::from_reader(BufReader::new(file));
    reader.config_mut().trim_text(true);

    let mut stations = Vec::new();
    let mut country_code = None;
    let mut buf = Vec::new();

    loop {
        match reader.read_event_into(&mut buf) {
            Ok(Event::Start(ref e)) | Ok(Event::Empty(ref e)) => {
                let tag_name = e.name();
                if tag_name.as_ref() == b"bouquet" {
                    for attr in e.attributes().flatten() {
                        if attr.key.as_ref() == b"country" {
                            if let Ok(val) = std::str::from_utf8(&attr.value) {
                                country_code = Some(val.trim().to_uppercase());
                            }
                        }
                    }
                } else if tag_name.as_ref() == b"station" {
                    let mut name = String::new();
                    let mut url = String::new();

                    for attr in e.attributes().flatten() {
                        match attr.key.as_ref() {
                            b"name" => {
                                if let Ok(val) = std::str::from_utf8(&attr.value) {
                                    name = val.trim().to_string();
                                }
                            }
                            b"url" => {
                                if let Ok(val) = std::str::from_utf8(&attr.value) {
                                    url = val.trim().to_string();
                                }
                            }
                            _ => {}
                        }
                    }

                    if !name.is_empty() && !url.is_empty() {
                        let st = match &country_code {
                            Some(c) if !c.is_empty() => Station::with_country(name, url, c),
                            _ => Station::new(name, url),
                        };
                        stations.push(st);
                    }
                }
            }
            Ok(Event::Eof) => break,
            Err(e) => {
                log::warn!("Erreur parsing bouquet {:?} : {}", path, e);
                break;
            }
            _ => {}
        }
        buf.clear();
    }

    stations
}

/// Charge l'intégralité du catalogue des bouquets locaux en mémoire
pub fn load_all_bouquet_stations() -> &'static [Station] {
    CACHED_BOUQUET_STATIONS.get_or_init(|| {
        let mut list = Vec::new();
        // 1. Bouquets DAB+ par pays
        if let Some(b_dir) = find_bouquets_dir() {
            if let Ok(entries) = std::fs::read_dir(&b_dir) {
                let mut paths: Vec<PathBuf> = entries
                    .flatten()
                    .map(|e| e.path())
                    .filter(|p| p.extension().map_or(false, |ext| ext == "xml"))
                    .collect();
                paths.sort();

                for p in paths {
                    let mut st_list = parse_bouquet_file(&p);
                    list.append(&mut st_list);
                }
            }
        }

        // 2. Collections thématiques et musicales d'exemples (x-*.xml, stations vérifiées actives)
        if let Some(ex_dir) = find_examples_dir() {
            if let Ok(entries) = std::fs::read_dir(&ex_dir) {
                let mut paths: Vec<PathBuf> = entries
                    .flatten()
                    .map(|e| e.path())
                    .filter(|p| p.extension().map_or(false, |ext| ext == "xml"))
                    .collect();
                paths.sort();

                for p in paths {
                    let mut st_list = parse_bouquet_file(&p);
                    list.append(&mut st_list);
                }
            }
        }

        log::info!("Catalogue mondial & musical chargé pour la découverte : {} stations", list.len());
        list
    })
}

/// Génère un indice aléatoire uniforme entre 0 et max - 1 (low-tech, zéro dépendance externe)
pub fn random_index(max: usize) -> usize {
    if max <= 1 {
        return 0;
    }

    let mut bytes = [0u8; 8];
    if let Ok(mut f) = File::open("/dev/urandom") {
        if f.read_exact(&mut bytes).is_ok() {
            let val = u64::from_ne_bytes(bytes);
            return (val as usize) % max;
        }
    }

    // Fallback avec l'horloge système
    let nanos = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.subsec_nanos())
        .unwrap_or(42);
    (nanos as usize) % max
}

/// Choisit une station au hasard parmi le catalogue en évitant les stations déjà sauvegardées
pub fn pick_random_station(exclude_urls: &[String]) -> Option<Station> {
    let catalog = load_all_bouquet_stations();
    if catalog.is_empty() {
        return None;
    }

    pick_random_station_from_slice(catalog, exclude_urls)
}

/// Sélectionne une station au hasard depuis une tranche de stations avec exclusion d'URLs
pub fn pick_random_station_from_slice(catalog: &[Station], exclude_urls: &[String]) -> Option<Station> {
    if catalog.is_empty() {
        return None;
    }

    // Filtrer les stations qui ne sont pas déjà dans les favoris
    let candidates: Vec<&Station> = catalog
        .iter()
        .filter(|s| !exclude_urls.iter().any(|ex| crate::import::normalize_url(&s.url) == crate::import::normalize_url(ex)))
        .collect();

    // Si toutes les radios du monde sont déjà dans les favoris, on pioche dans tout le catalogue
    let pool: &[&Station] = if !candidates.is_empty() {
        &candidates
    } else {
        &catalog.iter().collect::<Vec<&Station>>()
    };

    let idx = random_index(pool.len());
    pool.get(idx).map(|s| (*s).clone())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_bouquet_xml_snippet() {
        let xml = r#"<?xml version='1.0' encoding='utf-8'?>
<bouquet country="IS" name="Islande" flag="" multilingual="false">
  <national>
    <station name="Rás 1" url="https://ruv-ras1.akamaized.net/hls/live/2026857/ras1/master.m3u8" genre="Généraliste / Culture" />
    <station name="Rás 2" url="https://ruv-ras2.akamaized.net/hls/live/2026858/ras2/master.m3u8" genre="Musique &amp; Société" />
  </national>
</bouquet>"#;

        let stations = parse_bouquet_xml_str(xml);
        assert_eq!(stations.len(), 2);
        assert_eq!(stations[0].name, "Rás 1");
        assert_eq!(stations[0].country, Some("IS".to_string()));
        assert_eq!(stations[1].name, "Rás 2");
        assert_eq!(stations[1].country, Some("IS".to_string()));
    }

    #[test]
    fn test_random_index_bounds() {
        for max in [1, 2, 5, 100, 948] {
            let idx = random_index(max);
            assert!(idx < max);
        }
    }

    #[test]
    fn test_pick_random_station_with_exclusion() {
        let s1 = Station::new("Radio 1", "http://stream1.org");
        let s2 = Station::new("Radio 2", "http://stream2.org");
        let catalog = vec![s1.clone(), s2.clone()];

        // Si on exclut Radio 1, on ne doit obtenir que Radio 2
        let picked = pick_random_station_from_slice(&catalog, &["http://stream1.org".to_string()]);
        assert_eq!(picked.unwrap().name, "Radio 2");

        // Si on exclut tout, fallback sur une station
        let picked_all_excluded = pick_random_station_from_slice(
            &catalog,
            &["http://stream1.org".to_string(), "http://stream2.org".to_string()],
        );
        assert!(picked_all_excluded.is_some());
    }

    #[test]
    fn test_pick_random_station_from_real_bouquets() {
        // Teste avec le répertoire local de bouquets du projet s'il est présent
        let catalog = load_all_bouquet_stations();
        if !catalog.is_empty() {
            let picked = pick_random_station(&[]);
            assert!(picked.is_some());
            let st = picked.unwrap();
            assert!(!st.name.is_empty());
            assert!(!st.url.is_empty());
        }
    }
}
