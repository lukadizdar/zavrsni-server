from flask import Flask, render_template, jsonify
from pymongo import MongoClient, database, collection
from datetime import datetime, timedelta
import os
import socket
from typing import Optional, List, Dict, Any, Sequence, Mapping

app = Flask(__name__)

#ip search
def get_local_ip() -> str:
    s: Optional[socket.socket] = None
    ip_address = '127.0.0.1'
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip_address = s.getsockname()[0]
    except Exception as e:
        print(f"[IP DISCOVERY ERROR] Could not determine local IP: {e}. Falling back to {ip_address}")
    finally:
        if s:
            s.close()
    return ip_address

# mongodb same as server.py
MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
DATABASE_NAME = os.getenv('DATABASE_NAME', 'sensor_data')
COLLECTION_NAME = os.getenv('COLLECTION_NAME', 'readings')

HISTORY_LENGTH_MINUTES = 60 #60 samples in graph

#mongodb init
client: Optional[MongoClient] = None
db: Optional[database.Database] = None
readings_collection: Optional[collection.Collection] = None

try:
    client = MongoClient(MONGO_URI)
    db = client[DATABASE_NAME]
    readings_collection = db[COLLECTION_NAME]
    client.admin.command('ping')
    print(f"Successfully connected to MongoDB at {MONGO_URI} and database '{DATABASE_NAME}'.")
except Exception as e:
    print(f"ERROR: Could not connect to MongoDB: {e}")
    client = None
    db = None
    readings_collection = None

def get_aggregated_readings_from_db(limit: int = HISTORY_LENGTH_MINUTES) -> List[Dict[str, Any]]:
    if readings_collection is None:
        return []

    try:
        time_threshold = datetime.now() - timedelta(minutes=limit + 10)

        pipeline: Sequence[Mapping[str, Any]] = [
            {
                '$match': {
                    'timestamp': { '$gte': time_threshold }
                }
            },
            {
                '$group': {
                    '_id': {
                        'year': { '$year': '$timestamp' },
                        'month': { '$month': '$timestamp' },
                        'day': { '$dayOfMonth': '$timestamp' },
                        'hour': { '$hour': '$timestamp' },
                        'minute': { '$minute': '$timestamp' }
                    },
                    'temperature': { '$last': '$temperature' },
                    'humidity': { '$last': '$humidity' },
                    'timestamp_raw': { '$last': '$timestamp' },
                    'client_ip': { '$last': '$client_ip' }
                }
            },
            {
                '$sort': {
                    'timestamp_raw': -1
                }
            },
            {
                '$limit': limit
            },
            {
                '$project': {
                    '_id': 0,
                    'temperature': '$temperature',
                    'humidity': '$humidity',
                    'timestamp': '$timestamp_raw',
                    'timestamp_formatted': {
                        '$dateToString': {
                            'format': '%d-%m-%Y %H:%M:%S',
                            'date': '$timestamp_raw'
                        }
                    },
                    'client_ip': '$client_ip'
                }
            },
            {
                '$sort': {
                    'timestamp': 1
                }
            }
        ]
        aggregated_readings = list(readings_collection.aggregate(pipeline))
        return aggregated_readings
    except Exception as e:
        print(f"Error during MongoDB aggregation: {e}")
        return []

@app.route('/')
def index():
    latest_reading = None
    if readings_collection is not None:
        try:
            latest_reading = readings_collection.find_one(
                sort=[('timestamp', -1)]
            )
            if latest_reading and '_id' in latest_reading:
                latest_reading['_id'] = str(latest_reading['_id'])
        except Exception as e:
            print(f"Error fetching latest reading for initial render: {e}")
            latest_reading = None

    raw_aggregated_data = get_aggregated_readings_from_db(limit=HISTORY_LENGTH_MINUTES)
    initial_stats_data_for_table = list(reversed(raw_aggregated_data))
    local_server_ip = get_local_ip()
    socket_server_port = 5500
    return render_template(
        'index.html',
        initial_temperature=latest_reading.get('temperature') if latest_reading else None,
        initial_humidity=latest_reading.get('humidity') if latest_reading else None,
        initial_stats_data_for_table=initial_stats_data_for_table, # NEWEST FIRST for Jinja2 table
        initial_chart_data=raw_aggregated_data,           # OLDEST FIRST for JS charts
        local_server_ip=local_server_ip,
        socket_server_port=socket_server_port
    )

@app.route('/api/live_readings', methods=['GET'])
def get_live_readings():
    if readings_collection is None:
        return jsonify({"error": "Database not connected"}), 500

    try:
        latest_reading = readings_collection.find_one(
            sort=[('timestamp', -1)]
        )

        if latest_reading:
            latest_reading['_id'] = str(latest_reading['_id'])
            return jsonify(latest_reading), 200
        else:
            return jsonify({"message": "No readings found yet."}), 200
    except Exception as e:
        print(f"Error fetching live readings (API): {e}")
        return jsonify({"error": "Failed to fetch live readings"}), 500

@app.route('/api/statistics', methods=['GET'])
def get_statistics():
    aggregated_readings = get_aggregated_readings_from_db(limit=HISTORY_LENGTH_MINUTES)

    if not aggregated_readings and readings_collection is not None:
        total_readings = readings_collection.count_documents({})
        if total_readings > 0:
            return jsonify({"message": "No minute-aligned data in the last hour. Please ensure ESP32 is sending data.", "count": 0, "data": []}), 200
        else:
            return jsonify({"message": "No historical data available yet.", "count": 0, "data": []}), 200
    elif not aggregated_readings and readings_collection is None:
        return jsonify({"error": "Database not connected"}), 500


    return jsonify({
        "message": "Latest historical readings (1-minute samples).",
        "count": len(aggregated_readings),
        "data": aggregated_readings
    }), 200

if __name__ == '__main__':
    app.run(debug=True)
