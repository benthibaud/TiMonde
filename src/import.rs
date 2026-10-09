use crate::models::{Group, Station};
use serde::Deserialize;
use std::collections::HashSet;
use std::path::Path;

#[derive(Debug, Default)]
pub struct ImportReport {
    pub stations_added: usize,
    pub duplicates_skipped: usize,
    pub groups_created: usize,
}

#[derive(Debug, Deserialize)]
struct RtngStation {
    name: String,
    url: String,
    #[serde(default)]
    country: Option<String>,
}

#[derive(Debug, Deserialize)]
struct RtngGroup {
    group: String,
    #[serde(default)]
    stations: Vec<RtngStation>,
}

/// Collecte toutes les URLs de stations déjà existantes pour la détection globale de doublons
pub fn collect_all_urls(group: &Group, set: &mut HashSet<String>) {
    for s in &group.stations {
        if !s.is_separator() {
            set.insert(normalize_url(&s.url));
        }
    }
    for sub in &group.subgroups {
        collect_all_urls(sub, set);
    }
}

/// Normalise une URL pour comparaison stricte (sans slash final ni espaces)
pub fn normalize_url(url: &str) -> String {
    let cleaned = crate::models::clean_stream_url(url);
    if let Some(stripped) = cleaned.strip_suffix('/') {
        stripped.to_string()
    } else {
        cleaned
    }
}

/// Recherche ou crée un sous-groupe et retourne son index dans `parent.subgroups`
fn get_or_create_subgroup_idx(
    parent: &mut Group,
    name: &str,
    report: &mut ImportReport,
) -> usize {
    if let Some(pos) = parent.subgroups.iter().position(|g| g.name.eq_ignore_ascii_case(name)) {
        pos
    } else {
        report.groups_created += 1;
        parent.subgroups.push(Group::new(name));
        parent.subgroups.len() - 1
    }
}

/// Résout dynamiquement le groupe de destination par réemprunt
fn resolve_dest_group<'a>(
    root: &'a mut Group,
    target_idx: Option<usize>,
    sub_name: Option<&str>,
    report: &mut ImportReport,
) -> &'a mut Group {
    match (target_idx, sub_name) {
        (Some(t_idx), Some(name)) if !name.is_empty() && name != "root" => {
            let s_idx = get_or_create_subgroup_idx(&mut root.subgroups[t_idx], name, report);
            &mut root.subgroups[t_idx].subgroups[s_idx]
        }
        (Some(t_idx), _) => &mut root.subgroups[t_idx],
        (None, Some(name)) if !name.is_empty() && name != "root" => {
            let s_idx = get_or_create_subgroup_idx(root, name, report);
            &mut root.subgroups[s_idx]
        }
        (None, _) => root,
    }
}

/// Ajoute une station dans un groupe si elle n'est pas déjà présente (anti-doublon URL et Nom)
fn insert_station_dedup(
    group: &mut Group,
    station: Station,
    existing_urls: &mut HashSet<String>,
    report: &mut ImportReport,
) {
    if station.is_separator() {
        return;
    }

    let norm_url = normalize_url(&station.url);
    if existing_urls.contains(&norm_url) {
        report.duplicates_skipped += 1;
        return;
    }

    // Vérifie également si une station de même nom existe déjà dans ce groupe
    if group.stations.iter().any(|s| s.name.eq_ignore_ascii_case(&station.name)) {
        report.duplicates_skipped += 1;
        return;
    }

    existing_urls.insert(norm_url);
    group.stations.push(station);
    report.stations_added += 1;
}

