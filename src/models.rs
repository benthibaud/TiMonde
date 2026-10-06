/// Structure représentant un signet de webradio ou un séparateur
#[derive(Debug, Clone, PartialEq)]
pub struct Station {
    pub name: String,
    pub url: String,
}

impl Station {
    pub fn is_separator(&self) -> bool {
        self.name.starts_with("[separator-") || self.url.is_empty()
    }
}

/// Structure arborescente d'un groupe contenant des stations et des sous-groupes
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

    /// Nombre total de stations réelles (hors séparateurs)
    pub fn total_stations(&self) -> usize {
        let direct = self.stations.iter().filter(|s| !s.is_separator()).count();
        let recursive: usize = self.subgroups.iter().map(|g| g.total_stations()).sum();
        direct + recursive
    }
}
