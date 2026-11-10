use crate::models::Station;
use quick_xml::events::Event;
use quick_xml::Reader;
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::fs::File;
use std::io::{BufReader, Read};
use std::path::{Path, PathBuf};
use std::sync::OnceLock;

/// Cache en mémoire pour éviter de relire le disque à chaque tirage aléatoire
static CACHED_BOUQUET_STATIONS: OnceLock<Vec<Station>> = OnceLock::new();

/// Recherche l'emplacement du répertoire des bouquets DAB+/mondiaux
pub fn find_bouquets_dir() -> Option<PathBuf> {
    if let Ok(exe) = std::env::current_exe() {
        if let Some(exe_dir) = exe.parent() {
            let candidate_dev = exe_dir.join("../../data/bouquets");
            if candidate_dev.is_dir() {
                return Some(candidate_dev);
            }
        }
    }

    let candidate_rel = PathBuf::from("data/bouquets");
    if candidate_rel.is_dir() {
        return Some(candidate_rel);
    }

    let home = std::env::var("HOME").unwrap_or_else(|_| ".".to_string());
    let candidate_user = PathBuf::from(&home).join(".local/share/timonde/bouquets");
    if candidate_user.is_dir() {
        return Some(candidate_user);
    }

    let candidate_sys = PathBuf::from("/usr/share/timonde/bouquets");
    if candidate_sys.is_dir() {
        return Some(candidate_sys);
    }

    None
}

