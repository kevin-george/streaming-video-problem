from flask import Flask, request, jsonify
import uuid
import datetime

app = Flask(__name__)

# In-memory data storage for now
broadcasts = {}

@app.route('/broadcasts', methods=['POST'])
def register_broadcast():
    data = request.get_json()
    if data['stream_url'] is None:
        return jsonify({"error": "Missing stream_url"}), 400
    # If no unique identifier is in the request, we make one
    if data['broadcaster_id'] is None:
        broadcaster_id = f"broadcaster-{uuid.uuid4().hex[:8]}"
    else:
        broadcaster_id = data["broadcaster_id"]
    broadcasts[broadcaster_id] = {
        "broadcaster_id": data['broadcaster_id'],
        "stream_url": data['stream_url'],
        "status": "active",
        "created_at": datetime.datetime.now(datetime.timezone.utc)
    }
    return jsonify(broadcasts[broadcaster_id]), 201

@app.route('/broadcasts', methods=['GET'])
def list_broadcasts():
    return jsonify(list(broadcasts.values()))

@app.route('/broadcasts/<broadcaster_id>', methods=['DELETE'])
def delete_broadcast(broadcaster_id):
    if broadcaster_id not in broadcasts:
        return jsonify({"error": "Broadcaster not found"}), 404
    del broadcasts[broadcaster_id]
    return jsonify({}), 204

if __name__ == '__main__':
    app.run(debug=True)
