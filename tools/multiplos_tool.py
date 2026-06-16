from __future__ import annotations

from math import atan2, cos, degrees, radians, sin, sqrt

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
)

from core.formatacao import numero_decimal_ponto
from tools.inserir_pique_tool import Ferramenta as FerramentaInserirPique
from tools.inserir_pique_tool import TIPOS_PIQUE, _PiquePreview
from tools.dialog_lifetime import esconder_se_valido, limpar_global_ao_destruir, qobject_valido
from tools.unidades import SUFIXOS_MEDIDA, unidade_canvas
from ui.posicao_janelas import instalar_memoria_posicao, restaurar_posicao


class MultiplosPiquesDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("MultiplosPiquesDialog")
        self.setWindowTitle("Inserir múltiplos piques")
        self.setWindowFlags(Qt.Tool)
        self.setFixedWidth(306)
        self._unidade_sigla = "cm"
        self._unidade_fator = 1.0

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(6, 6, 6, 6)
        raiz.setSpacing(6)

        topo = QGridLayout()
        topo.setHorizontalSpacing(6)
        topo.setVerticalSpacing(4)
        topo.addWidget(QLabel("Modo"), 0, 0)
        self.cmb_modo = QComboBox()
        self.cmb_modo.addItems(["Pontos do mouse", "Elemento", "Sobre o contorno"])
        topo.addWidget(self.cmb_modo, 0, 1)

        self.cmb_parametro = QComboBox()
        self.cmb_parametro.addItem("Nº piques")
        self.spn_quantidade = QSpinBox()
        self.spn_quantidade.setRange(1, 999)
        self.spn_quantidade.setValue(10)
        topo.addWidget(self.cmb_parametro, 1, 0)
        topo.addWidget(self.spn_quantidade, 1, 1)
        raiz.addLayout(topo)

        grade = QGridLayout()
        grade.setHorizontalSpacing(6)
        grade.setVerticalSpacing(4)

        self.edt_largura = QLineEdit("0.5")
        self.edt_altura = QLineEdit("0.3")
        self.edt_angulo = QLineEdit("0")
        for edt in (self.edt_largura, self.edt_altura, self.edt_angulo):
            edt.setFixedWidth(66)

        self.cmb_tipo = QComboBox()
        self.cmb_tipo.addItems(TIPOS_PIQUE)
        self.cmb_tipo.setCurrentText("T - forma T")
        self.cmb_tipo.setMinimumWidth(172)
        self.cmb_tipo.setMaxVisibleItems(12)

        self.preview = _PiquePreview(self)
        self.preview.setMinimumSize(172, 84)

        self.lbl_largura = QLabel("Largura (cm)")
        self.lbl_altura = QLabel("Altura (cm)")
        grade.addWidget(self.lbl_largura, 0, 0)
        grade.addWidget(QLabel("Pique"), 0, 1)
        grade.addWidget(self.edt_largura, 1, 0)
        grade.addWidget(self.cmb_tipo, 1, 1)
        grade.addWidget(self.lbl_altura, 2, 0)
        grade.addWidget(self.edt_altura, 3, 0)
        grade.addWidget(QLabel("Ângulo"), 4, 0)
        linha_angulo = QHBoxLayout()
        linha_angulo.setContentsMargins(0, 0, 0, 0)
        linha_angulo.setSpacing(2)
        linha_angulo.addWidget(self.edt_angulo)
        linha_angulo.addWidget(QLabel("°"))
        grade.addLayout(linha_angulo, 5, 0)
        grade.addWidget(self.preview, 2, 1, 4, 1)
        raiz.addLayout(grade)

        self.lbl_status = QLabel("Pontos do mouse: clique no contorno ou dentro do molde.")
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setStyleSheet("color:#4c5d6f; font-size:11px;")
        raiz.addWidget(self.lbl_status)

        self.chk_sobre_contorno = QCheckBox()
        self.chk_sobre_contorno.setChecked(True)
        self.chk_sobre_contorno.hide()
        self.chk_ponto_controle = QCheckBox()
        self.chk_ponto_controle.setChecked(True)
        self.chk_ponto_controle.hide()
        self.chk_manter_distancia = QCheckBox()
        self.chk_manter_distancia.setChecked(True)
        self.chk_manter_distancia.hide()
        self.cmb_referencia = QComboBox()
        self.cmb_referencia.addItems(["Segmento mais próximo", "Ponto mais próximo"])
        self.cmb_referencia.hide()
        self.cmb_costura = QComboBox()
        self.cmb_costura.addItems(["Estendido", "Projetado", "Medir"])
        self.cmb_costura.setCurrentText("Estendido")
        self.cmb_costura.hide()
        for widget in (
            self.chk_sobre_contorno,
            self.chk_ponto_controle,
            self.chk_manter_distancia,
            self.cmb_referencia,
            self.cmb_costura,
        ):
            raiz.addWidget(widget)

        self.cmb_tipo.currentTextChanged.connect(self.preview.set_tipo)
        self.edt_largura.textChanged.connect(lambda _texto: self.preview.set_medidas(self.largura(), self.altura()))
        self.edt_altura.textChanged.connect(lambda _texto: self.preview.set_medidas(self.largura(), self.altura()))
        self.cmb_modo.currentTextChanged.connect(self._modo_alterado)
        self.preview.set_tipo(self.cmb_tipo.currentText())
        self.preview.set_medidas(self.largura(), self.altura())

        self.setStyleSheet(
            """
            QDialog#MultiplosPiquesDialog { background:#eef7f9; }
            QLabel { color:#16202a; font-size:11px; }
            QLineEdit, QComboBox, QSpinBox {
                background:#ffffff;
                border:1px solid #aeb8c2;
                min-height:19px;
                font-size:11px;
            }
            """
        )

    def modo(self) -> str:
        return self.cmb_modo.currentText()

    def quantidade(self) -> int:
        return int(self.spn_quantidade.value())

    def largura(self) -> float:
        return self._medida_cena(self.edt_largura.text(), 0.5)

    def altura(self) -> float:
        return self._medida_cena(self.edt_altura.text(), 0.3)

    def angulo(self) -> float:
        return numero_decimal_ponto(self.edt_angulo.text(), 0.0)

    def dx(self) -> float:
        return 0.0

    def dy(self) -> float:
        return 0.0

    def _medida_cena(self, texto: str, padrao_cena: float) -> float:
        padrao_unidade = float(padrao_cena) / self._unidade_fator
        return numero_decimal_ponto(texto, padrao_unidade, SUFIXOS_MEDIDA) * self._unidade_fator

    def set_unidade(self, sigla: str, fator: float) -> None:
        fator_antigo = max(1e-9, float(getattr(self, "_unidade_fator", 1.0)))
        valores_cena = [
            numero_decimal_ponto(self.edt_largura.text(), 0.5, SUFIXOS_MEDIDA) * fator_antigo,
            numero_decimal_ponto(self.edt_altura.text(), 0.3, SUFIXOS_MEDIDA) * fator_antigo,
        ]
        self._unidade_sigla = str(sigla or "cm")
        self._unidade_fator = max(1e-9, float(fator or 1.0))
        self.lbl_largura.setText(f"Largura ({self._unidade_sigla})")
        self.lbl_altura.setText(f"Altura ({self._unidade_sigla})")
        for edt, valor_cena in zip((self.edt_largura, self.edt_altura), valores_cena):
            texto = f"{valor_cena / self._unidade_fator:.3f}".rstrip("0").rstrip(".")
            edt.setText("0" if texto in {"", "-0"} else texto)
            edt.setPlaceholderText(self._unidade_sigla)
        self.preview.set_medidas(self.largura(), self.altura())

    def set_sobre_contorno(self, ativo: bool) -> None:
        self.chk_sobre_contorno.setChecked(bool(ativo))

    def _modo_alterado(self, modo: str) -> None:
        if modo == "Pontos do mouse":
            self.lbl_status.setText("Pontos do mouse: clique no contorno ou dentro do molde.")
        elif modo == "Elemento":
            self.lbl_status.setText("Elemento: clique no molde para distribuir a quantidade em volta dele.")
        else:
            self.lbl_status.setText("Sobre o contorno: clique no contorno do molde para distribuir os piques.")


