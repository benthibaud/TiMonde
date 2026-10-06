use crate::models::{Group, Station};
use quick_xml::events::Event;
use quick_xml::Reader;
use std::fs::File;
use std::io::BufReader;
use std::path::Path;

/// Erreurs de parsing de bookmarks
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

/// Charge et analyse un fichier bookmarks.xml historique de Radio Tray
pub fn load_bookmarks(path: impl AsRef<Path>) -> Result<Group, BookmarksError> {
    let file = File::open(path)?;
    let buf_reader = BufReader::new(file);
    parse_bookmarks_reader(buf_reader)
}

/// Analyse le flux XML depuis un lecteur bufferisé
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
                }
            }
            Event::Empty(e) => {
                let name = e.name();
                if name.as_ref() == b"bookmark" {
                    let mut station_name = String::new();
                    let mut station_url = String::new();

                    for attr in e.attributes().flatten() {
                        match attr.key.as_ref() {
                            b"name" => {
                                station_name = attr.unescape_value().unwrap_or_default().into_owned();
                            }
                            b"url" => {
                                station_url = attr.unescape_value().unwrap_or_default().into_owned();
                            }
                            _ => {}
                        }
                    }

                    if let Some(current_group) = group_stack.last_mut() {
                        current_group.stations.push(Station {
                            name: station_name,
                            url: station_url,
                        });
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
pub fn strip_root_levels(mut group: Group) -> Group {
    // Tant que le groupe racine contient un unique sous-groupe nommé "root" et aucune station directe,
    // on descend pour supprimer la couche d encadrement inutile
    while group.subgroups.len() == 1
        && group.stations.is_empty()
        && group.subgroups[0].name.eq_ignore_ascii_case("root")
    {
        group = group.subgroups.remove(0);
    }

    // Si après déroulement, le sous-groupe unique restant s appelle encore "root",
    // on fusionne ses éléments au premier niveau
    if group.subgroups.len() == 1 && group.subgroups[0].name.eq_ignore_ascii_case("root") {
        let child = group.subgroups.remove(0);
        group.stations.extend(child.stations);
        group.subgroups.extend(child.subgroups);
    }

    group.sort_stations_alphabetically();
    group.name = "root".to_string();
    group
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_simple_xml() {
        let sample = r#"
        <bookmarks>
            <group name="root">
                <group name="Musique">
                    <bookmark name="Radio 1" url="https://radio1.example/stream"/>
                    <bookmark name="[separator-123]" url=""/>
                    <bookmark name="Radio 2" url="https://radio2.example/stream"/>
                </group>
            </group>
        </bookmarks>
        "#;
        let root = parse_bookmarks_reader(sample.as_bytes()).expect("Le parsing doit réussir");
        assert_eq!(root.total_stations(), 2);
    }

    #[test]
    fn test_parse_real_bookmarks_if_available() {
        let path = std::path::Path::new("/mnt/Donnees/Docs_systeme/bookmarks.xml");
        if path.exists() {
            let root = load_bookmarks(path).expect("Le chargement du fichier réel doit réussir");
            let count = root.total_stations();
            println!("Nombre de stations chargées avec succès : {}", count);
            assert!(count > 1000, "Le fichier réel doit contenir plus de 1000 stations");
            // Vérifier que le niveau "root" n est plus présent dans les sous-groupes de premier niveau
            for sub in &root.subgroups {
                assert_ne!(sub.name.to_lowercase(), "root", "Aucun sous-groupe ne doit s appeler root");
            }
        }
    }

    #[test]
    fn test_strip_multiple_nested_roots() {
        let nested_sample = r#"<bookmarks>
            <group name="root">
                <group name="root">
                    <group name="root">
                        <group name="Jazz">
                            <bookmark name="Jazz Radio" url="https://jazz.example/stream"/>
                        </group>
                        <bookmark name="Radio Directe" url="https://direct.example/stream"/>
                    </group>
                </group>
            </group>
        </bookmarks>"#;

        let root = parse_bookmarks_reader(nested_sample.as_bytes()).expect("Parsing réussi");
        assert_eq!(root.subgroups.len(), 1);
        assert_eq!(root.subgroups[0].name, "Jazz");
        assert_eq!(root.stations.len(), 1);
        assert_eq!(root.stations[0].name, "Radio Directe");
        assert_eq!(root.total_stations(), 2);
    }

    #[test]
    fn test_save_removes_root_level() {
        let sample = r#"<bookmarks>
            <group name="root">
                <group name="Classique">
                    <bookmark name="Radio Classique" url="https://classique.example/stream"/>
                </group>
            </group>
        </bookmarks>"#;

        let root = parse_bookmarks_reader(sample.as_bytes()).expect("Parsing réussi");
        
        let temp_dir = std::env::temp_dir();
        let temp_file = temp_dir.join("timonde_test_save_no_root.xml");
        save_bookmarks(&root, &temp_file).expect("Sauvegarde réussie");

        let saved_content = std::fs::read_to_string(&temp_file).expect("Lecture fichier sauvegardé");
        let _ = std::fs::remove_file(&temp_file);

        // Le fichier XML sauvegardé ne doit contenir AUCUN tag root !
        assert!(!saved_content.contains("name=\"root\""), "Le XML sauvegardé ne doit pas avoir name=root");
        assert!(saved_content.contains("<group name=\"Classique\">"), "Le XML doit contenir le vrai groupe");

        // Re-parsing du fichier sauvegardé pour vérifier l intégrité
        let reloaded = parse_bookmarks_reader(saved_content.as_bytes()).expect("Re-parsing réussi");
        assert_eq!(reloaded.subgroups.len(), 1);
        assert_eq!(reloaded.subgroups[0].name, "Classique");
        assert_eq!(reloaded.total_stations(), 1);
    }
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

/// Sauvegarde l'arborescence des groupes au format bookmarks.xml avec indentation stricte
pub fn save_bookmarks(group: &Group, path: impl AsRef<Path>) -> Result<(), BookmarksError> {
    use std::io::Write;
    let path = path.as_ref();
    if let Some(parent) = path.parent() {
        let _ = std::fs::create_dir_all(parent);
    }

    // Sauvegarde de secours .bak si le fichier existe
    if path.exists() {
        let bak_path = path.with_extension("xml.bak");
        let _ = std::fs::copy(path, bak_path);
    }

    let file = File::create(path)?;
    let mut writer = std::io::BufWriter::new(file);

    writeln!(writer, "<bookmarks>")?;
    // Écrire directement les sous-groupes et stations au premier niveau sous <bookmarks>,
    // SANS balise englobante <group name=\"root\"> !
    for sub in &group.subgroups {
        write_group_xml(&mut writer, sub, 1)?;
    }
    for st in &group.stations {
        writeln!(
            writer,
            "\t<bookmark name=\"{}\" url=\"{}\"/>",
            escape_xml(&st.name),
            escape_xml(&st.url)
        )?;
    }
    writeln!(writer, "</bookmarks>")?;
    writer.flush()?;

    Ok(())
}

fn write_group_xml<W: std::io::Write>(writer: &mut W, group: &Group, indent: usize) -> Result<(), BookmarksError> {
    let tabs = "\t".repeat(indent);
    writeln!(writer, "{}<group name=\"{}\">", tabs, escape_xml(&group.name))?;

    for sub in &group.subgroups {
        write_group_xml(writer, sub, indent + 1)?;
    }

    let inner_tabs = "\t".repeat(indent + 1);
    for st in &group.stations {
        writeln!(
            writer,
            "{}<bookmark name=\"{}\" url=\"{}\"/>",
            inner_tabs,
            escape_xml(&st.name),
            escape_xml(&st.url)
        )?;
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
