/// Structure représentant un signet de webradio ou un séparateur
/// Represents a radio station bookmark or separator with optional country tag.
#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct Station {
    pub name: String,
    pub url: String,
    pub country: Option<String>,
    pub timezone: Option<String>,
}

/// Nettoie et normalise préventivement une URL de flux audio
/// (supprime les doublons de préfixes de protocole, anomalies de copier-coller, espaces, slashes superflus)
pub fn clean_stream_url(raw_url: &str) -> String {
    let mut u = raw_url.trim().to_string();
    if u.is_empty() {
        return u;
    }

    // 1. Gestion des espaces accidentels dans le protocole (ex: "http ://" ou "https ://")
    if u.starts_with("http ://") {
        u = format!("http://{}", &u["http ://".len()..]);
    } else if u.starts_with("https ://") {
        u = format!("https://{}", &u["https ://".len()..]);
    }

    // 2. Gestion des URLs relatives au protocole "//domaine.com"
    if u.starts_with("//") {
        u = format!("https://{}", &u[2..]);
    }

    // 3. Gestion des anomalies répétées ou imbriquées de protocole
    loop {
        if let Some(rest) = u.strip_prefix("httpshttps://") {
            u = format!("https://{}", rest);
            continue;
        }
        if let Some(rest) = u.strip_prefix("httphttp://") {
            u = format!("http://{}", rest);
            continue;
        }
        if let Some(rest) = u.strip_prefix("http://https://") {
            u = format!("https://{}", rest);
            continue;
        }
        if let Some(rest) = u.strip_prefix("https://http://") {
            u = format!("http://{}", rest);
            continue;
        }
        if let Some(rest) = u.strip_prefix("https://https://") {
            u = format!("https://{}", rest);
            continue;
        }
        if let Some(rest) = u.strip_prefix("http://http://") {
            u = format!("http://{}", rest);
            continue;
        }
        break;
    }

    // 4. Nettoyage des slashes multiples après le protocole ("http:///" ou "https:///")
    if let Some(rest) = u.strip_prefix("https:///") {
        u = format!("https://{}", rest.trim_start_matches("/"));
    } else if let Some(rest) = u.strip_prefix("http:///") {
        u = format!("http://{}", rest.trim_start_matches("/"));
    }

    u.trim().to_string()
}

impl Station {
    /// Crée une nouvelle station de radio sans étiquette de pays (avec nettoyage préventif d URL)
    /// Creates a new radio station without country tag (with preventive URL cleanup)
    pub fn new(name: impl Into<String>, url: impl Into<String>) -> Self {
        let u = clean_stream_url(&url.into());
        Self {
            name: name.into(),
            url: u,
            country: None,
            timezone: None,
        }
    }

    /// Crée une station avec étiquette de pays ISO 3166-1 (ex: "FR", "JP") et nettoyage d URL
    /// Creates a station with an ISO country code tag (e.g., "FR", "JP") and clean URL
    pub fn with_country(name: impl Into<String>, url: impl Into<String>, country: impl Into<String>) -> Self {
        let u = clean_stream_url(&url.into());
        Self {
            name: name.into(),
            url: u,
            country: Some(country.into()),
            timezone: None,
        }
    }

    /// Crée une station avec étiquette de pays ISO 3166-1 (ex: "FR", "JP") et fuseau horaire IANA
    pub fn with_timezone(name: impl Into<String>, url: impl Into<String>, country: impl Into<String>, timezone: impl Into<String>) -> Self {
        let u = clean_stream_url(&url.into());
        Self {
            name: name.into(),
            url: u,
            country: Some(country.into()),
            timezone: Some(timezone.into()),
        }
    }

    /// Crée un séparateur avec un titre optionnel (intertitre)
    /// Creates a separator with an optional section title
    pub fn separator(title: impl Into<String>) -> Self {
        Self {
            name: title.into(),
            url: String::new(),
            country: None,
            timezone: None,
        }
    }

