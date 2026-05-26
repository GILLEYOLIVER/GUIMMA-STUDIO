from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QComboBox, QFrame, QLabel, QSizePolicy, QSlider, QVBoxLayout

from tools.editar_pontos_de_curva_tool import Ferramenta as FerramentaEditarPontosCurva
from tools.preview_original_utils import desenhar_elementos_originais
from ui.posicao_janelas import restaurar_posicao, salvar_posicao


class _PainelEditarSegmento(QFrame):
    OBJETO = "PainelEditarSegmento"

    def __init__(self, ferramenta: "Ferramenta", canvas):
        super().__init__(canvas)
        self.ferramenta = ferramenta
        self.canvas = canvas
        self._arrastando = False
        self._offset = QPoint(0, 0)
        self._chave_posicao = "painel:editar"
        self.setObjectName(self.OBJETO)
        self.setWindowFlags(Qt.Widget)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setFixedWidth(202)
        self.setStyleSheet(
            """
            QFrame#PainelEditarSegmento {
                background: #f8fbfd;
                border: 1px solid #cfd8df;
                border-radius: 6px;
            }
            QLabel {
                color: #111111;
                font-size: 11px;
            }
            QComboBox {
                background: #ffffff;
                border: 1px solid #8d9aa3;
                min-height: 18px;
                font-size: 11px;
                padding-left: 2px;
            }
            QSlider::groove:horizontal {
                height: 4px;
                background: #e3e6e8;
                border: 1px solid #c8cdd2;
            }
            QSlider::handle:horizontal {
                width: 10px;
                margin: -6px 0;
                background: #1b75bb;
                border: 1px solid #0d4f8c;
            }
            QSlider::sub-page:horizontal {
                background: #d9ecff;
            }
            """
        )

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(6, 6, 6, 6)
        raiz.setSpacing(4)

        self.titulo = QLabel("Edite pontos do segmento")
        raiz.addWidget(self.titulo)

        self.cmb_modo = QComboBox()
        self.cmb_modo.addItems(["Editar", "Remover"])
        self.cmb_modo.currentTextChanged.connect(self._modo_alterado)
        raiz.addWidget(self.cmb_modo)

        self.lbl_suavidade = QLabel("Suavidade de curva")
        raiz.addWidget(self.lbl_suavidade)

        self.slider_suavidade = QSlider(Qt.Horizontal)
        self.slider_suavidade.setRange(0, 10)
        self.slider_suavidade.setSingleStep(1)
        self.slider_suavidade.setPageStep(1)
        self.slider_suavidade.setTickInterval(1)
        self.slider_suavidade.setTickPosition(QSlider.TicksBelow)
        self.slider_suavidade.setValue(ferramenta.suavidade)
        self.slider_suavidade.valueChanged.connect(self._suavidade_alterada)
        raiz.addWidget(self.slider_suavidade)

    def _modo_alterado(self, texto: str):
        self.ferramenta.definir_modo(texto)

    def _suavidade_alterada(self, valor: int):
        self.ferramenta.definir_suavidade(int(valor), registrar=True)

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton and event.position().y() <= 24:
            self._arrastando = True
            self._offset = event.position().toPoint()
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
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton and self._arrastando:
            self._arrastando = False
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


