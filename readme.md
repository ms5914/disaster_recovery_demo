# Check initial health status
curl -s http://localhost:8080/health

# Write initial test data
curl -X POST http://localhost:8080/write \
  -H "Content-Type: application/json" \
  -d '{"key":"test1", "value":"before_failure"}' | jq

# Verify initial write
curl -s http://localhost:8080/read/test1 | jq


# Trigger failure mode
curl -X POST http://localhost:5002/fail | jq

# Check health status after failure
curl -s http://localhost:8080/health

# Read existing data during failure
curl -s http://localhost:8080/read/test1 | jq

# Attempt to write new data during failure
curl -X POST http://localhost:8080/write \
  -H "Content-Type: application/json" \
  -d '{"key":"test2", "value":"during_failure"}' | jq

# Verify writes during failure
curl -s http://localhost:8080/read/test2 | jq
curl -s http://localhost:8080/read/test1 | jq

# Write more test data
curl -X POST http://localhost:8080/write \
  -H "Content-Type: application/json" \
  -d '{"key":"test3", "value":"after_failure"}'


# Trigger recovery
curl -X POST http://localhost:5002/recover

# Verify system health after recovery
curl -s http://localhost:8080/health


# Check all data after recovery
curl -s http://localhost:8080/read/test1 | jq
curl -s http://localhost:8080/read/test2 | jq
curl -s http://localhost:8080/read/test3 | jq
