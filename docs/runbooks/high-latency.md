# High Latency Runbook

## Symptoms
- P95 latency above 2 seconds
- Request processing time increased
- Slow response times reported by users

## Common Causes

### 1. Database Query Performance
**Symptoms**: Latency correlates with database queries
**Check**:
- Slow query logs
- Missing database indexes
- N+1 query problems
- Lock contention

**Fix**:
- Add indexes on frequently queried columns
- Use query explain plans
- Optimize joins
- Add database query caching
- Use connection pooling

### 2. External API Latency
**Symptoms**: Calls to third-party services are slow
**Check**:
- Network latency to external services
- API rate limiting
- Timeout configurations

**Fix**:
- Implement timeout limits
- Add caching for external data
- Use async/parallel requests
- Add circuit breakers

### 3. Memory Pressure / GC Pauses
**Symptoms**: Latency spikes correlate with memory usage
**Check**:
- Garbage collection frequency
- Memory leak indicators
- Heap size configuration

**Fix**:
- Tune GC settings
- Fix memory leaks
- Increase heap size
- Scale horizontally

### 4. Traffic Surge / Load
**Symptoms**: Latency increases with request volume
**Check**:
- Request rate trends
- CPU utilization
- Thread pool saturation

**Fix**:
- Scale horizontally (add instances)
- Add rate limiting
- Implement request queuing
- Use caching

## Investigation Steps
1. Check application performance metrics
2. Review database slow query logs
3. Verify external dependency health
4. Check system resources (CPU, memory)
5. Look for recent code changes

## Prevention
- Set performance budgets
- Load test before production
- Monitor database query performance
- Implement proper caching strategy