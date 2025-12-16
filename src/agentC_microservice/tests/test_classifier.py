"""
Script de teste para PlateClassifier.
Testa a classificação de crops em matrículas vs placas de perigo.
"""
from agentC_microservice.src.PlateClassifier import PlateClassifier
import cv2
import sys
import os

# Adicionar path
sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '../..')))


def test_classifier_with_images():
    """Testa classificador com imagens de exemplo."""
    classifier = PlateClassifier()

    # Imagens de teste (ajustar paths conforme necessário)
    test_images = [
        ("data/test_license_plate.jpg", "LICENSE_PLATE"),
        ("data/test_hazard_plate.jpg", "HAZARD_PLATE"),
    ]

    print("\n" + "="*60)
    print("🧪 Testing PlateClassifier")
    print("="*60 + "\n")

    for img_path, expected in test_images:
        if not os.path.exists(img_path):
            print(f"⚠️  Image not found: {img_path}")
            continue

        crop = cv2.imread(img_path)
        result = classifier.classify(crop)

        status = "✅" if result == expected else "❌"
        print(f"{status} {img_path}")
        print(f"   Result: {result.upper()}")
        print(f"   Expected: {expected}")

        # Salvar visualização
        vis_path = img_path.replace(".jpg", f"_classified_{result}.jpg")
        classifier.visualize_classification(crop, result, vis_path)
        print(f"   📁 Visualization saved: {vis_path}\n")


def test_synthetic_crops():
    """Testa com crops sintéticos."""
    import numpy as np

    classifier = PlateClassifier()

    print("\n" + "="*60)
    print("🧪 Testing with Synthetic Crops")
    print("="*60 + "\n")

    # 1. Matrícula simulada (branco, formato horizontal)
    license_crop = np.ones((100, 300, 3), dtype=np.uint8) * 255  # Branco
    result_license = classifier.classify(license_crop)
    print(f"1️⃣  White horizontal crop (3:1): {result_license.upper()}")
    print(f"   Expected: LICENSE_PLATE")
    print(f"   {'✅ PASS' if result_license == 'license_plate' else '❌ FAIL'}\n")

    # 2. Placa de perigo simulada (laranja, formato quadrado)
    hazard_crop = np.zeros((200, 200, 3), dtype=np.uint8)
    hazard_crop[:, :] = [0, 140, 255]  # BGR: Laranja
    result_hazard = classifier.classify(hazard_crop)
    print(f"2️⃣  Orange square crop (1:1): {result_hazard.upper()}")
    print(f"   Expected: HAZARD_PLATE")
    print(f"   {'✅ PASS' if result_hazard == 'hazard_plate' else '❌ FAIL'}\n")

    # 3. Crop amarelo horizontal (matrícula amarela)
    yellow_crop = np.zeros((80, 250, 3), dtype=np.uint8)
    yellow_crop[:, :] = [0, 255, 255]  # BGR: Amarelo
    result_yellow = classifier.classify(yellow_crop)
    print(f"3️⃣  Yellow horizontal crop (3.1:1): {result_yellow.upper()}")
    print(f"   Expected: LICENSE_PLATE")
    print(f"   {'✅ PASS' if result_yellow == 'license_plate' else '❌ FAIL'}\n")

    # 4. Crop vermelho vertical (placa de perigo)
    red_crop = np.zeros((300, 200, 3), dtype=np.uint8)
    red_crop[:, :] = [0, 0, 255]  # BGR: Vermelho
    result_red = classifier.classify(red_crop)
    print(f"4️⃣  Red vertical crop (1:1.5): {result_red.upper()}")
    print(f"   Expected: HAZARD_PLATE")
    print(f"   {'✅ PASS' if result_red == 'hazard_plate' else '❌ FAIL'}\n")


def main():
    """Executa todos os testes."""
    print("\n" + "🚀 Starting PlateClassifier Tests".center(60, "="))

    # Testes com crops sintéticos
    test_synthetic_crops()

    # Testes com imagens reais (se existirem)
    # test_classifier_with_images()

    print("\n" + "✅ Tests Complete".center(60, "=") + "\n")


if __name__ == "__main__":
    main()
