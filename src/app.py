from flask import Flask, jsonify, request
import requests
import json
import os
import time
import hashlib
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
CHECKPOINT_COUNTER = Counter('checkpoint_operations_total', 'Total number of checkpoint operations')
CHECKPOINT_FAILURES = Counter('checkpoint_failures_total', 'Total number of checkpoint failures')


app = Flask(__name__)
# Enable Prometheus metrics collection
prometheus_client.start_http_server(9090)


ROLE = os.environ.get('ROLE', 'primary')
DATA_DIR = '/app/data'
CHECKPOINT_DIR = '/app/checkpoints'
REPLICA_HOST = os.environ.get('REPLICA_HOST', 'backup-server')
PRIMARY_HOST = os.environ.get('PRIMARY_HOST', 'primary-server')
CHECKPOINT_INTERVAL = 30  # seconds

class DistributedDatabase:
    def __init__(self):
        self.data = {}
        self.healthy = True
        self.data_lock = threading.Lock()
        self.checkpoint_thread = None
        self.running = True
        self.initialize_storage()
        self.start_checkpoint_thread()

    def initialize_storage(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        os.makedirs(CHECKPOINT_DIR, exist_ok=True)

    def start_checkpoint_thread(self):
        self.checkpoint_thread = threading.Thread(target=self._checkpoint_loop, daemon=True)
        self.checkpoint_thread.start()

    def _checkpoint_loop(self):
        while self.running:
            try:
                self.create_checkpoint()
                time.sleep(CHECKPOINT_INTERVAL)
            except Exception as e:
                app.logger.error(f"Checkpoint failed: {e}")
                CHECKPOINT_FAILURES.inc()

    def _calculate_data_hash(self):
        """Calculate SHA-256 hash of the current data state"""
        data_str = json.dumps({str(k): v for k, v in self.data.items()}, sort_keys=True)
        return hashlib.sha256(data_str.encode('utf-8')).hexdigest()

    def create_checkpoint(self):
        if not self.healthy:
            return

        with self.data_lock:
            try:
                # Calculate hash of current data state
                data_hash = self._calculate_data_hash()
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

                # Check if this exact state was already checkpointed
                existing_checkpoints = [
                    f for f in os.listdir(CHECKPOINT_DIR)
                    if f.endswith(f"{data_hash}.json")
                ]

                if existing_checkpoints:
                    app.logger.info(f"Skipping checkpoint - state already saved with hash {data_hash}")
                    return data_hash

                checkpoint_file = f"{CHECKPOINT_DIR}/checkpoint_{timestamp}_{data_hash}.json"


            # Create the checkpoint file
                checkpoint_data = {
                    'timestamp': timestamp,
                    'hash': data_hash,
                    'role': ROLE,
                    'data': self.data,
                    'metadata': {
                        'num_keys': len(self.data),
                        'checkpoint_time': time.time()
                    }
                }

                with open(checkpoint_file, 'w') as f:
                    json.dump(checkpoint_data, f)

            # Keep only the last 5 checkpoints
                self._cleanup_old_checkpoints()

                CHECKPOINT_COUNTER.inc()
                app.logger.info(f"Checkpoint created: {checkpoint_file} with hash {data_hash}")
                return data_hash

            except Exception as e:
                app.logger.error(f"Failed to create checkpoint: {e}")
                CHECKPOINT_FAILURES.inc()
                raise

    def _cleanup_old_checkpoints(self):
        checkpoints = sorted([
            f for f in os.listdir(CHECKPOINT_DIR)
            if f.startswith('checkpoint_')
        ])
    # Keep only the last 5 checkpoints
        for checkpoint in checkpoints[:-5]:
            try:
                os.remove(os.path.join(CHECKPOINT_DIR, checkpoint))
            except Exception as e:
                app.logger.error(f"Failed to remove old checkpoint {checkpoint}: {e}")

    def load_data(self):
        # First try to load from the most recent checkpoint
        latest_checkpoint = self._get_latest_checkpoint()
        if latest_checkpoint:
            try:
                with open(latest_checkpoint, 'r') as f:
                    checkpoint_data = json.load(f)
                    self.data = checkpoint_data['data']

                    # Verify data integrity
                    current_hash = self._calculate_data_hash()
                    if current_hash != checkpoint_data['hash']:
                        raise ValueError(f"Checkpoint data integrity check failed. Expected hash: {checkpoint_data['hash']}, Got: {current_hash}")

                    app.logger.info(f"Loaded data from checkpoint: {latest_checkpoint}")
                    return
            except Exception as e:
                app.logger.error(f"Failed to load from checkpoint: {e}")

        # Fall back to regular data file if no checkpoint or checkpoint load fails
        try:
            with open(f"{DATA_DIR}/data.json", 'r') as f:
                self.data = json.load(f)
        except FileNotFoundError:
            self.data = {}

    def _get_latest_checkpoint(self):
        try:
            checkpoints = sorted([
                f for f in os.listdir(CHECKPOINT_DIR)
                if f.startswith('checkpoint_')
            ])
            if checkpoints:
                return os.path.join(CHECKPOINT_DIR, checkpoints[-1])
        except Exception as e:
            app.logger.error(f"Failed to get latest checkpoint: {e}")
        return None

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

@app.route('/data', methods=['GET'])
def get_all_data():
    return jsonify({
        'data': db.data,
        'role': ROLE,
        'timestamp': time.time()
    })

# New checkpoint-related endpoints
@app.route('/checkpoint', methods=['POST'])
def trigger_checkpoint():
    try:
        data_hash = db.create_checkpoint()
        return jsonify({
            'status': 'success',
            'message': 'Checkpoint created successfully',
            'hash': data_hash
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/checkpoints', methods=['GET'])
def list_checkpoints():
    try:
        checkpoints = []
        for filename in sorted(os.listdir(CHECKPOINT_DIR)):
            if filename.startswith('checkpoint_'):
                with open(os.path.join(CHECKPOINT_DIR, filename), 'r') as f:
                    checkpoint_data = json.load(f)
                    checkpoints.append({
                        'filename': filename,
                        'timestamp': checkpoint_data['timestamp'],
                        'hash': checkpoint_data['hash'],
                        'num_keys': checkpoint_data['metadata']['num_keys']
                    })
        return jsonify({
            'checkpoints': checkpoints,
            'count': len(checkpoints)
        })
    except Exception as e:
        return jsonify({
            'error': str(e)
        }), 500

@app.route('/checkpoints/<hash>', methods=['GET'])
def get_checkpoint_by_hash(hash):
    try:
        for filename in os.listdir(CHECKPOINT_DIR):
            if hash in filename:
                with open(os.path.join(CHECKPOINT_DIR, filename), 'r') as f:
                    checkpoint_data = json.load(f)
                    return jsonify(checkpoint_data)
        return jsonify({'error': 'Checkpoint not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/status')
def get_status():
    latest_checkpoint = db._get_latest_checkpoint()
    current_hash = db._calculate_data_hash()

    checkpoint_info = None
    if latest_checkpoint:
        try:
            with open(latest_checkpoint, 'r') as f:
                checkpoint_data = json.load(f)
                checkpoint_info = {
                    'filename': os.path.basename(latest_checkpoint),
                    'timestamp': checkpoint_data['timestamp'],
                    'hash': checkpoint_data['hash'],
                    'num_keys': checkpoint_data['metadata']['num_keys']
                }
        except Exception as e:
            app.logger.error(f"Failed to read checkpoint info: {e}")

    return jsonify({
        'role': ROLE,
        'healthy': db.healthy,
        'data_count': len(db.data),
        'data_keys': list(db.data.keys()),
        'current_hash': current_hash,
        'timestamp': time.time(),
        'latest_checkpoint': checkpoint_info
    })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
