# Zebra Agent

This will (eventually) become the main 'loop' for Zebra. Zebra is designed to be a long running entity with memory, goals and ability to act.

## Logical Components

### Memory (Information)
A tiered memory system which can be used by the agent loop. Long term picks up themes cross referenced to short term.

The compaction process should work analagous to dreaming, looking to review the recent data, compact it and identify learnings. Learning can be both the memory and improving the workflow, creating new workflows. 

### Memory (Workflows)
 
The engine is free to use workflows, define new ones and optimize existing ones. As part of it's compaction it will review their effectiveness, feature gaps and improve them.

### Workflow Engine
The workflow engine provides a structured way to learn skills. Each flow represents a sequence of events that achieve a goal. Zebr can combine flows to build complex logic either using nested workflows.

### Periodic Cycle
Zebra should operate on cycle - the cycle will have a budget of compute time, llm tokens. At end of each cycle it will 'dream' and optimize itself. Both the sleeping and cycle will have budgets. 
