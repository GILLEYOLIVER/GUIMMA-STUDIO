from __future__ import annotations

from math import sqrt

from PySide6.QtCore import QPoint, QPointF, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen
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
from tools.dialog_lifetime import esconder_se_valido, limpar_global_ao_destruir, qobject_valido
from ui.posicao_janelas import instalar_memoria_posicao, restaurar_posicao


class PiqueTextoDialog(QDialog):
    alterado = Signal()

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
        self.btn_remover = QPushButton("Limpar")
        self.btn_cancelar = QPushButton("Cancelar")
        self.btn_aplicar = QPushButton("Aplicar")
        self.btn_aplicar.setDefault(True)
        self.btn_remover.clicked.connect(self._limpar_texto)
        self.btn_cancelar.clicked.connect(self.reject)
        self.btn_aplicar.clicked.connect(self.accept)
        botoes.addWidget(self.btn_remover)
        botoes.addStretch(1)
        botoes.addWidget(self.btn_cancelar)
        botoes.addWidget(self.btn_aplicar)
        raiz.addLayout(botoes)

        dica = QLabel("Digite o texto. Clique no molde para posicionar. Botão direito finaliza.")
        dica.setObjectName("dica")
        dica.setWordWrap(True)
        raiz.addWidget(dica)

        self.btn_cancelar.hide()
        self.btn_aplicar.hide()

        self.edt_texto.textChanged.connect(lambda _texto: self.alterado.emit())
        self.spn_altura.valueChanged.connect(lambda _valor: self.alterado.emit())
        self.spn_dx.valueChanged.connect(lambda _valor: self.alterado.emit())
        self.spn_dy.valueChanged.connect(lambda _valor: self.alterado.emit())

        self.setStyleSheet(
            """
            QDialog#PiqueTextoDialog { background:#eef7f9; }
            QLabel { color:#16202a; font-size:11px; }
            QLabel#titulo { font-weight:600; font-size:12px; }
            QLabel#dica { color:#4c5d6f; }
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

    def _limpar_texto(self) -> None:
        self._remover = False
        self.edt_texto.clear()
        self.edt_texto.setFocus(Qt.OtherFocusReason)
        self.alterado.emit()

    def _remover_texto(self) -> None:
        self._remover = True
        self.accept()

    def _escolher_cor(self) -> None:
        cor = QColorDialog.getColor(QColor(self._cor), self, "Cor do texto do pique")
        if cor.isValid():
            self._cor = cor.name()
            self._atualizar_botao_cor()
            self.alterado.emit()

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
        self._pos_mao: QPointF | None = None
        self._dialog: PiqueTextoDialog | None = type(self)._dialog_global

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self._hover = None
        self._molde_idx = None
        self._pos_mao = None
        self._abrir_dialogo(canvas)
        self._status(canvas, "Pique Texto: digite o texto, clique no molde para posicionar. Direito finaliza.")
        canvas.update()

    def on_deactivate(self, canvas):
        esconder_se_valido(self._dialog)
        self._hover = None
        self._molde_idx = None
        self._pos_mao = None
        canvas.update()

    def on_canvas_resize(self, canvas) -> None:
        if qobject_valido(self._dialog):
            self._reposicionar_dialogo(canvas, self._dialog, None)

    def on_mouse_move(self, canvas, event) -> bool:
        pos = self._posicao_cena_sem_snap(canvas, event)
        self._pos_mao = QPointF(pos)
        molde_idx = self._molde_idx
        if molde_idx is None or not self._ponto_em_molde_idx(canvas, molde_idx, pos):
            molde_idx = self._molde_em_posicao(canvas, pos)
        self._hover = (molde_idx, -1, QPointF(pos)) if molde_idx is not None else None
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

        pos = self._posicao_cena_sem_snap(canvas, event)
        self._pos_mao = QPointF(pos)
        valores = self._valores_dialogo(canvas)
        if not str(valores.get("texto") or "").strip():
            self._status(canvas, "Digite o texto antes de posicionar no molde.")
            event.accept()
            return True
        molde_idx = self._molde_idx
        if molde_idx is None or not self._ponto_em_molde_idx(canvas, molde_idx, pos):
            molde_idx = self._molde_em_posicao(canvas, pos)
        if molde_idx is None:
            self._status(canvas, "Clique dentro do molde para deixar o texto.")
            event.accept()
            return True
        self._selecionar_molde(canvas, molde_idx)
        if self._criar_texto_interno(canvas, molde_idx, pos, valores):
            canvas.update()
            event.accept()
            return True

        event.accept()
        return True

    def on_paint_overlay(self, canvas, painter):
        ponto = self._pos_mao
        if ponto is None and self._hover is not None:
            _idx, _cfg_idx, ponto = self._hover
        if ponto is None:
            return
        valores = self._valores_dialogo(canvas)
        texto = str(valores.get("texto") or "").strip()
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        cor = QColor(self._cor_realce_canvas(canvas))
        painter.setPen(QPen(cor, 2))
        tela = canvas._cena_para_tela(ponto) if hasattr(canvas, "_cena_para_tela") else ponto
        painter.drawEllipse(tela, 7, 7)
        if texto:
            self._desenhar_texto_em_mao(canvas, painter, valores, ponto)
        else:
            painter.drawText(tela + QPointF(10.0, -8.0), "Aa")
        painter.restore()

    def _editar_texto_pique(self, canvas, alvo: tuple[int, int, QPointF], pos_clique: QPointF | None = None) -> bool:
        idx, cfg_idx, _ponto = alvo
        if cfg_idx < 0:
            return self._criar_texto_interno(canvas, idx, pos_clique or _ponto)
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

    def _criar_texto_interno(self, canvas, idx: int, ponto: QPointF, valores: dict | None = None) -> bool:
        if not (0 <= idx < len(canvas.cena.elementos)):
            return False
        el = canvas.cena.elementos[idx]
        if not isinstance(el, dict) or not el.get("molde"):
            return False
        if not self._ponto_dentro_molde(el, ponto):
            self._status(canvas, "Pique texto interno so pode ser criado dentro do molde.")
            return True

        valores = dict(valores or self._valores_dialogo(canvas))
        texto = str(valores.get("texto") or "").strip()
        if valores.get("remover") or not texto:
            self._status(canvas, "Texto vazio: nenhum pique texto foi criado.")
            return True

        tupla = (float(ponto.x()), float(ponto.y()))
        cfg = {
            "ponto": tupla,
            "ponto_controle": tupla,
            "tipo": "Texto",
            "sobre_contorno": False,
            "adicionar_ponto_controle": True,
            "manter_distancia_tamanhos": True,
            "aplicar_todos_tamanhos": True,
            "texto_sem_marca": True,
            "segmentos": [],
        }
        self._aplicar_texto_config(cfg, valores)
        configs = [item for item in (el.get("piques_config", []) or []) if isinstance(item, dict)]
        configs.append(cfg)
        el["piques_config"] = configs
        el["mostrar_piques"] = True
        self._adicionar_ponto_controle_auxiliar(el, ponto)
        if hasattr(canvas, "_registrar_historico"):
            canvas._registrar_historico()
        self._hover = (idx, len(configs) - 1, QPointF(ponto))
        self._status(canvas, "Texto posicionado. Clique outro ponto ou botão direito para finalizar.")
        return True

    def _abrir_dialogo(self, canvas) -> None:
        dialog = self._dialogo(canvas)
        try:
            dialog.alterado.disconnect()
        except Exception:
            pass
        dialog.alterado.connect(lambda: canvas.update())
        if not dialog.isVisible():
            dialog.show()
        self._reposicionar_dialogo(canvas, dialog, None)
        dialog.edt_texto.setFocus(Qt.OtherFocusReason)

    def _dialogo(self, canvas) -> PiqueTextoDialog:
        cls = type(self)
        if not qobject_valido(cls._dialog_global):
            cls._dialog_global = PiqueTextoDialog(canvas)
            instalar_memoria_posicao(cls._dialog_global, "dialog:pique_texto")
            limpar_global_ao_destruir(cls._dialog_global, cls, "_dialog_global")
        dialog = cls._dialog_global
        if not qobject_valido(dialog):
            dialog = PiqueTextoDialog(canvas)
            cls._dialog_global = dialog
            instalar_memoria_posicao(dialog, "dialog:pique_texto")
            limpar_global_ao_destruir(dialog, cls, "_dialog_global")
        if dialog.parentWidget() is not canvas:
            dialog.setParent(canvas)
        self._dialog = dialog
        return dialog

    def _valores_dialogo(self, canvas) -> dict:
        dialog = self._dialog if qobject_valido(self._dialog) else self._dialogo(canvas)
        return dialog.valores()

    def _reposicionar_dialogo(self, canvas, dialog: PiqueTextoDialog, pos_clique: QPointF | None) -> None:
        fallback = None
        if hasattr(canvas, "calcular_posicao_painel_auxiliar") and hasattr(canvas, "mapToGlobal"):
            pos = canvas.calcular_posicao_painel_auxiliar(dialog.width(), dialog.height(), abaixo_coordenadas=True)
            fallback = canvas.mapToGlobal(pos)
        elif pos_clique is not None and hasattr(canvas, "_cena_para_tela") and hasattr(canvas, "mapToGlobal"):
            tela = canvas._cena_para_tela(pos_clique)
            fallback = canvas.mapToGlobal(QPoint(int(tela.x()) + 14, int(tela.y()) + 14))
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
        self._pos_mao = None
        esconder_se_valido(self._dialog)
        if hasattr(canvas, "set_ferramenta_ativa"):
            canvas.set_ferramenta_ativa("selecionar")
        else:
            canvas.update()
        self._status(canvas, "Ferramenta Pique Texto finalizada.")

    def _desenhar_texto_em_mao(self, canvas, painter: QPainter, valores: dict, ponto: QPointF) -> None:
        texto = str(valores.get("texto") or "").strip()
        if not texto:
            return
        try:
            altura_cm = max(0.05, float(valores.get("altura_cm") or 0.45))
        except Exception:
            altura_cm = 0.45
        try:
            dx_cm = float(valores.get("dx_cm") or 0.0)
            dy_cm = float(valores.get("dy_cm") or 0.0)
        except Exception:
            dx_cm = dy_cm = 0.0
        pos_texto = QPointF(ponto.x() + dx_cm, ponto.y() + dy_cm)
        tela = canvas._cena_para_tela(pos_texto) if hasattr(canvas, "_cena_para_tela") else pos_texto
        cor = QColor(str(valores.get("cor") or "#ffffff"))
        if not cor.isValid():
            cor = QColor("#ffffff")
        fonte = painter.font()
        fonte.setBold(False)
        if hasattr(canvas, "_tamanho_texto_cm_para_px"):
            tamanho_px = canvas._tamanho_texto_cm_para_px(altura_cm, minimo_px=7.0, maximo_px=96.0)
        else:
            tamanho_px = max(7.0, min(96.0, altura_cm * max(float(getattr(canvas, "zoom", 20.0)), 1.0)))
        fonte.setPixelSize(int(round(tamanho_px)))
        painter.setFont(fonte)
        metrics = QFontMetrics(painter.font())
        linhas = texto.splitlines() or [texto]
        largura = max(metrics.horizontalAdvance(linha) for linha in linhas) + 10
        altura = (metrics.height() * len(linhas)) + 4
        rect = tela.x() - (largura / 2.0), tela.y() - (altura / 2.0), largura, altura
        halo = QColor("#000000" if cor.lightness() > 140 else "#ffffff")
        halo.setAlpha(165)
        painter.setPen(QPen(halo, 1.0))
        for ox, oy in ((-1.0, 0.0), (1.0, 0.0), (0.0, -1.0), (0.0, 1.0)):
            painter.drawText(int(rect[0] + ox), int(rect[1] + oy), int(rect[2]), int(rect[3]), Qt.AlignCenter, texto)
        painter.setPen(QPen(cor, 1.0))
        painter.drawText(int(rect[0]), int(rect[1]), int(rect[2]), int(rect[3]), Qt.AlignCenter, texto)

    def _ponto_em_molde_idx(self, canvas, idx: int | None, pos: QPointF) -> bool:
        if idx is None:
            return False
        try:
            el = canvas.cena.elementos[int(idx)]
        except Exception:
            return False
        return isinstance(el, dict) and el.get("molde") and self._ponto_dentro_molde(el, pos)

    def _molde_em_posicao(self, canvas, pos: QPointF) -> int | None:
        if hasattr(canvas, "_indice_molde_em_ponto"):
            idx = canvas._indice_molde_em_ponto(pos)
            if idx is not None:
                return int(idx)
        for idx, el in enumerate(getattr(canvas.cena, "elementos", []) or []):
            if isinstance(el, dict) and el.get("molde") and self._ponto_dentro_molde(el, pos):
                return idx
        return None

    def _ponto_dentro_molde(self, molde: dict, pos: QPointF) -> bool:
        poligono = [self._tupla_ponto(item) for item in molde.get("pontos", []) or []]
        poligono = [p for p in poligono if p is not None]
        if len(poligono) < 3:
            return self._ponto_dentro_bbox(molde, pos)
        return self._ponto_dentro_ou_na_borda((float(pos.x()), float(pos.y())), poligono)

    def _ponto_dentro_ou_na_borda(self, ponto: tuple[float, float], poligono: list[tuple[float, float]], tol: float = 1e-6) -> bool:
        px, py = ponto
        pts = list(poligono)
        if len(pts) >= 2 and self._dist_tuple(pts[0], pts[-1]) > tol:
            pts.append(pts[0])
        for a, b in zip(pts, pts[1:]):
            if self._dist_ponto_segmento_tuple(ponto, a, b) <= tol:
                return True
        dentro = False
        j = len(pts) - 1
        for i in range(len(pts)):
            xi, yi = pts[i]
            xj, yj = pts[j]
            cruza = (yi > py) != (yj > py)
            if cruza:
                den = yj - yi
                if abs(den) <= 1e-12:
                    den = 1e-12
                x_inter = ((xj - xi) * (py - yi) / den) + xi
                if px < x_inter:
                    dentro = not dentro
            j = i
        return dentro

    def _adicionar_ponto_controle_auxiliar(self, el: dict, ponto: QPointF) -> None:
        novo = (float(ponto.x()), float(ponto.y()))
        auxiliares = []
        for item in el.get("controle_auxiliares", []) or []:
            pt = self._tupla_ponto(item)
            if pt is not None:
                auxiliares.append(pt)
        if not any(self._dist_tuple(novo, item) <= 1e-6 for item in auxiliares):
            auxiliares.append(novo)
        el["controle_auxiliares"] = auxiliares
        el["pontos_auxiliares"] = [{"x": float(x), "y": float(y)} for x, y in auxiliares]

    def _posicao_cena(self, canvas, event) -> QPointF:
        try:
            return QPointF(canvas._ponto_com_snap(event.position()))
        except Exception:
            if hasattr(canvas, "_tela_para_cena"):
                return QPointF(canvas._tela_para_cena(event.position()))
            return QPointF(event.position())

    def _posicao_cena_sem_snap(self, canvas, event) -> QPointF:
        try:
            if hasattr(canvas, "_tela_para_cena"):
                return QPointF(canvas._tela_para_cena(event.position()))
        except Exception:
            pass
        try:
            return QPointF(event.position())
        except Exception:
            return self._posicao_cena(canvas, event)

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
    def _dist_tuple(a: tuple[float, float], b: tuple[float, float]) -> float:
        return sqrt(((float(a[0]) - float(b[0])) ** 2) + ((float(a[1]) - float(b[1])) ** 2))

    @staticmethod
    def _dist_ponto_segmento_tuple(p: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
        px, py = p
        ax, ay = a
        bx, by = b
        vx = bx - ax
        vy = by - ay
        denom = (vx * vx) + (vy * vy)
        if denom <= 1e-12:
            return sqrt(((px - ax) ** 2) + ((py - ay) ** 2))
        t = ((px - ax) * vx + (py - ay) * vy) / denom
        t = max(0.0, min(1.0, t))
        qx = ax + (vx * t)
        qy = ay + (vy * t)
        return sqrt(((px - qx) ** 2) + ((py - qy) ** 2))

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
