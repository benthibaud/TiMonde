use crate::models::{Group, Station};
use log::info;
use quick_xml::events::Event;
use quick_xml::Reader;
use std::fs::File;
use std::io::BufReader;
use std::path::{Path, PathBuf};

/// Erreurs de parsing de bookmarks / Bookmarks parsing errors
#[derive(Debug)]
pub enum BookmarksError {
    Io(std::io::Error),
    Xml(quick_xml::Error),
    Format(String),
}

impl From<std::io::Error> for BookmarksError {
    fn from(e: std::io::Error) -> Self {
        Self::Io(e)
    }
}

impl From<quick_xml::Error> for BookmarksError {
    fn from(e: quick_xml::Error) -> Self {
        Self::Xml(e)
    }
}

impl std::fmt::Display for BookmarksError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Io(e) => write!(f, "Erreur d'accès fichier : {}", e),
            Self::Xml(e) => write!(f, "Erreur syntaxe XML : {}", e),
            Self::Format(msg) => write!(f, "Erreur de format : {}", msg),
        }
    }
}

impl std::error::Error for BookmarksError {}

/// Charge et analyse un fichier bookmarks.xml historique ou moderne TiMonde
/// Loads and parses a historical or modern TiMonde bookmarks.xml file
pub fn load_bookmarks(path: impl AsRef<Path>) -> Result<Group, BookmarksError> {
    let file = File::open(path)?;
    let buf_reader = BufReader::new(file);
    parse_bookmarks_reader(buf_reader)
}

/// Analyse le flux XML depuis un lecteur bufferisé
/// Parses the XML stream from a buffered reader
pub fn parse_bookmarks_reader<R: std::io::BufRead>(reader: R) -> Result<Group, BookmarksError> {
    let mut xml = Reader::from_reader(reader);
    xml.config_mut().trim_text(true);

    let mut buf = Vec::new();
    let mut group_stack: Vec<Group> = vec![Group::new("root")];

    loop {
        match xml.read_event_into(&mut buf)? {
            Event::Start(e) => {
                let name = e.name();
                if name.as_ref() == b"group" {
                    let mut group_name = String::from("Sans nom");
                    for attr in e.attributes().flatten() {
                        if attr.key.as_ref() == b"name" {
                            group_name = attr.unescape_value().unwrap_or_default().into_owned();
                        }
                    }
                    group_stack.push(Group::new(group_name));
                } else if name.as_ref() == b"separator" {
                    let mut title = String::new();
                    for attr in e.attributes().flatten() {
                        if attr.key.as_ref() == b"title" || attr.key.as_ref() == b"name" {
                            title = attr.unescape_value().unwrap_or_default().into_owned();
                        }
                    }
                    if group_stack.len() == 1 {
                        group_stack[0].subgroups.push(Group::separator(title));
                    } else if let Some(current_group) = group_stack.last_mut() {
                        current_group.stations.push(Station::separator(title));
                    }
                }
            }
            Event::Empty(e) => {
                let name = e.name();
                if name.as_ref() == b"separator" {
                    let mut title = String::new();
                    for attr in e.attributes().flatten() {
                        if attr.key.as_ref() == b"title" || attr.key.as_ref() == b"name" {
                            title = attr.unescape_value().unwrap_or_default().into_owned();
                        }
                    }
                    if group_stack.len() == 1 {
                        group_stack[0].subgroups.push(Group::separator(title));
                    } else if let Some(current_group) = group_stack.last_mut() {
                        current_group.stations.push(Station::separator(title));
                    }
                } else if name.as_ref() == b"bookmark" {
                    let mut station_name = String::new();
                    let mut station_url = String::new();
                    let mut station_country: Option<String> = None;
                    let mut station_timezone: Option<String> = None;

                    for attr in e.attributes().flatten() {
                        match attr.key.as_ref() {
                            b"name" => {
                                station_name = attr.unescape_value().unwrap_or_default().into_owned();
                            }
                            b"url" => {
                                station_url = attr.unescape_value().unwrap_or_default().into_owned();
                            }
                            b"country" | b"countrycode" => {
                                let c = attr.unescape_value().unwrap_or_default().into_owned().trim().to_uppercase();
                                if !c.is_empty() {
                                    station_country = Some(c);
                                }
                            }
                            b"timezone" | b"tz" => {
                                let tz = attr.unescape_value().unwrap_or_default().into_owned().trim().to_string();
                                if !tz.is_empty() {
                                    station_timezone = Some(tz);
                                }
                            }
                            _ => {}
                        }
                    }

                    if let Some(current_group) = group_stack.last_mut() {
                        if station_name.starts_with("[separator-")
                            || station_name.starts_with("[separator")
                            || station_name == "---"
                            || station_name == "separator - - -"
                            || (station_url.is_empty() && station_name.contains("separator"))
                        {
                            let title = if station_name.starts_with("[separator-")
                                || station_name == "---"
                                || station_name == "separator - - -"
                            {
                                String::new()
                            } else {
                                station_name
                            };
                            current_group.stations.push(Station::separator(title));
                        } else {
                            current_group.stations.push(Station {
                                name: station_name,
                                url: station_url,
                                country: station_country,
                                timezone: station_timezone,
                            });
                        }
                    }
                }
            }
            Event::End(e) => {
                let name = e.name();
                if name.as_ref() == b"group" && group_stack.len() > 1 {
                    if let Some(finished_group) = group_stack.pop() {
                        if let Some(parent) = group_stack.last_mut() {
                            parent.subgroups.push(finished_group);
                        }
                    }
                }
            }
            Event::Eof => break,
            _ => {}
        }
        buf.clear();
    }

    let root = group_stack.pop().unwrap_or_else(|| Group::new("root"));
    let mut cleaned_root = strip_root_levels(root);
    cleaned_root.restructure_slash_groups();
    Ok(cleaned_root)
}

