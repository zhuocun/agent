"""Tool execution extension points.

Concrete tools should stay behind `ToolExecutor` implementations. The
streaming loop can then add orchestration without coupling provider adapters to
individual tool backends.
"""
