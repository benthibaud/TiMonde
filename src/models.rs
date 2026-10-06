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

    /// Trie les sous-groupes par ordre alphabétique (insensible à la casse)
    pub fn sort_subgroups_alphabetically(&mut self) {
        self.subgroups.sort_by_key(|a| a.name.to_lowercase());
    }

    /// Déplace un sous-groupe vers le haut (échange avec le précédent)
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
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_subgroup_reordering() {
        let mut root = Group::new("root");
        root.subgroups.push(Group::new("C"));
        root.subgroups.push(Group::new("A"));
        root.subgroups.push(Group::new("B"));

        // Tri alphabétique
        root.sort_subgroups_alphabetically();
        assert_eq!(root.subgroups[0].name, "A");
        assert_eq!(root.subgroups[1].name, "B");
        assert_eq!(root.subgroups[2].name, "C");

        // Déplacer B vers le haut
        assert!(root.move_subgroup_up("B"));
        assert_eq!(root.subgroups[0].name, "B");
        assert_eq!(root.subgroups[1].name, "A");

        // Déplacer B en haut alors qu'il est déjà premier -> false
        assert!(!root.move_subgroup_up("B"));

        // Déplacer B vers le bas
        assert!(root.move_subgroup_down("B"));
        assert_eq!(root.subgroups[1].name, "B");

        // Déplacer C en tout premier
        assert!(root.move_subgroup_to_top("C"));
        assert_eq!(root.subgroups[0].name, "C");
    }
}
