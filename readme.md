# Check initial health
curl -s http://localhost:8080/health

# Write initial data
curl -X POST http://localhost:8080/write \
-H "Content-Type: application/json" \
-d '{"key":"test1", "value":"before_failure"}' | jq

# Read initial data
curl -s http://localhost:8080/read/test1 | jq

# Trigger system failure
curl -X POST http://localhost:5002/fail | jq

# Check health after failure
curl -s http://localhost:8080/health

# Read data during failure
curl -s http://localhost:8080/read/test1 | jq

# Try writing during failure
curl -X POST http://localhost:8080/write \
-H "Content-Type: application/json" \
-d '{"key":"test2", "value":"during_failure"}' | jq

# Read second test data
curl -s http://localhost:8080/read/test2 | jq

# Read first test data again
curl -s http://localhost:8080/read/test1 | jq

# Write third test data
curl -X POST http://localhost:8080/write \
-H "Content-Type: application/json" \
-d '{"key":"test3", "value":"after_failure"}'

# Trigger system recovery
curl -X POST http://localhost:5002/recover

# Check health after recovery
curl -s http://localhost:8080/health

# Verify all data after recovery
curl -s http://localhost:8080/read/test1 | jq \
curl -s http://localhost:8080/read/test2 | jq \
curl -s http://localhost:8080/read/test3 | jq \