/// Recherche l'emplacement du répertoire des fichiers exemples thématiques & musicaux
pub fn find_examples_dir() -> Option<PathBuf> {
    if let Ok(exe) = std::env::current_exe() {
        if let Some(exe_dir) = exe.parent() {
            let candidate_dev = exe_dir.join("../../data/examples");
            if candidate_dev.is_dir() {
                return Some(candidate_dev);
            }
        }
    }

    let candidate_rel = PathBuf::from("data/examples");
    if candidate_rel.is_dir() {
        return Some(candidate_rel);
    }

    let home = std::env::var("HOME").unwrap_or_else(|_| ".".to_string());
    let candidate_user = PathBuf::from(&home).join(".local/share/timonde/examples");
    if candidate_user.is_dir() {
        return Some(candidate_user);
    }

    let candidate_sys = PathBuf::from("/usr/share/timonde/examples");
    if candidate_sys.is_dir() {
        return Some(candidate_sys);
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
                if tag_name.as_ref() == b"bouquet" || tag_name.as_ref() == b"group" {
                    for attr in e.attributes().flatten() {
                        if attr.key.as_ref() == b"country" {
                            if let Ok(val) = std::str::from_utf8(&attr.value) {
                                country_code = Some(val.trim().to_uppercase());
                            }
                        }
                    }
                } else if tag_name.as_ref() == b"station" || tag_name.as_ref() == b"bookmark" {
                    let mut name = String::new();
                    let mut url = String::new();
                    let mut st_country: Option<String> = None;
                    let mut st_timezone: Option<String> = None;
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
                            b"country" | b"countrycode" => {
                                if let Ok(val) = std::str::from_utf8(&attr.value) {
                                    let c = val.trim().to_uppercase();
                                    if !c.is_empty() {
                                        st_country = Some(c);
                                    }
                                }
                            }
                            b"timezone" | b"tz" => {
                                if let Ok(val) = std::str::from_utf8(&attr.value) {
                                    let tz = val.trim().to_string();
                                    if !tz.is_empty() {
                                        st_timezone = Some(tz);
                                    }
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

                    if !is_offline && !name.is_empty() && !url.is_empty() && !name.starts_with("[separator") {
                        let final_country = st_country.or_else(|| country_code.clone());
                        let st = match (final_country, st_timezone) {
                            (Some(c), Some(tz)) => Station::with_timezone(name, url, c, tz),
                            (Some(c), None) => Station::with_country(name, url, c),
                            (None, Some(tz)) => {
                                let mut s = Station::new(name, url);
                                s.timezone = Some(tz);
                                s
                            }
                            (None, None) => Station::new(name, url),
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

/// Analyse un fichier bouquet individuel sur le disque (en excluant les stations status="offline")
pub fn parse_bouquet_file(path: &Path) -> Vec<Station> {
    let mut file = match File::open(path) {
        Ok(f) => f,
        Err(e) => {
            log::warn!("Impossible d'ouvrir le fichier bouquet {:?} : {}", path, e);
            return Vec::new();
        }
    };
    let mut content = String::new();
    if let Err(e) = BufReader::new(&mut file).read_to_string(&mut content) {
        log::warn!("Erreur lecture bouquet {:?} : {}", path, e);
        return Vec::new();
    }
    parse_bouquet_xml_str(&content)
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
                    .filter(|p| p.extension().is_some_and(|ext| ext == "xml"))
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
                    .filter(|p| p.extension().is_some_and(|ext| ext == "xml"))
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

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct BouquetStationItem {
    pub name: String,
    pub url: String,
    pub genre: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub country: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub timezone: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default, PartialEq)]
pub struct BouquetSubGroup {
    pub national: Vec<BouquetStationItem>,
    pub regions: BTreeMap<String, Vec<BouquetStationItem>>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct BouquetLanguage {
    pub id: String,
    pub name: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct BouquetDetails {
    pub code: String,
    pub name: String,
    pub multilingual: bool,
    pub languages: Vec<BouquetLanguage>,
    pub national: Vec<BouquetStationItem>,
    pub regions: BTreeMap<String, Vec<BouquetStationItem>>,
    pub sub_bouquets: BTreeMap<String, BouquetSubGroup>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub xml_path: Option<String>,
}

/// Analyse le contenu XML d'un bouquet et extrait toute son arborescence
pub fn parse_bouquet_details_str(content: &str, file_path: Option<&str>) -> BouquetDetails {
    let mut reader = Reader::from_str(content);
    reader.config_mut().trim_text(true);

    let mut details = BouquetDetails {
        code: String::new(),
        name: String::new(),
        multilingual: false,
        languages: Vec::new(),
        national: Vec::new(),
        regions: BTreeMap::new(),
        sub_bouquets: BTreeMap::new(),
        xml_path: file_path.map(|s| s.to_string()),
    };

    let mut current_community_id: Option<String> = None;
    let mut current_region: Option<String> = None;
    let mut buf = Vec::new();

    loop {
        match reader.read_event_into(&mut buf) {
            Ok(Event::Start(ref e)) | Ok(Event::Empty(ref e)) => {
                let tag_name = e.name();
                match tag_name.as_ref() {
                    b"bouquet" => {
                        for attr in e.attributes().flatten() {
                            match attr.key.as_ref() {
                                b"country" => {
                                    if let Ok(val) = std::str::from_utf8(&attr.value) {
                                        details.code = val.trim().to_uppercase();
                                    }
                                }
                                b"name" => {
                                    if let Ok(val) = std::str::from_utf8(&attr.value) {
                                        details.name = val.trim().to_string();
                                    }
                                }
                                b"multilingual" => {
                                    if let Ok(val) = std::str::from_utf8(&attr.value) {
                                        details.multilingual = val.trim().eq_ignore_ascii_case("true");
                                    }
                                }
                                _ => {}
                            }
                        }
                    }
                    b"community" => {
                        let mut comm_id = String::new();
                        let mut comm_name = String::new();
                        for attr in e.attributes().flatten() {
                            match attr.key.as_ref() {
                                b"id" => {
                                    if let Ok(val) = std::str::from_utf8(&attr.value) {
                                        comm_id = val.trim().to_string();
                                    }
                                }
                                b"name" => {
                                    if let Ok(val) = std::str::from_utf8(&attr.value) {
                                        comm_name = val.trim().to_string();
                                    }
                                }
                                _ => {}
                            }
                        }
                        if !comm_id.is_empty() {
                            if comm_name.is_empty() {
                                comm_name = comm_id.clone();
                            }
                            details.languages.push(BouquetLanguage {
                                id: comm_id.clone(),
                                name: comm_name,
                            });
                            current_community_id = Some(comm_id);
                        }
                    }
                    b"region" => {
                        for attr in e.attributes().flatten() {
                            if attr.key.as_ref() == b"name" {
                                if let Ok(val) = std::str::from_utf8(&attr.value) {
                                    current_region = Some(val.trim().to_string());
                                }
                            }
                        }
                    }
                    b"station" | b"bookmark" => {
                        let mut name = String::new();
                        let mut url = String::new();
                        let mut genre = String::new();
                        let mut country: Option<String> = None;
                        let mut timezone: Option<String> = None;
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
                                b"genre" => {
                                    if let Ok(val) = std::str::from_utf8(&attr.value) {
                                        genre = val.trim().to_string();
                                    }
                                }
                                b"country" | b"countrycode" => {
                                    if let Ok(val) = std::str::from_utf8(&attr.value) {
                                        let c = val.trim().to_uppercase();
                                        if !c.is_empty() {
                                            country = Some(c);
                                        }
                                    }
                                }
                                b"timezone" | b"tz" => {
                                    if let Ok(val) = std::str::from_utf8(&attr.value) {
                                        let tz = val.trim().to_string();
                                        if !tz.is_empty() {
                                            timezone = Some(tz);
                                        }
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

                        if !is_offline && !name.is_empty() && !url.is_empty() && !name.starts_with("[separator") {
                            let station_country = country.or_else(|| {
                                if !details.code.is_empty() {
                                    Some(details.code.clone())
                                } else {
                                    None
                                }
                            });
                            let item = BouquetStationItem {
                                name,
                                url,
                                genre,
                                country: station_country,
                                timezone,
                            };

                            if let Some(ref comm_id) = current_community_id {
                                let sub = details.sub_bouquets.entry(comm_id.clone()).or_default();
                                if let Some(ref reg) = current_region {
                                    sub.regions.entry(reg.clone()).or_default().push(item);
                                } else {
                                    sub.national.push(item);
                                }
                            } else if let Some(ref reg) = current_region {
                                details.regions.entry(reg.clone()).or_default().push(item);
                            } else {
                                details.national.push(item);
                            }
                        }
                    }
                    _ => {}
                }
            }
            Ok(Event::End(ref e)) => {
                match e.name().as_ref() {
                    b"community" => current_community_id = None,
                    b"region" => current_region = None,
                    _ => {}
                }
            }
            Ok(Event::Eof) => break,
            Err(e) => {
                log::warn!("Erreur lors de l'analyse du bouquet : {}", e);
                break;
            }
            _ => {}
        }
        buf.clear();
    }

    details
}

/// Résout l'emplacement d'un fichier bouquet par son code pays ISO ou son chemin
pub fn find_bouquet_file_by_target(target: &str) -> Option<PathBuf> {
    let p = Path::new(target);
    if p.is_file() {
        return Some(p.to_path_buf());
    }

    if let Some(b_dir) = find_bouquets_dir() {
        let candidate_lower = b_dir.join(format!("{}.xml", target.to_lowercase()));
        if candidate_lower.is_file() {
            return Some(candidate_lower);
        }
        let candidate_upper = b_dir.join(format!("{}.xml", target.to_uppercase()));
        if candidate_upper.is_file() {
            return Some(candidate_upper);
        }
        let direct = b_dir.join(target);
        if direct.is_file() {
            return Some(direct);
        }
    }

    if let Some(ex_dir) = find_examples_dir() {
        let direct = ex_dir.join(target);
        if direct.is_file() {
            return Some(direct);
        }
        let with_ext = ex_dir.join(format!("{}.xml", target));
        if with_ext.is_file() {
            return Some(with_ext);
        }
    }

    None
}

/// Analyse un bouquet ciblé par son code ISO ou son chemin
pub fn dump_bouquet(target: &str) -> Option<BouquetDetails> {
    let path = find_bouquet_file_by_target(target)?;
    let mut file = File::open(&path).ok()?;
    let mut content = String::new();
    file.read_to_string(&mut content).ok()?;
    Some(parse_bouquet_details_str(&content, path.to_str()))
}

/// Sérialise en JSON l'arborescence complète du bouquet ciblé
pub fn dump_bouquet_json(target: &str) -> String {
    match dump_bouquet(target) {
        Some(details) => serde_json::to_string_pretty(&details).unwrap_or_else(|_| "{}".to_string()),
        None => "{}".to_string(),
    }
}

/// Renvoie la liste triée de tous les codes pays ayant un bouquet disponible
pub fn list_available_bouquet_codes() -> Vec<String> {
    let mut codes = Vec::new();
    if let Some(b_dir) = find_bouquets_dir() {
        if let Ok(entries) = std::fs::read_dir(b_dir) {
            for entry in entries.flatten() {
                let path = entry.path();
                if path.extension().is_some_and(|ext| ext == "xml") {
                    if let Some(stem) = path.file_stem().and_then(|s| s.to_str()) {
                        let upper = stem.to_ascii_uppercase();
                        if !upper.starts_with('X') && upper.len() == 2 {
                            codes.push(upper);
                        }
                    }
                }
            }
        }
    }
    codes.sort();
    codes.dedup();
    codes
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

    #[test]
    fn test_parse_bookmarks_xml_with_country_and_timezone() {
        let xml = r#"<?xml version="1.0" encoding="utf-8"?>
<bookmarks>
    <group name="Musique Celtique &amp; Irlandaise">
        <bookmark name="CAROCelt - Bretagne" url="https://carocelt.ice.infomaniak.ch/carocelt-128.mp3" country="FR" timezone="Europe/Paris"/>
        <bookmark name="Irish Pub Radio" url="http://solid24.streamupsolutions.com:8026/stream" country="IE" timezone="Europe/Dublin"/>
    </group>
</bookmarks>"#;

        let stations = parse_bouquet_xml_str(xml);
        assert_eq!(stations.len(), 2);
        assert_eq!(stations[0].name, "CAROCelt - Bretagne");
        assert_eq!(stations[0].country, Some("FR".to_string()));
        assert_eq!(stations[0].timezone, Some("Europe/Paris".to_string()));
        assert_eq!(stations[1].name, "Irish Pub Radio");
        assert_eq!(stations[1].country, Some("IE".to_string()));
        assert_eq!(stations[1].timezone, Some("Europe/Dublin".to_string()));
    }

    #[test]
    fn test_parse_bouquet_details_multilingual() {
        let xml = r#"<?xml version='1.0' encoding='utf-8'?>
<bouquet country="CH" name="Suisse" flag="" multilingual="true">
  <community id="FR" name="Romandie">
    <national>
      <station name="RTS 1" url="https://rts1.mp3" genre="Info" />
    </national>
    <regions>
      <region name="Jura">
        <station name="RFJ" url="https://rfj.mp3" genre="Locale" />
      </region>
    </regions>
  </community>
</bouquet>"#;

        let details = parse_bouquet_details_str(xml, Some("data/bouquets/ch.xml"));
        assert_eq!(details.code, "CH");
        assert_eq!(details.name, "Suisse");
        assert!(details.multilingual);
        assert_eq!(details.languages.len(), 1);
        assert_eq!(details.languages[0].id, "FR");
        let sub = details.sub_bouquets.get("FR").unwrap();
        assert_eq!(sub.national.len(), 1);
        assert_eq!(sub.national[0].name, "RTS 1");
        assert_eq!(sub.national[0].country, Some("CH".to_string()));
        let reg = sub.regions.get("Jura").unwrap();
        assert_eq!(reg.len(), 1);
        assert_eq!(reg[0].name, "RFJ");
    }
}