/// Supprime les paliers "root" superflus hérités de Radio Tray
/// Removes superfluous "root" nesting inherited from legacy Radio Tray
pub fn strip_root_levels(mut group: Group) -> Group {
    while group.subgroups.len() == 1
        && group.stations.is_empty()
        && group.subgroups[0].name.eq_ignore_ascii_case("root")
    {
        group = group.subgroups.remove(0);
    }

    if group.subgroups.len() == 1 && group.subgroups[0].name.eq_ignore_ascii_case("root") {
        let child = group.subgroups.remove(0);
        group.stations.extend(child.stations);
        group.subgroups.extend(child.subgroups);
    }

    group.name = "root".to_string();
    group
}

/// Sauvegarde l'arborescence des groupes au format bookmarks.xml avec indentation stricte
/// Saves group hierarchy into bookmarks.xml format with clean tabs indentation
pub fn save_bookmarks(group: &Group, path: impl AsRef<Path>) -> Result<(), BookmarksError> {
    use std::io::Write;
    let path = path.as_ref();
    if let Some(parent) = path.parent() {
        let _ = std::fs::create_dir_all(parent);
    }

    if path.exists() {
        let bak_path = path.with_extension("xml.bak");
        let _ = std::fs::copy(path, bak_path);
    }

    let tmp_path = path.with_extension("xml.tmp");
    {
        let file = File::create(&tmp_path)?;
        let mut writer = std::io::BufWriter::new(file);

        writeln!(writer, "<bookmarks>")?;
        for sub in &group.subgroups {
            if sub.is_separator() {
                let title = sub.separator_title().unwrap_or_default();
                writeln!(writer, "\t<separator title=\"{}\"/>", escape_xml(&title))?;
            } else {
                write_group_xml(&mut writer, sub, 1)?;
            }
        }
        for st in &group.stations {
            if st.is_separator() {
                let title = st.separator_title().unwrap_or_default();
                writeln!(writer, "\t<separator title=\"{}\"/>", escape_xml(&title))?;
            } else {
                let mut attrs = format!(
                    "name=\"{}\" url=\"{}\"",
                    escape_xml(&st.name),
                    escape_xml(&st.url)
                );
                if let Some(country) = &st.country {
                    attrs.push_str(&format!(" country=\"{}\"", escape_xml(country)));
                }
                if let Some(tz) = &st.timezone {
                    attrs.push_str(&format!(" timezone=\"{}\"", escape_xml(tz)));
                }
                writeln!(writer, "\t<bookmark {}/>", attrs)?;
            }
        }
        writeln!(writer, "</bookmarks>")?;
        writer.flush()?;
        writer.get_ref().sync_all()?;
    }
    std::fs::rename(&tmp_path, path)?;

    Ok(())
}