/// Ajoute une station (avec pays éventuel) à l'arbre avec contrôle strict des doublons
pub fn add_station_to_group(
    root: &mut Group,
    station: Station,
    target_group: Option<&str>,
) -> Result<String, String> {
    let clean_name = station.name.trim();
    let clean_url_str = crate::models::clean_stream_url(station.url.trim());
    let clean_url = clean_url_str.as_str();

    if clean_name.is_empty() {
        return Err("Le nom de la station ne peut pas être vide".to_string());
    }
    if !clean_url.starts_with("http://") && !clean_url.starts_with("https://") {
        return Err("L'URL doit commencer par http:// ou https://".to_string());
    }

    let mut existing_urls = HashSet::new();
    collect_all_urls(root, &mut existing_urls);

    let norm_url = normalize_url(clean_url);
    if existing_urls.contains(&norm_url) {
        return Err(format!("Le flux ({}) est déjà présent dans vos favoris", clean_url));
    }

    let dest_group = match target_group {
        Some(tg) if !tg.trim().is_empty() && !tg.eq_ignore_ascii_case("root") && tg.trim() != "/" => {
            root.get_or_create_subgroup_hierarchy(tg.trim())
        }
        _ => root,
    };

    if dest_group.stations.iter().any(|s| s.name.eq_ignore_ascii_case(clean_name)) {
        return Err(format!("Une station nommée '{}' existe déjà dans ce groupe", clean_name));
    }

    let mut to_insert = match station.country {
        Some(ref c) if !c.is_empty() => Station::with_country(clean_name, clean_url, c),
        _ => Station::new(clean_name, clean_url),
    };
    to_insert.timezone = station.timezone;
    dest_group.stations.push(to_insert);

    let dest_name = if dest_group.name == "root" {
        "la racine".to_string()
    } else {
        format!("le groupe '{}'", dest_group.name)
    };

    Ok(format!("Station '{}' ajoutée avec succès dans {}", clean_name, dest_name))
}

/// Ajoute une station unique à l'arbre avec contrôle strict des doublons
pub fn add_single_station(
    root: &mut Group,
    name: &str,
    url: &str,
    target_group: Option<&str>,
) -> Result<String, String> {
    add_station_to_group(root, Station::new(name, url), target_group)
}

/// Analyse et extrait les stations d'une playlist M3U avec métadonnées #EXTINF
pub fn parse_m3u_entries(content: &str) -> Vec<Station> {
    let mut stations = Vec::new();
    let mut current_name = None;

    for line in content.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }

        if trimmed.starts_with("#EXTINF:") {
            if let Some(pos) = trimmed.find(',') {
                current_name = Some(trimmed[pos + 1..].trim().to_string());
            }
        } else if !trimmed.starts_with('#') && (trimmed.starts_with("http://") || trimmed.starts_with("https://")) {
            let name = current_name.take().unwrap_or_else(|| {
                trimmed.split('/').next_back().unwrap_or("Station").to_string()
            });
            stations.push(Station::new(name, trimmed));
        }
    }
    stations
}

/// Découpe une ligne CSV en respectant les guillemets (RFC 4180)
fn split_csv_line(line: &str) -> Vec<String> {
    let mut fields = Vec::new();
    let mut current = String::new();
    let mut in_quotes = false;
    let mut chars = line.chars().peekable();

    while let Some(c) = chars.next() {
        match c {
            '"' => {
                if in_quotes && chars.peek() == Some(&'"') {
                    current.push('"');
                    chars.next();
                } else {
                    in_quotes = !in_quotes;
                }
            }
            ',' if !in_quotes => {
                fields.push(current.trim().to_string());
                current.clear();
            }
            _ => {
                current.push(c);
            }
        }
    }
    fields.push(current.trim().to_string());
    fields
}

