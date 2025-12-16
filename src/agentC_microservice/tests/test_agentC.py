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

import AgentC as agentC_module


@pytest.fixture
def agentC():
    producer = mock()
    when(agentC_module).Producer(...).thenReturn(producer)

    consumer = mock()
    when(agentC_module).Consumer(...).thenReturn(consumer)

    yolo = mock()
    when(agentC_module).YOLO_Hazard_Plate(...).thenReturn(yolo)

    ocr = mock()
    when(agentC_module).OCR(...).thenReturn(ocr)

    stream = mock()
    when(agentC_module).RTSPStream(...).thenReturn(stream)

    classifier = mock()
    when(agentC_module).PlateClassifier(...).thenReturn(classifier)

    agent = agentC_module.AgentC()
    agent.producer = producer
    agent.consumer = consumer
    agent.yolo = yolo
    agent.ocr = ocr
    agent.stream = stream
    agent.classifier = classifier

    yield agent
    unstub()


def test_publish_hz_detected(agentC):
    val_cap = captor()
    headers_cap = captor()

    agentC._publish_hz_detected(
        truck_id="TRK123",
        plate_text="AB12CD",
        plate_conf=0.88,
        crop_url="http://minio/crop.jpg"
    )

    verify(agentC.producer, times=1).produce(
        topic="hz-results-gate01",  # Assuming default GATE_ID is gate01
        key=None,
        value=val_cap,
        headers=headers_cap,
        callback=any_
    )

    payload = json.loads(val_cap.value.decode("utf-8"))
    assert payload["hazardPlate"] == "AB12CD"
    assert abs(payload["confidence"] - 0.88) < 1e-6
    assert "timestamp" in payload
    assert payload["cropUrl"] == "http://minio/crop.jpg"
    assert headers_cap.value["truckId"] == "TRK123"


def test_process_hazard_plate_detection(agentC):
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    when(agentC.stream).read().thenReturn(frame).thenReturn(None)

    results = mock()
    when(agentC.yolo).detect(any_).thenReturn(results)
    when(agentC.yolo).found_hazard_plate(results).thenReturn(True)
    when(agentC.yolo).get_boxes(results).thenReturn([[10, 20, 60, 50, 0.9]])

    when(agentC.ocr)._extract_text(any_).thenReturn(("PORT1234", 0.95))

    text, conf, crop = agentC.process_hazard_plate_detection("TRK123")

    assert text == "PORT1234"
    assert abs(conf - 1.0) < 1e-6 # Consensus returns 1.0 confidence
    assert crop is not None


def test_process_hazard_plate_no_detection(agentC):
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    when(agentC.stream).read().thenReturn(frame).thenReturn(None)

    results = mock()
    when(agentC.yolo).detect(any_).thenReturn(results)
    when(agentC.yolo).found_hazard_plate(results).thenReturn(False)

    text, conf, crop = agentC.process_hazard_plate_detection("TRK123")

    assert text is None
    assert conf is None
    assert crop is None


def test_main_loop_publish(agentC):
    msg = mock()
    payload = {"timestamp": "NOW"}

    when(msg).value().thenReturn(json.dumps(payload).encode("utf-8"))
    when(msg).error().thenReturn(False)
    when(msg).headers().thenReturn([("truckId", b"TRK999")])
    when(msg).topic().thenReturn("topic")
    when(msg).partition().thenReturn(0)
    when(msg).offset().thenReturn(0)

    when(agentC.consumer).poll(timeout=any_).thenReturn(msg).thenReturn(None)

    # Mock process_hazard_plate_detection to return a result
    when(agentC).process_hazard_plate_detection("TRK999").thenReturn(("PLT1234", 0.77, np.zeros((10,10,3), dtype=np.uint8)))
    
    # Mock crop storage upload
    when(agentC.crop_storage).upload_memory_image(any_, any_).thenReturn("http://minio/p.jpg")

    def stopper():
        time.sleep(0.5)
        agentC.stop()

    threading.Thread(target=stopper, daemon=True).start()
    agentC._loop()

    verify(agentC.producer, atLeast=1).produce(
        topic="hz-results-gate01",
        key=None,
        value=any_,
        headers={"truckId": "TRK999"},
        callback=any_
    )


def test_main_loop_no_plate(agentC):
    msg = mock()
    payload = {"timestamp": "NOW"}

    when(msg).value().thenReturn(json.dumps(payload).encode("utf-8"))
    when(msg).error().thenReturn(False)
    when(msg).headers().thenReturn([("truckId", b"TRK999")])
    when(msg).topic().thenReturn("topic")
    when(msg).partition().thenReturn(0)
    when(msg).offset().thenReturn(0)

    when(agentC.consumer).poll(timeout=any_).thenReturn(msg).thenReturn(None)

    when(agentC).process_hazard_plate_detection("TRK999").thenReturn((None, None, None))
    
    # Expect empty message publication
    # self._publish_hz_detected(truck_id, "N/A", -1, None)

    def stopper():
        time.sleep(0.5)
        agentC.stop()

    threading.Thread(target=stopper, daemon=True).start()
    agentC._loop()

    verify(agentC.producer, atLeast=1).produce(
        topic="hz-results-gate01",
        key=None,
        value=any_,  # We can check specific value if needed, but it should be the empty payload
        headers={"truckId": "TRK999"},
        callback=any_
    )


def test_stop(agentC):
    agentC.stop()
    assert agentC.running is False
