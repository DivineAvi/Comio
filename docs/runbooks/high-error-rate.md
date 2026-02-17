# High Error Rate Runbook

## Symptoms
- 5xx errors spike above 5% of total requests
- Error rate continues for more than 1 minute
- Users reporting failures

## Common Causes

### 1. Database Connection Issues
**Symptoms**: 500/503 errors, timeout exceptions
**Check**:
- Database connection pool exhausted
- Slow queries causing timeouts
- Database server overloaded

**Fix**:
- Increase connection pool size
- Add query timeouts
- Scale database resources
- Check for missing indexes

### 2. External API Failures
**Symptoms**: 502/504 errors, dependency timeouts
**Check**:
- Third-party service degraded
- Network connectivity issues
- API rate limits exceeded

**Fix**:
- Implement circuit breakers
- Add retry logic with exponential backoff
- Cache responses when possible
- Have fallback behavior

### 3. Code Bugs (Recent Deploy)
**Symptoms**: Errors started after recent deployment
**Check**:
- Check recent commits
- Review deployment logs
- Look for null pointer exceptions, type errors

**Fix**:
- Rollback to previous version
- Apply hotfix if cause is identified
- Add error handling

### 4. Resource Exhaustion
**Symptoms**: Memory/CPU saturation, OOM errors
**Check**:
- Memory usage trends
- Garbage collection frequency
- Thread pool exhaustion

**Fix**:
- Scale horizontally (add instances)
- Optimize memory usage
- Add resource limits
- Implement graceful degradation

## Investigation Steps
1. Check error logs for stack traces
2. Review recent deployments (last 1 hour)
3. Check database query performance
4. Verify external dependencies are healthy
5. Check resource utilization (CPU, memory, disk)

## Prevention
- Implement health checks
- Add circuit breakers for external calls
- Set up proper monitoring and alerting
- Use staging environment for testing