fn write_group_xml<W: std::io::Write>(
    writer: &mut W,
    group: &Group,
    indent: usize,
) -> Result<(), BookmarksError> {
    let tabs = "\t".repeat(indent);
    writeln!(writer, "{}<group name=\"{}\">", tabs, escape_xml(&group.name))?;

    let inner_tabs = "\t".repeat(indent + 1);
    for sub in &group.subgroups {
        if sub.is_separator() {
            let title = sub.separator_title().unwrap_or_default();
            writeln!(writer, "{}<separator title=\"{}\"/>", inner_tabs, escape_xml(&title))?;
        } else {
            write_group_xml(writer, sub, indent + 1)?;
        }
    }

    for st in &group.stations {
        if st.is_separator() {
            let title = st.separator_title().unwrap_or_default();
            writeln!(
                writer,
                "{}<separator title=\"{}\"/>",
                inner_tabs,
                escape_xml(&title)
            )?;
        } else {
            let mut attrs = format!("name=\"{}\" url=\"{}\"", escape_xml(&st.name), escape_xml(&st.url));
            if let Some(country) = &st.country {
                attrs.push_str(&format!(" country=\"{}\"", escape_xml(country)));
            }
            if let Some(tz) = &st.timezone {
                attrs.push_str(&format!(" timezone=\"{}\"", escape_xml(tz)));
            }
            writeln!(writer, "{}<bookmark {}/>", inner_tabs, attrs)?;
        }
    }

    writeln!(writer, "{}</group>", tabs)?;
    Ok(())
}

fn escape_xml(s: &str) -> String {
    s.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&apos;")
}

/// Met à jour l'URL d'une station dans l'arbre des groupes
pub fn update_station_url(group: &mut Group, station_name: &str, new_url: &str) -> bool {
    for st in &mut group.stations {
        if st.name == station_name {
            st.url = new_url.to_string();
            return true;
        }
    }
    for sub in &mut group.subgroups {
        if update_station_url(sub, station_name, new_url) {
            return true;
        }
    }
    false
}

/// Met à jour le nom et l'URL d'une station dans l'arborescence
pub fn update_station_info(
    group: &mut Group,
    target_url: &str,
    new_name: &str,
    new_url: &str,
) -> bool {
    update_station_full(group, target_url, new_name, new_url, None, None)
}

/// Met à jour récursivement le nom, l'URL et optionnellement le code pays d'une station
/// Recursively updates name, URL and optionally country code of a station
pub fn update_station_full(
    group: &mut Group,
    target_url: &str,
    new_name: &str,
    new_url: &str,
    new_country: Option<Option<String>>,
    new_timezone: Option<Option<String>>,
) -> bool {
    let norm_target = crate::import::normalize_url(target_url);
    for st in &mut group.stations {
        if st.url == target_url
            || crate::import::normalize_url(&st.url) == norm_target
            || (!st.is_separator() && st.name.eq_ignore_ascii_case(new_name))
        {
            st.name = new_name.to_string();
            st.url = crate::models::clean_stream_url(new_url);
            if let Some(c) = &new_country {
                st.country = c.clone();
            }
            if let Some(tz) = &new_timezone {
                st.timezone = tz.clone();
            }
            return true;
        }
    }
    for sub in &mut group.subgroups {
        if update_station_full(sub, target_url, new_name, new_url, new_country.clone(), new_timezone.clone()) {
            return true;
        }
    }
    false
}

/// Supprime récursivement une station identifiée par son URL dans l'arborescence
pub fn remove_station_by_url(group: &mut Group, target_url: &str) -> bool {
    if let Some(pos) = group.stations.iter().position(|s| s.url == target_url) {
        group.stations.remove(pos);
        return true;
    }
    for sub in &mut group.subgroups {
        if remove_station_by_url(sub, target_url) {
            return true;
        }
    }
    false
}

/// Structure de désérialisation et sérialisation pour une station issue du JSON UI
#[derive(serde::Serialize, serde::Deserialize, Debug, Clone)]
pub struct JsonStationInput {
    pub name: String,
    #[serde(default)]
    pub url: String,
    #[serde(default)]
    pub country: Option<String>,
    #[serde(default)]
    pub timezone: Option<String>,
    #[serde(default)]
    pub is_separator: bool,
}

/// Structure de désérialisation et sérialisation pour un groupe issu du JSON UI
#[derive(serde::Serialize, serde::Deserialize, Debug, Clone)]
pub struct JsonGroupInput {
    pub name: String,
    #[serde(default)]
    pub stations: Vec<JsonStationInput>,
    #[serde(default)]
    pub is_separator: bool,
}

