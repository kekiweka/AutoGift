from flask import Flask, request

app = Flask(__name__)

@app.route('/')
def home():
    return "Платёжный бот работает!"

@app.route('/payment_notify', methods=['POST'])
def payment_notify():
    data = request.form.to_dict()
    print("🔔 Получено уведомление:", data)
    return "OK"

if __name__ == '__main__':
    app.run()
