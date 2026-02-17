# Memory Leak Runbook

## Symptoms
- Memory usage continuously increasing over time
- Out of memory (OOM) errors
- Application crashes or restarts
- Slow garbage collection

## Common Causes

### 1. Unclosed Resources
**Symptoms**: Connection/file handle leaks
**Check**:
- Database connections not closed
- HTTP clients not cleaned up
- File handles left open
- WebSocket connections not terminated

**Fix**:
- Use context managers (`with` statements)
- Implement proper cleanup in `finally` blocks
- Add connection timeouts
- Review resource lifecycle

### 2. In-Memory Caching Without Eviction
**Symptoms**: Cache grows indefinitely
**Check**:
- Unbounded in-memory caches
- No TTL or max size limits
- Session data accumulation

**Fix**:
- Add cache eviction policies (LRU, TTL)
- Set maximum cache sizes
- Use external cache (Redis)
- Implement cache warming strategy

### 3. Event Listener Leaks
**Symptoms**: Event handlers accumulate
**Check**:
- Event listeners not unregistered
- Closure references holding objects
- Observer pattern memory leaks

**Fix**:
- Properly unregister event listeners
- Use weak references when appropriate
- Review event handler lifecycle

### 4. Large Object Retention
**Symptoms**: Large objects not garbage collected
**Check**:
- Global variables holding references
- Circular references
- Closures capturing large objects

**Fix**:
- Clear references when done
- Use weak references
- Avoid global state
- Profile memory usage

## Investigation Steps
1. Monitor memory usage over time
2. Take heap dumps before/after
3. Use memory profiler to identify leaks
4. Review recent code changes
5. Check for resource cleanup

## Prevention
- Use linters for resource management
- Implement resource cleanup testing
- Add memory usage monitoring
- Regular code reviews focusing on lifecycle