/// Reconstruit une arborescence Group "root" complète à partir d'un JSON produit par l'UI Python (Dumb UI)
pub fn rebuild_root_from_json(json_str: &str) -> Result<Group, String> {
    let raw_groups: Vec<JsonGroupInput> = serde_json::from_str(json_str)
        .map_err(|e| format!("JSON invalide : {}", e))?;

    let mut new_root = Group::new("root");

    for g in raw_groups {
        let norm_name = g.name.trim();

        if g.is_separator || norm_name.starts_with("[separator") || norm_name == "---" {
            let title = if norm_name.starts_with("[separator") || norm_name == "---" {
                ""
            } else {
                norm_name
            };
            new_root.subgroups.push(Group::separator(title));
            continue;
        }

        let is_root_literal = norm_name.is_empty()
            || norm_name == "/"
            || norm_name.eq_ignore_ascii_case("root")
            || norm_name.starts_with("[ / ]");

        let mut stations = Vec::new();
        for s in g.stations {
            let s_name = s.name.trim();
            if s.is_separator || s.url.is_empty() || s.url == "---" || s_name.starts_with("[separator") || s_name == "---" {
                let title = if s_name.starts_with("[separator") || s_name == "---" {
                    ""
                } else {
                    s_name
                };
                stations.push(Station::separator(title));
            } else {
                let mut st = Station::new(s_name, s.url.trim());
                st.country = s.country.map(|c| c.trim().to_ascii_uppercase()).filter(|c| !c.is_empty());
                st.timezone = s.timezone.map(|tz| tz.trim().to_string()).filter(|tz| !tz.is_empty());
                stations.push(st);
            }
        }

        if is_root_literal {
            new_root.stations.extend(stations);
        } else {
            let target_grp = new_root.get_or_create_subgroup_hierarchy(norm_name);
            target_grp.stations.extend(stations);
        }
    }

    Ok(new_root)
}

/// Reconstruit et sauvegarde atomiquement bookmarks.xml depuis un payload JSON transmis par la GUI
pub fn save_bookmarks_from_json(json_str: &str, bookmarks_path: impl AsRef<Path>) -> Result<usize, String> {
    let new_root = rebuild_root_from_json(json_str)?;
    let total = new_root.total_stations();
    save_bookmarks(&new_root, bookmarks_path.as_ref())
        .map_err(|e| format!("Erreur sauvegarde bookmarks : {}", e))?;
    Ok(total)
}

/// Convertit l'arborescence native Group en payload structuré pour l'UI Python (Dumb UI)
pub fn root_to_json_payload(root: &Group) -> Vec<JsonGroupInput> {
    let mut payload = Vec::new();

    // 1. Stations orphelines à la racine
    if !root.stations.is_empty() {
        let mut root_stations = Vec::new();
        for s in &root.stations {
            root_stations.push(JsonStationInput {
                name: s.name.clone(),
                url: s.url.clone(),
                country: s.country.clone(),
                timezone: s.timezone.clone(),
                is_separator: s.is_separator(),
            });
        }
        payload.push(JsonGroupInput {
            name: "[ / ] (Racine — Sans groupe)".to_string(),
            stations: root_stations,
            is_separator: false,
        });
    }

    // 2. Fonction récursive pour aplatir les groupes et sous-groupes avec le séparateur /
    fn walk_group(grp: &Group, prefix: &str, out: &mut Vec<JsonGroupInput>) {
        if grp.is_separator() {
            let title = if grp.name.is_empty() { "---".to_string() } else { grp.name.clone() };
            out.push(JsonGroupInput {
                name: title,
                stations: Vec::new(),
                is_separator: true,
            });
            return;
        }

        let full_name = if prefix.is_empty() {
            grp.name.clone()
        } else {
            format!("{}/{}", prefix, grp.name)
        };

        let mut st_list = Vec::new();
        for s in &grp.stations {
            st_list.push(JsonStationInput {
                name: s.name.clone(),
                url: s.url.clone(),
                country: s.country.clone(),
                timezone: s.timezone.clone(),
                is_separator: s.is_separator(),
            });
        }

        if !st_list.is_empty() || grp.subgroups.is_empty() {
            out.push(JsonGroupInput {
                name: full_name.clone(),
                stations: st_list,
                is_separator: false,
            });
        }

        for sub in &grp.subgroups {
            walk_group(sub, &full_name, out);
        }
    }

    for sub in &root.subgroups {
        walk_group(sub, "", &mut payload);
    }

    payload
}

/// Sérialise l'arbre des favoris complet au format JSON pour l'UI
pub fn dump_root_to_json(root: &Group) -> Result<String, String> {
    let payload = root_to_json_payload(root);
    serde_json::to_string_pretty(&payload)
        .map_err(|e| format!("Erreur sérialisation JSON : {}", e))
}

