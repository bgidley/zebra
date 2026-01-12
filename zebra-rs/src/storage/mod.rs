//! Storage module for workflow state persistence.

pub mod base;
pub mod memory;

pub use base::{ProcessLockGuard, StateStore};
pub use memory::InMemoryStore;
