from flask import Flask, jsonify, request
import requests

app = Flask(__name__)

ORDER_SERVICE_URL = "http://192.168.64.4:5002"

@app.route('/place_order', methods=['POST'])
def place_order():
    data = request.json  # Get user input
    name = data.get("name")
    order_id = data.get("order_id")

    if not name or not order_id:
        return jsonify({"error": "Missing name or order_id"}), 400

    response = requests.post(f"{ORDER_SERVICE_URL}/receive_order", json=data)

    return response.json(), response.status_code


@app.route('/get_orders/<string:name>', methods=['GET'])
def get_orders(name):
    response = requests.get(f"{ORDER_SERVICE_URL}/get_orders/{name}")

    return response.json(), response.status_code


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)  # Listen on all interfaces