/// Charge bookmarks.xml et le convertit directement en chaîne JSON
pub fn load_bookmarks_as_json(path: &Path) -> Result<String, String> {
    let root = load_bookmarks(path).map_err(|e| e.to_string())?;
    dump_root_to_json(&root)
}

/// Localise le fichier bookmarks.xml de l'utilisateur ou importe un fichier existant (RadioTray-Lite, RadioTray, RadioTray-NG)
pub fn find_bookmarks_path() -> PathBuf {
    let home = std::env::var("HOME").unwrap_or_else(|_| ".".to_string());

    // 1. Emplacement officiel TiMonde
    let timonde_path = PathBuf::from(&home).join(".config/timonde/bookmarks.xml");
    if timonde_path.exists() {
        return timonde_path;
    }

    // 2. Ancien emplacement radiotray-lite
    let rt_lite_path = PathBuf::from(&home).join(".config/radiotray-lite/bookmarks.xml");
    if rt_lite_path.exists() {
        return rt_lite_path;
    }

    // 3. Ancien emplacement radiotray classique
    let rt_path = PathBuf::from(&home).join(".config/radiotray/bookmarks.xml");
    if rt_path.exists() {
        return rt_path;
    }

    // 4. Emplacements radiotray-ng (JSON) : importation automatique si présent
    for rtng_candidate in &[
        PathBuf::from(&home).join(".local/share/radiotray-ng/bookmarks.json"),
        PathBuf::from(&home).join(".config/radiotray-ng/bookmarks.json"),
    ] {
        if rtng_candidate.exists() {
            let mut root = Group::new("root");
            if let Ok(report) = crate::import::import_file(&mut root, rtng_candidate, None) {
                info!("Importation automatique de radiotray-ng ({} stations) vers {}", report.stations_added, timonde_path.display());
                if let Some(parent) = timonde_path.parent() {
                    let _ = std::fs::create_dir_all(parent);
                }
                let _ = save_bookmarks(&root, &timonde_path);
                return timonde_path;
            }
        }
    }

    timonde_path
}

/// Génère un jeu de signets vide si aucun fichier n'existe (aucune radio imposée)
pub fn create_default_bookmarks(path: &Path) -> Group {
    if let Some(parent) = path.parent() {
        let _ = std::fs::create_dir_all(parent);
    }

    let default_xml = "<bookmarks>\n</bookmarks>\n";
    let _ = std::fs::write(path, default_xml);
    parse_bookmarks_reader(default_xml.as_bytes()).unwrap_or_else(|_| Group::new("root"))
}

