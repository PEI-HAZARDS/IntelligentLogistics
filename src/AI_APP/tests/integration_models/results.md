## License PLate Tests

```
PYTHONPATH=src uv run --active pytest -q \
  src/AI_APP/tests/integration_models/plate_classifier_integration_test.py \
  -m integration_model --plate-type license_plate \
  --crops-dir ../Crops_Images/finalCrops/licence_plate_crops
```

==================================================
  Expected type : license_plate
  Total crops   : 340
  Correct       : 338
  Wrong         : 2
  Accuracy      : 99.4%
  Counts        : license=338  hazard=2  unknown=0
==================================================

  Misclassified:
    - SB90TZI.png  AR=1.78  got=hazard_plate
    - SB90TZI_1.png  AR=1.85  got=hazard_plate



## Hazard PLate Tests


```
PYTHONPATH=src uv run --active pytest -q \
  src/AI_APP/tests/integration_models/plate_classifier_integration_test.py \
  -m integration_model --plate-type hazard_plate \
  --crops-dir ../Crops_Images/finalCrops/hazardCrops
```

==================================================
  Expected type : hazard_plate
  Total crops   : 155
  Correct       : 154
  Wrong         : 1
  Accuracy      : 99.4%
  Counts        : license=1  hazard=154  unknown=0
==================================================

  Misclassified:
    - crop_0_0_tanker_0-7308967113494873_png.rf.c6zhHUoauB7QJAaqu4WI.png  AR=1.26  got=license_plate


## Others
# Ter em conta que este de others não deve aparecer pois os modelos n costumam detetar isto é so mais informativo para perceber como isto funciona


```
PYTHONPATH=src uv run --active pytest -q \
  src/AI_APP/tests/integration_models/plate_classifier_integration_test.py \
  -m integration_model --plate-type unknown --min-expected-rate 1 \
  --crops-dir ../Crops_Images/finalCrops/otherCrops
```

==================================================
  Expected type : unknown
  Total crops   : 86
  Correct       : 66
  Wrong         : 20
  Accuracy      : 76.7%
  Counts        : license=0  hazard=20  unknown=66
==================================================

  Misclassified:
    - crop_1_0_tanker_0-5207744240760803_png.rf.qNybt6HbvGtv9kS1NWnL.png  AR=0.88  got=hazard_plate
    - crop_1_0_tanker_0-5292884111404419_png.rf.h4sgtUlVnPfJYsjAN5JI.png  AR=0.97  got=hazard_plate
    - crop_1_0_tanker_0-6748788356781006_png.rf.flEZtzinBebNVRKCGYGO.png  AR=0.78  got=hazard_plate
    - crop_1_0_tanker_0-789738655090332_png.rf.hSx86edEvHXAvNRDv86I.png  AR=0.76  got=hazard_plate
    - crop_1_0_tanker_0-8250750303268433_png.rf.t5jaeoji81SzltPcf9WB.png  AR=0.70  got=hazard_plate
    - crop_1_0_tanker_0-8377646207809448_png.rf.cvyRf4QM0vGtTQsJaCCF.png  AR=0.98  got=hazard_plate
    - crop_1_0_tanker_0-8609169721603394_png.rf.qLuO5No0V5a1j6GUijHZ.png  AR=0.87  got=hazard_plate
    - crop_1_0_tanker_0-8723387122154236_png.rf.DkE90xlKwtoCmzlCSw0K.png  AR=0.96  got=hazard_plate
    - crop_1_0_tanker_0-8949535489082336_png.rf.VOUm63npqrQnUqhOJOqz.png  AR=0.96  got=hazard_plate
    - crop_1_0_tanker_0-8958755731582642_png.rf.5laoU7dzXo6nIK7qdV86.png  AR=0.82  got=hazard_plate
    - crop_1_0_tanker_0-9058094024658203_png.rf.WK8iiEUAJZTW2mjsPPny.png  AR=0.96  got=hazard_plate
    - crop_1_0_tanker_0-9119629859924316_png.rf.HH7z0fzejx3P3Ox846Z3.png  AR=0.88  got=hazard_plate
    - crop_1_0_tanker_0-916267991065979_png.rf.6prszBX61FZc5dpAise9.png  AR=0.96  got=hazard_plate
    - crop_1_1_tanker_0-789738655090332_png.rf.hSx86edEvHXAvNRDv86I.png  AR=0.80  got=hazard_plate
    - crop_1_1_tanker_0-7956956624984741_png.rf.lX8a9U5z3quWCMdHBJk8.png  AR=0.98  got=hazard_plate
    - crop_1_1_tanker_0-8466237783432007_png.rf.GXPtAe2pJ09poDyAZbbB.png  AR=0.96  got=hazard_plate
    - crop_1_1_tanker_0-8503293991088867_png.rf.mN0b9MJFXe4Ftghw7PBD.png  AR=0.90  got=hazard_plate
    - crop_1_1_tanker_0-8845526576042175_png.rf.FOmoXlFlbdHZoKTcx4Rz.png  AR=0.50  got=hazard_plate
    - crop_1_2_tanker_0-6509631872177124_png.rf.V38lg2aP9TG2q4cHAngt.png  AR=0.96  got=hazard_plate
    - crop_1_4_tanker_0-6748788356781006_png.rf.flEZtzinBebNVRKCGYGO.png  AR=0.49  got=hazard_plate