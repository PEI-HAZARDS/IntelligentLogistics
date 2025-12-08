import sys
from pathlib import Path
import json
import time
import threading
import pytest
from mockito import when, verify, mock, unstub, any_, captor

# -------------------------------------------------------------------
# Ajuste de imports para a tua estrutura:
#
# IntelligentLogistics/
#   src/
#     shared_utils/
#     agentA_microservice/
#       src/
#         AgentA.py
#       tests/
#         test_agentA.py
# -------------------------------------------------------------------

TESTS_DIR = Path(__file__).resolve().parent
MICROSERVICE_ROOT = TESTS_DIR.parent              # .../agentA_microservice
GLOBAL_SRC = MICROSERVICE_ROOT.parent            # .../IntelligentLogistics/src

sys.path.insert(0, str(MICROSERVICE_ROOT / "src"))
sys.path.insert(0, str(GLOBAL_SRC))

import AgentA as agentA_module


@pytest.fixture
def agentA():
    """
    Cria AgentA com Producer e YOLO mockados via mockito.
    """
    producer = mock()
    when(agentA_module).Producer(...).thenReturn(producer)

    yolo = mock()
    when(agentA_module).YOLO_Truck(...).thenReturn(yolo)

    agent = agentA_module.AgentA(kafka_bootstrap="localhost:9092")
    agent.producer = producer
    agent.yolo = yolo

    yield agent
    unstub()


# ------------------------------------------------------------------------------
# TESTE 1 — _publish_truck_detected
# ------------------------------------------------------------------------------

def test_publish_truck_detected(agentA):
    val_cap = captor()
    headers_cap = captor()
    cb_cap = captor()

    agentA._publish_truck_detected(max_conf=0.87, num_boxes=3)

    # agora com matchers certos
    verify(agentA.producer, times=1).produce(
        topic="truck-detected",
        key=None,
        value=val_cap,
        headers=headers_cap,
        callback=cb_cap,
    )

    payload = json.loads(val_cap.value.decode("utf-8"))
    assert payload["detections"] == 3
    assert abs(payload["confidence"] - 0.87) < 1e-6
    assert "timestamp" in payload

    assert headers_cap.value["truckId"].startswith("TRK")

    verify(agentA.producer, times=1).poll(0)


# ------------------------------------------------------------------------------
# TESTE 2 — loop publica quando YOLO encontra camião
# ------------------------------------------------------------------------------

def test_loop_publishes_when_truck_found(agentA, monkeypatch):
    cap = mock()
    when(agentA_module).RTSPStream(...).thenReturn(cap)

    # frames: 3 frames e depois None
    when(cap).read().thenReturn("f1").thenReturn("f2").thenReturn("f3").thenReturn(None)

    results = mock()
    when(agentA.yolo).detect(any_).thenReturn(results)

    when(agentA.yolo).truck_found(results).thenReturn(True).thenReturn(False).thenReturn(False)

    when(agentA.yolo).get_boxes(results).thenReturn([
        [0, 0, 1, 1, 0.6],
        [0, 0, 1, 1, 0.9],
    ])

    monkeypatch.setattr(agentA_module, "MESSAGE_INTERVAL", 0)

    def stopper():
        time.sleep(0.2)
        agentA.stop()

    threading.Thread(target=stopper, daemon=True).start()
    agentA._loop()

    val_cap = captor()
    verify(agentA.producer, times=1).produce(value=val_cap, topic="truck-detected", key=None, headers=any_, callback=any_)

    payload = json.loads(val_cap.value.decode())
    assert payload["detections"] == 2
    assert abs(payload["confidence"] - 0.9) < 1e-6


# ------------------------------------------------------------------------------
# TESTE 3 — respeita MESSAGE_INTERVAL
# ------------------------------------------------------------------------------

def test_loop_respects_message_interval(agentA, monkeypatch):
    cap = mock()
    when(agentA_module).RTSPStream(...).thenReturn(cap)

    when(cap).read().thenReturn("f1").thenReturn("f2").thenReturn("f3").thenReturn(None)

    results = mock()
    when(agentA.yolo).detect(any_).thenReturn(results)

    when(agentA.yolo).truck_found(results).thenReturn(True).thenReturn(True).thenReturn(True)
    when(agentA.yolo).get_boxes(results).thenReturn([[0, 0, 1, 1, 0.8]])

    monkeypatch.setattr(agentA_module, "MESSAGE_INTERVAL", 9999)

    def stopper():
        time.sleep(0.2)
        agentA.stop()

    threading.Thread(target=stopper, daemon=True).start()
    agentA._loop()

    verify(agentA.producer, times=1).produce(...)


# ------------------------------------------------------------------------------
# TESTE 4 — não publica quando não há camião
# ------------------------------------------------------------------------------

def test_loop_no_truck(agentA, monkeypatch):
    cap = mock()
    when(agentA_module).RTSPStream(...).thenReturn(cap)

    when(cap).read().thenReturn("f1").thenReturn("f2").thenReturn(None)

    results = mock()
    when(agentA.yolo).detect(any_).thenReturn(results)
    when(agentA.yolo).truck_found(results).thenReturn(False).thenReturn(False)

    monkeypatch.setattr(agentA_module, "MESSAGE_INTERVAL", 0)

    def stopper():
        time.sleep(0.2)
        agentA.stop()

    threading.Thread(target=stopper, daemon=True).start()
    agentA._loop()

    verify(agentA.producer, times=0).produce(...)


# ------------------------------------------------------------------------------
# TESTE 5 — stop + flush
# ------------------------------------------------------------------------------

def test_stop_and_flush(agentA):
    cap = mock()
    when(agentA_module).RTSPStream(...).thenReturn(cap)

    when(cap).read().thenReturn("f1").thenReturn(None)

    results = mock()
    when(agentA.yolo).detect(any_).thenReturn(results)
    when(agentA.yolo).truck_found(results).thenReturn(False)

    def stopper():
        time.sleep(0.1)
        agentA.stop()

    threading.Thread(target=stopper, daemon=True).start()
    agentA._loop()

    verify(agentA.producer, times=1).flush(10)
    verify(cap, times=1).release()
