//! Tasks module containing action and condition traits.

pub mod base;
pub mod registry;

pub use base::{
    AlwaysTrueCondition, ConditionAction, ExecutionContext, NoOpAction, RouteNameCondition,
    TaskAction,
};
pub use registry::{ActionRegistry, BoxedAction, BoxedCondition};