/// Initialise le dossier ~/.config/timonde/examples/ avec les fichiers exemples de référence si vide ou inexistant
pub fn ensure_config_examples(config_dir: &Path) {
    let examples_dir = config_dir.join("examples");
    if !examples_dir.exists() {
        let _ = std::fs::create_dir_all(&examples_dir);
    }

    let candidates = [
        PathBuf::from("/usr/share/timonde/examples"),
        #[cfg(debug_assertions)]
        PathBuf::from(concat!(env!("CARGO_MANIFEST_DIR"), "/data/examples")),
    ];
    for source_dir in &candidates {
        if source_dir.is_dir() {
            if let Ok(entries) = std::fs::read_dir(source_dir) {
                let mut copied = 0;
                for entry in entries.flatten() {
                    let path = entry.path();
                    if path.is_file() {
                        if let Some(name) = path.file_name() {
                            let dest = examples_dir.join(name);
                            let should_copy = if !dest.exists() {
                                true
                            } else {
                                match (path.metadata().and_then(|m| m.modified()), dest.metadata().and_then(|m| m.modified())) {
                                    (Ok(src_m), Ok(dest_m)) => src_m > dest_m,
                                    _ => false,
                                }
                            };
                            if should_copy && std::fs::copy(&path, &dest).is_ok() {
                                copied += 1;
                            }
                        }
                    }
                }
                if copied > 0 {
                    info!("{} fichier(s) d'exemples mis à jour dans {:?}", copied, examples_dir);
                }
                break;
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_and_save_with_country_tags() {
        let sample = r#"
        <bookmarks>
            <group name="International">
                <bookmark name="France Inter" url="https://franceinter.fr/stream" country="FR"/>
                <bookmark name="NHK World" url="https://nhk.jp/stream" country="JP"/>
                <bookmark name="Legacy Radio" url="https://legacy.com/stream"/>
            </group>
        </bookmarks>
        "#;
        let root = parse_bookmarks_reader(sample.as_bytes()).expect("Parsing réussi");
        assert_eq!(root.subgroups[0].stations.len(), 3);
        assert_eq!(root.subgroups[0].stations[0].country, Some("FR".to_string()));
        assert_eq!(root.subgroups[0].stations[1].country, Some("JP".to_string()));
        assert_eq!(root.subgroups[0].stations[2].country, None);

        let temp_dir = std::env::temp_dir();
        let temp_file = temp_dir.join("timonde_test_country_save.xml");
        save_bookmarks(&root, &temp_file).expect("Sauvegarde réussie");

        let saved = std::fs::read_to_string(&temp_file).expect("Lecture");
        let _ = std::fs::remove_file(&temp_file);

        assert!(saved.contains(r#"country="FR""#));
        assert!(saved.contains(r#"country="JP""#));
        assert!(saved.contains(r#"<bookmark name="Legacy Radio" url="https://legacy.com/stream"/>"#));
    }

    #[test]
    fn test_parse_simple_xml_with_separators() {
        let sample = r#"
        <bookmarks>
            <group name="root">
                <group name="Musique">
                    <bookmark name="Radio 1" url="https://radio1.example/stream"/>
                    <bookmark name="[separator-ac3fe9ec-f485-46d2-a020-ab88ce2304ca]" url=""/>
                    <separator title="Section Jazz"/>
                    <bookmark name="Radio 2" url="https://radio2.example/stream"/>
                    <separator title=""/>
                </group>
            </group>
        </bookmarks>
        "#;
        let root = parse_bookmarks_reader(sample.as_bytes()).expect("Le parsing doit réussir");
        assert_eq!(root.total_stations(), 2);
    }

    #[test]
    fn test_bouquet_country_enrichment_flow() {
        let initial_xml = r#"
        <bookmarks>
            <group name="Favoris">
                <bookmark name="France Inter" url="https://franceinter.fr/stream"/>
                <bookmark name="FIP (Direct)" url="https://fip.fr/stream"/>
                <bookmark name="J-Wave 81.3 FM" url="https://jwave.jp/stream"/>
            </group>
        </bookmarks>
        "#;

        let mut root = parse_bookmarks_reader(initial_xml.as_bytes()).expect("Parse initial");
        assert_eq!(root.subgroups[0].stations[0].country, None);
        assert_eq!(root.subgroups[0].stations[1].country, None);
        assert_eq!(root.subgroups[0].stations[2].country, None);

        // Simulation import bouquet FR
        let enriched_fr1 = root.enrich_station_country("France Inter", "https://franceinter.fr/stream", "FR");
        let enriched_fr2 = root.enrich_station_country("FIP", "https://fip.fr/stream", "FR");
        assert!(enriched_fr1);
        assert!(enriched_fr2);

        // Simulation import bouquet JP
        let enriched_jp = root.enrich_station_country("J-Wave 81.3 FM", "https://jwave.jp/stream", "JP");
        assert!(enriched_jp);

        assert_eq!(root.subgroups[0].stations[0].country, Some("FR".to_string()));
        assert_eq!(root.subgroups[0].stations[1].country, Some("FR".to_string()));
        assert_eq!(root.subgroups[0].stations[2].country, Some("JP".to_string()));

        // Calcul de l'heure locale pour chaque station enrichie
        let time_fr = crate::timezone::get_local_time_for_country(root.subgroups[0].stations[0].country.as_deref().unwrap()).unwrap();
        assert_eq!(time_fr.country_name, "France");
        assert_eq!(time_fr.flag, "");

        let time_jp = crate::timezone::get_local_time_for_country(root.subgroups[0].stations[2].country.as_deref().unwrap()).unwrap();
        assert_eq!(time_jp.country_name, "Japon");
        assert_eq!(time_jp.flag, "");

        // Sauvegarde et relecture XML
        let temp_dir = std::env::temp_dir();
        let temp_file = temp_dir.join("timonde_enrichment_flow.xml");
        save_bookmarks(&root, &temp_file).expect("Sauvegarde");

        let reloaded = load_bookmarks(&temp_file).expect("Relecture");
        let _ = std::fs::remove_file(&temp_file);

        assert_eq!(reloaded.subgroups[0].stations[0].country, Some("FR".to_string()));
        assert_eq!(reloaded.subgroups[0].stations[1].country, Some("FR".to_string()));
        assert_eq!(reloaded.subgroups[0].stations[2].country, Some("JP".to_string()));
    }

    #[test]
    fn test_bookmarks_timezone_xml_roundtrip() {
        let sample = r#"
        <bookmarks>
            <group name="Antilles">
                <bookmark name="Radio Transat" url="https://radiotransat.gp/live" country="FR" timezone="America/Guadeloupe"/>
            </group>
        </bookmarks>
        "#;
        let root = parse_bookmarks_reader(sample.as_bytes()).expect("Parse avec timezone");
        let st = &root.subgroups[0].stations[0];
        assert_eq!(st.name, "Radio Transat");
        assert_eq!(st.country, Some("FR".to_string()));
        assert_eq!(st.timezone, Some("America/Guadeloupe".to_string()));

        // Sauvegarde temporaire et relecture
        let temp_dir = std::env::temp_dir();
        let temp_file = temp_dir.join("timonde_timezone_roundtrip.xml");
        save_bookmarks(&root, &temp_file).expect("Sauvegarde avec timezone");

        let reloaded = load_bookmarks(&temp_file).expect("Relecture avec timezone");
        let _ = std::fs::remove_file(&temp_file);

        let reloaded_st = &reloaded.subgroups[0].stations[0];
        assert_eq!(reloaded_st.name, "Radio Transat");
        assert_eq!(reloaded_st.country, Some("FR".to_string()));
        assert_eq!(reloaded_st.timezone, Some("America/Guadeloupe".to_string()));
    }

    #[test]
    fn test_group_separators_xml_roundtrip() {
        let sample = r#"
        <bookmarks>
            <group name="Généralistes">
                <bookmark name="France Inter" url="https://icecast.radiofrance.fr/franceinter.mp3"/>
            </group>
            <separator title="Thématiques"/>
            <group name="Musique">
                <bookmark name="FIP" url="https://icecast.radiofrance.fr/fip.mp3"/>
            </group>
            <separator/>
            <group name="International">
                <bookmark name="BBC 1" url="https://stream.bbc.co.uk/radio1"/>
            </group>
        </bookmarks>
        "#;
        let root = parse_bookmarks_reader(sample.as_bytes()).expect("Parse avec séparateurs de groupe");
        assert_eq!(root.subgroups.len(), 5);
        assert_eq!(root.subgroups[0].name, "Généralistes");
        assert!(root.subgroups[1].is_separator());
        assert_eq!(root.subgroups[1].separator_title(), Some("Thématiques".to_string()));
        assert_eq!(root.subgroups[2].name, "Musique");
        assert!(root.subgroups[3].is_separator());
        assert_eq!(root.subgroups[3].separator_title(), None);
        assert_eq!(root.subgroups[4].name, "International");

        // Sauvegarde temporaire et relecture
        let temp_dir = std::env::temp_dir();
        let temp_file = temp_dir.join("timonde_group_sep_roundtrip.xml");
        save_bookmarks(&root, &temp_file).expect("Sauvegarde");

        let reloaded = load_bookmarks(&temp_file).expect("Relecture");
        let _ = std::fs::remove_file(&temp_file);

        assert_eq!(reloaded.subgroups.len(), 5);
        assert_eq!(reloaded.subgroups[0].name, "Généralistes");
        assert!(reloaded.subgroups[1].is_separator());
        assert_eq!(reloaded.subgroups[1].separator_title(), Some("Thématiques".to_string()));
        assert_eq!(reloaded.subgroups[2].name, "Musique");
        assert!(reloaded.subgroups[3].is_separator());
        assert_eq!(reloaded.subgroups[3].separator_title(), None);
        assert_eq!(reloaded.subgroups[4].name, "International");
    }

    #[test]
    fn test_radiotray_lite_slash_groups_restructuring() {
        let sample = r#"
        <bookmarks>
            <group name="Sélection perso">
                <bookmark name="France Inter" url="https://icecast.radiofrance.fr/franceinter.mp3"/>
            </group>
            <group name=": Radio France">
                <bookmark name="France Musique" url="https://icecast.radiofrance.fr/francemusique.mp3"/>
            </group>
            <group name=": Radio France/ICI (Locales)">
                <bookmark name="ICI Alsace" url="https://icecast.radiofrance.fr/fbalsace.mp3"/>
            </group>
            <group name=": Radio France/FIP (Webradios)">
                <bookmark name="FIP Rock" url="https://icecast.radiofrance.fr/fiprock.mp3"/>
            </group>
            <group name="Afrique">
                <bookmark name="Radio Afrique 1" url="https://stream.afrique.com/1"/>
            </group>
            <group name="Afrique/Maroc">
                <bookmark name="Medi 1" url="https://stream.medi1.com/live"/>
            </group>
            <group name="Afrique/Maroc/Hit Radio">
                <bookmark name="Hit Radio 100%" url="https://stream.hitradio.ma/live"/>
            </group>
        </bookmarks>
        "#;

        let root = parse_bookmarks_reader(sample.as_bytes()).expect("Parse bookmarks");
        // Doit avoir 3 groupes principaux au 1er niveau : Sélection perso, : Radio France, Afrique
        assert_eq!(root.subgroups.len(), 3);
        assert_eq!(root.subgroups[0].name, "Sélection perso");
        assert_eq!(root.subgroups[1].name, ": Radio France");
        assert_eq!(root.subgroups[2].name, "Afrique");

        // : Radio France doit contenir 1 station directe et 2 sous-groupes (ICI (Locales) et FIP (Webradios))
        let rf = &root.subgroups[1];
        assert_eq!(rf.stations.len(), 1);
        assert_eq!(rf.stations[0].name, "France Musique");
        assert_eq!(rf.subgroups.len(), 2);
        assert_eq!(rf.subgroups[0].name, "ICI (Locales)");
        assert_eq!(rf.subgroups[0].stations[0].name, "ICI Alsace");
        assert_eq!(rf.subgroups[1].name, "FIP (Webradios)");
        assert_eq!(rf.subgroups[1].stations[0].name, "FIP Rock");

        // Afrique doit contenir 1 station directe et 1 sous-groupe Maroc, qui contient Medi 1 et 1 sous-groupe Hit Radio
        let afrique = &root.subgroups[2];
        assert_eq!(afrique.stations.len(), 1);
        assert_eq!(afrique.stations[0].name, "Radio Afrique 1");
        assert_eq!(afrique.subgroups.len(), 1);
        assert_eq!(afrique.subgroups[0].name, "Maroc");
        assert_eq!(afrique.subgroups[0].stations.len(), 1);
        assert_eq!(afrique.subgroups[0].stations[0].name, "Medi 1");
        assert_eq!(afrique.subgroups[0].subgroups.len(), 1);
        assert_eq!(afrique.subgroups[0].subgroups[0].name, "Hit Radio");
        assert_eq!(afrique.subgroups[0].subgroups[0].stations[0].name, "Hit Radio 100%");
    }

    #[test]
    fn test_rebuild_root_from_json() {
        let json_input = r#"[
            {
                "name": "[ / ] (Racine)",
                "stations": [
                    { "name": "Direct Root Station", "url": "http://root.example.com", "country": "FR" },
                    { "name": "Direct Separator", "url": "", "is_separator": true }
                ]
            },
            {
                "name": "Europe/France",
                "stations": [
                    { "name": "FIP", "url": "http://fip.fr", "country": "FR", "timezone": "Europe/Paris" }
                ]
            }
        ]"#;

        let root = rebuild_root_from_json(json_input).expect("Reconstruction JSON réussie");
        assert_eq!(root.stations.len(), 2);
        assert_eq!(root.stations[0].name, "Direct Root Station");
        assert!(root.stations[1].is_separator());

        assert_eq!(root.subgroups.len(), 1);
        assert_eq!(root.subgroups[0].name, "Europe");
        assert_eq!(root.subgroups[0].subgroups.len(), 1);
        assert_eq!(root.subgroups[0].subgroups[0].name, "France");
        assert_eq!(root.subgroups[0].subgroups[0].stations[0].name, "FIP");
        assert_eq!(root.subgroups[0].subgroups[0].stations[0].timezone, Some("Europe/Paris".to_string()));
        assert_eq!(root.total_stations(), 2);

        // Test du dump inverse JSON
        let dumped_json = dump_root_to_json(&root).expect("Dump JSON");
        assert!(dumped_json.contains("Direct Root Station"));
        assert!(dumped_json.contains("Europe/France"));
        assert!(dumped_json.contains("Europe/Paris"));

        // Re-reconstruction à partir du dump pour vérifier la fidélité
        let root2 = rebuild_root_from_json(&dumped_json).expect("Re-reconstruction JSON");
        assert_eq!(root2.total_stations(), 2);
        assert_eq!(root2.stations[0].name, "Direct Root Station");
        assert_eq!(root2.subgroups[0].subgroups[0].stations[0].name, "FIP");
    }
}