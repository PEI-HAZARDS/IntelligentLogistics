import sys
from pathlib import Path
import json
import time
import threading
import pytest
import types
import numpy as np
from mockito import when, verify, mock, unstub, any_, captor

TESTS_DIR = Path(__file__).resolve().parent
MICROSERVICE_ROOT = TESTS_DIR.parent
GLOBAL_SRC = MICROSERVICE_ROOT.parent

sys.path.insert(0, str(MICROSERVICE_ROOT / "src"))
sys.path.insert(0, str(GLOBAL_SRC))

if "ultralytics" not in sys.modules:
    ultralytics_stub = types.ModuleType("ultralytics")

    class YOLOStub:
        def __init__(self, *args, **kwargs):
            pass

    ultralytics_stub.YOLO = YOLOStub
    sys.modules["ultralytics"] = ultralytics_stub

import AgentB as agentB_module


@pytest.fixture
def agentB():
    producer = mock()
    when(agentB_module).Producer(...).thenReturn(producer)

    consumer = mock()
    when(agentB_module).Consumer(...).thenReturn(consumer)

    yolo = mock()
    when(agentB_module).YOLO_License_Plate(...).thenReturn(yolo)

    ocr = mock()
    when(agentB_module).OCR(...).thenReturn(ocr)

    stream = mock()
    when(agentB_module).RTSPStream(...).thenReturn(stream)

    agent = agentB_module.AgentB(kafka_bootstrap="localhost:9092")
    agent.producer = producer
    agent.consumer = consumer
    agent.yolo = yolo
    agent.ocr = ocr
    agent.stream = stream

    yield agent
    unstub()


def test_publish_lp_detected(agentB):
    val_cap = captor()
    headers_cap = captor()

    agentB._publish_lp_detected(
        timestamp="2025-01-01T10:00:00Z",
        truck_id="TRK123",
        plate_text="AB12CD",
        plate_conf=0.88
    )

    verify(agentB.producer, times=1).produce(
        topic="license-plate-detected",
        key=None,
        value=val_cap,
        headers=headers_cap,
    )

    payload = json.loads(val_cap.value.decode("utf-8"))
    assert payload["licensePlate"] == "AB12CD"
    assert abs(payload["confidence"] - 0.88) < 1e-6
    assert payload["timestamp"] == "2025-01-01T10:00:00Z"
    assert headers_cap.value["truckId"] == "TRK123"


def test_process_lp_detection(agentB):
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    when(agentB.stream).read().thenReturn(frame).thenReturn(None)

    results = mock()
    when(agentB.yolo).detect(any_).thenReturn(results)   # <- FIX AQUI
    when(agentB.yolo).found_license_plate(results).thenReturn(True)
    when(agentB.yolo).get_boxes(results).thenReturn([[10, 20, 60, 50, 0.9]])

    when(agentB.ocr)._extract_text(any_).thenReturn(("PORT1234", 0.95))

    text, conf, crop = agentB.process_license_plate_detection()

    assert text == "PORT1234"
    assert abs(conf - 0.95) < 1e-6
    assert crop is not None


def test_process_lp_no_detection(agentB):
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    when(agentB.stream).read().thenReturn(frame).thenReturn(None)

    results = mock()
    when(agentB.yolo).detect(any_).thenReturn(results)   # <- FIX AQUI TAMBÉM
    when(agentB.yolo).found_license_plate(results).thenReturn(False)

    text, conf, crop = agentB.process_license_plate_detection()

    assert text is None
    assert conf is None
    assert crop is None


def test_main_loop_publish(agentB):
    msg = mock()
    payload = {"timestamp": "NOW"}

    when(msg).value().thenReturn(json.dumps(payload).encode("utf-8"))
    when(msg).error().thenReturn(False)
    when(msg).headers().thenReturn([("truckId", b"TRK999")])

    when(agentB.consumer).poll(timeout=1.0).thenReturn(msg).thenReturn(None)

    when(agentB).process_license_plate_detection().thenReturn(("PLT1234", 0.77, object()))

    def stopper():
        time.sleep(0.2)
        agentB.stop()

    threading.Thread(target=stopper, daemon=True).start()
    agentB._loop()

    verify(agentB.producer, times=1).produce(
        topic="license-plate-detected",
        key=None,
        value=any_,
        headers={"truckId": "TRK999"}
    )


def test_main_loop_no_plate(agentB):
    msg = mock()
    payload = {"timestamp": "NOW"}

    when(msg).value().thenReturn(json.dumps(payload).encode("utf-8"))
    when(msg).error().thenReturn(False)
    when(msg).headers().thenReturn([("truckId", b"TRK999")])

    when(agentB.consumer).poll(timeout=1.0).thenReturn(msg).thenReturn(None)

    when(agentB).process_license_plate_detection().thenReturn((None, None, None))

    def stopper():
        time.sleep(0.2)
        agentB.stop()

    threading.Thread(target=stopper, daemon=True).start()
    agentB._loop()

    verify(agentB.producer, times=0).produce(...)


def test_stop(agentB):
    agentB.stop()
    assert agentB.running is False
