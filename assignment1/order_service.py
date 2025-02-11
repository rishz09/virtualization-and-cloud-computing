from flask import Flask, jsonify, request

app = Flask(__name__)

# Dictionary to store orders {name: [order_ids]}
orders_db = {}

@app.route('/receive_order', methods=['POST'])
def receive_order():
    data = request.json
    name = data.get("name")
    order_id = data.get("order_id")

    if not name or not order_id:
        return jsonify({"error": "Missing name or order_id"}), 400

    if name in orders_db:
        orders_db[name].append(order_id)
    else:
        orders_db[name] = [order_id]

    return jsonify({"message": f"Order {order_id} placed successfully for {name}!"})


@app.route('/get_orders/<string:name>', methods=['GET'])
def get_orders(name):
    if name in orders_db:
        return jsonify({"name": name, "orders": orders_db[name]})
    return jsonify({"message": f"No orders found for {name}"}), 404


@app.route('/all_orders', methods=['GET'])
def all_orders():
    return jsonify(orders_db)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002)  # Listen on all interfaces
