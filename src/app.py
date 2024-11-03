# app.py
from flask import Flask, jsonify, request
import requests
import json
import os
import time
from datetime import datetime
import threading
import prometheus_client
from prometheus_client import Counter, Histogram, Gauge


# Initialize Prometheus metrics
REQUESTS = Counter('http_requests_total', 'Total HTTP requests', ['method', 'endpoint', 'status'])
RESPONSE_TIME = Histogram('http_response_time_seconds', 'Response time in seconds', ['endpoint'])
HEALTH_STATUS = Gauge('node_health_status', 'Node health status (1=healthy, 0=unhealthy)')
DATA_ITEMS = Gauge('data_items_total', 'Total number of data items stored')
REPLICATION_FAILURES = Counter('replication_failures_total', 'Total number of replication failures')




app = Flask(__name__)
# Enable Prometheus metrics collection
prometheus_client.start_http_server(9090)


ROLE = os.environ.get('ROLE', 'primary')
DATA_DIR = '/app/data'
REPLICA_HOST = os.environ.get('REPLICA_HOST', 'backup-db')
PRIMARY_HOST = os.environ.get('PRIMARY_HOST', 'primary-db')

class DistributedDatabase:
    def __init__(self):
        self.data = {}
        self.healthy = True
        self.data_lock = threading.Lock()
        self.initialize_storage()
        
    def initialize_storage(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        self.load_data()
    
    def load_data(self):
        try:
            with open(f"{DATA_DIR}/data.json", 'r') as f:
                self.data = json.load(f)
        except FileNotFoundError:
            self.data = {}
    
    def save_data(self):
        with open(f"{DATA_DIR}/data.json", 'w') as f:
            json.dump(self.data, f)
            
    def replicate_to_backup(self, key, value):
        try:
            response = requests.post(
                f'http://{REPLICA_HOST}:5000/replicate',
                json={'key': key, 'value': value},
                timeout=5
            )
            return response.status_code == 200
        except requests.exceptions.RequestException as e:
            app.logger.error(f"Failed to replicate to backup: {e}")
            return False

db = DistributedDatabase()


@app.before_request
def before_request():
    request.start_time = time.time()

@app.after_request
def after_request(response):
    resp_time = time.time() - request.start_time
    REQUESTS.labels(
        method=request.method,
        endpoint=request.path,
        status=response.status_code
    ).inc()
    RESPONSE_TIME.labels(endpoint=request.path).observe(resp_time)
    return response

@app.route('/metrics')
def metrics():
    return prometheus_client.generate_latest()


@app.route('/health')
def health_check():
    HEALTH_STATUS.set(1 if db.healthy else 0)
    status = 'healthy' if db.healthy else 'unhealthy'
    response = {
        'status': status,
        'role': ROLE,
        'timestamp': time.time()
    }
    
    if not db.healthy and ROLE == 'primary':
        return jsonify(response), 503
    
    return jsonify(response)


@app.route('/write', methods=['POST'])
def write_data():
    try:
        data = request.get_json()
        key = data.get('key')
        value = data.get('value')
        
        # If we're primary and unhealthy, reject the write
        if ROLE == 'primary' and not db.healthy:
            REQUESTS.labels(method='POST', endpoint='/write', status=503).inc()
            return jsonify({'error': 'Primary is unhealthy'}), 503
            
        # If we're backup, accept writes when primary is down
        if ROLE == 'backup':
            # You might want to add a check to verify primary is actually down
            try:
                primary_health = requests.get(f'http://{PRIMARY_HOST}:5000/health', timeout=2)
                if primary_health.status_code == 200:
                    return jsonify({'error': 'Primary is still active'}), 503
            except requests.exceptions.RequestException:
                # Primary is unreachable, proceed with write
                pass
        
        with db.data_lock:
            db.data[key] = value
            db.save_data()
            DATA_ITEMS.set(len(db.data))
            # Only replicate if we're the healthy primary
            if ROLE == 'primary' and db.healthy:
                success = db.replicate_to_backup(key, value)
                if not success:
                    app.logger.warning("Failed to replicate to backup")
                    REPLICATION_FAILURES.inc()
        
        return jsonify({
            'status': 'success',
            'written_by': ROLE
        })
    except Exception as e:
        REQUESTS.labels(method='POST', endpoint='/write', status=500).inc()
        app.logger.error(f"Write failed: {str(e)}")
        return jsonify({'error': str(e)}), 500


# Add detailed status endpoint
@app.route('/status')
def get_status():
    return jsonify({
        'role': ROLE,
        'healthy': db.healthy,
        'data_count': len(db.data),
        'data_keys': list(db.data.keys()),
        'timestamp': time.time()
    })

# Add a debug endpoint
@app.route('/debug')
def debug():
    return jsonify({
        'role': ROLE,
        'healthy': db.healthy,
        'data_count': len(db.data),
        'timestamp': time.time(),
        'data': db.data
    })

@app.route('/read/<key>')
def read_data(key):
    if not db.healthy and ROLE == 'primary':
        return jsonify({'error': 'Service unhealthy'}), 503
    
    value = db.data.get(key)
    if value is None:
        return jsonify({'error': 'Key not found'}), 404
    
    return jsonify({'value': value})

@app.route('/replicate', methods=['POST'])
def replicate():
    if ROLE != 'backup':
        return jsonify({'error': 'Not a backup node'}), 400
    
    data = request.get_json()
    key = data.get('key')
    value = data.get('value')
    
    with db.data_lock:
        db.data[key] = value
        db.save_data()
    
    return jsonify({'status': 'success'})

@app.route('/fail', methods=['POST'])
def simulate_failure():
    db.healthy = False
    return jsonify({'status': 'Database failure simulated'})

@app.route('/recover', methods=['POST'])
def recover():
    if ROLE == 'primary':
        db.healthy = True
        
        # Sync data from backup before becoming active
        try:
            backup_data = requests.get(f'http://{REPLICA_HOST}:5000/data').json()
            with db.data_lock:
                db.data = backup_data['data']
                db.save_data()
            
            return jsonify({
                'status': 'recovered',
                'role': ROLE,
                'synced_keys': len(db.data)
            })
        except Exception as e:
            db.healthy = False  # Revert health status if sync fails
            return jsonify({
                'error': f'Recovery failed: {str(e)}',
                'role': ROLE
            }), 500
    else:
        return jsonify({
            'error': 'Not primary node',
            'role': ROLE
        }), 400

# Add endpoint to get all data (for recovery)
@app.route('/data', methods=['GET'])
def get_all_data():
    return jsonify({
        'data': db.data,
        'role': ROLE,
        'timestamp': time.time()
    })
    

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