    /// Détermine si cet élément est un séparateur
    /// Determines whether this item is a separator
    pub fn is_separator(&self) -> bool {
        self.url.is_empty()
            || self.url == "---"
            || self.name.starts_with("[separator-")
            || self.name.starts_with("[separator")
            || self.name == "---"
            || self.name == "separator - - -"
    }

    /// Récupère le titre propre du séparateur/intertitre si présent
    /// Extracts the clean section title for separators
    pub fn separator_title(&self) -> Option<String> {
        if !self.is_separator() {
            return None;
        }
        let trimmed = self.name.trim();
        if trimmed.is_empty()
            || trimmed.starts_with("[separator-")
            || trimmed.starts_with("[separator")
            || trimmed == "---"
            || trimmed == "separator - - -"
        {
            None
        } else {
            let clean = trimmed.trim_matches('-').trim();
            if clean.is_empty() {
                None
            } else {
                Some(clean.to_string())
            }
        }
    }
}

/// Structure arborescente d un groupe contenant des stations et des sous-groupes
/// Tree structure representing a group containing stations and subgroups
#[derive(Debug, Clone, PartialEq)]
pub struct Group {
    pub name: String,
    pub stations: Vec<Station>,
    pub subgroups: Vec<Group>,
}

impl Group {
    pub fn new(name: impl Into<String>) -> Self {
        Self {
            name: name.into(),
            stations: Vec::new(),
            subgroups: Vec::new(),
        }
    }

    /// Crée un séparateur ou un intertitre entre groupes
    /// Creates a separator or section title between groups
    pub fn separator(title: impl Into<String>) -> Self {
        let t = title.into();
        let name = if t.trim().is_empty() {
            "---".to_string()
        } else {
            format!("--- {} ---", t.trim())
        };
        Self {
            name,
            stations: Vec::new(),
            subgroups: Vec::new(),
        }
    }

    /// Détermine si cet élément de groupe est un séparateur/intertitre
    /// Determines whether this group item is a separator/section title
    pub fn is_separator(&self) -> bool {
        self.name.starts_with("---")
            || self.name.starts_with("[separator")
            || self.name == "separator - - -"
    }

    /// Titre propre du séparateur de groupe si présent
    /// Extracts clean title of group separator if present
    pub fn separator_title(&self) -> Option<String> {
        if !self.is_separator() {
            return None;
        }
        let trimmed = self.name.trim();
        let clean = trimmed.trim_matches('-').trim();
        if clean.is_empty() || clean.starts_with("[separator") {
            None
        } else {
            Some(clean.to_string())
        }
    }

    /// Nombre total de stations réelles (hors séparateurs)
    /// Total count of real stations (excluding separators)
    pub fn total_stations(&self) -> usize {
        if self.is_separator() {
            return 0;
        }
        let direct = self.stations.iter().filter(|s| !s.is_separator()).count();
        let recursive: usize = self.subgroups.iter().map(|g| g.total_stations()).sum();
        direct + recursive
    }

    /// Trie les stations de ce groupe et de tous ses sous-groupes par ordre alphabétique
    /// Sorts stations in this group and all subgroups alphabetically
    pub fn sort_stations_alphabetically(&mut self) {
        self.stations.sort_by_key(|s| s.name.to_lowercase());
        for sub in &mut self.subgroups {
            sub.sort_stations_alphabetically();
        }
    }

    /// Trie les sous-groupes par ordre alphabétique (insensible à la casse)
    /// Sorts subgroups alphabetically
    pub fn sort_subgroups_alphabetically(&mut self) {
        self.subgroups.sort_by_key(|a| a.name.to_lowercase());
    }

    /// Déplace un sous-groupe vers le haut (échange avec le précédent)
    /// Moves a subgroup up
    pub fn move_subgroup_up(&mut self, name: &str) -> bool {
        if let Some(pos) = self.subgroups.iter().position(|g| g.name.eq_ignore_ascii_case(name)) {
            if pos > 0 {
                self.subgroups.swap(pos, pos - 1);
                return true;
            }
        }
        false
    }

