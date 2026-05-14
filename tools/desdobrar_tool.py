from __future__ import annotations

from math import isfinite
from time import monotonic

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QCheckBox, QDialog, QVBoxLayout

from config import ICONS_DIR
from tools.dobrar_tool import Ferramenta as _DobrarBase
from ui.posicao_janelas import instalar_memoria_posicao, restaurar_posicao


class DesdobrarDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._chave_posicao = "dialog:desdobrar"
        self.setWindowTitle("Desdobrar")
        self.setWindowFlag(Qt.Tool, True)
        self.setModal(False)
        self.setFixedWidth(220)
        check_icon = (ICONS_DIR / "check_marcado.svg").as_posix()
        self.setStyleSheet(
            """
            QDialog { background:#efefef; color:#111111; }
            QCheckBox { color:#111111; }
            QCheckBox::indicator {
                width:14px;
                height:14px;
                border:1px solid #6c7480;
                background:#ffffff;
            }
            QCheckBox::indicator:checked {
                image:url(__CHECK_ICON__);
                background:#ffffff;
                border:1px solid #075f8c;
            }
            """
            .replace("__CHECK_ICON__", check_icon)
        )

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(8, 8, 8, 8)
        raiz.setSpacing(6)
        self.chk_inserir_pique = QCheckBox("Inserir pique")
        self.chk_inserir_pique.setChecked(False)
        raiz.addWidget(self.chk_inserir_pique)


