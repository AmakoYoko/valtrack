# forward_debugger.py (Flask du conteneur)
from flask import Flask, request, jsonify
app = Flask(__name__)

token = None
last_cookies = {}   # domain -> {name: value}

@app.post("/token")
def save_token():
    global token
    token = request.json.get("token")
    return {"ok": True}

@app.get("/json")
def get_token():
    return {"token": token}

@app.post("/cookies")
def save_cookies():
    global last_cookies
    data = request.get_json(force=True)
    # data = { "domain": "...", "cookies": {...} }
    d = data.get("domain")
    c = data.get("cookies") or {}
    print(data)
    if d:
        last_cookies.setdefault(d, {}).update(c)
    return {"ok": True}

@app.get("/cookies")
def get_cookies():
    return jsonify(last_cookies)

@app.get("/bundle")
def get_bundle():
    return jsonify({"token": token, "cookies": last_cookies})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
