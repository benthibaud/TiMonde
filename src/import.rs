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
}

#[derive(Debug, Deserialize)]
struct RtngGroup {
    group: String,
    #[serde(default)]
    stations: Vec<RtngStation>,
}

/// Collecte toutes les URLs de stations déjà existantes pour la détection globale de doublons
fn collect_all_urls(group: &Group, set: &mut HashSet<String>) {
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
fn normalize_url(url: &str) -> String {
    let u = url.trim();
    if let Some(stripped) = u.strip_suffix('/') {
        stripped.to_string()
    } else {
        u.to_string()
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
            stations.push(Station {
                name,
                url: trimmed.to_string(),
            });
        }
    }
    stations
}

/// Analyse et extrait les stations depuis un fichier CSV (Nom,URL ou Groupe,Nom,URL)
pub fn parse_csv_entries(content: &str) -> Vec<(Option<String>, Station)> {
    let mut list = Vec::new();
    for line in content.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() || trimmed.starts_with('#') {
            continue;
        }
        let cols: Vec<&str> = trimmed.split(',').map(|s| s.trim()).collect();
        if cols.len() == 2 && (cols[1].starts_with("http://") || cols[1].starts_with("https://")) {
            list.push((None, Station { name: cols[0].to_string(), url: cols[1].to_string() }));
        } else if cols.len() >= 3 && (cols[2].starts_with("http://") || cols[2].starts_with("https://")) {
            let group_name = if cols[0].is_empty() { None } else { Some(cols[0].to_string()) };
            list.push((group_name, Station { name: cols[1].to_string(), url: cols[2].to_string() }));
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
            let rtng_groups: Vec<RtngGroup> = serde_json::from_str(&content)
                .map_err(|e| format!("Format JSON radiotray-ng invalide : {}", e))?;

            let target_idx = target_group.map(|tg| get_or_create_subgroup_idx(root, tg, &mut report));

            for rg in rtng_groups {
                let clean_name = rg.group.trim();
                let sub_arg = if clean_name.is_empty() || clean_name == "root" {
                    None
                } else {
                    Some(clean_name)
                };

                for s in rg.stations {
                    let dest = resolve_dest_group(root, target_idx, sub_arg, &mut report);
                    insert_station_dedup(
                        dest,
                        Station { name: s.name, url: s.url },
                        &mut existing_urls,
                        &mut report,
                    );
                }
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
        existing_group.stations.push(Station {
            name: "Classic Rock".to_string(),
            url: "https://stream.rock.com/live/".to_string(),
        });
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
}