    /// Déplace un sous-groupe vers le bas (échange avec le suivant)
    /// Moves a subgroup down
    pub fn move_subgroup_down(&mut self, name: &str) -> bool {
        if let Some(pos) = self.subgroups.iter().position(|g| g.name.eq_ignore_ascii_case(name)) {
            if pos + 1 < self.subgroups.len() {
                self.subgroups.swap(pos, pos + 1);
                return true;
            }
        }
        false
    }

    /// Déplace un sous-groupe en toute première position
    /// Moves a subgroup to top
    pub fn move_subgroup_to_top(&mut self, name: &str) -> bool {
        if let Some(pos) = self.subgroups.iter().position(|g| g.name.eq_ignore_ascii_case(name)) {
            if pos > 0 {
                let g = self.subgroups.remove(pos);
                self.subgroups.insert(0, g);
                return true;
            }
        }
        false
    }

    /// Enrichit les stations existantes avec un code pays ISO si elles correspondent par URL ou par nom
    /// Enriches existing stations with an ISO country code if matching by URL or name
    pub fn enrich_station_country(&mut self, name: &str, url: &str, country_code: &str) -> bool {
        let mut modified = false;
        let clean_name = name.trim().to_lowercase();
        let clean_url = url.trim();

        for st in &mut self.stations {
            if !st.is_separator() {
                let match_url = !clean_url.is_empty() && st.url.trim() == clean_url;
                let match_name = !clean_name.is_empty() && st.name.trim().to_lowercase() == clean_name;
                if (match_url || match_name) && st.country.as_deref() != Some(country_code) {
                    st.country = Some(country_code.to_string());
                    modified = true;
                }
            }
        }

        for sub in &mut self.subgroups {
            if sub.enrich_station_country(name, url, country_code) {
                modified = true;
            }
        }

        modified
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_clean_stream_url() {
        assert_eq!(clean_stream_url("httpshttps://stream.org/audio"), "https://stream.org/audio");
        assert_eq!(clean_stream_url("httphttp://stream.org/audio"), "http://stream.org/audio");
        assert_eq!(clean_stream_url("http://https://stream.org/audio"), "https://stream.org/audio");
        assert_eq!(clean_stream_url("https://http://stream.org/audio"), "http://stream.org/audio");
        assert_eq!(clean_stream_url("https://https://stream.org/audio"), "https://stream.org/audio");
        assert_eq!(clean_stream_url("http://http://stream.org/audio"), "http://stream.org/audio");
        assert_eq!(clean_stream_url("https ://stream.org/audio"), "https://stream.org/audio");
        assert_eq!(clean_stream_url("http ://stream.org/audio"), "http://stream.org/audio");
        assert_eq!(clean_stream_url("//stream.org/audio"), "https://stream.org/audio");
        assert_eq!(clean_stream_url("https:///stream.org/audio"), "https://stream.org/audio");
        assert_eq!(clean_stream_url("   https://stream.org/audio/   "), "https://stream.org/audio/");

        let st = Station::new("Test Station", "httpshttps://live.radio.fr/stream");
        assert_eq!(st.url, "https://live.radio.fr/stream");
    }

    #[test]
    fn test_country_enrichment() {
        let mut root = Group::new("root");
        let mut grp = Group::new("Généralistes");
        grp.stations.push(Station::new("France Inter", "https://stream.radiofrance.fr/franceinter"));
        grp.stations.push(Station::new("Wit FM", "https://witfm.ice/witfm"));
        root.subgroups.push(grp);

        assert_eq!(root.subgroups[0].stations[0].country, None);

        let enriched = root.enrich_station_country("France Inter", "", "FR");
        assert!(enriched);
        assert_eq!(root.subgroups[0].stations[0].country, Some("FR".to_string()));
        assert_eq!(root.subgroups[0].stations[1].country, None);

        let enriched_url = root.enrich_station_country("Nom Inconnu", "https://witfm.ice/witfm", "FR");
        assert!(enriched_url);
        assert_eq!(root.subgroups[0].stations[1].country, Some("FR".to_string()));
    }

    #[test]
    fn test_group_separator_detection() {
        let sep_anon = Group::separator("");
        assert!(sep_anon.is_separator());
        assert_eq!(sep_anon.separator_title(), None);
        assert_eq!(sep_anon.total_stations(), 0);

        let sep_titled = Group::separator("Radios Thématiques");
        assert!(sep_titled.is_separator());
        assert_eq!(sep_titled.separator_title(), Some("Radios Thématiques".to_string()));
        assert_eq!(sep_titled.total_stations(), 0);

        let real_group = Group::new("Généralistes");
        assert!(!real_group.is_separator());
        assert_eq!(real_group.separator_title(), None);
    }

    #[test]
    fn test_separator_detection_and_titles() {
        let sep_anon = Station::separator("");
        assert!(sep_anon.is_separator());
        assert_eq!(sep_anon.separator_title(), None);
        assert_eq!(sep_anon.country, None);

        let sep_titled = Station::separator("Jazz & Blues");
        assert!(sep_titled.is_separator());
        assert_eq!(sep_titled.separator_title(), Some("Jazz & Blues".to_string()));

        let real_station = Station::with_country("FIP", "https://icecast.radiofrance.fr/fip-midfi.mp3", "FR");
        assert!(!real_station.is_separator());
        assert_eq!(real_station.country, Some("FR".to_string()));
    }

    #[test]
    fn test_subgroup_reordering() {
        let mut root = Group::new("root");
        root.subgroups.push(Group::new("C"));
        root.subgroups.push(Group::new("A"));
        root.subgroups.push(Group::new("B"));

        root.sort_subgroups_alphabetically();
        assert_eq!(root.subgroups[0].name, "A");
        assert_eq!(root.subgroups[1].name, "B");
        assert_eq!(root.subgroups[2].name, "C");

        assert!(root.move_subgroup_up("B"));
        assert_eq!(root.subgroups[0].name, "B");
        assert_eq!(root.subgroups[1].name, "A");
    }

    #[test]
    fn test_stations_sorting_alphabetically() {
        let mut group = Group::new("Rock");
        group.stations.push(Station::new("ZZ Top Radio", "http://zz.com"));
        group.stations.push(Station::new("AC/DC Station", "http://acdc.com"));
        group.stations.push(Station::new("Beatles Radio", "http://beatles.com"));

        group.sort_stations_alphabetically();
        assert_eq!(group.stations[0].name, "AC/DC Station");
        assert_eq!(group.stations[1].name, "Beatles Radio");
        assert_eq!(group.stations[2].name, "ZZ Top Radio");
    }
}

#[cfg(test)]
mod hierarchy_tests {
    use super::*;

    #[test]
    fn test_subgroup_hierarchy_nested() {
        let mut root = Group::new("root");
        fn get_or_create(mut current: &mut Group, path: &str) -> usize {
            for part in path.split("/") {
                let clean = part.trim();
                if clean.is_empty() || clean.eq_ignore_ascii_case("root") {
                    continue;
                }
                let pos = if let Some(idx) = current.subgroups.iter().position(|g| g.name.eq_ignore_ascii_case(clean)) {
                    idx
                } else {
                    current.subgroups.push(Group::new(clean));
                    current.subgroups.len() - 1
                };
                current = &mut current.subgroups[pos];
            }
            current.subgroups.len()
        }

        get_or_create(&mut root, ": Radio France/FIP (Webradios)");
        assert_eq!(root.subgroups.len(), 1);
        assert_eq!(root.subgroups[0].name, ": Radio France");
        assert_eq!(root.subgroups[0].subgroups.len(), 1);
        assert_eq!(root.subgroups[0].subgroups[0].name, "FIP (Webradios)");

        get_or_create(&mut root, ": Radio France/ICI (Locales)");
        assert_eq!(root.subgroups.len(), 1);
        assert_eq!(root.subgroups[0].subgroups.len(), 2);
    }
}