class Ferramenta(_DobrarBase):
    id_ferramenta = "desdobrar"
    nome = "Desdobrar"
    usa_painel_auxiliar = False
    descricao_painel = "Desdobra um molde usando um segmento do perímetro como eixo."

    _dialog_por_canvas: dict[int, DesdobrarDialog] = {}

    def __init__(self):
        super().__init__()
        self._molde_idx: int | None = None
        self._hover_idx = None
        self._ultimo_direito = 0.0

    def on_activate(self, canvas):
        self._resetar_desdobrar(canvas, limpar_selecao=False)
        dialog = self._obter_dialog(canvas)
        self._restaurar_dialog(canvas, dialog)
        dialog.show()
        dialog.raise_()
        self._status(canvas, "Desdobrar: clique em um molde. Depois passe o mouse no perímetro e clique para desdobrar.")

    def on_deactivate(self, canvas):
        dialog = self._dialog_por_canvas.get(id(canvas))
        if dialog is not None:
            dialog.hide()
        self._resetar_desdobrar(canvas, limpar_selecao=False)
        canvas.update()

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() == Qt.RightButton:
            if self._molde_idx is not None:
                self._resetar_desdobrar(canvas, limpar_selecao=True)
                self._status(canvas, "Desdobrar cancelado. Clique em um molde para começar novamente.")
                event.accept()
                return True
            agora = monotonic()
            if agora - self._ultimo_direito <= 0.45:
                canvas.set_ferramenta_ativa("selecionar")
                self._status(canvas, "Ferramenta Desdobrar finalizada. Voltando para Selecionar.")
            else:
                self._status(canvas, "Clique direito novamente para finalizar Desdobrar.")
            self._ultimo_direito = agora
            event.accept()
            return True
        if event.button() != Qt.LeftButton:
            return False

        pos = canvas._ponto_com_snap(event.position())
        if self._molde_idx is None:
            molde_idx = canvas._indice_molde_em_ponto(pos) if hasattr(canvas, "_indice_molde_em_ponto") else None
            if molde_idx is None:
                self._status(canvas, "Desdobrar: clique sobre um molde primeiro.")
                event.accept()
                return True
            self._molde_idx = int(molde_idx)
            canvas._selecionados = {self._molde_idx}
            self._hover_idx = None
            canvas.update()
            self._status(canvas, "Molde selecionado. Passe o mouse sobre o perímetro para escolher o eixo.")
            event.accept()
            return True

        alvo = self._hover_idx
        if alvo is None:
            alvo = self._linha_interna_em_ponto(canvas, self._molde_idx, pos)
        if alvo is None:
            self._status(canvas, "Passe o mouse sobre um segmento do perímetro e clique para desdobrar.")
            event.accept()
            return True
        self._aplicar_desdobrar(canvas, self._molde_idx, alvo)
        event.accept()
        return True

    def on_mouse_move(self, canvas, event) -> bool:
        if self._molde_idx is None:
            return False
        pos = canvas._ponto_com_snap(event.position())
        self._hover_idx = self._linha_interna_em_ponto(canvas, self._molde_idx, pos)
        canvas.update()
        return True

    def on_paint_overlay(self, canvas, painter):
        if self._molde_idx is None or self._hover_idx is None:
            return
        el = self._elemento_linha_ref(canvas, self._hover_idx)
        if el is None:
            return
        pontos = self._pontos_para_preview_linha(el)
        if len(pontos) < 2:
            return
        painter.save()
        cor = QColor(getattr(canvas, "_cores_canvas", {}).get("selecao", "#2da8ff"))
        painter.setPen(QPen(cor, 2.2, Qt.SolidLine))
        for a, b in zip(pontos, pontos[1:]):
            painter.drawLine(canvas._cena_para_tela(a), canvas._cena_para_tela(b))
        painter.restore()

    def _aplicar_desdobrar(self, canvas, molde_idx: int, linha_ref) -> None:
        if not (0 <= molde_idx < len(canvas.cena.elementos)):
            return
        molde = canvas.cena.elementos[molde_idx]
        linha = self._elemento_linha_ref(canvas, linha_ref)
        if linha is None:
            self._status(canvas, "Linha escolhida inválida para desdobrar.")
            return
        eixo = self._eixo_linha(linha)
        if eixo is None:
            self._status(canvas, "A linha escolhida não tem extremidades válidas para desdobrar.")
            return
        if self._restaurar_dobra_original(canvas, molde_idx, molde, linha, eixo):
            return
        pontos = self._pontos_elemento(molde)
        if len(pontos) < 3:
            self._status(canvas, "Molde sem contorno suficiente para desdobrar.")
            return
        base = pontos[:-1] if self._pontos_mesmos(pontos[0], pontos[-1]) else list(pontos)
        espelhado = [self._espelhar_ponto(p, eixo) for p in base]
        unidos = self._unir_poligonos(base, espelhado)
        if len(unidos) < 3:
            self._status(canvas, "Não foi possível formar o contorno desdobrado.")
            return
        if not self._pontos_mesmos(unidos[0], unidos[-1]):
            unidos.append(QPointF(unidos[0]))
        cantos = unidos[:-1] if self._pontos_mesmos(unidos[0], unidos[-1]) else unidos
        self._garantir_pontos_controle_eixo(cantos, eixo)
        if self._inserir_pique_ativo(canvas):
            self._inserir_piques_eixo(molde, eixo)
        molde["pontos"] = [(p.x(), p.y()) for p in unidos]
        molde["controle_cantos"] = [(p.x(), p.y()) for p in cantos]
        molde["pontos_controle_referencia"] = [(p.x(), p.y()) for p in cantos]
        molde["molde_dobrado"] = False
        molde["dobra_horizontal"] = False
        molde["dobra_vertical"] = False
        molde.pop("contornos_dobra_original", None)
        molde.setdefault("metadados", {})["ultima_transformacao"] = "desdobrar"
        canvas._selecionados = {molde_idx}
        canvas._registrar_historico()
        self._resetar_desdobrar(canvas, limpar_selecao=False)
        canvas._selecionados = {molde_idx}
        canvas.update()
        self._status(canvas, "Molde desdobrado pela linha escolhida. A ferramenta continua ativa.")

    def _restaurar_dobra_original(self, canvas, molde_idx: int, molde: dict, linha: dict, eixo_atual) -> bool:
        registros = molde.get("contornos_dobra_original")
        if not isinstance(registros, list) or not registros:
            return False
        pontos_atuais = self._pontos_elemento(molde)
        melhor = None
        melhor_dist = float("inf")
        for registro in reversed(registros):
            pontos = self._pontos_restauracao_original(registro, pontos_atuais)
            if len(pontos) < 3:
                continue
            eixo_reg = self._eixo_registro_original(registro)
            dist = self._distancia_eixos(eixo_atual, eixo_reg) if eixo_reg is not None else 0.0
            if dist < melhor_dist:
                melhor = pontos
                melhor_dist = dist
        if not melhor:
            return False
        if not self._pontos_mesmos(melhor[0], melhor[-1]):
            melhor.append(QPointF(melhor[0]))
        cantos = melhor[:-1] if self._pontos_mesmos(melhor[0], melhor[-1]) else melhor
        self._garantir_pontos_controle_eixo(cantos, eixo_atual)
        if self._inserir_pique_ativo(canvas):
            self._inserir_piques_eixo(molde, eixo_atual)
        molde["pontos"] = [(p.x(), p.y()) for p in melhor]
        molde["controle_cantos"] = [(p.x(), p.y()) for p in cantos]
        molde["pontos_controle_referencia"] = [(p.x(), p.y()) for p in cantos]
        molde["molde_dobrado"] = False
        molde["dobra_horizontal"] = False
        molde["dobra_vertical"] = False
        molde.pop("contornos_dobra_original", None)
        molde.setdefault("metadados", {})["ultima_transformacao"] = "desdobrar_original"
        canvas._selecionados = {molde_idx}
        canvas._registrar_historico()
        self._resetar_desdobrar(canvas, limpar_selecao=False)
        canvas._selecionados = {molde_idx}
        canvas.update()
        self._status(canvas, "Molde restaurado ao contorno original da dobra.")
        return True

    def _pontos_restauracao_original(self, registro, pontos_atuais: list[QPointF]) -> list[QPointF]:
        if isinstance(registro, dict):
            return self._pontos_registro_original(registro)
        metade_antiga = self._pontos_registro_original(registro)
        if len(metade_antiga) < 2:
            return []
        base_atual = pontos_atuais[:-1] if len(pontos_atuais) > 2 and self._pontos_mesmos(pontos_atuais[0], pontos_atuais[-1]) else list(pontos_atuais)
        metade = metade_antiga[:-1] if len(metade_antiga) > 2 and self._pontos_mesmos(metade_antiga[0], metade_antiga[-1]) else metade_antiga
        unidos = self._unir_poligonos(base_atual, metade)
        return unidos if len(unidos) >= 3 else metade_antiga

    def _pontos_registro_original(self, registro) -> list[QPointF]:
        origem = registro.get("pontos") if isinstance(registro, dict) else registro
        if not isinstance(origem, list):
            return []
        pontos: list[QPointF] = []
        for p in origem:
            if self._eh_ponto(p):
                pontos.append(QPointF(float(p[0]), float(p[1])))
        return pontos

    def _eixo_registro_original(self, registro):
        if not isinstance(registro, dict):
            return None
        eixo = registro.get("eixo")
        if not isinstance(eixo, dict):
            return None
        tipo = str(eixo.get("tipo") or "")
        if tipo == "h":
            return ("h", float(eixo.get("valor", 0.0)))
        if tipo == "v":
            return ("v", float(eixo.get("valor", 0.0)))
        p1 = eixo.get("p1")
        p2 = eixo.get("p2")
        if self._eh_ponto(p1) and self._eh_ponto(p2):
            return ("line", QPointF(float(p1[0]), float(p1[1])), QPointF(float(p2[0]), float(p2[1])))
        return None

    def _distancia_eixos(self, atual, salvo) -> float:
        if salvo is None:
            return 0.0
        a1, a2 = self._pontos_eixo(atual)
        b1, b2 = self._pontos_eixo(salvo)
        return min(
            self._dist(a1, b1) + self._dist(a2, b2),
            self._dist(a1, b2) + self._dist(a2, b1),
        )

    def _pontos_eixo(self, eixo) -> tuple[QPointF, QPointF]:
        if eixo[0] == "h":
            y = float(eixo[1])
            return QPointF(0.0, y), QPointF(1.0, y)
        if eixo[0] == "v":
            x = float(eixo[1])
            return QPointF(x, 0.0), QPointF(x, 1.0)
        return QPointF(eixo[1]), QPointF(eixo[2])

    def _linha_interna_em_ponto(self, canvas, molde_idx: int, pos: QPointF):
        return self._linha_do_proprio_molde_em_ponto(canvas, molde_idx, pos)

    def _elemento_linha_ref(self, canvas, ref) -> dict | None:
        if isinstance(ref, int):
            if 0 <= ref < len(canvas.cena.elementos):
                el = canvas.cena.elementos[ref]
                return el if isinstance(el, dict) else None
            return None
        if isinstance(ref, dict):
            return ref
        return None

    def _linha_do_proprio_molde_em_ponto(self, canvas, molde_idx: int, pos: QPointF) -> dict | None:
        if not (0 <= molde_idx < len(canvas.cena.elementos)):
            return None
        molde = canvas.cena.elementos[molde_idx]
        tolerancia = 8.0 / max(float(getattr(canvas, "zoom", 1.0)), 0.001)
        linhas = self._linhas_do_proprio_molde(molde)
        melhor = None
        melhor_dist = tolerancia
        for linha in linhas:
            pontos = self._pontos_para_preview_linha(linha)
            if len(pontos) < 2:
                continue
            dist = min(self._distancia_ponto_segmento(a, b, pos) for a, b in zip(pontos, pontos[1:]))
            if dist <= melhor_dist:
                melhor = linha
                melhor_dist = dist
        return melhor

    def _linhas_do_proprio_molde(self, molde: dict) -> list[dict]:
        linhas: list[dict] = []
        pontos = self._pontos_elemento(molde)
        base = pontos[:-1] if len(pontos) > 2 and self._pontos_mesmos(pontos[0], pontos[-1]) else pontos
        for a, b in zip(base, base[1:] + base[:1]):
            if self._dist(a, b) <= 1e-9:
                continue
            linhas.append(
                {
                    "tipo": "polyline",
                    "pontos": [(a.x(), a.y()), (b.x(), b.y())],
                    "origem_desdobrar": "perimetro_molde",
                }
            )
        return linhas

    def _obter_dialog(self, canvas) -> DesdobrarDialog:
        chave = id(canvas)
        parent = canvas.window() if hasattr(canvas, "window") else canvas
        dialog = self._dialog_por_canvas.get(chave)
        if dialog is None or dialog.parentWidget() is not parent:
            dialog = DesdobrarDialog(parent)
            self._dialog_por_canvas[chave] = dialog
            instalar_memoria_posicao(dialog, dialog._chave_posicao)
        return dialog

    def _restaurar_dialog(self, canvas, dialog: DesdobrarDialog) -> None:
        fallback = None
        if hasattr(canvas, "mapToGlobal"):
            fallback = canvas.mapToGlobal(QPoint(max(24, canvas.width() - dialog.width() - 32), 128))
        restaurar_posicao(dialog, dialog._chave_posicao, fallback=fallback)

    def _inserir_pique_ativo(self, canvas) -> bool:
        dialog = self._dialog_por_canvas.get(id(canvas))
        return bool(dialog is not None and dialog.chk_inserir_pique.isChecked())

    def _garantir_pontos_controle_eixo(self, cantos: list[QPointF], eixo) -> None:
        for ponto in self._pontos_eixo(eixo):
            if not any(self._dist(ponto, existente) <= 1e-6 for existente in cantos):
                cantos.append(QPointF(ponto))

    def _inserir_piques_eixo(self, molde: dict, eixo) -> None:
        marcacoes = list(molde.get("marcacoes_no_perimetro", []) or [])
        for ponto in self._pontos_eixo(eixo):
            existe = any(
                self._eh_ponto(item)
                and self._dist(ponto, QPointF(float(item[0]), float(item[1]))) <= 1e-6
                for item in marcacoes
            )
            if not existe:
                marcacoes.append((ponto.x(), ponto.y()))
        molde["marcacoes_no_perimetro"] = marcacoes

    def _indices_linhas_internas_proximas(self, canvas, molde_idx: int, pos: QPointF) -> list[int]:
        tolerancia = 8.0 / max(float(getattr(canvas, "zoom", 1.0)), 0.001)
        encontrados: list[int] = []
        for idx, el in enumerate(canvas.cena.elementos):
            if idx == molde_idx or not self._eh_linha_interna_do_molde(canvas, molde_idx, el):
                continue
            pontos = self._pontos_para_preview_linha(el)
            if any(self._distancia_ponto_segmento(a, b, pos) <= tolerancia for a, b in zip(pontos, pontos[1:])):
                encontrados.append(idx)
        return encontrados

    def _eh_linha_interna_do_molde(self, canvas, molde_idx: int, el: dict) -> bool:
        if not isinstance(el, dict) or el.get("molde"):
            return False
        if el.get("tipo") not in {"polyline", "bezier_quadratica"}:
            return False
        subtipo = str(el.get("subtipo_audaces") or el.get("metadados", {}).get("subtipo_audaces") or "").strip()
        if subtipo in {"contorno", "costura"} or el.get("costura_de_molde_id"):
            return False
        molde = canvas.cena.elementos[molde_idx]
        molde_id = str(molde.get("molde_id") or molde.get("id") or "").strip()
        el_molde_id = str(el.get("molde_id") or "").strip()
        if molde_id and el_molde_id == molde_id:
            return True
        if bool(el.get("molde_linha_vinculada")) and molde_id and el_molde_id == molde_id:
            return True
        pontos = self._pontos_para_preview_linha(el)
        if not pontos:
            return False
        if any(self._ponto_dentro_molde(molde, p) for p in pontos):
            return True
        bbox = self._bbox_pontos(self._pontos_elemento(molde))
        if bbox is None:
            return False
        min_x, min_y, max_x, max_y = bbox
        margem = max(max_x - min_x, max_y - min_y, 1.0) * 0.02
        return any((min_x - margem) <= p.x() <= (max_x + margem) and (min_y - margem) <= p.y() <= (max_y + margem) for p in pontos)

    def _eixo_linha(self, el: dict):
        if el.get("tipo") == "bezier_quadratica":
            p0 = el.get("p0")
            p2 = el.get("p2")
            if self._eh_ponto(p0) and self._eh_ponto(p2):
                return ("line", QPointF(float(p0[0]), float(p0[1])), QPointF(float(p2[0]), float(p2[1])))
            return None
        pontos = self._pontos_elemento(el)
        if len(pontos) >= 2:
            return ("line", QPointF(pontos[0]), QPointF(pontos[-1]))
        return None

    def _pontos_para_preview_linha(self, el: dict) -> list[QPointF]:
        if el.get("tipo") == "bezier_quadratica":
            if self._eh_ponto(el.get("p0")) and self._eh_ponto(el.get("p1")) and self._eh_ponto(el.get("p2")):
                p0 = QPointF(float(el["p0"][0]), float(el["p0"][1]))
                p1 = QPointF(float(el["p1"][0]), float(el["p1"][1]))
                p2 = QPointF(float(el["p2"][0]), float(el["p2"][1]))
                return [self._bezier(p0, p1, p2, i / 24.0) for i in range(25)]
            return []
        return self._pontos_elemento(el)

    def _ponto_dentro_molde(self, molde: dict, ponto: QPointF) -> bool:
        pontos = self._pontos_elemento(molde)
        if len(pontos) < 3:
            return False
        base = pontos[:-1] if self._pontos_mesmos(pontos[0], pontos[-1]) else pontos
        dentro = False
        j = len(base) - 1
        for i, pi in enumerate(base):
            pj = base[j]
            denom = pj.y() - pi.y()
            if abs(denom) <= 1e-12:
                denom = 1e-12 if denom >= 0 else -1e-12
            cruza = ((pi.y() > ponto.y()) != (pj.y() > ponto.y())) and (
                ponto.x() < (pj.x() - pi.x()) * (ponto.y() - pi.y()) / denom + pi.x()
            )
            if cruza:
                dentro = not dentro
            j = i
        return dentro

    def _resetar_desdobrar(self, canvas, limpar_selecao: bool) -> None:
        self._molde_idx = None
        self._hover_idx = None
        if limpar_selecao:
            canvas._selecionados = set()
        canvas.update()

    def _bbox_pontos(self, pontos: list[QPointF]) -> tuple[float, float, float, float] | None:
        if not pontos:
            return None
        return min(p.x() for p in pontos), min(p.y() for p in pontos), max(p.x() for p in pontos), max(p.y() for p in pontos)

    def _distancia_ponto_segmento(self, a: QPointF, b: QPointF, p: QPointF) -> float:
        abx = b.x() - a.x()
        aby = b.y() - a.y()
        apx = p.x() - a.x()
        apy = p.y() - a.y()
        denom = (abx * abx) + (aby * aby)
        if denom <= 1e-12:
            return self._dist(a, p)
        t = max(0.0, min(1.0, ((apx * abx) + (apy * aby)) / denom))
        proj = QPointF(a.x() + (abx * t), a.y() + (aby * t))
        return self._dist(proj, p)

    @staticmethod
    def _bezier(p0: QPointF, p1: QPointF, p2: QPointF, t: float) -> QPointF:
        u = 1.0 - t
        return QPointF(
            (u * u * p0.x()) + (2.0 * u * t * p1.x()) + (t * t * p2.x()),
            (u * u * p0.y()) + (2.0 * u * t * p1.y()) + (t * t * p2.y()),
        )

    @staticmethod
    def _eh_ponto(p) -> bool:
        if not isinstance(p, (list, tuple)) or len(p) < 2:
            return False
        try:
            return isfinite(float(p[0])) and isfinite(float(p[1]))
        except Exception:
            return False
