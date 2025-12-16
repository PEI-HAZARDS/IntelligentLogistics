import cv2
import numpy as np
import logging

logger = logging.getLogger("PlateClassifier")


class PlateClassifier:
    """
    Classifica crops de placas em:
    - LICENSE_PLATE: Matrícula (branco/amarelo, retângulo horizontal)
    - HAZARD_PLATE: Placa de perigo (laranja/vermelho, losango/retângulo vertical)
    """

    LICENSE_PLATE = "license_plate"
    HAZARD_PLATE = "hazard_plate"
    UNKNOWN = "unknown"

    def __init__(self):
        # Thresholds para classificação
        # Matrículas são largas (width/height > 1.8)
        self.min_aspect_ratio_license = 1.5
        self.max_aspect_ratio_hazard = 1.2   # Placas de perigo são quadradas/verticais

        # Ranges de cor HSV
        # Branco/Amarelo (matrículas)
        self.license_plate_colors = [
            # Branco
            ([0, 0, 200], [180, 30, 255]),
            # Amarelo
            ([20, 100, 100], [30, 255, 255])
        ]

        # Laranja/Vermelho (placas de perigo)
        self.hazard_plate_colors = [
            # Laranja
            ([10, 100, 100], [20, 255, 255]),
            # Vermelho (parte 1)
            ([0, 100, 100], [10, 255, 255]),
            # Vermelho (parte 2)
            ([170, 100, 100], [180, 255, 255])
        ]

    def classify(self, crop: np.ndarray) -> str:
        """
        Classifica o crop como LICENSE_PLATE ou HAZARD_PLATE.

        Args:
            crop: Imagem BGR do crop

        Returns:
            str: LICENSE_PLATE, HAZARD_PLATE ou UNKNOWN
        """
        if crop is None or crop.size == 0:
            return self.UNKNOWN

        height, width = crop.shape[:2]

        if height == 0 or width == 0:
            return self.UNKNOWN

        # 1. Análise de Forma (Aspect Ratio)
        aspect_ratio = width / height

        #logger.debug(f"[Classifier] Aspect ratio: {aspect_ratio:.2f}")

        # 2. Análise de Cor Dominante
        color_score = self._analyze_colors(crop)

        #logger.debug(
        #    f"[Classifier] Color scores - License: {color_score['license']:.2f}, "
        #    f"Hazard: {color_score['hazard']:.2f}"
        #)

        # 3. Classificação por Regras

        # Matrículas: Largas E cores branco/amarelo
        if aspect_ratio >= self.min_aspect_ratio_license:
            if color_score['license'] > color_score['hazard']:
                return self.LICENSE_PLATE

        # Placas de perigo: Quadradas/Verticais E cores laranja/vermelho
        if aspect_ratio <= self.max_aspect_ratio_hazard:
            if color_score['hazard'] > color_score['license']:
                return self.HAZARD_PLATE

        # Desempate apenas por cor se forma não for conclusiva
        if color_score['license'] > color_score['hazard'] * 1.5:
            return self.LICENSE_PLATE

        if color_score['hazard'] > color_score['license'] * 1.5:
            return self.HAZARD_PLATE

        #logger.warning(
        #    f"[Classifier] ❓ UNKNOWN classification (AR={aspect_ratio:.2f}, "
        #    f"License={color_score['license']:.2f}, Hazard={color_score['hazard']:.2f})"
        #)
        return self.UNKNOWN

    def _analyze_colors(self, crop: np.ndarray) -> dict:
        """
        Analisa a predominância de cores características.

        Returns:
            dict: {'license': score, 'hazard': score}
        """
        # Converter para HSV
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)

        # Calcular área total
        total_pixels = crop.shape[0] * crop.shape[1]

        # Score para cores de matrícula (branco/amarelo)
        license_pixels = 0
        for lower, upper in self.license_plate_colors:
            mask = cv2.inRange(hsv, np.array(lower), np.array(upper))
            license_pixels += cv2.countNonZero(mask)

        # Score para cores de placa de perigo (laranja/vermelho)
        hazard_pixels = 0
        for lower, upper in self.hazard_plate_colors:
            mask = cv2.inRange(hsv, np.array(lower), np.array(upper))
            hazard_pixels += cv2.countNonZero(mask)

        # Normalizar para 0-1
        license_score = license_pixels / total_pixels
        hazard_score = hazard_pixels / total_pixels

        return {
            'license': license_score,
            'hazard': hazard_score
        }

    def visualize_classification(self, crop: np.ndarray, classification: str,
                                 save_path: str = None) -> np.ndarray:
        """
        Cria visualização do crop com classificação.

        Args:
            crop: Imagem original
            classification: Resultado da classificação
            save_path: Caminho para salvar (opcional)

        Returns:
            np.ndarray: Imagem com overlay
        """
        # Fazer cópia
        vis = crop.copy()

        # Adicionar borda colorida
        if classification == self.LICENSE_PLATE:
            color = (0, 255, 0)  # Verde
            label = "LICENSE PLATE"
        elif classification == self.HAZARD_PLATE:
            color = (0, 0, 255)  # Vermelho
            label = "HAZARD PLATE"
        else:
            color = (128, 128, 128)  # Cinza
            label = "UNKNOWN"

        # Borda
        vis = cv2.copyMakeBorder(
            vis, 5, 5, 5, 5, cv2.BORDER_CONSTANT, value=color)

        # Texto
        cv2.putText(vis, label, (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                    0.7, color, 2, cv2.LINE_AA)

        # Salvar se solicitado
        if save_path:
            cv2.imwrite(save_path, vis)
            #logger.debug(f"[Classifier] Visualization saved: {save_path}")

        return vis
