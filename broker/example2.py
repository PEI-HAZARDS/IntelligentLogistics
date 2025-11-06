# agentB.py (corrigido)
from confluent_kafka import Producer, Consumer, KafkaException
import json, uuid, sys, signal

running = True
def handle_sigint(sig, frame):
    global running
    running = False
signal.signal(signal.SIGINT, handle_sigint)

conf_consumer = {
    'bootstrap.servers': 'localhost:9092',
    'group.id': 'agentB-group',
    'auto.offset.reset': 'earliest',
    'enable.auto.commit': True,           # commit automático
    'session.timeout.ms': 10000,          # opcional: janela de sessão
    'max.poll.interval.ms': 300000        # opcional: processamento longo
}
consumer = Consumer(conf_consumer)
consumer.subscribe(['truck-detected'])

conf_producer = {'bootstrap.servers': 'localhost:9092'}
producer = Producer(conf_producer)

try:
    while running:
        msg = consumer.poll(timeout=1.0)
        if msg is None:
            continue  # não sair; continuar à espera
        if msg.error():
            # podes fazer logging aqui se quiseres
            continue

        try:
            data = json.loads(msg.value())
        except json.JSONDecodeError:
            print("Mensagem inválida (JSON). A ignorar.")
            continue

        # ler correlationId (se existir) e decodificar
        corr_id = None
        hdrs = msg.headers() or []
        for k, v in hdrs:
            if k == 'correlationId' and v is not None:
                corr_id = v.decode() if isinstance(v, (bytes, bytearray)) else str(v)
                break
        if corr_id is None:
            corr_id = str(uuid.uuid4())

        # Simula reconhecimento da matrícula
        placa = "ABC-1234"
        event = {
            "timestamp": data.get("timestamp"),
            "truckId": data.get("truckId"),
            "licensePlate": placa,
            "confidence": 0.95
        }

        producer.produce(
            topic='license-plate-detected',
            key=None,
            value=json.dumps(event),
            headers={'correlationId': corr_id}
        )
        # força envio se o buffer estiver cheio
        producer.poll(0)
        print(f"Processado: {msg.topic()} -> {event}")

except KeyboardInterrupt:
    pass
except KafkaException as e:
    print(f"Kafka error: {e}")
finally:
    print("A fechar…")
    producer.flush(5)
    consumer.close()
