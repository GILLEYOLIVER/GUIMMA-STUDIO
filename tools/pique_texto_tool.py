from __future__ import annotations

from math import sqrt

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QColorDialog,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from tools.tool_base import FerramentaBase
from ui.posicao_janelas import instalar_memoria_posicao, restaurar_posicao


class PiqueTextoDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PiqueTextoDialog")
        self.setWindowTitle("Texto do pique")
        self.setWindowFlags(Qt.Tool)
        self.setFixedWidth(286)
        self._remover = False
        self._cor = "#ffffff"

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(10, 10, 10, 10)
        raiz.setSpacing(8)

        titulo = QLabel("Anotação vinculada ao pique")
        titulo.setObjectName("titulo")
        raiz.addWidget(titulo)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(6)

        self.edt_texto = QLineEdit()
        self.edt_texto.setObjectName("texto")
        self.edt_texto.setPlaceholderText("Ex.: Meio, dobra, encaixe")
        form.addRow("Texto", self.edt_texto)

        self.spn_altura = self._spin(0.05, 10.0, 0.45, sufixo=" cm")
        self.spn_altura.setObjectName("altura")
        form.addRow("Altura", self.spn_altura)

        self.spn_dx = self._spin(-50.0, 50.0, 0.35, sufixo=" cm")
        self.spn_dx.setObjectName("dx")
        form.addRow("Desloc. X", self.spn_dx)

        self.spn_dy = self._spin(-50.0, 50.0, -0.35, sufixo=" cm")
        self.spn_dy.setObjectName("dy")
        form.addRow("Desloc. Y", self.spn_dy)
        raiz.addLayout(form)

        cor_linha = QHBoxLayout()
        cor_linha.setContentsMargins(0, 0, 0, 0)
        cor_linha.setSpacing(8)
        self.btn_cor = QPushButton("Cor")
        self.btn_cor.clicked.connect(self._escolher_cor)
        cor_linha.addWidget(QLabel("Cor"))
        cor_linha.addWidget(self.btn_cor, 1)
        raiz.addLayout(cor_linha)

        botoes = QHBoxLayout()
        botoes.setContentsMargins(0, 0, 0, 0)
        botoes.setSpacing(6)
        self.btn_remover = QPushButton("Remover")
        self.btn_cancelar = QPushButton("Cancelar")
        self.btn_aplicar = QPushButton("Aplicar")
        self.btn_aplicar.setDefault(True)
        self.btn_remover.clicked.connect(self._remover_texto)
        self.btn_cancelar.clicked.connect(self.reject)
        self.btn_aplicar.clicked.connect(self.accept)
        botoes.addWidget(self.btn_remover)
        botoes.addStretch(1)
        botoes.addWidget(self.btn_cancelar)
        botoes.addWidget(self.btn_aplicar)
        raiz.addLayout(botoes)

        self.setStyleSheet(
            """
            QDialog#PiqueTextoDialog { background:#eef7f9; }
            QLabel { color:#16202a; font-size:11px; }
            QLabel#titulo { font-weight:600; font-size:12px; }
            QLineEdit, QDoubleSpinBox {
                background:#ffffff;
                border:1px solid #aeb8c2;
                border-radius:3px;
                min-height:22px;
                padding:2px 4px;
                font-size:11px;
            }
            QPushButton {
                background:#f8fbfd;
                border:1px solid #aeb8c2;
                border-radius:4px;
                min-height:23px;
                padding:2px 10px;
                font-size:11px;
            }
            QPushButton:hover { background:#d9efff; border-color:#77a8cc; }
            QPushButton:pressed { background:#bfe3ff; }
            """
        )
        self._atualizar_botao_cor()

    def carregar(self, cfg: dict, cor_padrao: str) -> None:
        self._remover = False
        texto = str(cfg.get("texto_pique") or cfg.get("pique_texto") or cfg.get("texto") or "")
        self.edt_texto.setText(texto)
        self.spn_altura.setValue(self._float_cfg(cfg, ("texto_altura_cm", "altura_texto_cm"), 0.45))
        self.spn_dx.setValue(self._float_cfg(cfg, ("texto_dx_cm", "texto_offset_x_cm"), 0.35))
        self.spn_dy.setValue(self._float_cfg(cfg, ("texto_dy_cm", "texto_offset_y_cm"), -0.35))
        cor = str(cfg.get("texto_cor") or cor_padrao or "#ffffff")
        self._cor = QColor(cor).name() if QColor(cor).isValid() else "#ffffff"
        self._atualizar_botao_cor()
        self.edt_texto.selectAll()
        self.edt_texto.setFocus(Qt.OtherFocusReason)

    def valores(self) -> dict:
        return {
            "texto": self.edt_texto.text().strip(),
            "altura_cm": float(self.spn_altura.value()),
            "dx_cm": float(self.spn_dx.value()),
            "dy_cm": float(self.spn_dy.value()),
            "cor": self._cor,
            "remover": bool(self._remover),
        }

    def _remover_texto(self) -> None:
        self._remover = True
        self.accept()

    def _escolher_cor(self) -> None:
        cor = QColorDialog.getColor(QColor(self._cor), self, "Cor do texto do pique")
        if cor.isValid():
            self._cor = cor.name()
            self._atualizar_botao_cor()

    def _atualizar_botao_cor(self) -> None:
        cor = QColor(self._cor if QColor(self._cor).isValid() else "#ffffff")
        texto = "#ffffff" if cor.lightness() < 128 else "#16202a"
        self.btn_cor.setText(cor.name())
        self.btn_cor.setStyleSheet(
            f"background:{cor.name()}; color:{texto}; border:1px solid #7b8a99; border-radius:4px;"
        )

    @staticmethod
    def _spin(minimo: float, maximo: float, valor: float, *, sufixo: str = "") -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(float(minimo), float(maximo))
        spin.setDecimals(2)
        spin.setSingleStep(0.05)
        spin.setSuffix(sufixo)
        spin.setValue(float(valor))
        return spin

    @staticmethod
    def _float_cfg(cfg: dict, chaves: tuple[str, ...], padrao: float) -> float:
        for chave in chaves:
            try:
                valor = cfg.get(chave)
                if valor is not None:
                    return float(valor)
            except Exception:
                continue
        return float(padrao)


