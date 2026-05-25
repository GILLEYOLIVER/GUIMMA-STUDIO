from __future__ import annotations

from copy import deepcopy
from math import hypot
from typing import Any

from PySide6.QtCore import QPoint, QPointF, Qt, QEvent
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
)

from core.geometry.engine import point_segment_distance, sample_quadratic_bezier_through_point
from tools.preview_original_utils import desenhar_elementos_originais
from tools.tool_base import FerramentaBase
from ui.posicao_janelas import restaurar_posicao, salvar_posicao

try:
    from tools.painel_ferramenta import PainelFerramentaBasico
except Exception:  # pragma: no cover
    PainelFerramentaBasico = None  # type: ignore[assignment]


class _PainelEditarPontosCurva(QFrame):
    """Caixa única da ferramenta, sem criar o painel auxiliar padrão."""

    OBJETO = "PainelEditarPontosCurvaUnico"

    def __init__(self, ferramenta: "Ferramenta", canvas):
        super().__init__(canvas)
        self.ferramenta = ferramenta
        self.canvas = canvas
        self._arrastando = False
        self._offset = QPoint(0, 0)
        self.setObjectName(self.OBJETO)
        self.setWindowFlags(Qt.Widget)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setFixedWidth(318)
        self.setMouseTracking(True)
        self._chave_posicao = "painel:editar_pontos_de_curva"
        self.setStyleSheet(
            """
            QFrame#PainelEditarPontosCurvaUnico {
                background: #ffffff;
                border: 1px solid #cfd8e3;
                border-radius: 10px;
            }
            QLabel { color:#1f2937; font-size:12px; }
            QLabel#TituloEditarPontosCurva {
                color:#111827;
                background:#eef2f7;
                font-size:15px;
                font-weight:700;
                padding:5px 7px;
                border-radius:5px;
            }
            QLabel#AjudaEditarPontosCurva {
                color:#64748b;
                font-size:11px;
                line-height:14px;
            }
            QSpinBox {
                background:#ffffff;
                color:#111827;
                border:1px solid #2f80ed;
                border-radius:6px;
                min-height:30px;
                padding:2px 8px;
                font-size:13px;
            }
            QPushButton {
                background:transparent;
                border:none;
                color:#334155;
                font-size:16px;
                border-radius:12px;
            }
            QPushButton:hover { background:#eef2f7; }
            """
        )

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(12, 10, 12, 12)
        raiz.setSpacing(8)

        topo = QHBoxLayout()
        topo.setContentsMargins(0, 0, 0, 0)
        topo.setSpacing(6)
        self.titulo = QLabel("Editar Pontos de Curva")
        self.titulo.setObjectName("TituloEditarPontosCurva")
        self.titulo.setToolTip("Arraste esta faixa para mover a caixa.")
        topo.addWidget(self.titulo, 1)
        fechar = QPushButton("×")
        fechar.setFixedSize(24, 24)
        fechar.setCursor(Qt.PointingHandCursor)
        fechar.clicked.connect(self.hide)
        topo.addWidget(fechar, 0)
        raiz.addLayout(topo)

        self.lbl_numero = QLabel("Número de pontos")
        raiz.addWidget(self.lbl_numero)

        self.spin = QSpinBox()
        self.spin.setRange(2, 300)
        self.spin.setKeyboardTracking(True)
        self.spin.setValue(5)
        self.spin.valueChanged.connect(self._valor_alterado)
        raiz.addWidget(self.spin)

        self.lbl_status = QLabel("✓ Clique em uma linha ou curva para editar")
        self.lbl_status.setStyleSheet("color:#15803d; font-size:11px;")
        self.lbl_status.setWordWrap(True)
        raiz.addWidget(self.lbl_status)

        linha = QFrame()
        linha.setFrameShape(QFrame.HLine)
        linha.setStyleSheet("background:#e2e8f0; max-height:1px;")
        raiz.addWidget(linha)

        ajuda = QLabel(
            "A linha selecionada fica azul e os pontos dela ficam vermelhos.\n"
            "Digite o número de pontos e a curva se ajusta na hora.\n"
            "Com 2 pontos vira reta; acima de 2 continua curva suave."
        )
        ajuda.setObjectName("AjudaEditarPontosCurva")
        ajuda.setWordWrap(True)
        raiz.addWidget(ajuda)

    def _valor_alterado(self, valor: int):
        self.ferramenta.definir_quantidade_pontos(int(valor), registrar=True)

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton and event.position().y() <= 42:
            self._arrastando = True
            self._offset = event.position().toPoint()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802
        if self._arrastando:
            novo = self.pos() + event.position().toPoint() - self._offset
            self.move(self._limitar(novo))
            self.ferramenta._painel_movido_usuario = True
            event.accept()
            return
        self.setCursor(Qt.OpenHandCursor if event.position().y() <= 42 else Qt.ArrowCursor)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton and self._arrastando:
            self._arrastando = False
            self.setCursor(Qt.OpenHandCursor)
            salvar_posicao(self, self._chave_posicao)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def hideEvent(self, event):  # noqa: N802
        salvar_posicao(self, self._chave_posicao)
        super().hideEvent(event)

    def _limitar(self, pos: QPoint) -> QPoint:
        parent = self.parentWidget()
        if parent is None:
            return pos
        margem = 8
        x = max(margem, min(pos.x(), max(margem, parent.width() - self.width() - margem)))
        y = max(margem, min(pos.y(), max(margem, parent.height() - self.height() - margem)))
        return QPoint(int(x), int(y))


