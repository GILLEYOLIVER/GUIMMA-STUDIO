from __future__ import annotations

import base64
from typing import Any


def vetorizar_preview_adsx(imagem_base64: str) -> dict[str, Any]:
    """
    Vetorização experimental de preview JPG do ADSX.
    Se OpenCV/numpy estiverem indisponíveis, retorna diagnóstico sem contornos.
    """
    relatorio: dict[str, Any] = {
        "origem": "adsx_preview_trace",
        "confianca": "baixa",
        "editavel": True,
        "requer_revisao_manual": True,
        "elementos": [],
        "mensagem": "Contornos gerados a partir de imagem de baixa resolução. Revise antes de usar.",
        "sucesso": False,
    }
    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore
    except Exception:
        relatorio["erro"] = "OpenCV/numpy indisponíveis para vetorização experimental."
        return relatorio

    try:
        bruto = base64.b64decode(imagem_base64 or "")
        arr = np.frombuffer(bruto, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            relatorio["erro"] = "Imagem preview inválida."
            return relatorio

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (3, 3), 0)
        _, thr = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        kernel = np.ones((2, 2), np.uint8)
        clean = cv2.morphologyEx(thr, cv2.MORPH_OPEN, kernel, iterations=1)
        clean = cv2.morphologyEx(clean, cv2.MORPH_CLOSE, kernel, iterations=1)

        contours, _ = cv2.findContours(clean, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        h, w = gray.shape[:2]
        area_img = float(max(w * h, 1))
        elementos: list[dict[str, Any]] = []
        for cnt in contours:
            area = float(cv2.contourArea(cnt))
            if area < max(80.0, area_img * 0.0002):
                continue
            per = float(cv2.arcLength(cnt, True))
            if per <= 0:
                continue
            approx = cv2.approxPolyDP(cnt, 0.0035 * per, True)
            if len(approx) < 5:
                continue
            x, y, cw, ch = cv2.boundingRect(approx)
            ratio = (cw * ch) / max(area, 1.0)
            if ratio > 25:  # provável texto/ruído comprido
                continue
            pontos = [(float(p[0][0]), float(p[0][1])) for p in approx]
            if len(pontos) < 5:
                continue
            if pontos[0] != pontos[-1]:
                pontos.append(pontos[0])
            elementos.append(
                {
                    "tipo": "polyline",
                    "pontos": pontos,
                    "origem": "adsx_preview_trace",
                    "confianca": "baixa",
                    "editavel": True,
                    "requer_revisao_manual": True,
                    "cor": "#72d6ff",
                }
            )
        relatorio["elementos"] = elementos
        relatorio["sucesso"] = bool(elementos)
        return relatorio
    except Exception as exc:
        relatorio["erro"] = str(exc)
        return relatorio
