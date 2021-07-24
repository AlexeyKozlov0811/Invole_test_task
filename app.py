import json
import requests
from datetime import datetime
from hashlib import sha256
from flask import Flask, render_template, request, redirect
from pydantic import BaseModel
from logging.config import dictConfig
from flask_sqlalchemy import SQLAlchemy


with open('logging_conf.json') as conf:
    logging_config = json.load(conf)
dictConfig(logging_config)


app = Flask(__name__)


with open('config.json') as conf:
    config = json.load(conf)
app.config.update(config)
db = SQLAlchemy(app)


class Payment(db.Model):
    shop_order_id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.Integer, nullable=False)
    description = db.Column(db.Text, nullable=True)
    creation_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    
    def __repr__(self):
        return '<Payment %d>' % self.shop_order_id


class PaymentSchema(BaseModel):
  amount: float
  currency: int
  description: str
  shop_order_id: int
  creation_date: datetime

  class Config:
        orm_mode = True


def generate_sign(data_to_hash: dict):
  """
  sign generator for payments
  """
  string_to_hash = ''
  for key in data_to_hash:
    string_to_hash += f'{data_to_hash[key]}:'
  string_to_hash = string_to_hash[:-1] + app.config['SECRET_KEY']
  sign = sha256(string_to_hash.encode('utf-8')).hexdigest()
  return sign

def EUR_handler(payment_data: PaymentSchema):
  """
  handler for payments with EUR
  """
  payment = {'amount': payment_data.amount, 'currency': payment_data.currency, 'shop_id': app.config['SHOP_ID'], 'shop_order_id': payment_data.shop_order_id}
  sign = generate_sign(payment)
  app.logger.info(f'Payment - {payment_data.shop_order_id} handler - EUR')
  return render_template('pay.html', payment=payment, sign=sign, description=payment_data.description)

def USD_handler(payment_data: PaymentSchema):
  """
  handler for payments with USD
  """
  payment = {'shop_currency': payment_data.currency, 'shop_amount': payment_data.amount, 'payer_currency': payment_data.currency, 'shop_id': app.config['SHOP_ID'], 'shop_order_id': payment_data.shop_order_id}
  sign = generate_sign(payment)
  url = "https://core.piastrix.com/bill/create"
  data = {"description": payment_data.description,
          "payer_currency": payment_data.currency,
          "shop_amount": payment_data.amount,
          "shop_currency": payment_data.currency,
          "shop_id": app.config['SHOP_ID'],
          "shop_order_id": payment_data.shop_order_id,
          "sign": sign
          }
  response = requests.post(url, json=data)
  response_data = response.json()
  app.logger.info(f'Payment - {payment_data.shop_order_id} handler - USD responce - {response_data}')
  if response_data['result']:
    return redirect(f"{response_data['data']['url']}")
  else:
    return response_data

def RUB_handler(payment_data: PaymentSchema):
  """
  handler for payments with RUB
  """
  payment = {'amount': payment_data.amount, 'currency': payment_data.currency, 'payway': 'advcash_rub','shop_id': app.config['SHOP_ID'], 'shop_order_id': payment_data.shop_order_id}
  sign = generate_sign(payment)
  url = "https://core.piastrix.com/invoice/create"
  data = {"description": payment_data.description,
          "amount": payment_data.amount,
          "currency": payment_data.currency,
          "payway": 'advcash_rub',
          "shop_id": app.config['SHOP_ID'],
          "shop_order_id": payment_data.shop_order_id,
          "sign": sign
          }
  response = requests.post(url, json=data)
  response_data = response.json()
  app.logger.info(f'Payment - {payment_data.shop_order_id} handler - RUB responce - {response_data}')
  if response_data['result']:
    return render_template('invoice.html', url=response_data['data']['url'], data=response_data['data']['data'])
  else:
    return response_data


# handlers dictionary
handler_to_currency = {
  978: EUR_handler,
  840: USD_handler,
  643: RUB_handler
}


@app.route('/')
def index():
  return render_template('index.html')


@app.route('/payment', methods=['POST'])
def payment_handler():
  payment_obj = Payment(amount=request.form.get('amount'), currency=request.form.get('currency'), description=request.form.get('description'))
  db.session.add(payment_obj)
  db.session.commit()
  payment_data = PaymentSchema.from_orm(payment_obj)
  app.logger.info(f'New payment - {payment_data}')
  return handler_to_currency[payment_data.currency](payment_data)


if __name__ == '__main__':
  app.run(debug=True)
