curl -s http://localhost:8080/health                 
curl -X POST http://localhost:8080/write \
  -H "Content-Type: application/json" \
  -d '{"key":"test1", "value":"before_failure"}' | jq
curl -s http://localhost:8080/read/test1 | jq
curl -X POST http://localhost:5002/fail | jq
curl -s http://localhost:8080/health         
curl -s http://localhost:8080/read/test1 | jq
curl -X POST http://localhost:8080/write \   
  -H "Content-Type: application/json" \
  -d '{"key":"test2", "value":"during_failure"}' | jq
curl -s http://localhost:8080/read/test2 | jq
curl -s http://localhost:8080/read/test1 | jq
curl -X POST http://localhost:8080/write \   
  -H "Content-Type: application/json" \
  -d '{"key":"test3", "value":"after_failure"}' 
curl -X POST http://localhost:5002/recover   
curl -s http://localhost:8080/health        
curl -s http://localhost:8080/read/test1 | jq
curl -s http://localhost:8080/read/test2 | jq
curl -s http://localhost:8080/read/test3 | jq