class Ferramenta(FerramentaBase):
    id_ferramenta = "pique_texto"
    nome = "Pique Texto"
    usa_painel_auxiliar = False
    descricao_painel = "Adiciona ou edita uma anotação presa ao pique selecionado."
    _dialog_global: PiqueTextoDialog | None = None

    def __init__(self):
        super().__init__()
        self._hover: tuple[int, int, QPointF] | None = None
        self._molde_idx: int | None = None

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self._hover = None
        self._molde_idx = None
        self._status(canvas, "Pique Texto: clique no molde e depois no pique para editar o texto. Direito finaliza.")
        canvas.update()

    def on_deactivate(self, canvas):
        self._hover = None
        self._molde_idx = None
        canvas.update()

    def on_mouse_move(self, canvas, event) -> bool:
        pos = self._posicao_cena(canvas, event)
        indices = {self._molde_idx} if self._molde_idx is not None else None
        self._hover = self._alvo_pique_config(canvas, pos, indices=indices)
        canvas.update()
        event.accept()
        return True

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() == Qt.RightButton:
            self._finalizar(canvas)
            event.accept()
            return True
        if event.button() != Qt.LeftButton:
            return False

        pos = self._posicao_cena(canvas, event)
        indices = {self._molde_idx} if self._molde_idx is not None else None
        alvo = self._alvo_pique_config(canvas, pos, indices=indices)
        if alvo is None and self._molde_idx is None:
            molde_idx = self._molde_em_posicao(canvas, pos)
            if molde_idx is not None:
                self._selecionar_molde(canvas, molde_idx)
                self._status(canvas, "Molde selecionado. Clique no pique que recebera o texto.")
                canvas.update()
                event.accept()
                return True
        if alvo is None:
            self._status(canvas, "Nenhum pique configurado encontrado no clique.")
            event.accept()
            return True

        if self._editar_texto_pique(canvas, alvo, pos):
            self._hover = alvo
            self._selecionar_molde(canvas, alvo[0])
            canvas.update()
            event.accept()
            return True

        event.accept()
        return True

    def on_paint_overlay(self, canvas, painter):
        if self._hover is None:
            return
        _idx, _cfg_idx, ponto = self._hover
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        cor = QColor(self._cor_realce_canvas(canvas))
        painter.setPen(QPen(cor, 2))
        tela = canvas._cena_para_tela(ponto) if hasattr(canvas, "_cena_para_tela") else ponto
        painter.drawEllipse(tela, 7, 7)
        painter.drawText(tela + QPointF(10.0, -8.0), "Aa")
        painter.restore()

    def _editar_texto_pique(self, canvas, alvo: tuple[int, int, QPointF], pos_clique: QPointF | None = None) -> bool:
        idx, cfg_idx, _ponto = alvo
        if not (0 <= idx < len(canvas.cena.elementos)):
            return False
        el = canvas.cena.elementos[idx]
        configs = el.get("piques_config", []) if isinstance(el, dict) else None
        if not isinstance(configs, list) or not (0 <= cfg_idx < len(configs)) or not isinstance(configs[cfg_idx], dict):
            return False

        dialog = self._dialogo(canvas)
        cor_padrao = self._cor_texto_canvas(canvas, el)
        dialog.carregar(configs[cfg_idx], cor_padrao)
        self._reposicionar_dialogo(canvas, dialog, pos_clique)
        if dialog.exec() != QDialog.Accepted:
            self._status(canvas, "Edicao do texto cancelada.")
            return True

        valores = dialog.valores()
        if valores.get("remover") or not valores.get("texto"):
            alterou = self._remover_texto_config(configs[cfg_idx])
            mensagem = "Texto do pique removido." if alterou else "Pique ja estava sem texto."
        else:
            alterou = self._aplicar_texto_config(configs[cfg_idx], valores)
            mensagem = "Texto do pique atualizado."

        if alterou and hasattr(canvas, "_registrar_historico"):
            canvas._registrar_historico()
        self._status(canvas, mensagem)
        return True

    def _dialogo(self, canvas) -> PiqueTextoDialog:
        cls = type(self)
        if cls._dialog_global is None:
            cls._dialog_global = PiqueTextoDialog(canvas)
            instalar_memoria_posicao(cls._dialog_global, "dialog:pique_texto")
        dialog = cls._dialog_global
        if dialog.parentWidget() is not canvas:
            dialog.setParent(canvas)
        return dialog

    def _reposicionar_dialogo(self, canvas, dialog: PiqueTextoDialog, pos_clique: QPointF | None) -> None:
        fallback = None
        if pos_clique is not None and hasattr(canvas, "_cena_para_tela") and hasattr(canvas, "mapToGlobal"):
            tela = canvas._cena_para_tela(pos_clique)
            fallback = canvas.mapToGlobal(QPoint(int(tela.x()) + 14, int(tela.y()) + 14))
        elif hasattr(canvas, "calcular_posicao_painel_auxiliar") and hasattr(canvas, "mapToGlobal"):
            pos = canvas.calcular_posicao_painel_auxiliar(dialog.width(), dialog.height(), abaixo_coordenadas=True)
            fallback = canvas.mapToGlobal(pos)
        restaurar_posicao(dialog, "dialog:pique_texto", fallback=fallback)

    @staticmethod
    def _aplicar_texto_config(cfg: dict, valores: dict) -> bool:
        antes = {
            chave: cfg.get(chave)
            for chave in ("texto_pique", "pique_texto", "texto", "texto_altura_cm", "texto_dx_cm", "texto_dy_cm", "texto_cor")
        }
        cfg.pop("pique_texto", None)
        if "texto" in cfg and str(cfg.get("texto") or "").strip() != str(valores.get("texto") or "").strip():
            cfg.pop("texto", None)
        cfg["texto_pique"] = str(valores.get("texto") or "").strip()
        cfg["texto_altura_cm"] = max(0.05, float(valores.get("altura_cm") or 0.45))
        cfg["texto_dx_cm"] = float(valores.get("dx_cm") or 0.0)
        cfg["texto_dy_cm"] = float(valores.get("dy_cm") or 0.0)
        cor = QColor(str(valores.get("cor") or "#ffffff"))
        cfg["texto_cor"] = cor.name() if cor.isValid() else "#ffffff"
        depois = {
            chave: cfg.get(chave)
            for chave in ("texto_pique", "pique_texto", "texto", "texto_altura_cm", "texto_dx_cm", "texto_dy_cm", "texto_cor")
        }
        return antes != depois

    @staticmethod
    def _remover_texto_config(cfg: dict) -> bool:
        alterou = False
        for chave in (
            "texto_pique",
            "pique_texto",
            "texto",
            "texto_altura_cm",
            "altura_texto_cm",
            "texto_dx_cm",
            "texto_dy_cm",
            "texto_offset_x_cm",
            "texto_offset_y_cm",
            "texto_cor",
        ):
            if chave in cfg:
                cfg.pop(chave, None)
                alterou = True
        return alterou

    def _alvo_pique_config(
        self,
        canvas,
        pos: QPointF,
        *,
        indices: set[int] | None = None,
    ) -> tuple[int, int, QPointF] | None:
        tolerancia = 14.0 / max(float(getattr(canvas, "zoom", 1.0)), 0.001)
        melhor: tuple[float, int, int, QPointF] | None = None
        for idx, el in enumerate(getattr(canvas.cena, "elementos", []) or []):
            if indices is not None and idx not in indices:
                continue
            if not isinstance(el, dict) or not el.get("molde"):
                continue
            for cfg_idx, cfg in enumerate(el.get("piques_config", []) or []):
                if not isinstance(cfg, dict):
                    continue
                ponto = self._ponto_pique_para_alvo(cfg)
                dist = self._dist(pos, ponto) if ponto is not None else float("inf")
                for segmento in cfg.get("segmentos", []) or []:
                    pts = self._segmento_cfg(segmento)
                    if pts is None:
                        continue
                    proj = self._projetar_ponto_segmento(pos, pts[0], pts[1])
                    dist_seg = self._dist(pos, proj)
                    if dist_seg < dist:
                        ponto = proj
                        dist = dist_seg
                if ponto is not None and dist <= tolerancia and (melhor is None or dist < melhor[0]):
                    melhor = (dist, idx, cfg_idx, QPointF(ponto))
        if melhor is None:
            return None
        _dist, idx, cfg_idx, ponto = melhor
        return idx, cfg_idx, ponto

    def _selecionar_molde(self, canvas, idx: int) -> None:
        self._molde_idx = int(idx)
        if hasattr(canvas, "_selecionados"):
            canvas._selecionados = {int(idx)}

    def _finalizar(self, canvas) -> None:
        self._hover = None
        self._molde_idx = None
        if hasattr(canvas, "set_ferramenta_ativa"):
            canvas.set_ferramenta_ativa("selecionar")
        else:
            canvas.update()
        self._status(canvas, "Ferramenta Pique Texto finalizada.")

    def _molde_em_posicao(self, canvas, pos: QPointF) -> int | None:
        if hasattr(canvas, "_indice_molde_em_ponto"):
            idx = canvas._indice_molde_em_ponto(pos)
            if idx is not None:
                return int(idx)
        for idx, el in enumerate(getattr(canvas.cena, "elementos", []) or []):
            if isinstance(el, dict) and el.get("molde") and self._ponto_dentro_bbox(el, pos):
                return idx
        return None

    def _posicao_cena(self, canvas, event) -> QPointF:
        try:
            return QPointF(canvas._ponto_com_snap(event.position()))
        except Exception:
            if hasattr(canvas, "_tela_para_cena"):
                return QPointF(canvas._tela_para_cena(event.position()))
            return QPointF(event.position())

    @staticmethod
    def _ponto_pique_para_alvo(cfg: dict) -> QPointF | None:
        ponto = Ferramenta._ponto_cfg(cfg)
        if ponto is not None:
            return ponto
        return Ferramenta._ponto_qt(cfg.get("ponto_controle"))

    @staticmethod
    def _ponto_cfg(cfg: dict) -> QPointF | None:
        try:
            return Ferramenta._ponto_qt(cfg.get("ponto"))
        except Exception:
            return None

    @staticmethod
    def _ponto_qt(valor) -> QPointF | None:
        try:
            if isinstance(valor, QPointF):
                return QPointF(valor)
            if isinstance(valor, dict):
                return QPointF(float(valor["x"]), float(valor["y"]))
            if isinstance(valor, (list, tuple)) and len(valor) >= 2:
                return QPointF(float(valor[0]), float(valor[1]))
        except Exception:
            return None
        return None

    @staticmethod
    def _tupla_ponto(valor) -> tuple[float, float] | None:
        try:
            if isinstance(valor, QPointF):
                return float(valor.x()), float(valor.y())
            if isinstance(valor, dict):
                return float(valor["x"]), float(valor["y"])
            if isinstance(valor, (list, tuple)) and len(valor) >= 2:
                return float(valor[0]), float(valor[1])
        except Exception:
            return None
        return None

    @staticmethod
    def _segmento_cfg(segmento) -> tuple[QPointF, QPointF] | None:
        try:
            if isinstance(segmento, dict):
                a = segmento.get("a") or segmento.get("inicio")
                b = segmento.get("b") or segmento.get("fim")
            elif isinstance(segmento, (list, tuple)) and len(segmento) >= 2:
                a, b = segmento[0], segmento[1]
            else:
                return None
            pa = Ferramenta._ponto_qt(a)
            pb = Ferramenta._ponto_qt(b)
            if pa is None or pb is None:
                return None
            return pa, pb
        except Exception:
            return None

    @staticmethod
    def _projetar_ponto_segmento(p: QPointF, a: QPointF, b: QPointF) -> QPointF:
        vx = b.x() - a.x()
        vy = b.y() - a.y()
        denom = (vx * vx) + (vy * vy)
        if denom <= 1e-12:
            return QPointF(a)
        t = ((p.x() - a.x()) * vx + (p.y() - a.y()) * vy) / denom
        t = max(0.0, min(1.0, t))
        return QPointF(a.x() + (vx * t), a.y() + (vy * t))

    def _ponto_dentro_bbox(self, molde: dict, pos: QPointF) -> bool:
        pontos = [pt for pt in (self._tupla_ponto(item) for item in molde.get("pontos", []) or []) if pt is not None]
        if not pontos:
            return False
        xs = [x for x, _y in pontos]
        ys = [y for _x, y in pontos]
        return min(xs) <= pos.x() <= max(xs) and min(ys) <= pos.y() <= max(ys)

    @staticmethod
    def _dist(a: QPointF, b: QPointF) -> float:
        return sqrt(((a.x() - b.x()) ** 2) + ((a.y() - b.y()) ** 2))

    @staticmethod
    def _cor_realce_canvas(canvas) -> str:
        try:
            cor = str(getattr(canvas, "_cores_canvas", {}).get("selecao", "#2da8ff"))
            return cor if QColor(cor).isValid() else "#2da8ff"
        except Exception:
            return "#2da8ff"

    @staticmethod
    def _cor_texto_canvas(canvas, molde: dict | None = None) -> str:
        candidatos = []
        if isinstance(molde, dict):
            candidatos.extend([molde.get("cor"), molde.get("cor_linha")])
        candidatos.append(getattr(canvas, "_linha_cor", None))
        candidatos.append("#ffffff")
        for valor in candidatos:
            cor = QColor(str(valor or ""))
            if cor.isValid():
                return cor.name()
        return "#ffffff"

    def _status(self, canvas, texto: str):
        self.set_status(texto)
        if getattr(canvas, "lbl_status", None) is not None:
            canvas.lbl_status.setText(texto)
