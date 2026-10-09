use crate::models::{Group, Station};
use quick_xml::events::Event;
use quick_xml::Reader;
use std::fs::File;
use std::io::BufReader;
use std::path::Path;

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
                    let finished_group = group_stack.pop().unwrap();
                    if let Some(parent) = group_stack.last_mut() {
                        parent.subgroups.push(finished_group);
                    }
                }
            }
            Event::Eof => break,
            _ => {}
        }
        buf.clear();
    }

    let root = group_stack.pop().unwrap_or_else(|| Group::new("root"));
    Ok(strip_root_levels(root))
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

    let file = File::create(path)?;
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
        } else if let Some(country) = &st.country {
            writeln!(
                writer,
                "\t<bookmark name=\"{}\" url=\"{}\" country=\"{}\"/>",
                escape_xml(&st.name),
                escape_xml(&st.url),
                escape_xml(country)
            )?;
        } else {
            writeln!(
                writer,
                "\t<bookmark name=\"{}\" url=\"{}\"/>",
                escape_xml(&st.name),
                escape_xml(&st.url)
            )?;
        }
    }
    writeln!(writer, "</bookmarks>")?;
    writer.flush()?;

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
}