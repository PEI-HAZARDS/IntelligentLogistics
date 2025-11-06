# agentA.py
from confluent_kafka import Producer
import json, time, uuid

def delivery_callback(err, msg):
    if err:
        print(f"Erro ao enviar: {err}")
    else:
        print(f"Mensagem entregue: {msg.topic()}, value: {msg.value()}")

conf = {'bootstrap.servers': 'localhost:9092'}
producer = Producer(conf)

# Exemplo de publicação
event = {
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "truckId": "TRK" + str(uuid.uuid4())[:8],
    "confidence": 0.87
}
producer.produce(
    topic='truck-detected',
    key=None,
    value=json.dumps(event),
    headers={'correlationId': str(uuid.uuid4())},
    callback=delivery_callback
)
producer.flush()