/// Analyse et extrait les stations depuis un fichier CSV (Nom,URL / Nom,URL,Pays / Groupe,Nom,URL / Groupe,Nom,URL,Pays)
pub fn parse_csv_entries(content: &str) -> Vec<(Option<String>, Station)> {
    let mut list = Vec::new();
    for line in content.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() || trimmed.starts_with('#') {
            continue;
        }
        let lower = trimmed.to_lowercase();
        if lower.starts_with("nom,")
            || lower.starts_with("name,")
            || lower.starts_with("groupe,")
            || lower.starts_with("group,")
        {
            continue;
        }

        let cols = split_csv_line(trimmed);
        if cols.len() == 2 && (cols[1].starts_with("http://") || cols[1].starts_with("https://")) {
            list.push((None, Station::new(&cols[0], &cols[1])));
        } else if cols.len() == 3 {
            if cols[1].starts_with("http://") || cols[1].starts_with("https://") {
                // Nom, URL, Pays
                let st = if !cols[2].is_empty() {
                    Station::with_country(&cols[0], &cols[1], &cols[2])
                } else {
                    Station::new(&cols[0], &cols[1])
                };
                list.push((None, st));
            } else if cols[2].starts_with("http://") || cols[2].starts_with("https://") {
                // Groupe, Nom, URL
                let group_name = if cols[0].is_empty() { None } else { Some(cols[0].clone()) };
                list.push((group_name, Station::new(&cols[1], &cols[2])));
            }
        } else if cols.len() >= 4 && (cols[2].starts_with("http://") || cols[2].starts_with("https://")) {
            // Groupe, Nom, URL, Pays
            let group_name = if cols[0].is_empty() { None } else { Some(cols[0].clone()) };
            let st = if !cols[3].is_empty() {
                Station::with_country(&cols[1], &cols[2], &cols[3])
            } else {
                Station::new(&cols[1], &cols[2])
            };
            list.push((group_name, st));
        }
    }
    list
}

/// Importe une liste depuis un fichier (JSON radiotray-ng, M3U, CSV ou XML) vers l'arbre de signets
pub fn import_file(
    root: &mut Group,
    file_path: &Path,
    target_group: Option<&str>,
) -> Result<ImportReport, String> {
    let content = std::fs::read_to_string(file_path)
        .map_err(|e| format!("Impossible de lire le fichier {:?} : {}", file_path, e))?;

    let ext = file_path
        .extension()
        .and_then(|e| e.to_str())
        .unwrap_or("")
        .to_ascii_lowercase();

    let mut report = ImportReport::default();
    let mut existing_urls = HashSet::new();
    collect_all_urls(root, &mut existing_urls);

    match ext.as_str() {
        "json" => {
            let target_idx = target_group.map(|tg| get_or_create_subgroup_idx(root, tg, &mut report));

            if let Ok(rtng_groups) = serde_json::from_str::<Vec<RtngGroup>>(&content) {
                for rg in rtng_groups {
                    let clean_name = rg.group.trim();
                    let sub_arg = if clean_name.is_empty() || clean_name == "root" {
                        None
                    } else {
                        Some(clean_name)
                    };

                    for s in rg.stations {
                        let dest = resolve_dest_group(root, target_idx, sub_arg, &mut report);
                        let st = match s.country {
                            Some(ref c) if !c.is_empty() => Station::with_country(s.name, s.url, c),
                            _ => Station::new(s.name, s.url),
                        };
                        insert_station_dedup(
                            dest,
                            st,
                            &mut existing_urls,
                            &mut report,
                        );
                    }
                }
            } else if let Ok(flat_stations) = serde_json::from_str::<Vec<RtngStation>>(&content) {
                for s in flat_stations {
                    let dest = resolve_dest_group(root, target_idx, None, &mut report);
                    let st = match s.country {
                        Some(ref c) if !c.is_empty() => Station::with_country(s.name, s.url, c),
                        _ => Station::new(s.name, s.url),
                    };
                    insert_station_dedup(
                        dest,
                        st,
                        &mut existing_urls,
                        &mut report,
                    );
                }
            } else {
                return Err("Format JSON non reconnu (attendu : groupes ou liste de stations)".to_string());
            }
        }
        "m3u" | "m3u8" => {
            let stations = parse_m3u_entries(&content);
            let target_idx = target_group.map(|tg| get_or_create_subgroup_idx(root, tg, &mut report));

            for s in stations {
                let dest = resolve_dest_group(root, target_idx, None, &mut report);
                insert_station_dedup(dest, s, &mut existing_urls, &mut report);
            }
        }
        "csv" => {
            let entries = parse_csv_entries(&content);
            let target_idx = target_group.map(|tg| get_or_create_subgroup_idx(root, tg, &mut report));

            for (csv_group, station) in entries {
                let dest = resolve_dest_group(root, target_idx, csv_group.as_deref(), &mut report);
                insert_station_dedup(dest, station, &mut existing_urls, &mut report);
            }
        }
        "xml" => {
            let imported_root = crate::bookmarks::parse_bookmarks_reader(content.as_bytes())
                .map_err(|e| format!("Format XML Radio Tray invalide : {}", e))?;

            let target_idx = target_group.map(|tg| get_or_create_subgroup_idx(root, tg, &mut report));

            // Fusionner les sous-groupes
            for sub in imported_root.subgroups {
                for s in sub.stations {
                    let dest = resolve_dest_group(root, target_idx, Some(&sub.name), &mut report);
                    insert_station_dedup(dest, s, &mut existing_urls, &mut report);
                }
            }

            // Fusionner les stations directes
            for s in imported_root.stations {
                let dest = resolve_dest_group(root, target_idx, None, &mut report);
                insert_station_dedup(dest, s, &mut existing_urls, &mut report);
            }
        }
        _ => {
            return Err(format!(
                "Format de fichier non reconnu (extension .{}) : les formats supportés sont .json (radiotray-ng), .m3u, .csv, .xml",
                ext
            ));
        }
    }

    Ok(report)
}

