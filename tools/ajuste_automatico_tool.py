from __future__ import annotations

from math import atan2, cos, hypot, radians, sin

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap, QTransform
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QLineEdit,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QVBoxLayout,
)

from config import ICONS_DIR
from tools.tool_base import FerramentaBase
from ui.posicao_janelas import instalar_memoria_posicao, salvar_posicao


class PreviewOrientacaoAa(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._angulo = 0
        self.setAlignment(Qt.AlignCenter)
        self.setFixedSize(90, 62)
        self.setStyleSheet("background:#ffffff; border:1px solid #999999;")
        self._pixmap_base = self._carregar_pixmap_base()
        self.atualizar_angulo(0)

    def _carregar_pixmap_base(self) -> QPixmap:
        caminho = ICONS_DIR / "Aa.svg"
        if caminho.exists():
            pix = QIcon(str(caminho)).pixmap(64, 44)
            if not pix.isNull():
                return pix
        pix = QPixmap(64, 44)
        pix.fill(Qt.transparent)
        painter = QPainter(pix)
        try:
            painter.setPen(Qt.NoPen)
            painter.setBrush(Qt.darkGray)
            painter.drawPolygon([
                QPointF(18, 34),
                QPointF(46, 34),
                QPointF(46, 10),
            ])
        finally:
            painter.end()
        return pix

    def atualizar_angulo(self, angulo: int):
        self._angulo = int(angulo) % 360
        canvas = QPixmap(self.width(), self.height())
        canvas.fill(Qt.transparent)
        painter = QPainter(canvas)
        try:
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.translate(self.width() / 2.0, self.height() / 2.0)
            # No canvas do GUIMMA, 0° aponta para a direita. O ícone Aa.svg é desenhado
            # para essa referência e gira conforme a opção marcada.
            painter.rotate(-float(self._angulo))
            painter.drawPixmap(
                int(-self._pixmap_base.width() / 2),
                int(-self._pixmap_base.height() / 2),
                self._pixmap_base,
            )
        finally:
            painter.end()
        self.setPixmap(canvas)


class AjusteAutomaticoDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._chave_posicao = "dialog:ajuste_automatico_textos_fio"
        self.setWindowTitle("Auto Ajuste de Textos")
        self.setModal(False)
        self.setWindowFlag(Qt.Tool, True)
        self.setMinimumWidth(420)
        self.setStyleSheet(
            """
            QDialog { background:#f4f4f4; color:#111111; }
            QLabel, QCheckBox, QRadioButton, QGroupBox { color:#111111; font-size:12px; }
            QGroupBox { border:1px solid #d7d7d7; margin-top:8px; padding-top:8px; }
            QGroupBox::title { subcontrol-origin: margin; left:8px; padding:0 3px; }
            QLineEdit { background:#ffffff; color:#111111; border:1px solid #c7c7c7; min-height:22px; padding-left:4px; }
            QPushButton { min-width:84px; min-height:26px; }
            """
        )

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(8, 8, 8, 8)
        raiz.setSpacing(6)

        gb_textos = QGroupBox("Textos")
        lay_textos = QGridLayout(gb_textos)
        lay_textos.setHorizontalSpacing(10)
        lay_textos.setVerticalSpacing(8)

        self.chk_ajustar_textos = QCheckBox("Ajustar tamanho dos textos")
        self.chk_ajustar_textos.setChecked(True)
        lay_textos.addWidget(self.chk_ajustar_textos, 0, 0, 1, 2)

        lay_textos.addWidget(QLabel("Tamanho mínimo (cm)"), 1, 0)
        self.sp_texto_min = self._spin(0.0, 30.0, 0.0, 0.1)
        lay_textos.addWidget(self.sp_texto_min, 1, 1)

        lay_textos.addWidget(QLabel("Tamanho máximo (cm)"), 2, 0)
        self.sp_texto_max = self._spin(0.1, 30.0, 2.0, 0.1)
        lay_textos.addWidget(self.sp_texto_max, 2, 1)

        coluna_orientacao = QGroupBox("")
        coluna_orientacao.setFlat(True)
        orient = QGridLayout(coluna_orientacao)
        orient.setContentsMargins(0, 0, 0, 0)
        orient.setHorizontalSpacing(4)
        orient.setVerticalSpacing(2)
        self.chk_orientacao_manual = QCheckBox("Orientação manual")
        self.chk_orientacao_manual.setChecked(True)
        orient.addWidget(self.chk_orientacao_manual, 0, 0, 1, 3)
        self.grp_orientacao = QButtonGroup(self)
        self.rb_90 = QRadioButton("90°")
        self.rb_180 = QRadioButton("180°")
        self.rb_0 = QRadioButton("0°")
        self.rb_270 = QRadioButton("270°")
        for valor, rb in ((90, self.rb_90), (180, self.rb_180), (0, self.rb_0), (270, self.rb_270)):
            self.grp_orientacao.addButton(rb, valor)
        self.rb_0.setChecked(True)
        self.preview_orientacao = PreviewOrientacaoAa()
        self.grp_orientacao.buttonClicked.connect(
            lambda *_: self.preview_orientacao.atualizar_angulo(self.grp_orientacao.checkedId())
        )
        orient.addWidget(self.rb_90, 1, 1, Qt.AlignCenter)
        orient.addWidget(self.rb_180, 2, 0, Qt.AlignVCenter)
        orient.addWidget(self.preview_orientacao, 2, 1, 2, 1)
        orient.addWidget(self.rb_0, 2, 2, Qt.AlignVCenter)
        orient.addWidget(self.rb_270, 4, 1, Qt.AlignCenter)
        lay_textos.addWidget(coluna_orientacao, 0, 2, 3, 1)
        lay_textos.setColumnStretch(2, 1)
        raiz.addWidget(gb_textos)

        gb_numeros = QGroupBox("Números")
        lay_numeros = QGridLayout(gb_numeros)
        lay_numeros.setHorizontalSpacing(10)
        lay_numeros.setVerticalSpacing(8)
        self.chk_ajustar_numeros = QCheckBox("Ajustar tamanho dos números")
        self.chk_ajustar_numeros.setChecked(True)
        lay_numeros.addWidget(self.chk_ajustar_numeros, 0, 0, 1, 2)
        lay_numeros.addWidget(QLabel("Tamanho mínimo (cm)"), 1, 0)
        self.sp_numero_min = self._spin(0.0, 30.0, 0.2, 0.1)
        lay_numeros.addWidget(self.sp_numero_min, 1, 1)
        lay_numeros.addWidget(QLabel("Tamanho máximo (cm)"), 2, 0)
        self.sp_numero_max = self._spin(0.1, 30.0, 0.8, 0.1)
        lay_numeros.addWidget(self.sp_numero_max, 2, 1)
        lay_numeros.setColumnStretch(2, 1)
        raiz.addWidget(gb_numeros)

        gb_fio = QGroupBox("Fio")
        lay_fio = QGridLayout(gb_fio)
        lay_fio.setHorizontalSpacing(10)
        lay_fio.setVerticalSpacing(8)
        self.chk_auto_fio = QCheckBox("Auto ajustar fio")
        self.chk_auto_fio.setChecked(True)
        lay_fio.addWidget(self.chk_auto_fio, 0, 0, 1, 2)
        lay_fio.addWidget(QLabel("Tamanho mínimo (cm)"), 1, 0)
        self.sp_fio_min = self._spin(0.0, 1000.0, 0.5, 0.1)
        lay_fio.addWidget(self.sp_fio_min, 1, 1)
        lay_fio.addWidget(QLabel("Tamanho máximo (cm)"), 2, 0)
        self.sp_fio_max = self._spin(0.1, 1000.0, 3.0, 0.1)
        lay_fio.addWidget(self.sp_fio_max, 2, 1)
        self.chk_centralizar = QCheckBox("Centralizar textos e fio dentro do molde")
        self.chk_centralizar.setChecked(True)
        lay_fio.addWidget(self.chk_centralizar, 3, 0, 1, 2)
        lay_fio.setColumnStretch(2, 1)
        raiz.addWidget(gb_fio)

        linha = QHBoxLayout()
        linha.addStretch(1)
        self.botoes = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.botoes.button(QDialogButtonBox.Ok).setText("✓  Ok")
        self.botoes.button(QDialogButtonBox.Cancel).setText("✕  Cancelar")
        linha.addWidget(self.botoes)
        raiz.addLayout(linha)

    def _spin(self, minimo: float, maximo: float, valor: float, passo: float) -> QLineEdit:
        campo = QLineEdit()
        campo.setText(self._formatar_numero_simples(valor))
        campo.setFixedWidth(78)
        campo.setToolTip("Use números simples: 1 = 1 cm, 2 = 2 cm, 0.5 = meio cm")
        campo.editingFinished.connect(lambda c=campo, mn=minimo, mx=maximo: self._normalizar_campo(c, mn, mx))
        return campo

    def _formatar_numero_simples(self, valor: float) -> str:
        txt = f"{float(valor):.4f}".rstrip("0").rstrip(".")
        return txt or "0"

    def _ler_numero(self, campo: QLineEdit, padrao: float, minimo: float, maximo: float) -> float:
        try:
            valor = float(str(campo.text()).strip().replace(",", "."))
        except Exception:
            valor = float(padrao)
        valor = max(float(minimo), min(float(maximo), valor))
        return valor

    def _normalizar_campo(self, campo: QLineEdit, minimo: float, maximo: float):
        valor = self._ler_numero(campo, 0.0, minimo, maximo)
        campo.setText(self._formatar_numero_simples(valor))

    def opcoes(self) -> dict:
        texto_min_raw = self._ler_numero(self.sp_texto_min, 0.0, 0.0, 30.0)
        texto_max_raw = self._ler_numero(self.sp_texto_max, 2.0, 0.0, 30.0)
        numero_min_raw = self._ler_numero(self.sp_numero_min, 0.2, 0.0, 30.0)
        numero_max_raw = self._ler_numero(self.sp_numero_max, 0.8, 0.0, 30.0)
        fio_min_raw = self._ler_numero(self.sp_fio_min, 0.5, 0.0, 1000.0)
        fio_max_raw = self._ler_numero(self.sp_fio_max, 3.0, 0.0, 1000.0)
        texto_min = min(texto_min_raw, texto_max_raw)
        texto_max = max(texto_min_raw, texto_max_raw)
        numero_min = min(numero_min_raw, numero_max_raw)
        numero_max = max(numero_min_raw, numero_max_raw)
        fio_min = min(fio_min_raw, fio_max_raw)
        fio_max = max(fio_min_raw, fio_max_raw)
        return {
            "ajustar_textos": bool(self.chk_ajustar_textos.isChecked()),
            "texto_min": texto_min,
            "texto_max": texto_max,
            "orientacao_manual": bool(self.chk_orientacao_manual.isChecked()),
            "orientacao": int(self.grp_orientacao.checkedId()),
            "ajustar_numeros": bool(self.chk_ajustar_numeros.isChecked()),
            "numero_min": numero_min,
            "numero_max": numero_max,
            "auto_fio": bool(self.chk_auto_fio.isChecked()),
            "fio_min": fio_min,
            "fio_max": fio_max,
            "centralizar": bool(self.chk_centralizar.isChecked()),
        }


class Ferramenta(FerramentaBase):
    id_ferramenta = "ajuste_automatico"
    nome = "Auto Ajuste"
    usa_painel_auxiliar = False
    descricao_painel = "Ajusta automaticamente nome, fio e posição dos textos dos moldes."

    _dialog_por_canvas: dict[int, AjusteAutomaticoDialog] = {}

    def on_activate(self, canvas):
        super().on_activate(canvas)
        dialog = self._obter_dialog(canvas)
        self._restaurar_dialog(canvas, dialog)
        try:
            dialog.botoes.accepted.disconnect()
        except Exception:
            pass
        try:
            dialog.botoes.rejected.disconnect()
        except Exception:
            pass
        dialog.botoes.accepted.connect(lambda: self._aplicar_e_fechar(canvas, dialog))
        dialog.botoes.rejected.connect(dialog.hide)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        self._status(canvas, "Auto ajuste: configure e confirme para aplicar no selecionado ou em todos os moldes.")

    def on_deactivate(self, canvas):
        dialog = self._dialog_por_canvas.get(id(canvas))
        if dialog is not None:
            dialog.hide()

    def _obter_dialog(self, canvas) -> AjusteAutomaticoDialog:
        chave = id(canvas)
        parent = canvas.window() if hasattr(canvas, "window") else canvas
        dialog = self._dialog_por_canvas.get(chave)
        if dialog is None or dialog.parentWidget() is not parent:
            dialog = AjusteAutomaticoDialog(parent)
            self._dialog_por_canvas[chave] = dialog
            instalar_memoria_posicao(dialog, dialog._chave_posicao)
        return dialog

    def _restaurar_dialog(self, canvas, dialog: AjusteAutomaticoDialog):
        """Abre o Auto Ajuste sempre abaixo da caixa de Coordenadas.

        O diálogo é criado tendo a janela principal como parent, enquanto o painel
        de coordenadas é filho do canvas. Por isso não podemos usar painel.x()/y()
        diretamente: essas coordenadas são relativas ao canvas e acabavam colocando
        o Auto Ajuste em posição errada, por cima/acima da caixa de Coordenadas.
        Aqui convertemos a posição do painel para o mesmo sistema de coordenadas
        do parent do diálogo e só então calculamos a posição abaixo.
        """
        dialog.adjustSize()

        margem = 12
        parent = dialog.parentWidget()
        painel = getattr(canvas, "painel_coordenadas", None)

        def _limitar_no_parent(pos: QPoint) -> QPoint:
            if parent is None:
                return pos
            largura_parent = max(1, parent.width())
            altura_parent = max(1, parent.height())
            x = max(8, min(pos.x(), largura_parent - dialog.width() - 8))
            y = max(8, min(pos.y(), altura_parent - dialog.height() - 8))
            return QPoint(x, y)

        # Fallback: canto superior direito do canvas, mas já convertido para o parent.
        try:
            origem_canvas_no_parent = canvas.mapTo(parent, QPoint(0, 0)) if parent is not None else QPoint(0, 0)
        except Exception:
            origem_canvas_no_parent = QPoint(0, 0)
        posicao = QPoint(
            origem_canvas_no_parent.x() + max(24, canvas.width() - dialog.width() - 36),
            origem_canvas_no_parent.y() + 48,
        )

        try:
            if painel is not None and painel.isVisible():
                if parent is not None:
                    topo_painel = painel.mapTo(parent, QPoint(0, 0))
                else:
                    topo_painel = QPoint(painel.x(), painel.y())

                # Alinha a direita do Auto Ajuste com a direita da caixa de Coordenadas
                # e posiciona logo abaixo dela, como na referência enviada.
                posicao = QPoint(
                    topo_painel.x() + painel.width() - dialog.width(),
                    topo_painel.y() + painel.height() + margem,
                )
        except Exception:
            pass

        posicao = _limitar_no_parent(posicao)
        dialog.move(posicao)
        salvar_posicao(dialog, dialog._chave_posicao)

    def _aplicar_e_fechar(self, canvas, dialog: AjusteAutomaticoDialog):
        quantidade = self.aplicar(canvas, dialog.opcoes())
        dialog.hide()
        if quantidade <= 0:
            self._status(canvas, "Auto ajuste: nenhum molde encontrado.")
        elif quantidade == 1:
            self._status(canvas, "Auto ajuste aplicado em 1 molde.")
        else:
            self._status(canvas, f"Auto ajuste aplicado em {quantidade} moldes.")

    def aplicar(self, canvas, opcoes: dict) -> int:
        if canvas is None or not hasattr(canvas, "cena"):
            return 0
        indices = self._indices_alvo(canvas)
        if not indices:
            return 0
        for idx in indices:
            el = canvas.cena.elementos[idx]
            self._ajustar_molde(el, opcoes)
        if hasattr(canvas, "_selecionados") and len(indices) == 1:
            canvas._selecionados = {indices[0]}
        if hasattr(canvas, "_registrar_historico"):
            canvas._registrar_historico()
        canvas.update()
        return len(indices)

    def _indices_alvo(self, canvas) -> list[int]:
        selecionados = [int(i) for i in sorted(getattr(canvas, "_selecionados", set()) or [])]
        moldes_sel = [i for i in selecionados if 0 <= i < len(canvas.cena.elementos) and canvas.cena.elementos[i].get("molde")]
        if moldes_sel:
            return moldes_sel
        return [i for i, el in enumerate(canvas.cena.elementos) if isinstance(el, dict) and el.get("molde")]

    def _ajustar_molde(self, el: dict, op: dict) -> None:
        pontos = self._pontos_molde(el)
        if len(pontos) < 3:
            return
        bbox = self._bbox(pontos)
        centro = self._ponto_central_interno(pontos, bbox)
        textos_ativos = self._textos_ativos(el)

        # Remove as chaves antigas em pixel que faziam letras/fio ficarem enormes
        # quando o molde estava com pouco zoom. A unidade correta desta ferramenta
        # agora é sempre CENTÍMETRO de cena: 1 = 1 cm, 0.5 = meio cm.
        for chave in (
            "nome_tamanho_px", "tam_nome_px", "tamanho_nome_px",
            "fio_tamanho_px", "tam_fio_px", "tamanho_fio_px",
        ):
            el.pop(chave, None)

        if op.get("ajustar_textos", True):
            tamanhos_textos = {
                chave: self._tamanho_texto(el, bbox, op, chave)
                for chave in textos_ativos
            }
            if op.get("centralizar", True) and textos_ativos:
                posicoes = self._posicoes_textos_centralizados(centro, bbox, textos_ativos, tamanhos_textos)
                for chave, ponto in posicoes.items():
                    self._aplicar_posicao_texto(el, chave, ponto)
            for chave in textos_ativos:
                tamanho_cm = tamanhos_textos[chave]
                el[f"texto_{chave}_altura_cm"] = tamanho_cm
                if op.get("centralizar", True):
                    el[f"referencia_texto_{chave}"] = "Livre"
                    el[f"alinhamento_texto_{chave}"] = "Centro"
                if op.get("orientacao_manual", False):
                    el[f"texto_{chave}_angulo"] = float(op.get("orientacao", 0))
                if chave == "nome":
                    el["tam_nome"] = tamanho_cm
                    el["tamanho_nome"] = tamanho_cm
                    el["fonte_nome"] = tamanho_cm
                    if op.get("orientacao_manual", False):
                        el["nome_angulo"] = float(op.get("orientacao", 0))

        if op.get("ajustar_numeros", True):
            el["numero_altura_cm"] = self._tamanho_numeros(el, bbox, op)
            el["mostrar_numeros"] = True

        if op.get("auto_fio", True):
            tamanho_texto = max(
                [float(el.get(f"texto_{chave}_altura_cm") or 0.0) for chave in textos_ativos] or [0.0]
            )
            centro_fio = self._centro_fio_abaixo_textos(centro, bbox, el, textos_ativos, tamanho_texto)
            p1, p2, ang = self._calcular_fio(el, pontos, bbox, centro_fio, op)
            el["fio_origem"] = (float(p1.x()), float(p1.y()))
            el["fio_fim"] = (float(p2.x()), float(p2.y()))
            el["fio_angulo"] = float(ang)
            el["mostrar_fio"] = True
            tamanho_fio_cm = max(0.05, min(float(op.get("fio_max", 3.0)), self._dist(p1, p2)))
            el["tam_fio"] = max(0.15, min(0.8, tamanho_fio_cm * 0.18))
            el["tamanho_fio"] = el["tam_fio"]
            el["fonte_fio"] = el["tam_fio"]

    def _textos_ativos(self, el: dict) -> list[str]:
        ativos: list[str] = []
        if str(el.get("nome_molde") or "").strip() or el.get("mostrar_nome", True):
            ativos.append("nome")
        if str(el.get("descricao") or "").strip() or el.get("visual_descricao", False):
            ativos.append("descricao")
        if str(el.get("observacoes") or el.get("observacao") or "").strip() or el.get("visual_observacoes", False):
            ativos.append("observacoes")
        return ativos

    def _texto_molde(self, el: dict, chave: str) -> str:
        if chave == "nome":
            return str(el.get("nome_molde") or "").strip()
        if chave == "descricao":
            return str(el.get("descricao") or "").strip()
        return str(el.get("observacoes") or el.get("observacao") or "").strip()

    def _posicoes_textos_centralizados(
        self,
        centro: QPointF,
        bbox: tuple[float, float, float, float],
        textos: list[str],
        tamanhos: dict[str, float],
    ) -> dict[str, QPointF]:
        altura_molde = max(0.1, bbox[3] - bbox[1])
        passo_minimo = max(0.25, altura_molde * 0.08)
        alturas = [max(0.05, float(tamanhos.get(chave, 0.0))) for chave in textos]
        espacos = [max(passo_minimo, altura * 1.15) for altura in alturas]
        altura_total = sum(espacos)
        y = centro.y() - (altura_total / 2.0)
        posicoes: dict[str, QPointF] = {}
        for chave, espaco in zip(textos, espacos):
            y += espaco / 2.0
            posicoes[chave] = QPointF(centro.x(), y)
            y += espaco / 2.0
        return posicoes

    def _aplicar_posicao_texto(self, el: dict, chave: str, ponto: QPointF) -> None:
        valor = (float(ponto.x()), float(ponto.y()))
        el[f"ponto_texto_{chave}"] = valor
        if chave == "nome":
            el["ponto_texto"] = valor
            el["nome_posicao"] = valor
            el["nome_centro"] = valor
            el["mostrar_nome"] = True
        elif chave == "descricao":
            el["visual_descricao"] = True
        elif chave == "observacoes":
            el["visual_observacoes"] = True

    def _pontos_molde(self, el: dict) -> list[QPointF]:
        pontos: list[QPointF] = []
        for item in el.get("pontos", []) or []:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                try:
                    pontos.append(QPointF(float(item[0]), float(item[1])))
                except Exception:
                    pass
        if len(pontos) >= 2 and self._dist(pontos[0], pontos[-1]) <= 1e-9:
            pontos = pontos[:-1]
        return pontos

    def _bbox(self, pontos: list[QPointF]) -> tuple[float, float, float, float]:
        xs = [p.x() for p in pontos]
        ys = [p.y() for p in pontos]
        return min(xs), min(ys), max(xs), max(ys)

    def _ponto_central_interno(self, pontos: list[QPointF], bbox: tuple[float, float, float, float]) -> QPointF:
        area = 0.0
        cx = 0.0
        cy = 0.0
        for a, b in zip(pontos, pontos[1:] + pontos[:1]):
            cross = (a.x() * b.y()) - (b.x() * a.y())
            area += cross
            cx += (a.x() + b.x()) * cross
            cy += (a.y() + b.y()) * cross
        if abs(area) > 1e-9:
            centro = QPointF(cx / (3.0 * area), cy / (3.0 * area))
            if self._ponto_dentro_poligono(centro, pontos):
                return centro

        min_x, min_y, max_x, max_y = bbox
        centro_bbox = QPointF((min_x + max_x) / 2.0, (min_y + max_y) / 2.0)
        if self._ponto_dentro_poligono(centro_bbox, pontos):
            return centro_bbox

        melhor = pontos[0]
        melhor_dist = -1.0
        largura = max(max_x - min_x, 1e-9)
        altura = max(max_y - min_y, 1e-9)
        for ix in range(1, 10):
            for iy in range(1, 10):
                p = QPointF(min_x + (largura * ix / 10.0), min_y + (altura * iy / 10.0))
                if not self._ponto_dentro_poligono(p, pontos):
                    continue
                dist = min(self._dist_ponto_segmento(p, a, b) for a, b in zip(pontos, pontos[1:] + pontos[:1]))
                if dist > melhor_dist:
                    melhor = p
                    melhor_dist = dist
        return QPointF(melhor)

    def _tamanho_texto(self, el: dict, bbox: tuple[float, float, float, float], op: dict, chave: str = "nome") -> float:
        texto = self._texto_molde(el, chave)
        min_cm = float(op.get("texto_min", 0.0))
        max_cm = float(op.get("texto_max", 2.0))
        largura = max(0.0, bbox[2] - bbox[0])
        altura = max(0.0, bbox[3] - bbox[1])
        menor_lado = max(0.1, min(largura, altura))
        maior_lado = max(0.1, max(largura, altura))
        # Mantém o tamanho em centímetros de cena para acompanhar o zoom junto com o molde.
        # Depois o canvas ainda reduz se o texto encostar nos limites do molde.
        por_altura = menor_lado * 0.35
        por_largura = maior_lado / max(2.5, max(1, len(texto)) * 0.62)
        cm = min(max_cm, por_altura, por_largura)
        if min_cm > 0:
            cm = max(min_cm, cm)
        return max(0.05, min(max_cm if max_cm > 0 else 0.05, cm))

    def _tamanho_numeros(self, el: dict, bbox: tuple[float, float, float, float], op: dict) -> float:
        min_cm = float(op.get("numero_min", 0.2))
        max_cm = float(op.get("numero_max", 0.8))
        largura = max(0.0, bbox[2] - bbox[0])
        altura = max(0.0, bbox[3] - bbox[1])
        menor_lado = max(0.1, min(largura, altura))
        maior_lado = max(0.1, max(largura, altura))
        total_pontos = max(1, len(el.get("controle_cantos") or el.get("pontos") or []))
        digitos = max(1, len(str(total_pontos)))
        por_altura = menor_lado * 0.12
        por_largura = maior_lado / max(8.0, digitos * 7.0)
        cm = min(max_cm, por_altura, por_largura)
        if min_cm > 0:
            cm = max(min_cm, cm)
        return max(0.05, min(max_cm if max_cm > 0 else 0.05, cm))

    def _calcular_fio(
        self,
        el: dict,
        pontos: list[QPointF],
        bbox: tuple[float, float, float, float],
        centro: QPointF,
        op: dict,
    ) -> tuple[QPointF, QPointF, float]:
        if op.get("orientacao_manual", False):
            ang = float(op.get("orientacao", 0.0)) % 360.0
        else:
            ang = self._angulo_fio_atual(el)
        direcao = QPointF(cos(radians(ang)), -sin(radians(ang)))
        extremos = self._intersecoes_linha_poligono(centro, direcao, pontos)
        if len(extremos) >= 2:
            extremos.sort(key=lambda p: (p.x() - centro.x()) * direcao.x() + (p.y() - centro.y()) * direcao.y())
            a = extremos[0]
            b = extremos[-1]
        else:
            a, b = self._linha_por_bbox(centro, direcao, bbox)

        comprimento_disponivel = max(self._dist(a, b) * 0.76, 0.0)
        fio_min = max(0.0, float(op.get("fio_min", 0.5)))
        fio_max = max(fio_min, float(op.get("fio_max", 3.0)))
        comprimento = max(fio_min, min(fio_max, comprimento_disponivel))
        if comprimento_disponivel > 1e-9:
            comprimento = min(comprimento, comprimento_disponivel)
        metade = comprimento / 2.0
        p1 = QPointF(centro.x() - direcao.x() * metade, centro.y() - direcao.y() * metade)
        p2 = QPointF(centro.x() + direcao.x() * metade, centro.y() + direcao.y() * metade)
        return p1, p2, ang

    def _centro_fio_abaixo_textos(
        self,
        centro: QPointF,
        bbox: tuple[float, float, float, float],
        el: dict,
        textos: list[str],
        tamanho_texto: float,
    ) -> QPointF:
        min_x, min_y, max_x, max_y = bbox
        altura = max(0.0, max_y - min_y)
        y_base = centro.y()
        pontos_textos = []
        for chave in textos:
            valor = el.get(f"ponto_texto_{chave}")
            if isinstance(valor, (list, tuple)) and len(valor) >= 2:
                try:
                    pontos_textos.append(QPointF(float(valor[0]), float(valor[1])))
                except Exception:
                    pass
        if pontos_textos:
            y_base = max(p.y() for p in pontos_textos)
        deslocamento = max(0.25, float(tamanho_texto or 0.0) * 0.85, altura * 0.045)
        y = min(max_y - max(0.15, altura * 0.06), y_base + deslocamento)
        return QPointF(centro.x(), y)

    def _angulo_fio_atual(self, el: dict) -> float:
        try:
            return float(el.get("fio_angulo")) % 360.0
        except Exception:
            pass
        p1 = el.get("fio_origem")
        p2 = el.get("fio_fim")
        if isinstance(p1, (list, tuple)) and isinstance(p2, (list, tuple)) and len(p1) == 2 and len(p2) == 2:
            dx = float(p2[0]) - float(p1[0])
            dy = float(p1[1]) - float(p2[1])
            if abs(dx) > 1e-9 or abs(dy) > 1e-9:
                return atan2(dy, dx) * 180.0 / 3.141592653589793 % 360.0
        return 0.0

    def _linha_por_bbox(self, centro: QPointF, direcao: QPointF, bbox: tuple[float, float, float, float]) -> tuple[QPointF, QPointF]:
        min_x, min_y, max_x, max_y = bbox
        comprimento = max(max_x - min_x, max_y - min_y) * 0.6
        return (
            QPointF(centro.x() - direcao.x() * comprimento / 2.0, centro.y() - direcao.y() * comprimento / 2.0),
            QPointF(centro.x() + direcao.x() * comprimento / 2.0, centro.y() + direcao.y() * comprimento / 2.0),
        )

    def _intersecoes_linha_poligono(self, centro: QPointF, direcao: QPointF, pontos: list[QPointF]) -> list[QPointF]:
        saida: list[QPointF] = []
        for a, b in zip(pontos, pontos[1:] + pontos[:1]):
            inter = self._intersecao_linha_segmento(centro, direcao, a, b)
            if inter is None:
                continue
            if all(self._dist(inter, existente) > 1e-6 for existente in saida):
                saida.append(inter)
        return saida

    def _intersecao_linha_segmento(self, p: QPointF, d: QPointF, a: QPointF, b: QPointF) -> QPointF | None:
        sx = b.x() - a.x()
        sy = b.y() - a.y()
        den = (d.x() * sy) - (d.y() * sx)
        if abs(den) <= 1e-9:
            return None
        ax = a.x() - p.x()
        ay = a.y() - p.y()
        t = (ax * sy - ay * sx) / den
        u = (ax * d.y() - ay * d.x()) / den
        if -1e-9 <= u <= 1.0 + 1e-9:
            return QPointF(p.x() + d.x() * t, p.y() + d.y() * t)
        return None

    def _ponto_dentro_poligono(self, ponto: QPointF, pontos: list[QPointF]) -> bool:
        dentro = False
        x = ponto.x()
        y = ponto.y()
        j = len(pontos) - 1
        for i in range(len(pontos)):
            xi, yi = pontos[i].x(), pontos[i].y()
            xj, yj = pontos[j].x(), pontos[j].y()
            cruza = ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / max(yj - yi, 1e-12) + xi)
            if cruza:
                dentro = not dentro
            j = i
        return dentro

    def _dist_ponto_segmento(self, p: QPointF, a: QPointF, b: QPointF) -> float:
        abx = b.x() - a.x()
        aby = b.y() - a.y()
        denom = abx * abx + aby * aby
        if denom <= 1e-12:
            return self._dist(p, a)
        t = max(0.0, min(1.0, ((p.x() - a.x()) * abx + (p.y() - a.y()) * aby) / denom))
        proj = QPointF(a.x() + abx * t, a.y() + aby * t)
        return self._dist(p, proj)

    def _dist(self, a: QPointF, b: QPointF) -> float:
        return hypot(a.x() - b.x(), a.y() - b.y())

    def _status(self, canvas, texto: str):
        lbl = getattr(canvas, "lbl_status", None)
        if lbl is not None:
            lbl.setText(texto)
        else:
            janela = canvas.window() if hasattr(canvas, "window") else None
            lbl_janela = getattr(janela, "lbl_status", None)
            if lbl_janela is not None:
                lbl_janela.setText(texto)