class Ferramenta(FerramentaInserirPique):
    id_ferramenta = "multiplos"
    nome = "Múltiplos Piques"
    usa_painel_auxiliar = False
    _dialog_global: MultiplosPiquesDialog | None = None

    def __init__(self):
        super().__init__()
        self._dialog: MultiplosPiquesDialog | None = type(self)._dialog_global
        self._interativo: dict | None = None
        self._preview_pontos: list[QPointF] = []

    def on_activate(self, canvas):
        self._hover = None
        self._molde_idx = None
        self._interativo = None
        self._preview_pontos = []
        self._abrir_dialogo(canvas)
        self.set_status("Múltiplos piques: primeiro clique inicia, mova no sentido desejado, segundo clique fixa.")

    def on_deactivate(self, canvas):
        esconder_se_valido(self._dialog)
        self._hover = None
        self._molde_idx = None
        self._interativo = None
        self._preview_pontos = []
        canvas.update()

    def on_canvas_resize(self, canvas) -> None:
        self._reposicionar_dialogo(canvas)

    def on_mouse_move(self, canvas, event) -> bool:
        pos = self._posicao_cena(canvas, event)
        if self._interativo is not None:
            self._atualizar_preview_interativo(canvas, pos)
        else:
            self._hover = self._hover_para_posicao(canvas, pos)
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
        if not qobject_valido(self._dialog):
            return False

        pos = self._posicao_cena(canvas, event)
        if self._interativo is not None:
            return self._finalizar_interativo(canvas, event, pos)
        modo = self._dialog.modo()
        return self._iniciar_interativo(canvas, event, pos, modo)

    def on_paint_overlay(self, canvas, painter):
        self._desenhar_molde_selecionado(canvas, painter)
        if self._interativo is not None:
            self._desenhar_preview_multiplos(canvas, painter)
            return
        if self._hover is not None:
            self._desenhar_preview_pique(canvas, painter)

    def _abrir_dialogo(self, canvas) -> None:
        cls = type(self)
        if not qobject_valido(cls._dialog_global):
            cls._dialog_global = MultiplosPiquesDialog(canvas)
            instalar_memoria_posicao(cls._dialog_global, "dialog:multiplos_piques")
            limpar_global_ao_destruir(cls._dialog_global, cls, "_dialog_global")
        self._dialog = cls._dialog_global
        if not qobject_valido(self._dialog):
            return
        if self._dialog.parentWidget() is not canvas:
            self._dialog.setParent(canvas)
        if not self._dialog.isVisible():
            self._dialog.show()
        self._dialog.set_unidade(*unidade_canvas(canvas))
        self._reposicionar_dialogo(canvas)

    def on_unidade_medida_alterada(self, canvas):
        if qobject_valido(self._dialog):
            self._dialog.set_unidade(*unidade_canvas(canvas))

    def _reposicionar_dialogo(self, canvas) -> None:
        if not qobject_valido(self._dialog):
            return
        fallback = None
        if hasattr(canvas, "calcular_posicao_painel_auxiliar") and hasattr(canvas, "mapToGlobal"):
            pos = canvas.calcular_posicao_painel_auxiliar(self._dialog.width(), self._dialog.height(), abaixo_coordenadas=True)
            fallback = canvas.mapToGlobal(pos)
        elif hasattr(canvas, "mapToGlobal"):
            fallback = canvas.mapToGlobal(QPoint(12, 12))
        restaurar_posicao(self._dialog, "dialog:multiplos_piques", fallback=fallback)

    def _iniciar_interativo(self, canvas, event, pos: QPointF, modo: str) -> bool:
        if not qobject_valido(self._dialog):
            return False
        alvo_contorno = self._alvo_no_contorno(canvas, pos)
        if modo == "Pontos do mouse" and alvo_contorno is None:
            idx = self._molde_em_posicao(canvas, pos)
            if idx is None:
                self.set_status("Clique no contorno ou dentro do molde para iniciar os múltiplos piques.")
                event.accept()
                return True
            if not self._ponto_dentro_molde(canvas.cena.elementos[idx], pos):
                self.set_status("Clique dentro do molde para iniciar piques internos.")
                event.accept()
                return True
            self._selecionar_molde(canvas, idx)
            self._dialog.set_sobre_contorno(False)
            self._interativo = {
                "tipo": "interno",
                "idx": idx,
                "inicio": QPointF(pos),
                "fim": QPointF(pos),
            }
            self._preview_pontos = []
            self.set_status("Piques internos: mova o mouse; o imã angular guia a direção. Segundo clique fixa.")
            canvas.update()
            event.accept()
            return True

        if alvo_contorno is None:
            idx = self._molde_em_posicao(canvas, pos)
            if idx is None:
                self.set_status("Clique no molde ou no contorno para iniciar.")
                event.accept()
                return True
            proj = self._projecao_contorno(canvas.cena.elementos[idx], pos)
            if proj is None:
                self.set_status("Não foi possível localizar o contorno do molde.")
                event.accept()
                return True
            ponto_inicio, s_inicio, total = proj[0], proj[1], proj[2]
        else:
            idx, ponto_inicio = alvo_contorno
            proj = self._projecao_contorno(canvas.cena.elementos[idx], ponto_inicio)
            if proj is None:
                self.set_status("Não foi possível localizar o contorno do molde.")
                event.accept()
                return True
            ponto_inicio, s_inicio, total = proj[0], proj[1], proj[2]

        self._selecionar_molde(canvas, idx)
        self._dialog.set_sobre_contorno(True)
        self._interativo = {
            "tipo": "contorno",
            "idx": idx,
            "inicio": QPointF(ponto_inicio),
            "s_inicio": float(s_inicio),
            "s_anterior": float(s_inicio),
            "progresso": 0.0,
            "total": float(total),
        }
        self._preview_pontos = []
        self.set_status("Mova no sentido horário ou anti-horário. Segundo clique fixa os piques.")
        canvas.update()
        event.accept()
        return True

    def _finalizar_interativo(self, canvas, event, pos: QPointF) -> bool:
        if not qobject_valido(self._dialog) or self._interativo is None:
            return False
        self._atualizar_preview_interativo(canvas, pos)
        estado = dict(self._interativo)
        pontos = [QPointF(p) for p in self._preview_pontos]
        if not pontos:
            self.set_status("Mova o mouse para criar a divisão antes de finalizar.")
            event.accept()
            return True
        idx = int(estado.get("idx", -1))
        self._dialog.set_sobre_contorno(estado.get("tipo") == "contorno")
        aplicados = 0
        for ponto in pontos:
            if self._aplicar_pique(canvas, idx, ponto):
                aplicados += 1
        if aplicados and hasattr(canvas, "_registrar_historico"):
            canvas._registrar_historico()
        self._interativo = None
        self._preview_pontos = []
        self._hover = None
        canvas.update()
        plural = "s" if aplicados != 1 else ""
        self.set_status(f"{aplicados} pique{plural} fixado{plural}.")
        event.accept()
        return True

    def _atualizar_preview_interativo(self, canvas, pos: QPointF) -> None:
        if not qobject_valido(self._dialog) or self._interativo is None:
            self._preview_pontos = []
            return
        tipo = self._interativo.get("tipo")
        idx = int(self._interativo.get("idx", -1))
        if not (0 <= idx < len(canvas.cena.elementos)):
            self._preview_pontos = []
            return
        if tipo == "interno":
            inicio = QPointF(self._interativo.get("inicio"))
            fim = self._posicao_interna_com_snap_angular(canvas, inicio, pos)
            self._interativo["fim"] = QPointF(fim)
            self._preview_pontos = self._pontos_uniformes_linha(inicio, fim, self._dialog.quantidade())
            return

        el = canvas.cena.elementos[idx]
        proj = self._projecao_contorno(el, pos)
        if proj is None:
            self._preview_pontos = []
            return
        _ponto, s_atual, total, _distancia = proj
        s_anterior = float(self._interativo.get("s_anterior", s_atual))
        delta = float(s_atual) - s_anterior
        if total > 1e-9:
            if delta > total / 2.0:
                delta -= total
            elif delta < -total / 2.0:
                delta += total
        progresso = float(self._interativo.get("progresso", 0.0)) + delta
        limite = max(0.0, float(total) - 1e-6)
        progresso = max(-limite, min(limite, progresso))
        self._interativo["s_anterior"] = float(s_atual)
        self._interativo["progresso"] = progresso
        self._interativo["total"] = float(total)
        self._preview_pontos = self._pontos_uniformes_intervalo_contorno(
            el,
            float(self._interativo.get("s_inicio", 0.0)),
            progresso,
            self._dialog.quantidade(),
        )

    def _desenhar_preview_multiplos(self, canvas, painter) -> None:
        if not qobject_valido(self._dialog) or self._interativo is None:
            return
        idx = int(self._interativo.get("idx", -1))
        if not (0 <= idx < len(canvas.cena.elementos)):
            return
        el = canvas.cena.elementos[idx]
        sobre_contorno = self._interativo.get("tipo") == "contorno"
        cor = self._cor_realce_canvas(canvas)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        if self._interativo.get("tipo") == "interno":
            inicio = self._interativo.get("inicio")
            fim = self._interativo.get("fim")
            if isinstance(inicio, QPointF) and isinstance(fim, QPointF):
                if hasattr(canvas, "_desenhar_segmento"):
                    canvas._desenhar_segmento(painter, inicio, fim, cor=cor, espessura=1.4)
                else:
                    painter.setPen(QPen(QColor(cor), 1))
                    painter.drawLine(canvas._cena_para_tela(inicio), canvas._cena_para_tela(fim))
        for ponto in self._preview_pontos:
            segmento_info = self._segmento_mais_proximo_elemento(el, ponto) if sobre_contorno else None
            segmento = (segmento_info[1], segmento_info[2]) if segmento_info is not None else None
            segmentos = self._segmentos_pique(
                el,
                QPointF(ponto),
                segmento,
                self._dialog.cmb_tipo.currentText(),
                self._dialog.largura(),
                self._dialog.altura(),
                self._dialog.angulo(),
                sobre_contorno=sobre_contorno,
            )
            for a, b in segmentos:
                pa = QPointF(float(a[0]), float(a[1]))
                pb = QPointF(float(b[0]), float(b[1]))
                if hasattr(canvas, "_desenhar_segmento"):
                    canvas._desenhar_segmento(painter, pa, pb, cor=cor, espessura=2.2)
                else:
                    painter.setPen(QPen(QColor(cor), 2))
                    painter.drawLine(canvas._cena_para_tela(pa), canvas._cena_para_tela(pb))
        painter.restore()

    def _hover_para_posicao(self, canvas, pos: QPointF) -> tuple[int, QPointF] | None:
        indices = {self._molde_idx} if self._molde_idx is not None else None
        alvo = self._alvo_no_contorno(canvas, pos, indices=indices)
        if alvo is not None:
            if qobject_valido(self._dialog):
                self._dialog.set_sobre_contorno(True)
            return alvo
        idx = self._molde_idx if self._molde_idx is not None else self._molde_em_posicao(canvas, pos)
        if idx is not None and self._ponto_dentro_molde(canvas.cena.elementos[idx], pos):
            if qobject_valido(self._dialog):
                self._dialog.set_sobre_contorno(False)
            return idx, QPointF(pos)
        return None

    def _projecao_contorno(self, el: dict, pos: QPointF) -> tuple[QPointF, float, float, float] | None:
        segmentos = self._segmentos_contorno_com_distancia(el)
        if not segmentos:
            return None
        melhor: tuple[float, QPointF, float] | None = None
        total = sum(comp for _a, _b, comp, _inicio in segmentos)
        for a, b, comp, inicio in segmentos:
            proj = self._projetar_ponto_segmento(pos, a, b)
            dist = self._dist(pos, proj)
            frac = self._fracao_no_segmento(proj, a, b) if comp > 1e-12 else 0.0
            s = inicio + (comp * frac)
            if melhor is None or dist < melhor[0]:
                melhor = (dist, proj, s)
        if melhor is None:
            return None
        dist, ponto, s = melhor
        return QPointF(ponto), float(s % total if total > 1e-9 else 0.0), float(total), float(dist)

    def _segmentos_contorno_com_distancia(self, el: dict) -> list[tuple[QPointF, QPointF, float, float]]:
        base = [self._ponto_qt(item) for item in el.get("pontos", []) or []]
        base = [p for p in base if p is not None]
        if len(base) >= 2 and self._dist(base[0], base[-1]) <= 1e-6:
            base = base[:-1]
        if len(base) < 2:
            return []
        acumulado = 0.0
        segmentos: list[tuple[QPointF, QPointF, float, float]] = []
        for a, b in zip(base, base[1:] + [base[0]]):
            comp = self._dist(a, b)
            if comp <= 1e-9:
                continue
            segmentos.append((QPointF(a), QPointF(b), comp, acumulado))
            acumulado += comp
        return segmentos

    def _pontos_uniformes_intervalo_contorno(
        self,
        el: dict,
        s_inicio: float,
        progresso: float,
        quantidade: int,
    ) -> list[QPointF]:
        segmentos = self._segmentos_contorno_com_distancia(el)
        total = sum(comp for _a, _b, comp, _inicio in segmentos)
        distancia = abs(float(progresso))
        if not segmentos or total <= 1e-9 or distancia <= 1e-6:
            return []
        sinal = 1.0 if progresso >= 0.0 else -1.0
        qtd = max(1, int(quantidade))
        passo = distancia / float(qtd + 1)
        pontos: list[QPointF] = []
        for n in range(1, qtd + 1):
            s = (float(s_inicio) + (sinal * passo * n)) % total
            pontos.append(self._ponto_em_distancia_contorno(segmentos, s))
        return pontos

    @staticmethod
    def _ponto_em_distancia_contorno(segmentos: list[tuple[QPointF, QPointF, float, float]], distancia: float) -> QPointF:
        total = sum(comp for _a, _b, comp, _inicio in segmentos)
        if total <= 1e-9:
            return QPointF()
        alvo = float(distancia) % total
        ultimo = segmentos[-1][1]
        for a, b, comp, inicio in segmentos:
            if alvo <= inicio + comp:
                t = max(0.0, min(1.0, (alvo - inicio) / comp if comp > 1e-12 else 0.0))
                return QPointF(a.x() + ((b.x() - a.x()) * t), a.y() + ((b.y() - a.y()) * t))
            ultimo = b
        return QPointF(ultimo)

    @staticmethod
    def _pontos_uniformes_linha(inicio: QPointF, fim: QPointF, quantidade: int) -> list[QPointF]:
        dx = fim.x() - inicio.x()
        dy = fim.y() - inicio.y()
        if sqrt((dx * dx) + (dy * dy)) <= 1e-6:
            return []
        qtd = max(1, int(quantidade))
        pontos: list[QPointF] = []
        for n in range(1, qtd + 1):
            t = n / float(qtd + 1)
            pontos.append(QPointF(inicio.x() + (dx * t), inicio.y() + (dy * t)))
        return pontos

    def _posicao_interna_com_snap_angular(self, canvas, inicio: QPointF, pos: QPointF) -> QPointF:
        if hasattr(canvas, "_snap_angular"):
            try:
                return QPointF(canvas._snap_angular(inicio, pos, travar_principais=True))
            except Exception:
                pass
        if not bool(getattr(canvas, "_snap_ativo", True)):
            return QPointF(pos)
        dx = pos.x() - inicio.x()
        dy = pos.y() - inicio.y()
        dist = sqrt((dx * dx) + (dy * dy))
        if dist <= 1e-9:
            return QPointF(pos)
        ang = degrees(atan2(-dy, dx))
        passo = float(getattr(canvas, "_snap_angular_passo", 45.0) or 45.0)
        passo = max(1.0, passo)
        ang_travado = round(ang / passo) * passo
        return QPointF(inicio.x() + (dist * cos(radians(ang_travado))), inicio.y() - (dist * sin(radians(ang_travado))))

    def _pontos_uniformes_contorno(self, el: dict, quantidade: int) -> list[QPointF]:
        pontos = [self._ponto_qt(item) for item in el.get("pontos", []) or []]
        pontos = [p for p in pontos if p is not None]
        if len(pontos) < 2:
            return []
        segmentos: list[tuple[QPointF, QPointF, float]] = []
        total = 0.0
        for a, b in zip(pontos, pontos[1:]):
            comp = self._dist(a, b)
            if comp <= 1e-9:
                continue
            segmentos.append((a, b, comp))
            total += comp
        if total <= 1e-9:
            return []

        qtd = max(1, int(quantidade))
        passo = total / float(qtd + 1)
        saida: list[QPointF] = []
        for n in range(1, qtd + 1):
            distancia = passo * n
            saida.append(self._ponto_no_contorno(segmentos, distancia))
        return saida

    @staticmethod
    def _ponto_no_contorno(segmentos: list[tuple[QPointF, QPointF, float]], distancia: float) -> QPointF:
        restante = max(0.0, float(distancia))
        ultimo = segmentos[-1][1]
        for a, b, comp in segmentos:
            if restante <= comp:
                t = restante / comp if comp > 1e-12 else 0.0
                return QPointF(a.x() + ((b.x() - a.x()) * t), a.y() + ((b.y() - a.y()) * t))
            restante -= comp
            ultimo = b
        return QPointF(ultimo)

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
            return False
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