/// Échappe une valeur pour le format CSV selon la norme RFC 4180
fn escape_csv(field: &str) -> String {
    if field.contains(',') || field.contains('"') || field.contains('\n') || field.contains('\r') {
        format!("\"{}\"", field.replace('"', "\"\""))
    } else {
        field.to_string()
    }
}

pub fn export_to_csv(root: &Group, file_path: &Path) -> Result<usize, String> {
    let mut lines = Vec::new();
    lines.push("# Export des favoris TiMonde".to_string());
    lines.push("Groupe,Nom,URL,Pays".to_string());

    let mut count = 0;

    fn collect_stations(group: &Group, group_name: &str, lines: &mut Vec<String>, count: &mut usize) {
        for s in &group.stations {
            if !s.is_separator() && !s.url.trim().is_empty() {
                let escaped_group = escape_csv(group_name);
                let escaped_name = escape_csv(&s.name);
                let escaped_url = escape_csv(&s.url);
                let escaped_country = escape_csv(s.country.as_deref().unwrap_or(""));
                lines.push(format!("{},{},{},{}", escaped_group, escaped_name, escaped_url, escaped_country));
                *count += 1;
            }
        }
        for sub in &group.subgroups {
            if !sub.is_separator() {
                let sub_name = if group_name.is_empty() {
                    sub.name.clone()
                } else {
                    format!("{}/{}", group_name, sub.name)
                };
                collect_stations(sub, &sub_name, lines, count);
            }
        }
    }

    // Stations directes à la racine
    for s in &root.stations {
        if !s.is_separator() && !s.url.trim().is_empty() {
            let escaped_name = escape_csv(&s.name);
            let escaped_url = escape_csv(&s.url);
            let escaped_country = escape_csv(s.country.as_deref().unwrap_or(""));
            lines.push(format!(",{},{},{}", escaped_name, escaped_url, escaped_country));
            count += 1;
        }
    }

    // Sous-groupes
    for sub in &root.subgroups {
        if !sub.is_separator() {
            collect_stations(sub, &sub.name, &mut lines, &mut count);
        }
    }

    let content = lines.join("
") + "
";
    if let Some(parent) = file_path.parent() {
        if !parent.as_os_str().is_empty() {
            let _ = std::fs::create_dir_all(parent);
        }
    }
    std::fs::write(file_path, content)
        .map_err(|e| format!("Impossible d'écrire le fichier CSV {:?} : {}", file_path, e))?;

    Ok(count)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_import_radiotray_ng_json_with_dedup() {
        let json_data = r#"[
            {
                "group": "Rock",
                "stations": [
                    { "name": "Classic Rock", "url": "https://stream.rock.com/live" },
                    { "name": "Hard Rock", "url": "https://stream.rock.com/hard" }
                ]
            }
        ]"#;

        let mut root = Group::new("root");
        let mut existing_group = Group::new("Rock");
        existing_group.stations.push(Station::new("Classic Rock", "https://stream.rock.com/live/"));
        root.subgroups.push(existing_group);

        let temp_file = std::env::temp_dir().join("test_rtng.json");
        std::fs::write(&temp_file, json_data).unwrap();

        let report = import_file(&mut root, &temp_file, None).unwrap();
        let _ = std::fs::remove_file(temp_file);

        assert_eq!(report.stations_added, 1, "Une seule station doit être ajoutée");
        assert_eq!(report.duplicates_skipped, 1, "Un doublon doit être ignoré");
        assert_eq!(root.total_stations(), 2);
    }

    #[test]
    fn test_import_m3u_with_target_group() {
        let m3u_data = "#EXTM3U\n#EXTINF:-1,Radio Alpha\nhttps://alpha.example/stream\n#EXTINF:-1,Radio Beta\nhttps://beta.example/stream\n";
        let temp_file = std::env::temp_dir().join("test_import.m3u");
        std::fs::write(&temp_file, m3u_data).unwrap();

        let mut root = Group::new("root");
        let report = import_file(&mut root, &temp_file, Some("Favoris Web")).unwrap();
        let _ = std::fs::remove_file(temp_file);

        assert_eq!(report.stations_added, 2);
        assert_eq!(report.groups_created, 1);
        assert_eq!(root.subgroups[0].name, "Favoris Web");
        assert_eq!(root.subgroups[0].stations.len(), 2);
    }

    #[test]
    fn test_import_csv_with_country() {
        let csv = "Nom,URL,Pays
Radio Transat,https://stream.rcs.revma.com/dy09pqzctwzuv,GP
FIP,https://icecast.radiofrance.fr/fip-hifi.aac,FR";
        let entries = parse_csv_entries(csv);
        assert_eq!(entries.len(), 2);
        assert_eq!(entries[0].1.name, "Radio Transat");
        assert_eq!(entries[0].1.country, Some("GP".to_string()));
        assert_eq!(entries[1].1.name, "FIP");
        assert_eq!(entries[1].1.country, Some("FR".to_string()));
    }

    #[test]
    fn test_import_csv() {
        let csv_data = "Rock,Led Zep Radio,https://led.example/stream\nPop,Hit Radio,https://hit.example/stream\nDirect Radio,https://direct.example/stream\n";
        let temp_file = std::env::temp_dir().join("test_import.csv");
        std::fs::write(&temp_file, csv_data).unwrap();

        let mut root = Group::new("root");
        let report = import_file(&mut root, &temp_file, None).unwrap();
        let _ = std::fs::remove_file(temp_file);

        assert_eq!(report.stations_added, 3);
        assert_eq!(report.duplicates_skipped, 0);
        assert_eq!(root.subgroups.len(), 2);
        assert_eq!(root.stations.len(), 1);
    }
    #[test]
    fn test_add_station_with_malformed_url_cleanup() {
        let mut root = Group::new("root");
        let st = Station::new("Radio Malformée", "httpshttps://malformed.example/stream");
        let res = add_station_to_group(&mut root, st, Some("Tests"));
        assert!(res.is_ok());
        assert_eq!(root.subgroups[0].stations[0].url, "https://malformed.example/stream");
    }

    #[test]
    fn test_add_single_station_with_dedup() {
        let mut root = Group::new("root");
        let res = add_single_station(&mut root, "FIP", "https://icecast.radiofrance.fr/fip-midfi.mp3", Some("Jazz"));
        assert!(res.is_ok());
        assert_eq!(root.subgroups.len(), 1);
        assert_eq!(root.subgroups[0].stations.len(), 1);

        // Doublon d URL
        let dup_url = add_single_station(&mut root, "FIP Bis", "https://icecast.radiofrance.fr/fip-midfi.mp3/", None);
        assert!(dup_url.is_err(), "L URL en doublon doit être rejetée");

        // Doublon de nom dans le groupe
        let dup_name = add_single_station(&mut root, "FIP", "https://autre.flux/stream", Some("Jazz"));
        assert!(dup_name.is_err(), "Le nom en doublon dans le même groupe doit être rejeté");

        // Même nom mais dans un autre groupe -> autorisé
        let ok_diff_group = add_single_station(&mut root, "FIP", "https://autre.flux/stream", None);
        assert!(ok_diff_group.is_ok());
    }

    #[test]
    fn test_add_station_with_country_and_timezone() {
        let mut root = Group::new("root");
        let mut st = Station::new("Radio Karukera", "http://stream.karukera.gp/live");
        st.country = Some("FR".to_string());
        st.timezone = Some("America/Guadeloupe".to_string());

        let res = add_station_to_group(&mut root, st, Some("Antilles"));
        assert!(res.is_ok());

        let antilles = root.subgroups.iter().find(|g| g.name == "Antilles").unwrap();
        let found = antilles.stations.iter().find(|s| s.name == "Radio Karukera").unwrap();
        assert_eq!(found.country.as_deref(), Some("FR"));
        assert_eq!(found.timezone.as_deref(), Some("America/Guadeloupe"));
    }

    #[test]
    fn test_add_station_to_group_preserves_country() {
        let mut root = Group::new("root");
        let st = Station::with_country("J-Wave", "https://jwave.stream/live", "JP");
        let res = add_station_to_group(&mut root, st, Some("Asie"));
        assert!(res.is_ok());
        assert_eq!(root.subgroups.len(), 1);
        assert_eq!(root.subgroups[0].stations.len(), 1);
        assert_eq!(root.subgroups[0].stations[0].name, "J-Wave");
        assert_eq!(root.subgroups[0].stations[0].country, Some("JP".to_string()));
    }
    #[test]
    fn test_export_and_reimport_csv() {
        let mut root = Group::new("root");
        let mut g = Group::new("Rock");
        g.stations.push(Station::with_country("Led Zep Radio", "https://led.example/stream", "UK"));
        root.subgroups.push(g);

        let temp_file = std::env::temp_dir().join("test_export.csv");
        let exported_count = export_to_csv(&root, &temp_file).unwrap();
        assert_eq!(exported_count, 1);

        let mut imported_root = Group::new("root");
        let report = import_file(&mut imported_root, &temp_file, None).unwrap();
        assert_eq!(report.stations_added, 1);
        assert_eq!(imported_root.subgroups.len(), 1);
        assert_eq!(imported_root.subgroups[0].name, "Rock");
        assert_eq!(imported_root.subgroups[0].stations[0].name, "Led Zep Radio");
        assert_eq!(imported_root.subgroups[0].stations[0].country.as_deref(), Some("UK"));

        let _ = std::fs::remove_file(temp_file);
    }

    #[test]
    fn test_add_station_with_slash_conventions() {
        let mut root = Group::new("root");

        // 1. Racine avec "/" ou None
        let st_root1 = Station::new("Radio Racine 1", "https://root1.stream/live");
        assert!(add_station_to_group(&mut root, st_root1, Some("/")).is_ok());
        assert_eq!(root.stations.len(), 1);
        assert_eq!(root.stations[0].name, "Radio Racine 1");

        // 2. Groupe principal avec "/Gabon"
        let st_gabon = Station::new("Radio Gabon", "https://gabon.stream/live");
        assert!(add_station_to_group(&mut root, st_gabon, Some("/Gabon")).is_ok());
        let gabon = root.subgroups.iter().find(|g| g.name == "Gabon").unwrap();
        assert_eq!(gabon.stations[0].name, "Radio Gabon");

        // 3. Sous-groupe hiérarchique avec "/France/Bretagne"
        let st_bretagne = Station::new("Radio Bro Gwened", "https://bretagne.stream/live");
        assert!(add_station_to_group(&mut root, st_bretagne, Some("/France/Bretagne")).is_ok());
        let france = root.subgroups.iter().find(|g| g.name == "France").unwrap();
        let bretagne = france.subgroups.iter().find(|g| g.name == "Bretagne").unwrap();
        assert_eq!(bretagne.stations[0].name, "Radio Bro Gwened");

        // 4. Sous-groupe sans slash initial "Belgique/NL"
        let st_vrt = Station::new("VRT Radio 1", "https://vrt.stream/live");
        assert!(add_station_to_group(&mut root, st_vrt, Some("Belgique/NL")).is_ok());
        let belgique = root.subgroups.iter().find(|g| g.name == "Belgique").unwrap();
        let nl = belgique.subgroups.iter().find(|g| g.name == "NL").unwrap();
        assert_eq!(nl.stations[0].name, "VRT Radio 1");
    }
}