class Ferramenta(FerramentaBase):
    id_ferramenta = "editar_pontos_de_curva"
    nome = "Editar Pontos de Curva"
    descricao_painel = ""
    usa_painel_auxiliar = False  # impede a caixa intrusa do FerramentaBase

    def __init__(self):
        super().__init__()
        self._canvas = None
        self._painel: _PainelEditarPontosCurva | None = None
        self._painel_movido_usuario = False
        self._idx_elemento: int | None = None
        self._arrastando: tuple[int, int] | None = None
        self._quantidade_pontos = 5
        self._pontos_exibidos: list[QPointF] = []
        self._ultima_pos_arraste: QPointF | None = None
        self._original_arraste: dict[int, dict] = {}

    def on_activate(self, canvas):
        # Não chama super().on_activate(canvas), porque ele cria o painel auxiliar intruso.
        self._canvas = canvas
        self._idx_elemento = None
        self._arrastando = None
        self._pontos_exibidos = []
        self._ultima_pos_arraste = None
        self._original_arraste = {}
        self._fechar_paineis_intrusos(canvas)
        self._mostrar_painel(canvas)
        self.set_status("Clique em uma linha ou curva para editar os pontos.")
        try:
            canvas.installEventFilter(self)
            canvas.update()
        except Exception:
            pass

    def on_deactivate(self, canvas):
        self._ocultar_painel()
        self._idx_elemento = None
        self._arrastando = None
        self._pontos_exibidos = []
        self._ultima_pos_arraste = None
        self._original_arraste = {}
        try:
            canvas.removeEventFilter(self)
            canvas.update()
        except Exception:
            pass

    def desativar(self):
        self._ocultar_painel()

    def set_status(self, texto: str):
        canvas = self._canvas
        try:
            lbl = getattr(canvas, "lbl_status", None)
            if lbl is not None:
                lbl.setText(texto)
        except Exception:
            pass

    def definir_quantidade_pontos(self, quantidade: int, registrar: bool = True):
        self._quantidade_pontos = max(2, min(300, int(quantidade or 2)))
        canvas = self._canvas
        if canvas is None or self._idx_elemento is None:
            self._atualizar_texto_painel()
            return
        if self._idx_elemento < 0 or self._idx_elemento >= len(canvas.cena.elementos):
            self._limpar_selecao(canvas)
            return
        el = canvas.cena.elementos[self._idx_elemento]
        if not self._elemento_editavel(el):
            return

        self._aplicar_quantidade_no_elemento(el, self._quantidade_pontos)
        self._pontos_exibidos = self._pontos_controle_do_elemento(el)
        self._atualizar_texto_painel()
        if registrar:
            self._registrar_historico_seguro(canvas)
            self._emitir_alteracao_segura(canvas)
        self.set_status(f"Curva ajustada para {self._quantidade_pontos} ponto(s).")
        canvas.update()

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() != Qt.LeftButton:
            return False
        pos = self._ponto_mouse_cena(canvas, event)

        alca = self._alca_em_ponto(canvas, pos)
        if alca is not None:
            self._arrastando = alca
            self._ultima_pos_arraste = QPointF(pos)
            idx_alca, _indice_alca = alca
            self._original_arraste = self._capturar_original_arraste(canvas, idx_alca)
            self.set_status("Arraste o ponto vermelho para ajustar a curva.")
            event.accept()
            return True

        idx = self._elemento_em_ponto(canvas, pos)
        if idx is None:
            self._limpar_selecao(canvas)
            self._atualizar_texto_painel()
            self.set_status("Clique exatamente sobre uma linha ou curva para editar.")
            event.accept()
            return True

        self._idx_elemento = idx
        try:
            canvas._selecionados = {idx}
        except Exception:
            pass
        el = canvas.cena.elementos[idx]
        self._garantir_controle_inicial(el)
        self._pontos_exibidos = self._pontos_controle_do_elemento(el)
        if len(self._pontos_exibidos) >= 2:
            self._quantidade_pontos = len(self._pontos_exibidos)
            self._set_spin_sem_sinal(self._quantidade_pontos)
        self._atualizar_texto_painel()
        self.set_status(f"Elemento selecionado: {len(self._pontos_exibidos)} ponto(s).")
        canvas.update()
        event.accept()
        return True

    def on_mouse_move(self, canvas, event) -> bool:
        if self._arrastando is None:
            return False
        idx, indice = self._arrastando
        if idx < 0 or idx >= len(canvas.cena.elementos):
            return False
        el = canvas.cena.elementos[idx]
        pontos = self._pontos_controle_do_elemento(el)
        if indice < 0 or indice >= len(pontos):
            return False
        pos = self._ponto_mouse_cena(canvas, event)
        if self._ultima_pos_arraste is not None and self._dist(self._ultima_pos_arraste, pos) <= 0.01:
            event.accept()
            return True
        self._ultima_pos_arraste = QPointF(pos)
        pontos[indice] = QPointF(pos)
        self._gravar_pontos_no_elemento(el, pontos, curva=(len(pontos) > 2))
        self._idx_elemento = idx
        self._pontos_exibidos = self._pontos_controle_do_elemento(el)
        snap_info = ""
        if hasattr(canvas, "descricao_snap_atual"):
            try:
                descricao = canvas.descricao_snap_atual()
                snap_info = f" | {descricao}" if descricao else ""
            except Exception:
                snap_info = ""
        self.set_status(f"Movendo ponto {indice + 1}: X {pos.x():.2f} | Y {pos.y():.2f}{snap_info}")
        canvas.update()
        event.accept()
        return True

    def on_mouse_release(self, canvas, event) -> bool:
        if event.button() != Qt.LeftButton or self._arrastando is None:
            return False
        self._arrastando = None
        self._ultima_pos_arraste = None
        self._original_arraste = {}
        self._atualizar_texto_painel()
        self._registrar_historico_seguro(canvas)
        self._emitir_alteracao_segura(canvas)
        self.set_status("Curva atualizada.")
        canvas.update()
        event.accept()
        return True

    def on_paint_overlay(self, canvas, painter):
        if self._idx_elemento is None:
            return
        if self._idx_elemento < 0 or self._idx_elemento >= len(canvas.cena.elementos):
            return
        el = canvas.cena.elementos[self._idx_elemento]
        if not self._elemento_editavel(el):
            return

        pontos_controle = self._pontos_controle_do_elemento(el)
        self._pontos_exibidos = pontos_controle
        if len(pontos_controle) < 2:
            return

        desenhar_elementos_originais(canvas, painter, self._original_arraste)
        painter.save()
        try:
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setPen(self._caneta_azul())
            painter.setBrush(Qt.NoBrush)
            if len(pontos_controle) == 2:
                painter.drawLine(canvas._cena_para_tela(pontos_controle[0]), canvas._cena_para_tela(pontos_controle[1]))
            else:
                painter.drawPath(self._path_suave_tela(canvas, pontos_controle))

            for i, ponto in enumerate(pontos_controle):
                pt = canvas._cena_para_tela(ponto)
                raio = 4.8 + (2.0 if self._arrastando == (self._idx_elemento, i) else 0.0)
                painter.setPen(QPen(QColor("#8b0000"), 1.2))
                painter.setBrush(QColor("#e11d48"))
                painter.drawEllipse(pt, raio, raio)
        finally:
            painter.restore()

    def _capturar_original_arraste(self, canvas, idx: int) -> dict[int, dict]:
        if 0 <= idx < len(canvas.cena.elementos) and isinstance(canvas.cena.elementos[idx], dict):
            return {idx: deepcopy(canvas.cena.elementos[idx])}
        return {}

    def eventFilter(self, obj, event):
        if obj is self._canvas and event.type() in (QEvent.Resize, QEvent.Show):
            self._reposicionar_painel(force=False)
        return False

    def _mostrar_painel(self, canvas):
        self._fechar_paineis_intrusos(canvas)
        painel = None
        try:
            existentes = canvas.findChildren(QFrame, _PainelEditarPontosCurva.OBJETO)
            painel = existentes[0] if existentes else None
        except Exception:
            painel = None
        if painel is None:
            painel = _PainelEditarPontosCurva(self, canvas)
        else:
            painel.ferramenta = self
            painel.canvas = canvas
        self._painel = painel
        self._set_spin_sem_sinal(self._quantidade_pontos)
        self._reposicionar_painel(force=True)
        self._atualizar_texto_painel()
        painel.show()
        painel.raise_()

    def _fechar_paineis_intrusos(self, canvas):
        try:
            for painel in list(canvas.findChildren(QFrame, _PainelEditarPontosCurva.OBJETO)):
                if painel is not self._painel:
                    painel.hide()
                    painel.setParent(None)
                    painel.deleteLater()
        except Exception:
            pass
        if PainelFerramentaBasico is not None:
            try:
                for painel in list(canvas.findChildren(PainelFerramentaBasico)):  # type: ignore[arg-type]
                    texto = ""
                    try:
                        texto = painel.windowTitle() or ""
                    except Exception:
                        pass
                    try:
                        texto += " " + " ".join(lbl.text() for lbl in painel.findChildren(QLabel))
                    except Exception:
                        pass
                    if "Editar Pontos de Curva" in texto or "Clique sobre uma linha" in texto:
                        painel.hide()
                        painel.setParent(None)
                        painel.deleteLater()
            except Exception:
                pass

    def _ocultar_painel(self):
        if self._painel is not None:
            self._painel.hide()

    def _reposicionar_painel(self, force: bool = False):
        if self._painel is None or self._canvas is None:
            return
        if self._painel_movido_usuario and not force:
            self._painel.move(self._painel._limitar(self._painel.pos()))
            return
        margem = 14
        if hasattr(self._canvas, "calcular_posicao_painel_auxiliar"):
            destino = self._canvas.calcular_posicao_painel_auxiliar(
                self._painel.width(),
                self._painel.height(),
                abaixo_coordenadas=True,
            )
        else:
            destino = QPoint(max(margem, self._canvas.width() - self._painel.width() - margem), margem)
        if not restaurar_posicao(self._painel, self._painel._chave_posicao, fallback=self._painel._limitar(destino)):
            salvar_posicao(self._painel, self._painel._chave_posicao)

    def _set_spin_sem_sinal(self, valor: int):
        if self._painel is None:
            return
        self._painel.spin.blockSignals(True)
        self._painel.spin.setValue(max(2, min(300, int(valor))))
        self._painel.spin.blockSignals(False)

    def _atualizar_texto_painel(self):
        if self._painel is None:
            return
        if self._idx_elemento is None:
            self._painel.lbl_status.setText("✓ Clique em uma linha ou curva para editar")
        else:
            self._painel.lbl_status.setText(f"✓ Elemento selecionado: {len(self._pontos_exibidos)} ponto(s).")

    def _limpar_selecao(self, canvas):
        self._idx_elemento = None
        self._arrastando = None
        self._pontos_exibidos = []
        try:
            canvas._selecionados = set()
        except Exception:
            pass
        try:
            canvas.update()
        except Exception:
            pass

    def _ponto_mouse_cena(self, canvas, event) -> QPointF:
        if self._arrastando is not None and hasattr(canvas, "_ponto_com_snap_movimento"):
            try:
                return canvas._ponto_com_snap_movimento(
                    event.position(),
                    ignorar_elementos={self._arrastando[0]},
                    elementos_sombra=self._original_arraste,
                )
            except Exception:
                pass
        if self._arrastando is not None and hasattr(canvas, "_ponto_com_snap"):
            try:
                return canvas._ponto_com_snap(event.position())
            except Exception:
                pass
        try:
            # Para escolher, o clique deve bater na linha real.
            return canvas._tela_para_cena(event.position())
        except Exception:
            return canvas._ponto_com_snap(event.position())

    def _caneta_azul(self) -> QPen:
        pen = QPen(QColor("#0b7cff"), 2.0)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        return pen

    def _elemento_editavel(self, el: dict) -> bool:
        return isinstance(el, dict) and len(self._pontos_render_do_elemento(el)) >= 2

    def _garantir_controle_inicial(self, el: dict):
        if len(self._pontos_controle_do_elemento(el)) >= 2:
            return
        pontos = self._pontos_render_do_elemento(el)
        if len(pontos) < 2:
            return
        if len(pontos) > 24:
            qtd = min(max(self._quantidade_pontos, 2), 24)
            controles = self._reamostrar_polyline(pontos, qtd)
        else:
            controles = list(pontos)
        self._salvar_controles(el, controles)

    def _pontos_controle_do_elemento(self, el: dict) -> list[QPointF]:
        if not isinstance(el, dict):
            return []
        for chave in ("pontos_principais", "pontos_controle_curva", "pontos_controle_principais", "pontos_controle", "controle_pontos"):
            pts = self._normalizar_lista_pontos(el.get(chave))
            if len(pts) >= 2:
                return pts
        if all(k in el for k in ("p0", "p1", "p2")):
            try:
                return [QPointF(float(el[k][0]), float(el[k][1])) for k in ("p0", "p1", "p2")]
            except Exception:
                pass
        return []

    def _pontos_render_do_elemento(self, el: dict) -> list[QPointF]:
        if not isinstance(el, dict):
            return []
        if all(k in el for k in ("p0", "p1", "p2")):
            try:
                p0 = QPointF(float(el["p0"][0]), float(el["p0"][1]))
                p1 = QPointF(float(el["p1"][0]), float(el["p1"][1]))
                p2 = QPointF(float(el["p2"][0]), float(el["p2"][1]))
                return self._amostrar_bezier_quadratica(p0, p1, p2, 80)
            except Exception:
                pass
        for chave in ("curva_pontos", "pontos", "vertices", "pontos_molde"):
            pts = self._normalizar_lista_pontos(el.get(chave))
            if len(pts) >= 2:
                return pts
        for a, b in (("inicio", "fim"), ("p_inicio", "p_fim"), ("start", "end"), ("a", "b")):
            if a in el and b in el:
                pa = self._ponto_de_valor(el.get(a))
                pb = self._ponto_de_valor(el.get(b))
                if pa is not None and pb is not None:
                    return [pa, pb]
        for nomes in (("x1", "y1", "x2", "y2"), ("x_ini", "y_ini", "x_fim", "y_fim")):
            if all(k in el for k in nomes):
                try:
                    return [QPointF(float(el[nomes[0]]), float(el[nomes[1]])), QPointF(float(el[nomes[2]]), float(el[nomes[3]]))]
                except Exception:
                    pass
        return []

    def _aplicar_quantidade_no_elemento(self, el: dict, quantidade: int):
        quantidade = max(2, min(300, int(quantidade)))
        base = self._pontos_controle_do_elemento(el)
        if len(base) < 2:
            base = self._pontos_render_do_elemento(el)
        if len(base) < 2:
            return
        if quantidade == 2:
            controles = [QPointF(base[0]), QPointF(base[-1])]
            self._gravar_pontos_no_elemento(el, controles, curva=False)
            return
        # Reamostra mantendo o formato visual atual da curva, não uma polilinha quebrada.
        render_atual = self._pontos_render_do_elemento(el)
        if len(render_atual) < 2:
            render_atual = self._amostrar_curva_suave(base, self._amostras_desenho(quantidade))
        controles = self._reamostrar_polyline(render_atual, quantidade)
        self._gravar_pontos_no_elemento(el, controles, curva=True)

    def _salvar_controles(self, el: dict, pontos: list[QPointF]):
        lista = [(float(p.x()), float(p.y())) for p in pontos]
        el["pontos_principais"] = list(lista)
        el["pontos_controle_curva"] = list(lista)
        el["pontos_controle_principais"] = list(lista)
        el["pontos_controle"] = list(lista)
        el["numero_pontos_curva"] = len(lista)
        el["quantidade_pontos_curva"] = len(lista)

    def _gravar_pontos_no_elemento(self, el: dict, pontos: list[QPointF], curva: bool):
        if len(pontos) < 2:
            return
        self._salvar_controles(el, pontos)
        controles = [(float(p.x()), float(p.y())) for p in pontos]
        quantidade = len(pontos)

        tipo_curva = str(el.get("tipo_curva") or "").lower()
        if quantidade == 2 or not curva:
            desenho = list(controles)
            el["curva"] = False
            el["suave"] = False
            el["tipo_linha"] = "reta"
        elif tipo_curva == "parabola_3p" and quantidade == 3:
            p0, pmedio, p2 = pontos
            desenho = sample_quadratic_bezier_through_point(
                (float(p0.x()), float(p0.y())),
                (float(pmedio.x()), float(pmedio.y())),
                (float(p2.x()), float(p2.y())),
                self._amostras_desenho(quantidade),
            )
            el["curva"] = True
            el["suave"] = True
            el["curva_suave"] = True
            el["curva_editavel"] = True
            el["pontos_tracado_real"] = True
            el["renderizacao"] = "polyline"
            el["tipo_curva"] = "parabola_3p"
            el["tipo_linha"] = "curva"
            el["subtipo"] = el.get("subtipo") or "curva"
        else:
            desenho = [(float(p.x()), float(p.y())) for p in self._amostrar_curva_suave(pontos, self._amostras_desenho(quantidade))]
            el["curva"] = True
            el["suave"] = True
            el["curva_suave"] = True
            el["curva_editavel"] = True
            el["pontos_tracado_real"] = True
            el["renderizacao"] = "polyline"
            el["tipo_curva"] = el.get("tipo_curva") or "spline_natural"
            el["tipo_linha"] = "curva"
            el["subtipo"] = el.get("subtipo") or "curva"

        if all(k in el for k in ("p0", "p1", "p2")):
            p0 = pontos[0]
            p2 = pontos[-1]
            p1 = QPointF((p0.x() + p2.x()) / 2.0, (p0.y() + p2.y()) / 2.0) if quantidade == 2 else pontos[len(pontos) // 2]
            el["p0"] = (float(p0.x()), float(p0.y()))
            el["p1"] = (float(p1.x()), float(p1.y()))
            el["p2"] = (float(p2.x()), float(p2.y()))

        gravou = False
        for chave in ("curva_pontos", "pontos", "vertices", "pontos_molde"):
            if isinstance(el.get(chave), list):
                el[chave] = list(desenho)
                gravou = True
                # Mantém as listas principais sincronizadas quando existirem.
                if chave != "pontos" and isinstance(el.get("pontos"), list):
                    el["pontos"] = list(desenho)
                if chave != "curva_pontos" and isinstance(el.get("curva_pontos"), list):
                    el["curva_pontos"] = list(desenho)
                break
        if not gravou:
            for a, b in (("inicio", "fim"), ("p_inicio", "p_fim"), ("start", "end"), ("a", "b")):
                if a in el and b in el:
                    el[a], el[b] = controles[0], controles[-1]
                    gravou = True
                    break
        if not gravou and all(k in el for k in ("x1", "y1", "x2", "y2")):
            el["x1"], el["y1"] = controles[0]
            el["x2"], el["y2"] = controles[-1]
            gravou = True
        if not gravou:
            el["tipo"] = "polyline"
            el["pontos"] = list(desenho)

    def _normalizar_lista_pontos(self, pontos: Any) -> list[QPointF]:
        if not isinstance(pontos, list):
            return []
        saida: list[QPointF] = []
        for pt in pontos:
            p = self._ponto_de_valor(pt)
            if p is not None:
                saida.append(p)
        return saida

    def _ponto_de_valor(self, valor: Any) -> QPointF | None:
        if isinstance(valor, QPointF):
            return QPointF(valor)
        if isinstance(valor, (tuple, list)) and len(valor) >= 2:
            try:
                return QPointF(float(valor[0]), float(valor[1]))
            except Exception:
                return None
        if isinstance(valor, dict):
            for ax, ay in (("x", "y"), ("X", "Y")):
                if ax in valor and ay in valor:
                    try:
                        return QPointF(float(valor[ax]), float(valor[ay]))
                    except Exception:
                        return None
        return None

    def _path_suave_tela(self, canvas, pontos: list[QPointF]) -> QPainterPath:
        tela = [canvas._cena_para_tela(p) for p in pontos]
        path = QPainterPath()
        if not tela:
            return path
        path.moveTo(tela[0])
        if len(tela) == 2:
            path.lineTo(tela[1])
            return path
        for i in range(len(tela) - 1):
            p0 = tela[max(i - 1, 0)]
            p1 = tela[i]
            p2 = tela[i + 1]
            p3 = tela[min(i + 2, len(tela) - 1)]
            c1 = QPointF(p1.x() + (p2.x() - p0.x()) / 6.0, p1.y() + (p2.y() - p0.y()) / 6.0)
            c2 = QPointF(p2.x() - (p3.x() - p1.x()) / 6.0, p2.y() - (p3.y() - p1.y()) / 6.0)
            path.cubicTo(c1, c2, p2)
        return path

    def _amostrar_bezier_quadratica(self, p0: QPointF, p1: QPointF, p2: QPointF, segmentos: int = 80) -> list[QPointF]:
        pontos: list[QPointF] = []
        n = max(8, int(segmentos))
        for i in range(n + 1):
            t = i / n
            u = 1.0 - t
            pontos.append(QPointF((u * u * p0.x()) + (2.0 * u * t * p1.x()) + (t * t * p2.x()),
                                  (u * u * p0.y()) + (2.0 * u * t * p1.y()) + (t * t * p2.y())))
        return pontos

    def _amostrar_curva_suave(self, pontos: list[QPointF], quantidade: int) -> list[QPointF]:
        quantidade = max(2, int(quantidade))
        if len(pontos) <= 2:
            return self._reamostrar_polyline(pontos, quantidade)
        brutos: list[QPointF] = []
        subdiv = max(16, min(48, quantidade // max(1, len(pontos) - 1)))
        for i in range(len(pontos) - 1):
            p0 = pontos[max(i - 1, 0)]
            p1 = pontos[i]
            p2 = pontos[i + 1]
            p3 = pontos[min(i + 2, len(pontos) - 1)]
            for j in range(subdiv):
                t = j / float(subdiv)
                brutos.append(self._catmull_rom(p0, p1, p2, p3, t))
        brutos.append(QPointF(pontos[-1]))
        return self._reamostrar_polyline(brutos, quantidade)

    def _catmull_rom(self, p0: QPointF, p1: QPointF, p2: QPointF, p3: QPointF, t: float) -> QPointF:
        t2 = t * t
        t3 = t2 * t
        x = 0.5 * ((2.0 * p1.x()) + (-p0.x() + p2.x()) * t + (2.0 * p0.x() - 5.0 * p1.x() + 4.0 * p2.x() - p3.x()) * t2 + (-p0.x() + 3.0 * p1.x() - 3.0 * p2.x() + p3.x()) * t3)
        y = 0.5 * ((2.0 * p1.y()) + (-p0.y() + p2.y()) * t + (2.0 * p0.y() - 5.0 * p1.y() + 4.0 * p2.y() - p3.y()) * t2 + (-p0.y() + 3.0 * p1.y() - 3.0 * p2.y() + p3.y()) * t3)
        return QPointF(x, y)

    def _reamostrar_polyline(self, pontos: list[QPointF], quantidade: int) -> list[QPointF]:
        quantidade = max(2, int(quantidade))
        if len(pontos) <= 1:
            return [QPointF(pontos[0])] if pontos else []
        comprimentos = [0.0]
        total = 0.0
        for a, b in zip(pontos, pontos[1:]):
            total += hypot(b.x() - a.x(), b.y() - a.y())
            comprimentos.append(total)
        if total <= 1e-9:
            return [QPointF(pontos[0]) for _ in range(quantidade)]
        novos: list[QPointF] = []
        seg = 0
        for i in range(quantidade):
            alvo = total * (i / max(quantidade - 1, 1))
            while seg < len(comprimentos) - 2 and comprimentos[seg + 1] < alvo:
                seg += 1
            a = pontos[seg]
            b = pontos[min(seg + 1, len(pontos) - 1)]
            ini = comprimentos[seg]
            fim = comprimentos[min(seg + 1, len(comprimentos) - 1)]
            t = 0.0 if fim <= ini else (alvo - ini) / (fim - ini)
            novos.append(QPointF(a.x() + (b.x() - a.x()) * t, a.y() + (b.y() - a.y()) * t))
        return novos

    def _amostras_desenho(self, quantidade_controles: int) -> int:
        return max(72, min(480, int(quantidade_controles) * 12))

    def _alca_em_ponto(self, canvas, pos: QPointF) -> tuple[int, int] | None:
        if self._idx_elemento is None or not (0 <= self._idx_elemento < len(canvas.cena.elementos)):
            return None
        tolerancia = 12.0 / max(float(getattr(canvas, "zoom", 1.0)), 0.001)
        melhor: tuple[int, int] | None = None
        melhor_d = tolerancia
        pontos = self._pontos_controle_do_elemento(canvas.cena.elementos[self._idx_elemento])
        for i, ponto in enumerate(pontos):
            d = self._dist(ponto, pos)
            if d <= melhor_d:
                melhor_d = d
                melhor = (self._idx_elemento, i)
        return melhor

    def _elemento_em_ponto(self, canvas, pos: QPointF) -> int | None:
        tolerancia = 18.0 / max(float(getattr(canvas, "zoom", 1.0)), 0.001)
        melhor_idx = None
        melhor_d = tolerancia
        elementos = getattr(getattr(canvas, "cena", None), "elementos", []) or []
        for idx in range(len(elementos) - 1, -1, -1):
            el = elementos[idx]
            if not self._elemento_editavel(el):
                continue
            pontos_render = self._pontos_render_do_elemento(el)
            if len(pontos_render) < 2:
                continue
            d = self._distancia_ponto_polyline(pos, pontos_render)
            if d <= melhor_d:
                melhor_d = d
                melhor_idx = idx
        return melhor_idx

    def _distancia_ponto_polyline(self, p: QPointF, pontos: list[QPointF]) -> float:
        melhor = float("inf")
        for a, b in zip(pontos, pontos[1:]):
            melhor = min(melhor, self._distancia_ponto_segmento(p, a, b))
        return melhor

    def _distancia_ponto_segmento(self, p: QPointF, a: QPointF, b: QPointF) -> float:
        return float(point_segment_distance((p.x(), p.y()), (a.x(), a.y()), (b.x(), b.y())))

    def _dist(self, a: QPointF, b: QPointF) -> float:
        return hypot(a.x() - b.x(), a.y() - b.y())

    def _registrar_historico_seguro(self, canvas):
        try:
            canvas._registrar_historico()
        except Exception:
            pass

    def _emitir_alteracao_segura(self, canvas):
        try:
            sinal = getattr(canvas, "elementos_alterados", None)
            if sinal is not None and hasattr(sinal, "emit"):
                sinal.emit()
        except Exception:
            pass
