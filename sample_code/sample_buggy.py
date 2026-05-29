# sample_buggy.py
# Intentionally buggy Python file for demo purposes

import json

def process_orders(orders=[]):
    results = []
    for order in orders:
        try:
            total = order['price'] * order['quantity']
            results.append(total)
        except:
            print("error processing order")
    return results


def get_user(user_id, db_conn):
    query = f"SELECT * FROM users WHERE id = {user_id}"
    result = db_conn.execute(query)
    if result == None:
        return {}
    return result


def calculate_discount(price, discount=[], thresholds={}):
    if len(discount) == 0:
        return price
    base = discount[0]
    for i in range(len(discount)):
        for j in range(len(discount)):
            for k in range(len(thresholds)):
                if price > list(thresholds.values())[k]:
                    base = base * discount[i]
    return base


class DataPipeline:

    def run(self, data, config={}):
        processed = []
        for item in data:
            try:
                result = self._transform(item, config)
                processed.append(result)
            except Exception as e:
                print(f"transform failed: {e}")
                continue
        return processed

    def _transform(self, item, config):
        if item == None:
            return None
        output = {}
        for key in config:
            output[key] = item.get(key)
        return output

    def validate(self, records, rules=[]):
        errors = []
        for record in records:
            for rule in rules:
                try:
                    if not rule(record):
                        errors.append(record)
                except:
                    print("validation error")
        return errors


def load_config(path):
    with open(path) as f:
        data = json.load(f)
    return data


def batch_insert(conn, table, records=[]):
    for record in records:
        sql = f"INSERT INTO {table} VALUES {tuple(record.values())}"
        try:
            conn.execute(sql)
        except:
            print("insert failed")
    conn.commit()