class Ferramenta(FerramentaEditarPontosCurva):
    id_ferramenta = "editar"
    nome = "Editar"
    usa_painel_auxiliar = False

    def __init__(self):
        super().__init__()
        self._modo = "editar"
        self.suavidade = 4
        self._painel: _PainelEditarSegmento | None = None
        self._arrastando_alca_editar: tuple[int, int, str] | None = None

    def definir_modo(self, modo: str) -> None:
        modo_txt = str(modo or "").strip().lower()
        self._modo = "remover" if modo_txt.startswith("rem") else "editar"
        if self._modo == "remover":
            self.set_status("Remover: clique em um ponto do segmento para apagar.")
        else:
            self.set_status("Editar: arraste pontos do segmento para ajustar.")
        canvas = self._canvas
        if canvas is not None:
            try:
                canvas.update()
            except Exception:
                pass

    def definir_suavidade(self, valor: int, registrar: bool = True) -> None:
        self.suavidade = max(0, min(10, int(valor)))
        canvas = self._canvas
        if canvas is None or self._idx_elemento is None:
            return
        if not (0 <= self._idx_elemento < len(canvas.cena.elementos)):
            return
        el = canvas.cena.elementos[self._idx_elemento]
        pontos = self._pontos_controle_do_elemento(el)
        if len(pontos) < 3:
            return
        self._gravar_pontos_no_elemento(el, pontos, curva=True)
        if registrar:
            self._registrar_historico_seguro(canvas)
            self._emitir_alteracao_segura(canvas)
        canvas.update()

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() != Qt.LeftButton:
            return False
        pos = self._ponto_mouse_cena(canvas, event)
        if self._modo != "remover":
            alca = self._alca_bezier_em_ponto(canvas, pos)
            if alca is not None:
                self._arrastando_alca_editar = alca
                self._ultima_pos_arraste = QPointF(pos)
                self._original_arraste = self._capturar_original_arraste(canvas, alca[0])
                self.set_status("Arraste a alca cinza para ajustar a tangente do segmento.")
                event.accept()
                canvas.update()
                return True
            return super().on_mouse_press(canvas, event)

        alca = self._alca_em_ponto(canvas, pos)
        if alca is not None:
            idx, indice = alca
            self._remover_ponto_controle(canvas, idx, indice)
            event.accept()
            return True
        idx = self._elemento_em_ponto(canvas, pos)
        if idx is not None:
            self._idx_elemento = idx
            canvas._selecionados = {idx}
            el = canvas.cena.elementos[idx]
            self._garantir_controle_inicial(el)
            self._pontos_exibidos = self._pontos_controle_do_elemento(el)
            self.set_status("Segmento selecionado. Clique em um ponto para remover.")
            canvas.update()
            event.accept()
            return True
        self.set_status("Remover: clique sobre o segmento ou sobre um ponto.")
        return False

    def on_mouse_move(self, canvas, event) -> bool:
        if self._modo == "remover":
            return False
        if self._arrastando is not None:
            idx, indice = self._arrastando
            if not (0 <= idx < len(canvas.cena.elementos)):
                return False
            el = canvas.cena.elementos[idx]
            pontos = self._pontos_controle_do_elemento(el)
            if not (0 <= indice < len(pontos)):
                return False
            pos = self._ponto_mouse_cena(canvas, event)
            antigo = QPointF(pontos[indice])
            if self._dist(antigo, pos) <= 0.01:
                event.accept()
                return True
            pontos[indice] = QPointF(pos)
            self._deslocar_alcas_do_ponto(el, indice, pos.x() - antigo.x(), pos.y() - antigo.y())
            self._aplicar_bezier_no_elemento(el, pontos)
            self._idx_elemento = idx
            self._pontos_exibidos = self._pontos_controle_do_elemento(el)
            self.set_status(f"Movendo ponto {indice + 1}: X {pos.x():.2f} | Y {pos.y():.2f}")
            canvas.update()
            event.accept()
            return True
        if self._arrastando_alca_editar is not None:
            idx, indice, lado = self._arrastando_alca_editar
            if not (0 <= idx < len(canvas.cena.elementos)):
                return False
            el = canvas.cena.elementos[idx]
            pontos = self._pontos_controle_do_elemento(el)
            if not (0 <= indice < len(pontos)):
                return False
            pos = self._ponto_mouse_cena(canvas, event)
            alcas = self._garantir_alcas_bezier(el, pontos)
            alcas[indice][lado] = (float(pos.x()), float(pos.y()))
            self._salvar_alcas_bezier(el, alcas)
            self._aplicar_bezier_no_elemento(el, pontos)
            self._pontos_exibidos = pontos
            self.set_status(f"Alca {indice + 1}: X {pos.x():.2f} | Y {pos.y():.2f}")
            canvas.update()
            event.accept()
            return True
        return super().on_mouse_move(canvas, event)

    def on_mouse_release(self, canvas, event) -> bool:
        if event.button() == Qt.LeftButton and self._arrastando_alca_editar is not None:
            self._arrastando_alca_editar = None
            self._ultima_pos_arraste = None
            self._original_arraste = {}
            self._registrar_historico_seguro(canvas)
            self._emitir_alteracao_segura(canvas)
            self.set_status("Tangente atualizada.")
            canvas.update()
            event.accept()
            return True
        return super().on_mouse_release(canvas, event)

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
            alcas = self._garantir_alcas_bezier(el, pontos_controle)
            self._desenhar_poligono_controle(canvas, painter, pontos_controle, alcas)
            self._desenhar_curva_editada(canvas, painter, pontos_controle)
            self._desenhar_pontos_do_segmento(canvas, painter, pontos_controle)
        finally:
            painter.restore()

    def _remover_ponto_controle(self, canvas, idx: int, indice: int) -> bool:
        if not (0 <= idx < len(canvas.cena.elementos)):
            return False
        el = canvas.cena.elementos[idx]
        pontos = self._pontos_controle_do_elemento(el)
        if len(pontos) <= 2 or not (0 <= indice < len(pontos)):
            self.set_status("Nao e possivel remover: o segmento precisa manter ao menos 2 pontos.")
            return False
        pontos.pop(indice)
        alcas = self._normalizar_alcas_bezier(el.get("alcas_editar_segmento"), len(pontos) + 1)
        if alcas is not None and 0 <= indice < len(alcas):
            alcas.pop(indice)
            self._salvar_alcas_bezier(el, alcas)
        self._aplicar_bezier_no_elemento(el, pontos)
        self._idx_elemento = idx
        self._pontos_exibidos = self._pontos_controle_do_elemento(el)
        canvas._selecionados = {idx}
        self._registrar_historico_seguro(canvas)
        self._emitir_alteracao_segura(canvas)
        canvas.update()
        self.set_status(f"Ponto removido. Restam {len(self._pontos_exibidos)} ponto(s).")
        return True

    def _desenhar_curva_editada(self, canvas, painter, pontos: list[QPointF]) -> None:
        pen = QPen(QColor("#ff1b1b"), 1.4)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        if len(pontos) == 2:
            painter.drawLine(canvas._cena_para_tela(pontos[0]), canvas._cena_para_tela(pontos[1]))
        else:
            el = canvas.cena.elementos[self._idx_elemento] if self._idx_elemento is not None else {}
            painter.drawPath(self._path_bezier_tela(canvas, el, pontos))

    def _desenhar_poligono_controle(self, canvas, painter, pontos: list[QPointF], alcas: list[dict]) -> None:
        pen = QPen(QColor("#666666"), 0.9)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        for i, ponto in enumerate(pontos):
            for lado in ("anterior", "proximo"):
                handle = self._ponto_de_valor(alcas[i].get(lado)) if i < len(alcas) else None
                if handle is not None:
                    painter.drawLine(canvas._cena_para_tela(ponto), canvas._cena_para_tela(handle))
        painter.setPen(QPen(QColor("#303030"), 0.8))
        painter.setBrush(QColor("#777777"))
        for item in alcas:
            for lado in ("anterior", "proximo"):
                handle = self._ponto_de_valor(item.get(lado))
                if handle is not None:
                    pt = canvas._cena_para_tela(handle)
                    painter.drawEllipse(pt, 4.0, 4.0)

    def _desenhar_pontos_do_segmento(self, canvas, painter, pontos: list[QPointF]) -> None:
        for i, ponto in enumerate(pontos):
            pt = canvas._cena_para_tela(ponto)
            selecionado = self._arrastando == (self._idx_elemento, i)
            if selecionado:
                painter.setPen(QPen(QColor("#ff1b1b"), 1.4))
                painter.setBrush(QColor("#ffffff"))
                painter.drawRect(int(pt.x() - 4), int(pt.y() - 4), 8, 8)
                continue
            painter.setPen(QPen(QColor("#ff1b1b"), 1.0))
            painter.setBrush(QColor("#0b0b0b"))
            painter.drawEllipse(pt, 4.2, 4.2)

    def _alca_bezier_em_ponto(self, canvas, pos: QPointF) -> tuple[int, int, str] | None:
        if self._idx_elemento is None or not (0 <= self._idx_elemento < len(canvas.cena.elementos)):
            return None
        el = canvas.cena.elementos[self._idx_elemento]
        pontos = self._pontos_controle_do_elemento(el)
        if len(pontos) < 2:
            return None
        alcas = self._garantir_alcas_bezier(el, pontos)
        tolerancia = 12.0 / max(float(getattr(canvas, "zoom", 1.0)), 0.001)
        melhor: tuple[int, int, str] | None = None
        melhor_d = tolerancia
        for i, item in enumerate(alcas):
            for lado in ("anterior", "proximo"):
                handle = self._ponto_de_valor(item.get(lado))
                if handle is None:
                    continue
                d = self._dist(handle, pos)
                if d <= melhor_d:
                    melhor = (self._idx_elemento, i, lado)
                    melhor_d = d
        return melhor

    def _garantir_alcas_bezier(self, el: dict, pontos: list[QPointF]) -> list[dict]:
        existentes = self._normalizar_alcas_bezier(el.get("alcas_editar_segmento"), len(pontos))
        if existentes is not None:
            return existentes
        alcas: list[dict] = []
        intensidade = 0.18 + (self.suavidade / 10.0) * 0.22
        for i, ponto in enumerate(pontos):
            anterior = pontos[i - 1] if i > 0 else None
            proximo = pontos[i + 1] if i < len(pontos) - 1 else None
            item: dict[str, tuple[float, float] | None] = {"anterior": None, "proximo": None}
            if anterior is not None:
                dx = ponto.x() - anterior.x()
                dy = ponto.y() - anterior.y()
                item["anterior"] = (ponto.x() - dx * intensidade, ponto.y() - dy * intensidade)
            if proximo is not None:
                dx = proximo.x() - ponto.x()
                dy = proximo.y() - ponto.y()
                item["proximo"] = (ponto.x() + dx * intensidade, ponto.y() + dy * intensidade)
            alcas.append(item)
        self._salvar_alcas_bezier(el, alcas)
        return alcas

    def _normalizar_alcas_bezier(self, valor, tamanho: int) -> list[dict] | None:
        if not isinstance(valor, list) or len(valor) != tamanho:
            return None
        saida: list[dict] = []
        for item in valor:
            if not isinstance(item, dict):
                return None
            normalizado = {"anterior": None, "proximo": None}
            for lado in ("anterior", "proximo"):
                ponto = self._ponto_de_valor(item.get(lado))
                if ponto is not None:
                    normalizado[lado] = (float(ponto.x()), float(ponto.y()))
            saida.append(normalizado)
        return saida

    def _salvar_alcas_bezier(self, el: dict, alcas: list[dict]) -> None:
        el["alcas_editar_segmento"] = [
            {
                "anterior": item.get("anterior"),
                "proximo": item.get("proximo"),
            }
            for item in alcas
        ]

    def _aplicar_bezier_no_elemento(self, el: dict, pontos: list[QPointF]) -> None:
        if len(pontos) < 2:
            return
        desenho = self._amostrar_bezier_por_alcas(el, pontos, self._amostras_desenho(len(pontos)))
        self._salvar_controles(el, pontos)
        el["pontos"] = [(float(p.x()), float(p.y())) for p in desenho]
        el["curva"] = len(pontos) > 2
        el["suave"] = len(pontos) > 2
        el["curva_suave"] = len(pontos) > 2
        el["curva_editavel"] = True
        el["pontos_tracado_real"] = True
        el["renderizacao"] = "polyline"
        el["tipo_linha"] = "curva" if len(pontos) > 2 else "reta"
        el["tipo_curva"] = "bezier_alcas"

    def _amostrar_bezier_por_alcas(self, el: dict, pontos: list[QPointF], quantidade: int) -> list[QPointF]:
        alcas = self._garantir_alcas_bezier(el, pontos)
        saida: list[QPointF] = []
        segmentos = max(8, int(quantidade / max(1, len(pontos) - 1)))
        for i in range(len(pontos) - 1):
            p0 = pontos[i]
            p3 = pontos[i + 1]
            p1 = self._ponto_de_valor(alcas[i].get("proximo")) or p0
            p2 = self._ponto_de_valor(alcas[i + 1].get("anterior")) or p3
            for j in range(segmentos):
                if i > 0 and j == 0:
                    continue
                t = j / float(segmentos)
                saida.append(self._bezier_cubica(p0, p1, p2, p3, t))
        saida.append(QPointF(pontos[-1]))
        return saida

    def _bezier_cubica(self, p0: QPointF, p1: QPointF, p2: QPointF, p3: QPointF, t: float) -> QPointF:
        u = 1.0 - t
        x = (u ** 3 * p0.x()) + (3 * u * u * t * p1.x()) + (3 * u * t * t * p2.x()) + (t ** 3 * p3.x())
        y = (u ** 3 * p0.y()) + (3 * u * u * t * p1.y()) + (3 * u * t * t * p2.y()) + (t ** 3 * p3.y())
        return QPointF(x, y)

    def _path_bezier_tela(self, canvas, el: dict, pontos: list[QPointF]):
        path = super()._path_suave_tela(canvas, pontos)
        if len(pontos) < 2:
            return path
        try:
            from PySide6.QtGui import QPainterPath

            alcas = self._garantir_alcas_bezier(el, pontos)
            path = QPainterPath(canvas._cena_para_tela(pontos[0]))
            for i in range(len(pontos) - 1):
                p1 = self._ponto_de_valor(alcas[i].get("proximo")) or pontos[i]
                p2 = self._ponto_de_valor(alcas[i + 1].get("anterior")) or pontos[i + 1]
                path.cubicTo(canvas._cena_para_tela(p1), canvas._cena_para_tela(p2), canvas._cena_para_tela(pontos[i + 1]))
        except Exception:
            pass
        return path

    def _deslocar_alcas_do_ponto(self, el: dict, indice: int, dx: float, dy: float) -> None:
        alcas = self._normalizar_alcas_bezier(el.get("alcas_editar_segmento"), len(self._pontos_controle_do_elemento(el)))
        if alcas is None or not (0 <= indice < len(alcas)):
            return
        for lado in ("anterior", "proximo"):
            ponto = self._ponto_de_valor(alcas[indice].get(lado))
            if ponto is not None:
                alcas[indice][lado] = (ponto.x() + dx, ponto.y() + dy)
        self._salvar_alcas_bezier(el, alcas)

    def _mostrar_painel(self, canvas):
        self._fechar_paineis_intrusos(canvas)
        painel = None
        try:
            existentes = canvas.findChildren(QFrame, _PainelEditarSegmento.OBJETO)
            painel = existentes[0] if existentes else None
        except Exception:
            painel = None
        if painel is None:
            painel = _PainelEditarSegmento(self, canvas)
        else:
            painel.ferramenta = self
            painel.canvas = canvas
        self._painel = painel
        painel.cmb_modo.blockSignals(True)
        painel.cmb_modo.setCurrentText("Remover" if self._modo == "remover" else "Editar")
        painel.cmb_modo.blockSignals(False)
        painel.slider_suavidade.blockSignals(True)
        painel.slider_suavidade.setValue(self.suavidade)
        painel.slider_suavidade.blockSignals(False)
        self._reposicionar_painel(force=True)
        painel.show()
        painel.raise_()

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

    def _atualizar_texto_painel(self):
        return None

    def _set_spin_sem_sinal(self, valor: int):
        return None

    def _amostras_desenho(self, quantidade_controles: int) -> int:
        base = max(2, int(quantidade_controles))
        fator = 8 + (self.suavidade * 6)
        return max(24, min(720, base * fator))

    def _path_suave_tela(self, canvas, pontos: list[QPointF]):
        return super()._path_suave_tela(canvas, pontos)
