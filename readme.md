mahakshah@Mahaks-MacBook-Pro-2 src % curl -s http://localhost:8080/health      
{"role":"primary","status":"healthy","timestamp":1730606406.8366997}
mahakshah@Mahaks-MacBook-Pro-2 src % 
mahakshah@Mahaks-MacBook-Pro-2 src % 
mahakshah@Mahaks-MacBook-Pro-2 src % 
mahakshah@Mahaks-MacBook-Pro-2 src % echo -e "\nWriting initial data:"            
curl -X POST http://localhost:8080/write \
  -H "Content-Type: application/json" \
  -d '{"key":"test1", "value":"before_failure"}' | jq

Writing initial data:
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
100    85  100    44  100    41   1723   1606 --:--:-- --:--:-- --:--:--  3400
{
  "status": "success",
  "written_by": "primary"
}
mahakshah@Mahaks-MacBook-Pro-2 src % curl -s http://localhost:8080/read/test1 | jq
{
  "value": "before_failure"
}
mahakshah@Mahaks-MacBook-Pro-2 src % curl -X POST http://localhost:5002/fail | jq
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
100    40  100    40    0     0   2233      0 --:--:-- --:--:-- --:--:--  2352
{
  "status": "Database failure simulated"
}
mahakshah@Mahaks-MacBook-Pro-2 src % curl -s http://localhost:8080/health         
{"role":"backup","status":"healthy","timestamp":1730606588.870764}
mahakshah@Mahaks-MacBook-Pro-2 src % curl -s http://localhost:8080/read/test1 | jq
{
  "value": "before_failure"
}
mahakshah@Mahaks-MacBook-Pro-2 src % curl -X POST http://localhost:8080/write \   
  -H "Content-Type: application/json" \
  -d '{"key":"test2", "value":"during_failure"}' | jq
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
100    84  100    43  100    41    706    673 --:--:-- --:--:-- --:--:--  1400
{
  "status": "success",
  "written_by": "backup"
}
mahakshah@Mahaks-MacBook-Pro-2 src % curl -s http://localhost:8080/read/test2 | jq
{
  "value": "during_failure"
}
mahakshah@Mahaks-MacBook-Pro-2 src % curl -s http://localhost:8080/read/test1 | jq
{
  "value": "before_failure"
}
mahakshah@Mahaks-MacBook-Pro-2 src % curl -X POST http://localhost:8080/write \   
  -H "Content-Type: application/json" \
  -d '{"key":"test3", "value":"after_failure"}' 
{"status":"success","written_by":"backup"}
mahakshah@Mahaks-MacBook-Pro-2 src % curl -X POST http://localhost:5002/recover   
{"role":"primary","status":"recovered","synced_keys":3}
mahakshah@Mahaks-MacBook-Pro-2 src % 
mahakshah@Mahaks-MacBook-Pro-2 src % 
mahakshah@Mahaks-MacBook-Pro-2 src % curl -s http://localhost:8080/health        
{"role":"primary","status":"healthy","timestamp":1730606720.6349406}
mahakshah@Mahaks-MacBook-Pro-2 src % curl -s http://localhost:8080/read/test1 | jq
{
  "value": "before_failure"
}
mahakshah@Mahaks-MacBook-Pro-2 src % curl -s http://localhost:8080/read/test2 | jq
{
  "value": "during_failure"
}
mahakshah@Mahaks-MacBook-Pro-2 src % curl -s http://localhost:8080/read/test3 | jq
{
  "value": "after_failure"
}
mahakshah@Mahaks-MacBook-Pro-2 src % 
