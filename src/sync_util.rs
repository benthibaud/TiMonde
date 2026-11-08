//! Utilitaires de synchronisation sécurisés
//! Garantit une tolérance totale aux pannes (anti-poisoning) sans aucun unwrap.

use std::sync::{Mutex, MutexGuard};

pub trait SafeLock<T> {
    /// Acquiert le verrou sur le Mutex en récupérant de manière transparente l'état interne
    /// même si le Mutex a été empoisonné par un panic survenu dans un autre thread.
    fn safe_lock(&self) -> MutexGuard<'_, T>;
}

impl<T> SafeLock<T> for Mutex<T> {
    #[inline]
    fn safe_lock(&self) -> MutexGuard<'_, T> {
        self.lock().unwrap_or_else(|poisoned| poisoned.into_inner())
    }
}
