from __future__ import annotations

from copy import deepcopy
from math import atan2, cos, degrees, radians, sin, sqrt

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QCheckBox, QComboBox, QDialog, QFormLayout, QLineEdit

from core.geometry.engine import (
    quadratic_bezier_control_for_point,
    quadratic_bezier_parameter_for_point,
    sample_quadratic_bezier_through_point,
)
from tools.tool_base import FerramentaBase
from ui.posicao_janelas import instalar_memoria_posicao, restaurar_posicao


class Ferramenta(FerramentaBase):
    id_ferramenta = "manipular_pontos"
    nome = "Manipular Pontos"
    usar_caixa_passo = False
    arraste_por_clique = True
    gerencia_coordenadas_operacao = True
    _dlg_global: QDialog | None = None
    _edt_dx_global: QLineEdit | None = None
    _edt_dy_global: QLineEdit | None = None
    _cmb_n_pontos_global: QComboBox | None = None
    _chk_discreto_global: QCheckBox | None = None

    def __init__(self):
        super().__init__()
        self._arrastando_ponto_poly: tuple[int, int] | None = None
        self._arrastando_controle_molde: tuple[int, str, int] | None = None
        self._arrastando_dobra_pontilhada: tuple[int, int, int] | None = None
        self._hover_ponto_poly: tuple[int, int] | None = None
        self._hover_controle_molde: tuple[int, str, int] | None = None
        self._hover_dobra_pontilhada: tuple[int, int, int] | None = None
        self._hover_elemento_idx: int | None = None
        self._hover_molde_idx: int | None = None
        self._guia_ponto_poly: tuple[QPointF, QPointF | None, QPointF | None] | None = None
        self._guia_eixo: tuple[QPointF, QPointF] | None = None
        self._angulo_info: tuple[QPointF, QPointF, QPointF, float] | None = None
        self._ponto_selecionado: tuple[int, int] | None = None
        self._controles_selecionados: set[tuple[int, str, int]] = set()
        self._estado_arraste_controle: dict | None = None
        self._estado_arraste_ponto: dict | None = None
        self._estado_arraste_dobra: dict | None = None
        cls = type(self)
        self._dlg_passo: QDialog | None = cls._dlg_global
        self._edt_dx: QLineEdit | None = cls._edt_dx_global
        self._edt_dy: QLineEdit | None = cls._edt_dy_global
        self._cmb_n_pontos: QComboBox | None = cls._cmb_n_pontos_global
        self._chk_discreto: QCheckBox | None = cls._chk_discreto_global

    def on_activate(self, canvas):
        self._arrastando_ponto_poly = None
        self._arrastando_controle_molde = None
        self._arrastando_dobra_pontilhada = None
        self._hover_ponto_poly = None
        self._hover_controle_molde = None
        self._hover_dobra_pontilhada = None
        self._hover_elemento_idx = None
        self._hover_molde_idx = None
        self._guia_ponto_poly = None
        self._guia_eixo = None
        self._angulo_info = None
        self._ponto_selecionado = None
        self._controles_selecionados.clear()
        self._estado_arraste_controle = None
        self._estado_arraste_ponto = None
        self._estado_arraste_dobra = None
        if self.usar_caixa_passo:
            self._abrir_caixa_passo(canvas)
        self.set_status(f"{self.nome}: clique em um ponto para prender no cursor, clique de novo para soltar. Shift seleciona varios pontos.")

    def on_deactivate(self, canvas):
        if self._dlg_passo:
            self._dlg_passo.hide()
        self._arrastando_ponto_poly = None
        self._arrastando_controle_molde = None
        self._arrastando_dobra_pontilhada = None
        self._estado_arraste_controle = None
        self._estado_arraste_ponto = None
        self._estado_arraste_dobra = None
        self._guia_eixo = None

    def on_canvas_resize(self, canvas) -> None:
        if self.usar_caixa_passo:
            self._reposicionar_caixa_passo(canvas)

    def _abrir_caixa_passo(self, canvas):
        cls = type(self)
        if cls._dlg_global is not None:
            try:
                cls._dlg_global.isVisible()
            except RuntimeError:
                cls._dlg_global = None
                cls._edt_dx_global = None
                cls._edt_dy_global = None
                cls._cmb_n_pontos_global = None
                cls._chk_discreto_global = None
        if cls._dlg_global is None:
            cls._dlg_global = QDialog(canvas)
            cls._dlg_global.setObjectName(f"guimma_{self.id_ferramenta}_dialog")
            cls._dlg_global.setWindowTitle(self.nome)
            cls._dlg_global.setWindowFlags(Qt.Tool)
            lay = QFormLayout(cls._dlg_global)
            cls._edt_dx_global = QLineEdit("0")
            cls._edt_dy_global = QLineEdit("0")
            cls._cmb_n_pontos_global = QComboBox()
            cls._cmb_n_pontos_global.addItems(["1 ponto", "N pontos"])
            cls._chk_discreto_global = QCheckBox("Discreto")
            lay.addRow("DX (cm)", cls._edt_dx_global)
            lay.addRow("DY (cm)", cls._edt_dy_global)
            lay.addRow("Nº pontos", cls._cmb_n_pontos_global)
            lay.addRow("", cls._chk_discreto_global)
            cls._dlg_global.setFixedWidth(210)
            instalar_memoria_posicao(cls._dlg_global, f"dialog:{self.id_ferramenta}")
        self._dlg_passo = cls._dlg_global
        self._edt_dx = cls._edt_dx_global
        self._edt_dy = cls._edt_dy_global
        self._cmb_n_pontos = cls._cmb_n_pontos_global
        self._chk_discreto = cls._chk_discreto_global
        if not self._dlg_passo.isVisible():
            self._dlg_passo.show()
        self._reposicionar_caixa_passo(canvas)

    def _reposicionar_caixa_passo(self, canvas):
        if not self._dlg_passo:
            return
        if hasattr(canvas, "calcular_posicao_painel_auxiliar"):
            pos_local = canvas.calcular_posicao_painel_auxiliar(
                self._dlg_passo.width(),
                self._dlg_passo.height(),
                abaixo_coordenadas=True,
            )
            restaurar_posicao(self._dlg_passo, f"dialog:{self.id_ferramenta}", fallback=canvas.mapToGlobal(pos_local))

    def _ler_delta_configurado(self) -> tuple[float, float]:
        try:
            dx = float((self._edt_dx.text() if self._edt_dx else "0").replace(",", "."))
        except Exception:
            dx = 0.0
        try:
            dy = float((self._edt_dy.text() if self._edt_dy else "0").replace(",", "."))
        except Exception:
            dy = 0.0
        return dx, dy

    def _modo_n_pontos(self) -> bool:
        if not self._cmb_n_pontos:
            return False
        return self._cmb_n_pontos.currentText().strip().lower() == "n pontos"

    def _modo_discreto(self) -> bool:
        return bool(self._chk_discreto.isChecked()) if self._chk_discreto else False

    def _shift_pressionado(self, event) -> bool:
        try:
            return bool(event.modifiers() & Qt.ShiftModifier)
        except Exception:
            return False

    def _elemento_curva_suave(self, elemento: dict) -> bool:
        if not isinstance(elemento, dict):
            return False
        return bool(
            elemento.get("curva_suave")
            or elemento.get("suavizar")
            or str(elemento.get("tipo_curva") or "").lower() == "parabola_3p"
            or str(elemento.get("tipo_curva") or "").lower().startswith("spline")
            or str(elemento.get("renderizacao") or "").lower() == "curva_suave"
        )

    def _sincronizar_curva_suave(self, el: dict) -> None:
        if el.get("molde"):
            return
        # Curva com traçado real: manter somente os controles como controles.
        if self._curva_tracado_real(el):
            controles = self._pontos_controle_curva(el)
            if len(controles) >= 2:
                self._salvar_controles_curva_real(el, controles)
            return
        if not self._elemento_curva_suave(el):
            return
        pontos = list(el.get("pontos") or [])
        normalizados: list[tuple[float, float]] = []
        for item in pontos:
            pt = self._ponto_qt(item)
            if pt is not None:
                normalizados.append((pt.x(), pt.y()))
        if len(normalizados) < 2:
            return
        el["pontos"] = list(normalizados)
        el["pontos_controle_curva"] = list(normalizados)
        el["pontos_principais"] = list(normalizados)
        el["curva_suave"] = True
        el["tipo_curva"] = str(el.get("tipo_curva") or "spline_np_controle")
        el["renderizacao"] = "curva_suave"

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() == Qt.RightButton and self._arraste_ativo():
            self._cancelar_arraste(canvas, event)
            return True
        if event.button() != Qt.LeftButton:
            return False
        pos = canvas._ponto_com_snap(event.position())
        if self.arraste_por_clique and self._arraste_ativo():
            self.on_mouse_move(canvas, event)
            self._finalizar_arraste(canvas, event)
            return True
        shift = self._shift_pressionado(event)

        dobra_pontilhada = self._dobra_pontilhada_em_ponto(canvas, pos)
        if dobra_pontilhada is not None:
            self._arrastando_dobra_pontilhada = dobra_pontilhada
            self._hover_dobra_pontilhada = dobra_pontilhada
            self._estado_arraste_dobra = self._criar_estado_arraste_dobra(canvas, dobra_pontilhada)
            self._hover_controle_molde = None
            self._hover_ponto_poly = None
            if hasattr(canvas, "iniciar_operacao_coordenadas"):
                canvas.iniciar_operacao_coordenadas(pos)
            event.accept()
            canvas.update()
            return True

        controle = self._controle_molde_em_ponto(canvas, pos)
        if controle is not None:
            if shift:
                if controle in self._controles_selecionados:
                    self._controles_selecionados.remove(controle)
                else:
                    self._controles_selecionados.add(controle)
                self._hover_controle_molde = controle
                self._hover_molde_idx = controle[0]
                self._ponto_selecionado = None
                event.accept()
                canvas.update()
                return True

            if controle not in self._controles_selecionados:
                self._controles_selecionados = {controle}
            self._arrastando_controle_molde = controle
            self._hover_controle_molde = controle
            self._hover_molde_idx = controle[0]
            self._ponto_selecionado = None
            self._estado_arraste_controle = self._criar_estado_arraste_controle(canvas, controle)
            origem_coord = self.origem_coordenadas(canvas)
            if origem_coord is not None and hasattr(canvas, "iniciar_operacao_coordenadas"):
                canvas.iniciar_operacao_coordenadas(origem_coord)
            dx, dy = self._ler_delta_configurado()
            if abs(dx) > 1e-9 or abs(dy) > 1e-9:
                self._mover_controles_por_delta(canvas, self._alvos_controle_para_arraste(controle), dx, -dy)
                canvas._registrar_historico()
                self._arrastando_controle_molde = None
                self._estado_arraste_controle = None
            event.accept()
            canvas.update()
            return True

        ponto_poly = self._ponto_polilinha_em_ponto(canvas, pos)
        if ponto_poly is None:
            if not shift:
                self._controles_selecionados.clear()
            return False
        idx, p_idx = ponto_poly
        self._arrastando_ponto_poly = (idx, p_idx)
        self._ponto_selecionado = (idx, p_idx)
        self._hover_ponto_poly = (idx, p_idx)
        self._estado_arraste_ponto = self._criar_estado_arraste_ponto(canvas, idx, p_idx)
        origem_coord = self.origem_coordenadas(canvas)
        if origem_coord is not None and hasattr(canvas, "iniciar_operacao_coordenadas"):
            canvas.iniciar_operacao_coordenadas(origem_coord)
        dx, dy = self._ler_delta_configurado()
        if abs(dx) > 1e-9 or abs(dy) > 1e-9:
            delta_x = dx
            # Convenção solicitada: DY negativo move para baixo, DY positivo para cima.
            delta_y = -dy
            el = canvas.cena.elementos[idx]
            pontos = el.get("pontos", [])
            if 0 <= p_idx < len(pontos):
                x, y = pontos[p_idx]
                destino = QPointF(float(x) + delta_x, float(y) + delta_y)
                if self._modo_discreto():
                    destino = QPointF(round(destino.x(), 2), round(destino.y(), 2))
                self._atualizar_ponto(canvas, idx, p_idx, destino)
                self._mover_ponto_proporcional(canvas, idx, p_idx, delta_x, delta_y, mover_n_pontos=self._modo_n_pontos())
                canvas._registrar_historico()
                self._estado_arraste_ponto = None
        self._guia_ponto_poly = self._gerar_guia(canvas, idx, p_idx)
        canvas.update()
        event.accept()
        return True

    def _mover_ponto_proporcional(self, canvas, idx: int, p_idx: int, dx: float, dy: float, mover_n_pontos: bool = False):
        if not (0 <= idx < len(canvas.cena.elementos)):
            return
        el = canvas.cena.elementos[idx]
        pontos = list(el.get("pontos", []))
        pontos_anteriores = list(pontos)
        if len(pontos) < 3:
            return
        fechado = len(pontos) >= 2 and canvas._dist(QPointF(float(pontos[0][0]), float(pontos[0][1])), QPointF(float(pontos[-1][0]), float(pontos[-1][1]))) <= 1e-6
        n = len(pontos) - 1 if fechado else len(pontos)
        if n < 2:
            return

        if mover_n_pontos and el.get("molde") and self._mover_molde_n_pontos(canvas, el, p_idx, dx, dy):
            pontos = list(el.get("pontos", []))
        elif mover_n_pontos:
            alcance = max(2, n // 2)
            for i in range(n):
                if i == p_idx:
                    continue
                if fechado:
                    dist_passos = min((i - p_idx) % n, (p_idx - i) % n)
                else:
                    dist_passos = abs(i - p_idx)
                peso = max(0.0, 1.0 - (dist_passos / float(alcance + 1)))
                if peso <= 0.0:
                    continue
                fator = 0.60 * peso
                x, y = pontos[i]
                nx = float(x) + (dx * fator)
                ny = float(y) + (dy * fator)
                if self._modo_discreto():
                    nx = round(nx, 2)
                    ny = round(ny, 2)
                pontos[i] = (nx, ny)
        else:
            # Em molde, um controle deforma só os trechos até as âncoras vizinhas.
            # O deslocamento do ponto selecionado já foi aplicado em _atualizar_ponto.
            if el.get("molde"):
                pontos_base = list(pontos)
                if 0 <= p_idx < len(pontos_base):
                    x, y = pontos_base[p_idx]
                    pontos_base[p_idx] = (float(x) - dx, float(y) - dy)
                    if fechado and p_idx == 0 and len(pontos_base) >= 2:
                        pontos_base[-1] = pontos_base[0]
                self._redistribuir_molde_local_por_ponto(canvas, el, pontos_base, p_idx, dx, dy)
                pontos = list(el.get("pontos", []))

        if fechado and len(pontos) >= 2:
            pontos[-1] = pontos[0]
        el["pontos"] = pontos
        self._sincronizar_curva_suave(el)
        if el.get("molde"):
            for antigo, novo in zip(pontos_anteriores, pontos):
                anterior_pt = QPointF(float(antigo[0]), float(antigo[1]))
                novo_pt = QPointF(float(novo[0]), float(novo[1]))
                if canvas._dist(anterior_pt, novo_pt) > 1e-9:
                    self._mover_controles_correspondentes(canvas, el, anterior_pt, novo_pt)
            self._reajustar_fio_no_molde(el)

    def _mover_molde_n_pontos(self, canvas, el: dict, p_idx: int, dx: float, dy: float) -> bool:
        pontos_base = list(el.get("pontos", []))
        if len(pontos_base) < 4:
            return False
        fechado = len(pontos_base) >= 2 and canvas._dist(
            QPointF(float(pontos_base[0][0]), float(pontos_base[0][1])),
            QPointF(float(pontos_base[-1][0]), float(pontos_base[-1][1])),
        ) <= 1e-6
        n = len(pontos_base) - 1 if fechado else len(pontos_base)
        if not (0 <= p_idx < n):
            return False

        principais = sorted(i for i in self._indices_pontos_principais_molde(canvas, el) if 0 <= i < n)
        if len(principais) < 2 or p_idx not in principais:
            return False

        # No modo N pontos do molde, apenas o ponto principal selecionado
        # recebe deslocamento direto. Os demais principais ficam estáveis e
        # os pontos intermediários são redistribuídos proporcionalmente.
        disp_principais: dict[int, tuple[float, float]] = {p_idx: (dx, dy)}
        for p in principais:
            if p == p_idx:
                continue
            disp_principais[p] = (0.0, 0.0)

        novos = list(pontos_base)
        for p in principais:
            if p == p_idx:
                continue
            ddx, ddy = disp_principais[p]
            x, y = pontos_base[p]
            nx = float(x) + ddx
            ny = float(y) + ddy
            if self._modo_discreto():
                nx = round(nx, 2)
                ny = round(ny, 2)
            novos[p] = (nx, ny)

        pares: list[tuple[int, int]] = []
        if fechado:
            for i, a in enumerate(principais):
                b = principais[(i + 1) % len(principais)]
                pares.append((a, b))
        else:
            pares.extend((a, b) for a, b in zip(principais, principais[1:]))

        for a, b in pares:
            indices = self._indices_intervalo(a, b, n, fechado)
            if len(indices) <= 2:
                continue
            dxa, dya = disp_principais.get(a, (0.0, 0.0))
            dxb, dyb = disp_principais.get(b, (0.0, 0.0))
            denom = max(1, len(indices) - 1)
            for pos, idx_local in enumerate(indices[1:-1], start=1):
                t = max(0.0, min(1.0, pos / float(denom)))
                ddx = (dxa * (1.0 - t)) + (dxb * t)
                ddy = (dya * (1.0 - t)) + (dyb * t)
                nx = float(pontos_base[idx_local][0]) + ddx
                ny = float(pontos_base[idx_local][1]) + ddy
                if self._modo_discreto():
                    nx = round(nx, 2)
                    ny = round(ny, 2)
                novos[idx_local] = (nx, ny)

        if fechado and len(novos) >= 2:
            novos[-1] = novos[0]
        el["pontos"] = novos
        self._sincronizar_curva_suave(el)
        return True

    def _indices_intervalo(self, a: int, b: int, n: int, fechado: bool) -> list[int]:
        if n <= 0:
            return []
        if not fechado:
            if a <= b:
                return list(range(a, b + 1))
            return list(range(b, a + 1))
        out = [a]
        i = a
        while i != b:
            i = (i + 1) % n
            out.append(i)
            if len(out) > (n + 1):
                break
        return out

    def on_mouse_move(self, canvas, event) -> bool:
        pos = self._posicao_arraste_livre(canvas, event)
        if self._arrastando_dobra_pontilhada is not None:
            self._atualizar_dobra_pontilhada(canvas, self._arrastando_dobra_pontilhada, self._normalizar_destino(pos))
            self._hover_dobra_pontilhada = self._arrastando_dobra_pontilhada
            if hasattr(canvas, "atualizar_operacao_coordenadas"):
                canvas.atualizar_operacao_coordenadas(pos)
            canvas.update()
            event.accept()
            return True

        if self._arrastando_controle_molde is not None:
            idx, tipo, controle_idx = self._arrastando_controle_molde
            estado = self._estado_arraste_controle
            if estado is not None:
                origem = estado.get("origem")
                if isinstance(origem, QPointF):
                    destino = self._destino_com_snap_e_eixos(canvas, origem, pos)
                    dx = destino.x() - origem.x()
                    dy = destino.y() - origem.y()
                    self._restaurar_estado_arraste(canvas, estado)
                    self._mover_controles_por_delta(canvas, set(estado.get("alvos", set())), dx, dy)
                    self._atualizar_info_angulo_controle_molde(canvas, idx, tipo, controle_idx, destino)
            else:
                atual = self._ponto_controle_molde(canvas, idx, tipo, controle_idx)
                if atual is not None:
                    destino = self._destino_com_snap_e_eixos(canvas, atual, pos)
                    dx = destino.x() - atual.x()
                    dy = destino.y() - atual.y()
                    self._mover_controles_por_delta(canvas, self._alvos_controle_para_arraste((idx, tipo, controle_idx)), dx, dy)
                    self._atualizar_info_angulo_controle_molde(canvas, idx, tipo, controle_idx, destino)
            self._hover_controle_molde = self._arrastando_controle_molde
            self._hover_molde_idx = idx
            destino_coord = self.posicao_coordenadas_atual(canvas)
            if destino_coord is not None and hasattr(canvas, "atualizar_operacao_coordenadas"):
                canvas.atualizar_operacao_coordenadas(destino_coord)
            canvas.update()
            event.accept()
            return True

        if self._arrastando_ponto_poly is not None:
            idx, p_idx = self._arrastando_ponto_poly
            estado = self._estado_arraste_ponto
            destino = self._normalizar_destino(pos)
            if estado is not None:
                origem = estado.get("origem")
                if isinstance(origem, QPointF):
                    destino = self._destino_com_snap_e_eixos(canvas, origem, pos)
                    self._restaurar_estado_arraste(canvas, estado)
                    dx = destino.x() - origem.x()
                    dy = destino.y() - origem.y()
                    self._atualizar_ponto(canvas, idx, p_idx, destino)
                    self._mover_ponto_proporcional(canvas, idx, p_idx, dx, dy, mover_n_pontos=self._modo_n_pontos())
            else:
                self._atualizar_ponto(canvas, idx, p_idx, destino)
            self._guia_ponto_poly = self._gerar_guia(canvas, idx, p_idx)
            self._atualizar_info_angulo(canvas, idx, p_idx, destino)
            destino_coord = self.posicao_coordenadas_atual(canvas)
            if destino_coord is not None and hasattr(canvas, "atualizar_operacao_coordenadas"):
                canvas.atualizar_operacao_coordenadas(destino_coord)
            canvas.update()
            event.accept()
            return True

        self._hover_ponto_poly = self._ponto_polilinha_em_ponto(canvas, pos)
        self._hover_controle_molde = self._controle_molde_em_ponto(canvas, pos)
        self._hover_dobra_pontilhada = self._dobra_pontilhada_em_ponto(canvas, pos)
        self._hover_molde_idx = self._hover_controle_molde[0] if self._hover_controle_molde is not None else None
        self._hover_elemento_idx = self._elemento_em_hover(canvas, pos)
        canvas.update()
        event.accept()
        return True

    def _arraste_ativo(self) -> bool:
        return (
            self._arrastando_ponto_poly is not None
            or self._arrastando_controle_molde is not None
            or self._arrastando_dobra_pontilhada is not None
        )

    def on_mouse_release(self, canvas, event) -> bool:
        if event.button() != Qt.LeftButton:
            return False
        if not self._arraste_ativo():
            return False
        if self.arraste_por_clique:
            event.accept()
            return True
        self._finalizar_arraste(canvas, event)
        return True

    def _finalizar_arraste(self, canvas, event) -> None:
        destino_final = self.posicao_coordenadas_atual(canvas)
        self._arrastando_ponto_poly = None
        self._arrastando_controle_molde = None
        self._arrastando_dobra_pontilhada = None
        self._estado_arraste_controle = None
        self._estado_arraste_ponto = None
        self._estado_arraste_dobra = None
        self._guia_ponto_poly = None
        self._guia_eixo = None
        self._angulo_info = None
        self._ponto_selecionado = None
        self._hover_ponto_poly = None
        self._hover_controle_molde = None
        self._hover_molde_idx = None
        if destino_final is not None and hasattr(canvas, "definir_origem_preview_coordenadas"):
            if hasattr(canvas, "finalizar_operacao_coordenadas"):
                canvas.finalizar_operacao_coordenadas(destino_final)
            else:
                canvas.definir_origem_preview_coordenadas(destino_final)
                if hasattr(canvas, "painel_coordenadas"):
                    canvas.painel_coordenadas.atualizar_preview(destino_final, destino_final)
        canvas._registrar_historico()
        canvas.update()
        event.accept()

    def _cancelar_arraste(self, canvas, event) -> None:
        for estado in (self._estado_arraste_controle, self._estado_arraste_ponto, self._estado_arraste_dobra):
            if estado is not None:
                self._restaurar_estado_arraste(canvas, estado)
        self._arrastando_ponto_poly = None
        self._arrastando_controle_molde = None
        self._arrastando_dobra_pontilhada = None
        self._estado_arraste_controle = None
        self._estado_arraste_ponto = None
        self._estado_arraste_dobra = None
        self._guia_ponto_poly = None
        self._guia_eixo = None
        self._angulo_info = None
        self._ponto_selecionado = None
        self._hover_ponto_poly = None
        self._hover_controle_molde = None
        self._hover_dobra_pontilhada = None
        self._hover_molde_idx = None
        if hasattr(canvas, "cancelar_operacao_coordenadas"):
            canvas.cancelar_operacao_coordenadas(limpar_preview=True)
        canvas.update()
        event.accept()

    def origem_coordenadas(self, canvas) -> QPointF | None:
        if self._estado_arraste_controle is not None:
            origem = self._estado_arraste_controle.get("origem")
            if isinstance(origem, QPointF):
                return QPointF(origem)
        if self._estado_arraste_ponto is not None:
            origem = self._estado_arraste_ponto.get("origem")
            if isinstance(origem, QPointF):
                return QPointF(origem)
        if self._arrastando_dobra_pontilhada is not None:
            idx, lado, ponto_idx = self._arrastando_dobra_pontilhada
            ponto = self._ponto_dobra_pontilhada(canvas, idx, lado, ponto_idx)
            if ponto is not None:
                return QPointF(ponto)
        if self._hover_controle_molde is not None:
            ponto = self._ponto_controle_molde(canvas, *self._hover_controle_molde)
            if ponto is not None:
                return QPointF(ponto)
        if self._hover_ponto_poly is not None:
            idx, p_idx = self._hover_ponto_poly
            if 0 <= idx < len(canvas.cena.elementos):
                pontos = canvas.cena.elementos[idx].get("pontos", []) or []
                if 0 <= p_idx < len(pontos):
                    try:
                        return QPointF(float(pontos[p_idx][0]), float(pontos[p_idx][1]))
                    except Exception:
                        return None
        return None

    def posicao_coordenadas_atual(self, canvas) -> QPointF | None:
        if self._arrastando_controle_molde is not None:
            ponto = self._ponto_controle_molde(canvas, *self._arrastando_controle_molde)
            if ponto is not None:
                return QPointF(ponto)
        if self._arrastando_ponto_poly is not None:
            idx, p_idx = self._arrastando_ponto_poly
            if 0 <= idx < len(canvas.cena.elementos):
                pontos = canvas.cena.elementos[idx].get("pontos", []) or []
                if 0 <= p_idx < len(pontos):
                    try:
                        return QPointF(float(pontos[p_idx][0]), float(pontos[p_idx][1]))
                    except Exception:
                        return None
        if self._arrastando_dobra_pontilhada is not None:
            idx, lado, ponto_idx = self._arrastando_dobra_pontilhada
            ponto = self._ponto_dobra_pontilhada(canvas, idx, lado, ponto_idx)
            if ponto is not None:
                return QPointF(ponto)
        return None

    def on_paint_overlay(self, canvas, painter):
        self._desenhar_linha_curva_selecionada(canvas, painter)
        self._desenhar_pontos_controle_curvas_visiveis(canvas, painter)
        self._desenhar_molde_em_manipulacao(canvas, painter)
        self._desenhar_controles_molde_hover(canvas, painter)
        self._desenhar_guia_angular_arraste(canvas, painter)
        self._desenhar_hover(canvas, painter)
        self._desenhar_hover_dobra_pontilhada(canvas, painter)

    def _curva_tracado_real(self, el: dict) -> bool:
        if not isinstance(el, dict) or el.get("molde"):
            return False
        return bool(
            el.get("pontos_tracado_real")
            or el.get("curva_editavel")
            or el.get("pontos_principais")
            or el.get("pontos_controle_curva")
        )

    def _dist_pontos_local(self, a: QPointF, b: QPointF) -> float:
        dx = a.x() - b.x()
        dy = a.y() - b.y()
        return (dx * dx + dy * dy) ** 0.5

    def _resolver_segundas_derivadas_local(self, valores: list[float], t: list[float]) -> list[float]:
        n = len(valores)
        if n <= 2:
            return [0.0] * n
        m = n - 2
        a = [0.0] * m
        b = [0.0] * m
        c = [0.0] * m
        d = [0.0] * m
        for j in range(m):
            i = j + 1
            h0 = max(t[i] - t[i - 1], 1e-9)
            h1 = max(t[i + 1] - t[i], 1e-9)
            a[j] = h0
            b[j] = 2.0 * (h0 + h1)
            c[j] = h1
            d[j] = 6.0 * (((valores[i + 1] - valores[i]) / h1) - ((valores[i] - valores[i - 1]) / h0))
        for i in range(1, m):
            w = a[i] / b[i - 1]
            b[i] -= w * c[i - 1]
            d[i] -= w * d[i - 1]
        internos = [0.0] * m
        internos[-1] = d[-1] / b[-1]
        for i in range(m - 2, -1, -1):
            internos[i] = (d[i] - c[i] * internos[i + 1]) / b[i]
        return [0.0] + internos + [0.0]

    def _avaliar_spline_local(self, ti: float, tj: float, yi: float, yj: float, mi: float, mj: float, u: float) -> float:
        h = max(tj - ti, 1e-9)
        a = (tj - u) / h
        b = (u - ti) / h
        return a * yi + b * yj + (((a ** 3) - a) * mi + ((b ** 3) - b) * mj) * (h * h) / 6.0

    def _gerar_tracado_curva_real(
        self,
        controles: list[QPointF],
        fechado: bool = False,
        tipo_curva: str | None = None,
    ) -> list[tuple[float, float]]:
        controles = [QPointF(p) for p in controles]
        if len(controles) <= 1:
            return [(p.x(), p.y()) for p in controles]
        if len(controles) == 2:
            return [(controles[0].x(), controles[0].y()), (controles[1].x(), controles[1].y())]
        if not fechado and str(tipo_curva or "").lower() == "parabola_3p" and len(controles) == 3:
            return self._gerar_parabola_3p_curva_real(controles)

        saida: list[QPointF] = []
        total = len(controles)
        limite = total if fechado else total - 1
        for i in range(limite):
            p0 = controles[(i - 1) % total] if fechado or i > 0 else controles[i]
            p1 = controles[i]
            p2 = controles[(i + 1) % total]
            p3 = controles[(i + 2) % total] if fechado or i + 2 < total else p2
            if i == 0:
                saida.append(QPointF(p1))
            dist = self._dist_pontos_local(p1, p2)
            amostras = max(8, min(22, int(dist * 0.10) + 8))
            for s in range(1, amostras + 1):
                saida.append(self._catmull_rom_centripeta(p0, p1, p2, p3, s / float(amostras)))
        if fechado and saida:
            saida[-1] = QPointF(saida[0])
        return [(float(p.x()), float(p.y())) for p in saida]

    def _gerar_parabola_3p_curva_real(self, controles: list[QPointF]) -> list[tuple[float, float]]:
        p0, pmedio, p2 = [QPointF(p) for p in controles]
        return sample_quadratic_bezier_through_point(
            (float(p0.x()), float(p0.y())),
            (float(pmedio.x()), float(pmedio.y())),
            (float(p2.x()), float(p2.y())),
            96,
        )

    def _parametro_parabola_3p(self, p0: QPointF, pmedio: QPointF, p2: QPointF) -> float:
        return quadratic_bezier_parameter_for_point(
            (float(p0.x()), float(p0.y())),
            (float(pmedio.x()), float(pmedio.y())),
            (float(p2.x()), float(p2.y())),
        )

    def _catmull_rom(self, p0: QPointF, p1: QPointF, p2: QPointF, p3: QPointF, t: float) -> QPointF:
        t2 = t * t
        t3 = t2 * t
        x = 0.5 * (
            (2.0 * p1.x())
            + (-p0.x() + p2.x()) * t
            + (2.0 * p0.x() - 5.0 * p1.x() + 4.0 * p2.x() - p3.x()) * t2
            + (-p0.x() + 3.0 * p1.x() - 3.0 * p2.x() + p3.x()) * t3
        )
        y = 0.5 * (
            (2.0 * p1.y())
            + (-p0.y() + p2.y()) * t
            + (2.0 * p0.y() - 5.0 * p1.y() + 4.0 * p2.y() - p3.y()) * t2
            + (-p0.y() + 3.0 * p1.y() - 3.0 * p2.y() + p3.y()) * t3
        )
        return QPointF(x, y)

    def _catmull_rom_centripeta(self, p0: QPointF, p1: QPointF, p2: QPointF, p3: QPointF, t: float) -> QPointF:
        def tj(ti: float, a: QPointF, b: QPointF) -> float:
            return ti + max(self._dist_pontos_local(a, b), 1e-6) ** 0.5

        t0 = 0.0
        t1 = tj(t0, p0, p1)
        t2 = tj(t1, p1, p2)
        t3 = tj(t2, p2, p3)
        t = t1 + max(0.0, min(1.0, t)) * (t2 - t1)

        def interp(a: QPointF, b: QPointF, ta: float, tb: float) -> QPointF:
            den = max(tb - ta, 1e-9)
            return QPointF(
                ((tb - t) / den) * a.x() + ((t - ta) / den) * b.x(),
                ((tb - t) / den) * a.y() + ((t - ta) / den) * b.y(),
            )

        a1 = interp(p0, p1, t0, t1)
        a2 = interp(p1, p2, t1, t2)
        a3 = interp(p2, p3, t2, t3)
        b1 = interp(a1, a2, t0, t2)
        b2 = interp(a2, a3, t1, t3)
        return interp(b1, b2, t1, t2)

    def _salvar_controles_curva_real(self, el: dict, controles: list[QPointF]) -> None:
        lista = [(float(p.x()), float(p.y())) for p in controles]
        el["pontos_principais"] = list(lista)
        el["pontos_controle_curva"] = list(lista)
        el["pontos_controle_principais"] = list(lista)
        el["pontos_controle"] = list(lista)
        el["curva_editavel"] = True
        el["curva_suave"] = True
        el["pontos_tracado_real"] = True
        el["renderizacao"] = "polyline"
        el["tipo_curva"] = el.get("tipo_curva") or "spline_catmull_rom"

    def _pontos_controle_curva(self, el: dict) -> list[QPointF]:
        """Retorna somente os pontos principais/controláveis da curva."""
        origem = el.get("pontos_principais") or el.get("pontos_controle_curva") or el.get("pontos") or []
        pontos: list[QPointF] = []
        if not isinstance(origem, list):
            return pontos
        for item in origem:
            pt = self._ponto_qt(item)
            if pt is None:
                continue
            if not pontos:
                pontos.append(QPointF(pt))
                continue
            dx = pt.x() - pontos[-1].x()
            dy = pt.y() - pontos[-1].y()
            if ((dx * dx) + (dy * dy)) > 1e-9:
                pontos.append(QPointF(pt))
        return pontos

    def _indice_ponto_controle_para_ponto_real(self, canvas, el: dict, controle_idx: int) -> int | None:
        """Converte o ponto de controle visível para o índice real em el["pontos"]."""
        if self._curva_tracado_real(el):
            return controle_idx
        pontos = list(el.get("pontos", []) or [])
        controles = self._pontos_controle_curva(el)
        if not (0 <= controle_idx < len(controles)):
            return None
        alvo = controles[controle_idx]
        melhor_idx = None
        melhor_dist = float("inf")
        for i, item in enumerate(pontos):
            pt = self._ponto_qt(item)
            if pt is None:
                continue
            dist = canvas._dist(pt, alvo)
            if dist < melhor_dist:
                melhor_dist = dist
                melhor_idx = i
        return melhor_idx

    def _indices_curvas_para_mostrar(self, canvas) -> set[int]:
        indices: set[int] = set()
        for idx in getattr(canvas, "_selecionados", set()) or set():
            if 0 <= int(idx) < len(canvas.cena.elementos):
                indices.add(int(idx))
        if self._hover_elemento_idx is not None:
            indices.add(int(self._hover_elemento_idx))
        if self._hover_ponto_poly is not None:
            indices.add(int(self._hover_ponto_poly[0]))
        if self._ponto_selecionado is not None:
            indices.add(int(self._ponto_selecionado[0]))
        if self._arrastando_ponto_poly is not None:
            indices.add(int(self._arrastando_ponto_poly[0]))
        return indices

    def _desenhar_linha_curva_selecionada(self, canvas, painter) -> None:
        """Realça a curva em azul quando ela está em hover/selecionada/manipulação."""
        for idx in sorted(self._indices_curvas_para_mostrar(canvas)):
            if not (0 <= idx < len(canvas.cena.elementos)):
                continue
            el = canvas.cena.elementos[idx]
            if el.get("tipo") != "polyline" or not self._elemento_curva_suave(el):
                continue
            pontos = [self._ponto_qt(p) for p in (el.get("pontos", []) or [])]
            pontos = [p for p in pontos if p is not None]
            if len(pontos) < 2:
                continue
            painter.save()
            try:
                painter.setBrush(Qt.NoBrush)
                esp = max(1.8, float(el.get("espessura", 1.0)) + 0.8)
                if el.get("pontos_tracado_real"):
                    canvas._desenhar_polilinha(
                        painter, pontos, cor="#2da8ff", espessura=esp, estilo="solid", amplitude=1.0
                    )
                elif (
                    str(el.get("tipo_curva") or "").lower() == "parabola_3p"
                    and hasattr(canvas, "_desenhar_parabola_3p_elemento")
                    and canvas._desenhar_parabola_3p_elemento(
                        painter,
                        el,
                        cor="#2da8ff",
                        espessura=esp,
                        estilo="solid",
                        amplitude=1.0,
                    )
                ):
                    pass
                elif el.get("pontos_tracado_real"):
                    canvas._desenhar_polilinha(
                        painter, pontos, cor="#2da8ff", espessura=esp, estilo="solid", amplitude=1.0
                    )
                elif hasattr(canvas, "_desenhar_curva_suave_por_pontos"):
                    canvas._desenhar_curva_suave_por_pontos(
                        painter, pontos, cor="#2da8ff", espessura=esp, estilo="solid"
                    )
                else:
                    canvas._desenhar_polilinha(
                        painter, pontos, cor="#2da8ff", espessura=esp, estilo="solid", amplitude=1.0
                    )
            finally:
                painter.restore()

    def _desenhar_pontos_controle_curvas_visiveis(self, canvas, painter) -> None:
        """Mostra os pontos de controle principais em vermelho para poder mover."""
        for idx in sorted(self._indices_curvas_para_mostrar(canvas)):
            if not (0 <= idx < len(canvas.cena.elementos)):
                continue
            el = canvas.cena.elementos[idx]
            if el.get("tipo") != "polyline" or not self._elemento_curva_suave(el):
                continue
            if el.get("molde"):
                controles = self._pontos_polyline_editaveis_molde(el)
            else:
                controles = self._pontos_controle_curva(el)
            if not controles:
                continue
            painter.save()
            try:
                painter.setPen(QPen(QColor("#ff2f5f"), 1.2))
                painter.setBrush(QColor("#ff2f5f"))
                for pt_cena in controles:
                    pt = canvas._cena_para_tela(pt_cena)
                    painter.drawRect(int(pt.x() - 4), int(pt.y() - 4), 8, 8)
            finally:
                painter.restore()

    def _dobra_pontilhada_em_ponto(self, canvas, ponto: QPointF) -> tuple[int, int, int] | None:
        tolerancia = 8.0 / max(canvas.zoom, 0.001)
        melhor: tuple[int, int, int] | None = None
        melhor_dist = float("inf")
        candidatos = sorted(canvas._selecionados) if canvas._selecionados else list(range(len(canvas.cena.elementos)))
        for idx in candidatos:
            if not (0 <= idx < len(canvas.cena.elementos)):
                continue
            el = canvas.cena.elementos[idx]
            registros = el.get("contornos_dobra_original")
            if not isinstance(registros, list):
                continue
            for reg_idx, registro in enumerate(registros):
                if not isinstance(registro, dict):
                    continue
                pontos = registro.get("contorno_pontilhado") or registro.get("metade_movida")
                if not isinstance(pontos, list):
                    continue
                limite = len(pontos)
                if limite >= 2 and self._pontos_lista_mesmos(pontos[0], pontos[-1]):
                    limite -= 1
                for p_idx in range(limite):
                    pt = self._ponto_qt(pontos[p_idx])
                    if pt is None:
                        continue
                    dist = canvas._dist(pt, ponto)
                    if dist <= tolerancia and dist < melhor_dist:
                        melhor = (idx, reg_idx, p_idx)
                        melhor_dist = dist
        return melhor

    def _atualizar_dobra_pontilhada(self, canvas, alvo: tuple[int, int, int], destino: QPointF) -> None:
        idx, reg_idx, p_idx = alvo
        if not (0 <= idx < len(canvas.cena.elementos)):
            return
        registros = canvas.cena.elementos[idx].get("contornos_dobra_original")
        if not isinstance(registros, list) or not (0 <= reg_idx < len(registros)):
            return
        registro = registros[reg_idx]
        if not isinstance(registro, dict):
            return
        for chave in ("contorno_pontilhado", "metade_movida"):
            pontos = list(registro.get(chave) or [])
            if not (0 <= p_idx < len(pontos)):
                continue
            fechado = len(pontos) >= 2 and self._pontos_lista_mesmos(pontos[0], pontos[-1])
            pontos[p_idx] = (destino.x(), destino.y())
            if fechado:
                if p_idx == 0:
                    pontos[-1] = pontos[0]
                elif p_idx == len(pontos) - 1:
                    pontos[0] = pontos[-1]
            registro[chave] = pontos

    def _ponto_dobra_pontilhada(self, canvas, idx: int, reg_idx: int, p_idx: int) -> QPointF | None:
        if not (0 <= idx < len(canvas.cena.elementos)):
            return None
        registros = canvas.cena.elementos[idx].get("contornos_dobra_original")
        if not isinstance(registros, list) or not (0 <= reg_idx < len(registros)):
            return None
        registro = registros[reg_idx]
        if not isinstance(registro, dict):
            return None
        pontos = registro.get("contorno_pontilhado") or registro.get("metade_movida")
        if not isinstance(pontos, list) or not (0 <= p_idx < len(pontos)):
            return None
        return self._ponto_qt(pontos[p_idx])

    def _pontos_lista_mesmos(self, a, b) -> bool:
        pa = self._ponto_qt(a)
        pb = self._ponto_qt(b)
        if pa is None or pb is None:
            return False
        return abs(pa.x() - pb.x()) <= 1e-7 and abs(pa.y() - pb.y()) <= 1e-7

    def _desenhar_hover_dobra_pontilhada(self, canvas, painter) -> None:
        alvo = self._arrastando_dobra_pontilhada or self._hover_dobra_pontilhada
        if alvo is None:
            return
        idx, reg_idx, p_idx = alvo
        if not (0 <= idx < len(canvas.cena.elementos)):
            return
        registros = canvas.cena.elementos[idx].get("contornos_dobra_original")
        if not isinstance(registros, list) or not (0 <= reg_idx < len(registros)):
            return
        registro = registros[reg_idx]
        if not isinstance(registro, dict):
            return
        pontos = registro.get("contorno_pontilhado") or registro.get("metade_movida")
        if not isinstance(pontos, list) or not (0 <= p_idx < len(pontos)):
            return
        pt = self._ponto_qt(pontos[p_idx])
        if pt is None:
            return
        tela = canvas._cena_para_tela(pt)
        painter.setPen(QPen(QColor("#66d9ff"), 2.0))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(int(tela.x() - 11), int(tela.y() - 11), 22, 22)

    def _ponto_polilinha_em_ponto(self, canvas, ponto: QPointF) -> tuple[int, int] | None:
        tolerancia = 10.0 / max(canvas.zoom, 0.001)
        candidatos = sorted(canvas._selecionados) if canvas._selecionados else list(range(len(canvas.cena.elementos)))
        for idx in candidatos:
            if idx < 0 or idx >= len(canvas.cena.elementos):
                continue
            el = canvas.cena.elementos[idx]
            if el.get("tipo") != "polyline":
                continue

            if el.get("molde"):
                # Moldes so podem ser deformados pelos controles oficiais
                # (controle_cantos/controle_auxiliares), tratados antes desta busca.
                continue

            # Curva suave: só os pontos principais/controláveis aparecem e podem ser pegos.
            if self._elemento_curva_suave(el):
                controles = self._pontos_controle_curva(el)
                for controle_idx, controle in enumerate(controles):
                    if canvas._dist(controle, ponto) <= tolerancia:
                        p_real = self._indice_ponto_controle_para_ponto_real(canvas, el, controle_idx)
                        if p_real is not None:
                            return idx, p_real
                continue

            pontos = el.get("pontos", [])
            if el.get("molde"):
                indices_permitidos = self._indices_pontos_principais_molde(canvas, el)
                if not indices_permitidos:
                    continue
                indices_para_testar = sorted(indices_permitidos)
            else:
                indices_para_testar = range(len(pontos))
            for p_idx in indices_para_testar:
                if not (0 <= p_idx < len(pontos)):
                    continue
                x, y = pontos[p_idx]
                if canvas._dist(QPointF(float(x), float(y)), ponto) <= tolerancia:
                    return idx, p_idx
        return None

    def _pontos_polyline_editaveis_molde(self, el: dict) -> list[QPointF]:
        atuais = self._pontos_controle_molde_por_chaves(el, ("controle_cantos", "controle_auxiliares"))
        if atuais:
            return atuais
        return self._pontos_controle_molde_por_chaves(el, ("pontos_controle_principais", "pontos_auxiliares"))

    def _pontos_controle_molde_por_chaves(self, el: dict, chaves: tuple[str, ...]) -> list[QPointF]:
        saida: list[QPointF] = []
        vistos: set[tuple[float, float]] = set()
        for chave in chaves:
            valores = el.get(chave, [])
            if not isinstance(valores, list):
                continue
            for item in valores:
                pt = self._ponto_qt(item)
                if pt is None:
                    continue
                assinatura = (round(float(pt.x()), 7), round(float(pt.y()), 7))
                if assinatura in vistos:
                    continue
                vistos.add(assinatura)
                saida.append(QPointF(pt))
        return saida

    def _polyline_fechada(self, canvas, pontos: list) -> bool:
        if len(pontos) < 2:
            return False
        p0 = self._ponto_qt(pontos[0])
        pn = self._ponto_qt(pontos[-1])
        if p0 is None or pn is None:
            return False
        return canvas._dist(p0, pn) <= 1e-6

    def _indices_pontos_principais_molde(self, canvas, el: dict) -> set[int]:
        """
        Em moldes, a ferramenta Mover ponto deve operar apenas em pontos principais
        (controle_cantos), ignorando pontos auxiliares intermediários do contorno.
        """
        pontos = list(el.get("pontos", []))
        if not pontos:
            return set()
        fechado = len(pontos) >= 2 and canvas._dist(
            QPointF(float(pontos[0][0]), float(pontos[0][1])),
            QPointF(float(pontos[-1][0]), float(pontos[-1][1])),
        ) <= 1e-6
        n_base = len(pontos) - 1 if fechado else len(pontos)
        if n_base <= 0:
            return set()

        controles = el.get("controle_cantos", []) or []
        if not controles:
            return set(range(n_base))

        tol = 8.0 / max(canvas.zoom, 0.001)
        usados: set[int] = set()
        indices: set[int] = set()
        for item in controles:
            cp = self._ponto_qt(item)
            if cp is None:
                continue
            melhor_idx = -1
            melhor_dist = float("inf")
            for i in range(n_base):
                x, y = pontos[i]
                if i in usados:
                    continue
                dist = canvas._dist(cp, QPointF(float(x), float(y)))
                if dist < melhor_dist:
                    melhor_dist = dist
                    melhor_idx = i
            if melhor_idx >= 0 and melhor_dist <= tol:
                indices.add(melhor_idx)
                usados.add(melhor_idx)
        return {i for i in indices if 0 <= i < n_base}

    def _controle_molde_em_ponto(self, canvas, ponto: QPointF) -> tuple[int, str, int] | None:
        tolerancia = 8.0 / max(canvas.zoom, 0.001)
        melhor: tuple[int, str, int] | None = None
        melhor_dist = float("inf")
        candidatos = sorted(canvas._selecionados) if canvas._selecionados else list(range(len(canvas.cena.elementos)))
        for idx in candidatos:
            if idx < 0 or idx >= len(canvas.cena.elementos):
                continue
            el = canvas.cena.elementos[idx]
            if not el.get("molde"):
                continue
            for tipo, chave in (("canto", "controle_cantos"), ("aux", "controle_auxiliares")):
                for c_idx, item in enumerate(el.get(chave, [])):
                    controle = self._ponto_qt(item)
                    if controle is None:
                        continue
                    dist = canvas._dist(controle, ponto)
                    if dist <= tolerancia and dist < melhor_dist:
                        melhor = (idx, tipo, c_idx)
                        melhor_dist = dist
        return melhor

    def _molde_em_ponto(self, canvas, pos: QPointF) -> int | None:
        if not hasattr(canvas, "_indices_elementos_em_ponto"):
            return None
        for idx in canvas._indices_elementos_em_ponto(pos):
            if 0 <= idx < len(canvas.cena.elementos) and canvas.cena.elementos[idx].get("molde"):
                return idx
        return None

    def _elemento_em_hover(self, canvas, pos: QPointF) -> int | None:
        if canvas._snap_resultado is not None and canvas._snap_resultado.elemento_idx is not None:
            idx = int(canvas._snap_resultado.elemento_idx)
            if 0 <= idx < len(canvas.cena.elementos):
                return idx
        if not hasattr(canvas, "_indices_elementos_em_ponto"):
            return None
        candidatos = canvas._indices_elementos_em_ponto(pos)
        if not candidatos:
            return None
        return candidatos[0]

    def _gerar_guia(self, canvas, idx: int, p_idx: int):
        el = canvas.cena.elementos[idx]
        if self._curva_tracado_real(el):
            pontos = self._pontos_controle_curva(el)
        else:
            pontos = [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]
        if not (0 <= p_idx < len(pontos)):
            return None
        anterior = pontos[p_idx - 1] if p_idx > 0 else None
        proximo = pontos[p_idx + 1] if p_idx + 1 < len(pontos) else None
        return QPointF(pontos[p_idx]), anterior, proximo

    def _atualizar_ponto(self, canvas, idx: int, p_idx: int, pos: QPointF):
        el = canvas.cena.elementos[idx]

        if self._curva_tracado_real(el):
            controles = self._pontos_controle_curva(el)
            if not (0 <= p_idx < len(controles)):
                return
            controles[p_idx] = QPointF(pos)
            self._salvar_controles_curva_real(el, controles)
            el["pontos"] = self._gerar_tracado_curva_real(
                controles,
                fechado=bool(el.get("fechado")),
                tipo_curva=str(el.get("tipo_curva") or ""),
            )
            return

        pontos = list(el.get("pontos", []))
        if not (0 <= p_idx < len(pontos)):
            return
        anterior = QPointF(float(pontos[p_idx][0]), float(pontos[p_idx][1]))
        pontos[p_idx] = (pos.x(), pos.y())
        if len(pontos) >= 2:
            p0 = QPointF(float(pontos[0][0]), float(pontos[0][1]))
            pn = QPointF(float(pontos[-1][0]), float(pontos[-1][1]))
            if canvas._dist(p0, pn) <= 0.0001:
                if p_idx == 0:
                    pontos[-1] = pontos[0]
                elif p_idx == len(pontos) - 1:
                    pontos[0] = pontos[-1]
        el["pontos"] = pontos
        self._sincronizar_curva_suave(el)
        if el.get("molde"):
            self._mover_controles_correspondentes(canvas, el, anterior, pos)
            self._reajustar_fio_no_molde(el)

    def _mover_controles_correspondentes(self, canvas, el: dict, anterior: QPointF, novo: QPointF):
        tol = 10.0 / max(canvas.zoom, 0.001)
        dx = novo.x() - anterior.x()
        dy = novo.y() - anterior.y()
        for chave in ("controle_cantos", "controle_auxiliares"):
            atualizados: list[tuple[float, float]] = []
            for cx, cy in el.get(chave, []):
                cp = QPointF(float(cx), float(cy))
                if canvas._dist(cp, anterior) <= tol:
                    atualizados.append((cp.x() + dx, cp.y() + dy))
                else:
                    atualizados.append((cp.x(), cp.y()))
            if atualizados:
                el[chave] = atualizados

    def _alvos_controle_para_arraste(self, controle: tuple[int, str, int]) -> set[tuple[int, str, int]]:
        if controle in self._controles_selecionados:
            return set(self._controles_selecionados)
        return {controle}

    def _normalizar_destino(self, destino: QPointF) -> QPointF:
        if self._modo_discreto():
            return QPointF(round(destino.x(), 2), round(destino.y(), 2))
        return QPointF(destino)

    def _snap_exato_ativo(self, canvas) -> bool:
        snap = getattr(canvas, "_snap_resultado", None)
        tipo = str(getattr(snap, "tipo", "") or "").lower()
        return tipo in {
            "nó",
            "nÃ³",
            "ponto médio",
            "ponto mÃ©dio",
            "centro",
            "borda",
            "coord",
            "interseção",
            "interseÃ§Ã£o",
            "controle",
            "controle principal",
            "controle auxiliar",
            "fio",
            "nome",
        }

    def _destino_com_snap_e_eixos(self, canvas, origem: QPointF, destino: QPointF) -> QPointF:
        ajustado = QPointF(destino)
        ajustado = self._normalizar_destino(ajustado)
        self._guia_eixo = (QPointF(origem), QPointF(ajustado))
        return ajustado

    def _posicao_arraste_livre(self, canvas, event) -> QPointF:
        if self._arraste_ativo() and hasattr(canvas, "_tela_para_cena"):
            canvas._snap_resultado = None
            canvas._snap_candidatos = []
            canvas._snap_indice = 0
            return canvas._tela_para_cena(event.position())
        return canvas._ponto_com_snap(event.position())

    def _snap_angular_suave(self, origem: QPointF, destino: QPointF) -> QPointF:
        dx = destino.x() - origem.x()
        dy = destino.y() - origem.y()
        dist = sqrt((dx * dx) + (dy * dy))
        if dist <= 1e-9:
            return QPointF(destino)
        ang = degrees(atan2(-dy, dx))
        alvo = round(ang / 45.0) * 45.0
        if self._distancia_angular_local(ang, alvo) > 2.0:
            return QPointF(destino)
        rad = radians(alvo)
        ux = cos(rad)
        uy = -sin(rad)
        proj = (dx * ux) + (dy * uy)
        if proj <= 1e-9:
            return QPointF(destino)
        return QPointF(round(origem.x() + (proj * ux), 12), round(origem.y() + (proj * uy), 12))

    @staticmethod
    def _distancia_angular_local(a: float, b: float) -> float:
        diff = abs((a - b) % 360.0)
        return min(diff, 360.0 - diff)

    def _criar_estado_arraste_controle(self, canvas, controle: tuple[int, str, int]) -> dict | None:
        origem = self._ponto_controle_molde(canvas, *controle)
        if origem is None:
            return None
        alvos = self._alvos_controle_para_arraste(controle)
        indices = {idx for idx, _tipo, _controle_idx in alvos}
        return {
            "origem": QPointF(origem),
            "alvos": set(alvos),
            "elementos": self._capturar_elementos(canvas, indices),
            "mapas_auxiliares": self._mapas_auxiliares_arraste(canvas, indices),
            "auxiliares_retos": self._auxiliares_retos_arraste(canvas, indices),
        }

    def _criar_estado_arraste_ponto(self, canvas, idx: int, p_idx: int) -> dict | None:
        if not (0 <= idx < len(canvas.cena.elementos)):
            return None
        el = canvas.cena.elementos[idx]
        if self._curva_tracado_real(el):
            pontos = self._pontos_controle_curva(el)
        else:
            pontos = el.get("pontos", [])
        if not (0 <= p_idx < len(pontos)):
            return None
        origem = self._ponto_qt(pontos[p_idx])
        if origem is None:
            return None
        return {
            "origem": QPointF(origem),
            "elementos": self._capturar_elementos(canvas, {idx}),
        }

    def _criar_estado_arraste_dobra(self, canvas, alvo: tuple[int, int, int]) -> dict | None:
        idx, _reg_idx, _p_idx = alvo
        if not (0 <= idx < len(canvas.cena.elementos)):
            return None
        return {
            "elementos": self._capturar_elementos(canvas, {idx}),
        }

    def _capturar_elementos(self, canvas, indices: set[int]) -> dict[int, dict]:
        capturados: dict[int, dict] = {}
        for idx in indices:
            if 0 <= idx < len(canvas.cena.elementos) and isinstance(canvas.cena.elementos[idx], dict):
                capturados[idx] = deepcopy(canvas.cena.elementos[idx])
        return capturados

    def _restaurar_estado_arraste(self, canvas, estado: dict) -> None:
        elementos = estado.get("elementos", {})
        if not isinstance(elementos, dict):
            return
        mapas_auxiliares = estado.get("mapas_auxiliares", {})
        if not isinstance(mapas_auxiliares, dict):
            mapas_auxiliares = {}
        auxiliares_retos = estado.get("auxiliares_retos", {})
        if not isinstance(auxiliares_retos, dict):
            auxiliares_retos = {}
        for idx, elemento in elementos.items():
            if 0 <= int(idx) < len(canvas.cena.elementos):
                restaurado = deepcopy(elemento)
                mapa = mapas_auxiliares.get(int(idx))
                if mapa is not None:
                    restaurado["_segmentos_auxiliares_arraste"] = list(mapa)
                retos = auxiliares_retos.get(int(idx))
                if retos is not None:
                    restaurado["_auxiliares_retos_arraste"] = list(retos)
                canvas.cena.elementos[int(idx)] = restaurado

    def _mapas_auxiliares_arraste(self, canvas, indices: set[int]) -> dict[int, list[int]]:
        mapas: dict[int, list[int]] = {}
        for idx in indices:
            if not (0 <= int(idx) < len(canvas.cena.elementos)):
                continue
            el = canvas.cena.elementos[int(idx)]
            mapa = self._mapa_segmentos_auxiliares_molde(canvas, el)
            if mapa:
                mapas[int(idx)] = mapa
        return mapas

    def _auxiliares_retos_arraste(self, canvas, indices: set[int]) -> dict[int, list[bool]]:
        retos: dict[int, list[bool]] = {}
        for idx in indices:
            if not (0 <= int(idx) < len(canvas.cena.elementos)):
                continue
            el = canvas.cena.elementos[int(idx)]
            mapa = self._mapa_segmentos_auxiliares_molde(canvas, el)
            valores = self._mapa_auxiliares_sobre_retas_molde(canvas, el, mapa)
            if valores:
                retos[int(idx)] = valores
        return retos

    def _mapa_segmentos_auxiliares_molde(self, canvas, el: dict) -> list[int]:
        if not self._molde_tem_controles_curva(el):
            return []
        cantos = [p for p in (self._ponto_qt(item) for item in el.get("controle_cantos", []) or []) if p is not None]
        auxiliares = [p for p in (self._ponto_qt(item) for item in el.get("controle_auxiliares", []) or []) if p is not None]
        if len(cantos) < 2 or not auxiliares:
            return []
        pontos = list(el.get("pontos", []) or [])
        fechado = self._molde_fechado_por_pontos_ou_controles(canvas, el, pontos, cantos)
        segmentos = self._segmentos_cantos(cantos, fechado)
        if not segmentos:
            return []
        mapa_por_ordem = self._mapa_segmentos_auxiliares_por_ordem_pontos(
            canvas,
            pontos,
            cantos,
            auxiliares,
            segmentos,
            fechado,
        )
        if mapa_por_ordem:
            return mapa_por_ordem
        por_segmento = self._auxiliares_por_segmento_indexados(cantos, segmentos, auxiliares, preferir_ordem=False)
        mapa = [-1 for _ in auxiliares]
        for seg_ordem, itens in por_segmento.items():
            for aux_idx, _t, _pt in itens:
                if 0 <= aux_idx < len(mapa):
                    mapa[aux_idx] = int(seg_ordem)
        return mapa if all(seg >= 0 for seg in mapa) else []

    def _mapa_segmentos_auxiliares_por_ordem_pontos(
        self,
        canvas,
        pontos: list,
        cantos: list[QPointF],
        auxiliares: list[QPointF],
        segmentos: list[tuple[int, int]],
        fechado: bool,
    ) -> list[int]:
        if len(pontos) < 2 or not auxiliares:
            return []
        n = len(pontos) - 1 if fechado and len(pontos) >= 2 else len(pontos)
        if n <= 0:
            return []
        pontos_base = pontos[:n]
        indices_cantos: list[int | None] = []
        for canto in cantos:
            indices_cantos.append(self._indice_ponto_mais_proximo(canvas, pontos_base, canto))
        if any(idx is None for idx in indices_cantos):
            return []

        mapa = [-1 for _ in auxiliares]
        for aux_idx, aux in enumerate(auxiliares):
            aresta_aux = self._aresta_contorno_mais_proxima(pontos_base, aux, fechado)
            if aresta_aux is None:
                return []
            aresta_a, aresta_b = aresta_aux
            candidatos: list[tuple[float, int]] = []
            for seg_ordem, (a_idx, b_idx) in enumerate(segmentos):
                inicio = indices_cantos[a_idx]
                fim = indices_cantos[b_idx]
                if inicio is None or fim is None:
                    return []
                indices = self._indices_intervalo(int(inicio), int(fim), n, fechado)
                if int(aresta_a) in indices and int(aresta_b) in indices:
                    a = cantos[a_idx]
                    b = cantos[b_idx]
                    candidatos.append((self._distancia_ponto_segmento_local(aux, a, b), seg_ordem))
            if not candidatos:
                return []
            mapa[aux_idx] = min(candidatos, key=lambda item: item[0])[1]
        return mapa if all(seg >= 0 for seg in mapa) else []

    def _aresta_contorno_mais_proxima(self, pontos: list, aux: QPointF, fechado: bool) -> tuple[int, int] | None:
        pts = [self._ponto_qt(item) for item in pontos]
        pts = [pt for pt in pts if pt is not None]
        if len(pts) < 2:
            return None
        limite = len(pts) if fechado else len(pts) - 1
        melhor: tuple[int, int] | None = None
        melhor_dist = float("inf")
        for i in range(limite):
            j = (i + 1) % len(pts)
            if not fechado and j <= i:
                continue
            dist = self._distancia_ponto_segmento_local(aux, pts[i], pts[j])
            if dist < melhor_dist:
                melhor_dist = dist
                melhor = (i, j)
        return melhor

    def _mapa_auxiliares_sobre_retas_molde(self, canvas, el: dict, mapa: list[int]) -> list[bool]:
        cantos = [p for p in (self._ponto_qt(item) for item in el.get("controle_cantos", []) or []) if p is not None]
        auxiliares = [p for p in (self._ponto_qt(item) for item in el.get("controle_auxiliares", []) or []) if p is not None]
        if len(cantos) < 2 or not auxiliares:
            return []
        pontos = list(el.get("pontos", []) or [])
        fechado = self._molde_fechado_por_pontos_ou_controles(canvas, el, pontos, cantos)
        segmentos = self._segmentos_cantos(cantos, fechado)
        if not self._mapa_auxiliares_valido(mapa, auxiliares, segmentos):
            return []
        saida: list[bool] = []
        for aux_idx, aux in enumerate(auxiliares):
            a_idx, b_idx = segmentos[int(mapa[aux_idx])]
            a = cantos[a_idx]
            b = cantos[b_idx]
            limite_reta = max(0.02, self._dist_pontos_local(a, b) * 0.002)
            saida.append(self._distancia_ponto_segmento_local(aux, a, b) <= limite_reta)
        return saida

    def _ponto_controle_molde(self, canvas, idx: int, tipo: str, controle_idx: int) -> QPointF | None:
        if not (0 <= idx < len(canvas.cena.elementos)):
            return None
        el = canvas.cena.elementos[idx]
        chave = "controle_cantos" if tipo == "canto" else "controle_auxiliares"
        controles = el.get(chave, [])
        if not (0 <= controle_idx < len(controles)):
            return None
        return self._ponto_qt(controles[controle_idx])

    def _mover_controles_por_delta(self, canvas, controles: set[tuple[int, str, int]], dx: float, dy: float) -> None:
        if abs(dx) <= 1e-9 and abs(dy) <= 1e-9:
            return
        for idx, tipo, controle_idx in sorted(controles):
            atual = self._ponto_controle_molde(canvas, idx, tipo, controle_idx)
            if atual is None:
                continue
            destino = QPointF(atual.x() + dx, atual.y() + dy)
            destino = self._normalizar_destino(destino)
            self._arrastar_controle_molde(canvas, idx, tipo, controle_idx, destino)

    def _arrastar_controle_molde(self, canvas, idx: int, tipo: str, controle_idx: int, destino: QPointF):
        if not (0 <= idx < len(canvas.cena.elementos)):
            return
        el = canvas.cena.elementos[idx]
        if el.get("tipo") != "polyline":
            return
        destino = self._normalizar_destino(destino)
        if tipo == "canto":
            self._arrastar_canto_molde(canvas, el, controle_idx, destino)
        else:
            self._arrastar_auxiliar_molde(canvas, el, controle_idx, destino)
        self._regenerar_molde_por_controles(canvas, el)
        self._reajustar_fio_no_molde(el)

    def _arrastar_canto_molde(self, canvas, el: dict, controle_idx: int, destino: QPointF):
        cantos = list(el.get("controle_cantos", []))
        if not (0 <= controle_idx < len(cantos)):
            return
        anterior = self._ponto_qt(cantos[controle_idx])
        if anterior is None:
            return
        dx = destino.x() - anterior.x()
        dy = destino.y() - anterior.y()
        pontos_originais = list(el.get("pontos", []))
        ponto_idx = self._indice_ponto_mais_proximo(canvas, pontos_originais, anterior)
        cantos[controle_idx] = (destino.x(), destino.y())
        el["controle_cantos"] = cantos
        self._atualizar_espelho_controle(el, "pontos_controle_principais", controle_idx, destino)

        pontos = list(el.get("pontos", []))
        tol = 10.0 / max(canvas.zoom, 0.001)
        for p_idx, (x, y) in enumerate(pontos):
            if canvas._dist(QPointF(float(x), float(y)), anterior) <= tol:
                pontos[p_idx] = (destino.x(), destino.y())
        if len(pontos) >= 2:
            p0 = QPointF(float(pontos[0][0]), float(pontos[0][1]))
            pn = QPointF(float(pontos[-1][0]), float(pontos[-1][1]))
            if canvas._dist(p0, pn) <= tol:
                pontos[-1] = pontos[0]
        el["pontos"] = pontos
        if ponto_idx is not None and not self._molde_tem_controles_curva(el):
            self._redistribuir_molde_local_por_ponto(canvas, el, pontos_originais, ponto_idx, dx, dy)

    def _indice_ponto_mais_proximo(self, canvas, pontos: list, alvo: QPointF) -> int | None:
        if not pontos:
            return None
        tol = 10.0 / max(canvas.zoom, 0.001)
        melhor_idx: int | None = None
        melhor_dist = float("inf")
        for idx, item in enumerate(pontos):
            pt = self._ponto_qt(item)
            if pt is None:
                continue
            dist = canvas._dist(pt, alvo)
            if dist < melhor_dist:
                melhor_dist = dist
                melhor_idx = idx
        if melhor_idx is None or melhor_dist > tol:
            return None
        return melhor_idx

    def _arrastar_auxiliar_molde(self, canvas, el: dict, controle_idx: int, destino: QPointF):
        aux = list(el.get("controle_auxiliares", []))
        if not (0 <= controle_idx < len(aux)):
            return

        origem_aux = self._ponto_qt(aux[controle_idx])
        if origem_aux is None:
            return
        aux_originais = [p for p in (self._ponto_qt(item) for item in aux) if p is not None]
        destino = self._limitar_auxiliar_no_trecho(canvas, el, controle_idx, origem_aux, destino, aux_originais)
        dx = destino.x() - origem_aux.x()
        dy = destino.y() - origem_aux.y()
        pontos_originais = list(el.get("pontos", []))
        ponto_idx = self._indice_ponto_mais_proximo(canvas, pontos_originais, origem_aux)
        aux[controle_idx] = (destino.x(), destino.y())
        el["controle_auxiliares"] = aux
        el["_auxiliar_arrastado_idx"] = int(controle_idx)
        self._atualizar_espelho_controle(el, "pontos_auxiliares", controle_idx, destino)

        cantos = list(el.get("controle_cantos", []))
        if len(cantos) < 2 or len(pontos_originais) < 2:
            if ponto_idx is not None:
                self._redistribuir_molde_local_por_ponto(canvas, el, pontos_originais, ponto_idx, dx, dy)
            return

        if self._molde_tem_controles_curva(el):
            self._mover_extremos_se_auxiliar_for_alca_reta(
                canvas,
                el,
                controle_idx,
                aux_originais,
                pontos_originais,
                dx,
                dy,
            )
            return

        a_idx, b_idx = self._segmento_indices_do_auxiliar(cantos, aux, controle_idx, origem_aux)
        if a_idx is None or b_idx is None:
            if ponto_idx is not None:
                self._redistribuir_molde_local_por_ponto(canvas, el, pontos_originais, ponto_idx, dx, dy)
            return
        a = self._ponto_qt(cantos[a_idx])
        b = self._ponto_qt(cantos[b_idx])
        if a is None or b is None:
            if ponto_idx is not None:
                self._redistribuir_molde_local_por_ponto(canvas, el, pontos_originais, ponto_idx, dx, dy)
            return

        ponto_a_idx = self._indice_ponto_mais_proximo(canvas, pontos_originais, a)
        ponto_b_idx = self._indice_ponto_mais_proximo(canvas, pontos_originais, b)
        if ponto_a_idx is None or ponto_b_idx is None or ponto_a_idx == ponto_b_idx:
            if ponto_idx is not None:
                self._redistribuir_molde_local_por_ponto(canvas, el, pontos_originais, ponto_idx, dx, dy)
            return

        fechado = len(pontos_originais) >= 2 and canvas._dist(
            self._ponto_qt(pontos_originais[0]) or QPointF(),
            self._ponto_qt(pontos_originais[-1]) or QPointF(),
        ) <= 1e-6
        n = len(pontos_originais) - 1 if fechado else len(pontos_originais)
        indices = self._indices_intervalo(ponto_a_idx, ponto_b_idx, n, fechado)
        if len(indices) < 2:
            return

        pontos = list(pontos_originais)
        denom = max(1, len(indices) - 1)
        controle_bezier = self._controle_quadratico_passando_por_meio(a, destino, b)
        for pos, idx_local in enumerate(indices):
            t = pos / float(denom)
            novo = self._bezier_quadratica(a, controle_bezier, b, t)
            if self._modo_discreto():
                novo = QPointF(round(novo.x(), 2), round(novo.y(), 2))
            pontos[idx_local] = (novo.x(), novo.y())
        if fechado and len(pontos) >= 2:
            pontos[-1] = pontos[0]
        el["pontos"] = pontos
        self._sincronizar_curva_suave(el)

    def _limitar_auxiliar_no_trecho(
        self,
        canvas,
        el: dict,
        controle_idx: int,
        origem_aux: QPointF,
        destino: QPointF,
        auxiliares_originais: list[QPointF],
    ) -> QPointF:
        cantos = [p for p in (self._ponto_qt(item) for item in el.get("controle_cantos", []) or []) if p is not None]
        if len(cantos) < 2 or not (0 <= controle_idx < len(auxiliares_originais)):
            return QPointF(destino)
        pontos = list(el.get("pontos", []) or [])
        fechado = self._molde_fechado_por_pontos_ou_controles(canvas, el, pontos, cantos)
        segmentos = self._segmentos_cantos(cantos, fechado)
        if not segmentos:
            return QPointF(destino)

        mapa = el.get("_segmentos_auxiliares_arraste")
        if self._mapa_auxiliares_valido(mapa, auxiliares_originais, segmentos):
            seg_ordem = int(mapa[controle_idx])
        else:
            a_idx, b_idx = self._segmento_indices_do_auxiliar(
                [(p.x(), p.y()) for p in cantos],
                [(p.x(), p.y()) for p in auxiliares_originais],
                controle_idx,
                origem_aux,
            )
            if a_idx is None or b_idx is None:
                return QPointF(destino)
            try:
                seg_ordem = segmentos.index((int(a_idx), int(b_idx)))
            except ValueError:
                return QPointF(destino)

        a_idx, b_idx = segmentos[seg_ordem]
        a = cantos[a_idx]
        b = cantos[b_idx]
        abx = b.x() - a.x()
        aby = b.y() - a.y()
        den = (abx * abx) + (aby * aby)
        if den <= 1e-12:
            return QPointF(destino)

        def parametro_livre(pt: QPointF) -> float:
            return (((pt.x() - a.x()) * abx) + ((pt.y() - a.y()) * aby)) / den

        atual_t = parametro_livre(origem_aux)
        destino_t = parametro_livre(destino)
        vizinhos = [0.0, 1.0]
        for aux_idx, aux in enumerate(auxiliares_originais):
            if aux_idx == controle_idx:
                continue
            if self._mapa_auxiliares_valido(mapa, auxiliares_originais, segmentos):
                if int(mapa[aux_idx]) != seg_ordem:
                    continue
            else:
                seg_aux = self._segmento_controle_mais_proximo(cantos, aux)
                if seg_aux != segmentos[seg_ordem]:
                    continue
            vizinhos.append(parametro_livre(aux))
        anteriores = [t for t in vizinhos if t < atual_t]
        proximos = [t for t in vizinhos if t > atual_t]
        limite_min = max(anteriores) if anteriores else 0.0
        limite_max = min(proximos) if proximos else 1.0
        comprimento = max(sqrt(den), 1e-9)
        folga = min(0.005, 0.05 / comprimento)
        limite_min += folga
        limite_max -= folga
        if limite_min > limite_max:
            meio = (limite_min + limite_max) / 2.0
            limite_min = limite_max = meio
        t_final = max(limite_min, min(limite_max, destino_t))

        proj_destino = QPointF(a.x() + (abx * destino_t), a.y() + (aby * destino_t))
        offset_x = destino.x() - proj_destino.x()
        offset_y = destino.y() - proj_destino.y()
        ajustado = QPointF(a.x() + (abx * t_final) + offset_x, a.y() + (aby * t_final) + offset_y)
        return self._normalizar_destino(ajustado)

    def _mover_extremos_se_auxiliar_for_alca_reta(
        self,
        canvas,
        el: dict,
        controle_idx: int,
        auxiliares_originais: list[QPointF],
        pontos_originais: list,
        dx: float,
        dy: float,
    ) -> None:
        if abs(dx) <= 1e-9 and abs(dy) <= 1e-9:
            return
        cantos = [p for p in (self._ponto_qt(item) for item in el.get("controle_cantos", []) or []) if p is not None]
        if len(cantos) < 2 or not (0 <= controle_idx < len(auxiliares_originais)):
            return
        fechado = self._molde_fechado_por_pontos_ou_controles(canvas, el, pontos_originais, cantos)
        segmentos = self._segmentos_cantos(cantos, fechado)
        por_segmento = self._auxiliares_por_segmento_indexados(cantos, segmentos, auxiliares_originais)
        segmento_alvo: tuple[int, int] | None = None
        for seg_ordem, itens in por_segmento.items():
            if len(itens) != 1:
                continue
            aux_idx, _t, pt_aux = itens[0]
            if aux_idx == controle_idx:
                segmento_alvo = segmentos[seg_ordem]
                a_idx, b_idx = segmento_alvo
                a = cantos[a_idx]
                b = cantos[b_idx]
                desvio = self._distancia_ponto_segmento_local(pt_aux, a, b)
                limite_reta = max(0.02, self._dist_pontos_local(a, b) * 0.002)
                if desvio > limite_reta:
                    return
                break
        if segmento_alvo is None:
            return

        cantos_raw = list(el.get("controle_cantos", []) or [])
        for canto_idx in segmento_alvo:
            if not (0 <= canto_idx < len(cantos_raw)):
                continue
            canto = self._ponto_qt(cantos_raw[canto_idx])
            if canto is None:
                continue
            destino = QPointF(canto.x() + dx, canto.y() + dy)
            if self._modo_discreto():
                destino = QPointF(round(destino.x(), 2), round(destino.y(), 2))
            cantos_raw[canto_idx] = (float(destino.x()), float(destino.y()))
            self._atualizar_espelho_controle(el, "pontos_controle_principais", canto_idx, destino)
        el["controle_cantos"] = cantos_raw

    def _redistribuir_molde_local_por_ponto(
        self,
        canvas,
        el: dict,
        pontos_base: list,
        p_idx: int,
        dx: float,
        dy: float,
    ) -> bool:
        if len(pontos_base) < 2:
            return False
        fechado = len(pontos_base) >= 2 and canvas._dist(
            self._ponto_qt(pontos_base[0]) or QPointF(),
            self._ponto_qt(pontos_base[-1]) or QPointF(),
        ) <= 1e-6
        n = len(pontos_base) - 1 if fechado else len(pontos_base)
        if n <= 0:
            return False
        if fechado and p_idx == len(pontos_base) - 1:
            p_idx = 0
        if not (0 <= p_idx < n):
            return False

        ancoras = self._ancoras_molde_ordenadas(canvas, el, pontos_base)
        if p_idx not in ancoras:
            ancoras.append(p_idx)
            ancoras.sort()
        pos_atual = next((i for i, ancora in enumerate(ancoras) if ancora == p_idx), None)
        if pos_atual is None:
            return False

        novos = list(pontos_base)
        x, y = pontos_base[p_idx]
        nx = float(x) + dx
        ny = float(y) + dy
        if self._modo_discreto():
            nx = round(nx, 2)
            ny = round(ny, 2)
        novos[p_idx] = (nx, ny)

        anterior = ancoras[pos_atual - 1] if pos_atual > 0 else (ancoras[-1] if fechado and len(ancoras) > 1 else None)
        proximo = (
            ancoras[pos_atual + 1]
            if pos_atual + 1 < len(ancoras)
            else (ancoras[0] if fechado and len(ancoras) > 1 else None)
        )

        if anterior is not None and anterior != p_idx:
            indices = self._indices_intervalo(anterior, p_idx, n, fechado)
            self._aplicar_deslocamento_intervalo_molde(novos, pontos_base, indices, (0.0, 0.0), (dx, dy))
        if proximo is not None and proximo != p_idx:
            indices = self._indices_intervalo(p_idx, proximo, n, fechado)
            self._aplicar_deslocamento_intervalo_molde(novos, pontos_base, indices, (dx, dy), (0.0, 0.0))

        if fechado and len(novos) >= 2:
            novos[-1] = novos[0]
        el["pontos"] = novos
        self._sincronizar_curva_suave(el)
        return True

    def _ancoras_molde_ordenadas(self, canvas, el: dict, pontos_base: list) -> list[int]:
        fechado = len(pontos_base) >= 2 and canvas._dist(
            self._ponto_qt(pontos_base[0]) or QPointF(),
            self._ponto_qt(pontos_base[-1]) or QPointF(),
        ) <= 1e-6
        n = len(pontos_base) - 1 if fechado else len(pontos_base)
        if n <= 0:
            return []
        encontrados: set[int] = set()
        for chave in ("controle_cantos", "controle_auxiliares"):
            for item in el.get(chave, []) or []:
                pt = self._ponto_qt(item)
                if pt is None:
                    continue
                idx = self._indice_ponto_mais_proximo(canvas, pontos_base[:n], pt)
                if idx is not None and 0 <= idx < n:
                    encontrados.add(idx)
        return sorted(encontrados)

    def _aplicar_deslocamento_intervalo_molde(
        self,
        novos: list,
        pontos_base: list,
        indices: list[int],
        desloc_a: tuple[float, float],
        desloc_b: tuple[float, float],
    ) -> None:
        if len(indices) < 2:
            return
        denom = max(1, len(indices) - 1)
        dxa, dya = desloc_a
        dxb, dyb = desloc_b
        for pos, idx_local in enumerate(indices):
            if not (0 <= idx_local < len(pontos_base)):
                continue
            t = max(0.0, min(1.0, pos / float(denom)))
            ddx = (dxa * (1.0 - t)) + (dxb * t)
            ddy = (dya * (1.0 - t)) + (dyb * t)
            x, y = pontos_base[idx_local]
            nx = float(x) + ddx
            ny = float(y) + ddy
            if self._modo_discreto():
                nx = round(nx, 2)
                ny = round(ny, 2)
            novos[idx_local] = (nx, ny)

    def _segmento_indices_do_auxiliar(
        self,
        cantos: list,
        auxiliares: list,
        controle_idx: int,
        origem_aux: QPointF,
    ) -> tuple[int | None, int | None]:
        total = len(cantos)
        if total < 2:
            return None, None
        return self._segmento_controle_mais_proximo(cantos, origem_aux)

    def _bezier_quadratica(self, a: QPointF, controle: QPointF, b: QPointF, t: float) -> QPointF:
        u = 1.0 - t
        x = (u * u * a.x()) + (2.0 * u * t * controle.x()) + (t * t * b.x())
        y = (u * u * a.y()) + (2.0 * u * t * controle.y()) + (t * t * b.y())
        return QPointF(x, y)

    def _controle_quadratico_passando_por_meio(self, a: QPointF, meio: QPointF, b: QPointF) -> QPointF:
        x, y = quadratic_bezier_control_for_point(
            (float(a.x()), float(a.y())),
            (float(meio.x()), float(meio.y())),
            (float(b.x()), float(b.y())),
        )
        return QPointF(x, y)

    def _molde_tem_controles_curva(self, el: dict) -> bool:
        cantos = el.get("controle_cantos", [])
        auxiliares = el.get("controle_auxiliares", [])
        return isinstance(cantos, list) and len(cantos) >= 1 and isinstance(auxiliares, list)

    def _garantir_auxiliares_minimos_curva_molde(
        self,
        canvas,
        el: dict,
        recompor_segmentos: set[int] | None = None,
    ) -> None:
        cantos = [p for p in (self._ponto_qt(item) for item in el.get("controle_cantos", []) or []) if p is not None]
        if not cantos:
            return
        pontos = [p for p in (self._ponto_qt(item) for item in el.get("pontos", []) or []) if p is not None]
        fechado = self._molde_fechado_por_pontos_ou_controles(canvas, el, el.get("pontos", []) or [], cantos)
        segmentos = self._segmentos_cantos(cantos, fechado)
        if not segmentos:
            return
        auxiliares = [p for p in (self._ponto_qt(item) for item in el.get("controle_auxiliares", []) or []) if p is not None]
        por_segmento = self._auxiliares_por_segmento_indexados(cantos, segmentos, auxiliares, preferir_ordem=False)
        recompor_segmentos = set(recompor_segmentos or set())
        novos_aux: list[QPointF] = []
        alterou = False

        for seg_ordem, (a_idx, b_idx) in enumerate(segmentos):
            existentes = [QPointF(pt) for _idx, _t, pt in por_segmento.get(seg_ordem, [])]
            trecho = self._trecho_contorno_molde(canvas, pontos, cantos, a_idx, b_idx, fechado)
            curva = self._segmento_molde_eh_curvo(cantos[a_idx], cantos[b_idx], trecho, existentes)
            precisa_recompor = curva and (seg_ordem in recompor_segmentos or len(existentes) < 2)
            if precisa_recompor:
                amostrados = self._amostrar_auxiliares_minimos_trecho(trecho, cantos[a_idx], cantos[b_idx], quantidade=3)
                if len(amostrados) >= 2:
                    novos_aux.extend(amostrados)
                    alterou = True
                    continue
            novos_aux.extend(existentes)

        if alterou:
            el["controle_auxiliares"] = [(float(p.x()), float(p.y())) for p in novos_aux]
            el["pontos_auxiliares"] = [{"x": float(p.x()), "y": float(p.y())} for p in novos_aux]

    def _trecho_contorno_molde(
        self,
        canvas,
        pontos: list[QPointF],
        cantos: list[QPointF],
        a_idx: int,
        b_idx: int,
        fechado: bool,
    ) -> list[QPointF]:
        if not pontos:
            a = cantos[a_idx]
            b = cantos[b_idx]
            return [QPointF(a), QPointF(b)]
        base = [QPointF(p) for p in pontos]
        if len(base) >= 2 and self._dist_pontos_local(base[0], base[-1]) <= 1e-6:
            base = base[:-1]
        if not base:
            return []
        if a_idx == b_idx and fechado:
            return [*base, QPointF(base[0])]
        n = len(base)
        inicio = self._indice_ponto_mais_proximo(canvas, base, cantos[a_idx])
        fim = self._indice_ponto_mais_proximo(canvas, base, cantos[b_idx])
        if inicio is None or fim is None:
            return [QPointF(cantos[a_idx]), QPointF(cantos[b_idx])]
        return [QPointF(base[i]) for i in self._indices_intervalo(inicio, fim, n, fechado)]

    def _segmento_molde_eh_curvo(
        self,
        a: QPointF,
        b: QPointF,
        trecho: list[QPointF],
        auxiliares: list[QPointF],
    ) -> bool:
        if self._dist_pontos_local(a, b) <= 1e-9:
            return True
        limite = max(0.02, self._dist_pontos_local(a, b) * 0.002)
        for pt in auxiliares:
            if self._distancia_ponto_segmento_local(pt, a, b) > limite:
                return True
        if len(trecho) <= 2:
            return False
        return any(self._distancia_ponto_segmento_local(pt, a, b) > limite for pt in trecho[1:-1])

    def _amostrar_auxiliares_minimos_trecho(
        self,
        trecho: list[QPointF],
        a: QPointF,
        b: QPointF,
        quantidade: int,
    ) -> list[QPointF]:
        caminho = [QPointF(p) for p in trecho if p is not None]
        if len(caminho) < 2:
            caminho = [QPointF(a), QPointF(b)]
        if len(caminho) >= 2 and self._dist_pontos_local(caminho[0], caminho[-1]) <= 1e-9:
            total = sum(self._dist_pontos_local(x, y) for x, y in zip(caminho, caminho[1:]))
            if total <= 1e-9:
                return []
        return [
            self._ponto_em_caminho_por_fracao(caminho, i / float(quantidade + 1))
            for i in range(1, quantidade + 1)
        ]

    def _ponto_em_caminho_por_fracao(self, caminho: list[QPointF], fracao: float) -> QPointF:
        if not caminho:
            return QPointF()
        if len(caminho) == 1:
            return QPointF(caminho[0])
        total = sum(self._dist_pontos_local(a, b) for a, b in zip(caminho, caminho[1:]))
        if total <= 1e-9:
            return QPointF(caminho[0])
        alvo = total * max(0.0, min(1.0, fracao))
        acumulado = 0.0
        for a, b in zip(caminho, caminho[1:]):
            dist = self._dist_pontos_local(a, b)
            if dist <= 1e-9:
                continue
            if acumulado + dist >= alvo:
                t = (alvo - acumulado) / dist
                return QPointF(a.x() + ((b.x() - a.x()) * t), a.y() + ((b.y() - a.y()) * t))
            acumulado += dist
        return QPointF(caminho[-1])

    def _regenerar_molde_por_controles(self, canvas, el: dict) -> bool:
        if not self._molde_tem_controles_curva(el):
            return False
        cantos = [p for p in (self._ponto_qt(item) for item in el.get("controle_cantos", []) or []) if p is not None]
        if not cantos:
            return False
        pontos_anteriores = list(el.get("pontos", []) or [])
        fechado = self._molde_fechado_por_pontos_ou_controles(canvas, el, pontos_anteriores, cantos)
        if len(cantos) < 2 and not fechado:
            return False
        segmentos = self._segmentos_cantos(cantos, fechado)
        if not segmentos:
            return False

        auxiliares = [p for p in (self._ponto_qt(item) for item in el.get("controle_auxiliares", []) or []) if p is not None]
        topologia_alterada = bool(el.pop("_controles_topologia_alterada", False))
        mapa_arraste = el.pop("_segmentos_auxiliares_arraste", None)
        auxiliares_retos_arraste = el.pop("_auxiliares_retos_arraste", None)
        auxiliar_arrastado_idx = el.pop("_auxiliar_arrastado_idx", None)
        if self._mapa_auxiliares_valido(mapa_arraste, auxiliares, segmentos) and not topologia_alterada:
            auxiliares = self._alinhar_auxiliares_por_mapa(
                cantos,
                segmentos,
                auxiliares,
                mapa_arraste,
                preservar_idx=auxiliar_arrastado_idx,
                auxiliares_retos=auxiliares_retos_arraste,
            )
            atribuicoes = self._atribuir_auxiliares_por_mapa(cantos, segmentos, auxiliares, mapa_arraste)
        else:
            auxiliares = self._alinhar_auxiliares_unicos_as_retas(
                cantos,
                segmentos,
                auxiliares,
                preferir_ordem=not topologia_alterada,
                preservar_idx=auxiliar_arrastado_idx,
                auxiliares_retos=auxiliares_retos_arraste,
            )
            atribuicoes = self._atribuir_auxiliares_a_segmentos(cantos, segmentos, auxiliares, preferir_ordem=not topologia_alterada)
        densidades = self._densidade_segmentos_molde(canvas, pontos_anteriores, cantos, segmentos)

        novos: list[tuple[float, float]] = []
        for seg_ordem, (a_idx, b_idx) in enumerate(segmentos):
            a = cantos[a_idx]
            b = cantos[b_idx]
            controles_segmento = [a, *atribuicoes.get(seg_ordem, []), b]
            trecho = self._amostrar_trecho_molde(controles_segmento, densidades.get(seg_ordem, 24))
            if not trecho:
                continue
            if novos:
                trecho = trecho[1:]
            novos.extend((float(p.x()), float(p.y())) for p in trecho)

        if fechado and novos:
            if self._dist_pontos_local(QPointF(*novos[0]), QPointF(*novos[-1])) > 1e-6:
                novos.append(novos[0])
            else:
                novos[-1] = novos[0]
        if len(novos) < 2:
            return False

        el["pontos"] = novos
        el["controle_cantos"] = [(float(p.x()), float(p.y())) for p in cantos]
        el["controle_auxiliares"] = [(float(p.x()), float(p.y())) for p in auxiliares]
        el["pontos_controle_principais"] = [{"x": float(p.x()), "y": float(p.y())} for p in cantos]
        el["pontos_auxiliares"] = [{"x": float(p.x()), "y": float(p.y())} for p in auxiliares]
        self._sincronizar_curva_suave(el)
        return True

    def _mapa_auxiliares_valido(self, mapa, auxiliares: list[QPointF], segmentos: list[tuple[int, int]]) -> bool:
        if not isinstance(mapa, list) or len(mapa) != len(auxiliares):
            return False
        total_segmentos = len(segmentos)
        return all(isinstance(seg, int) and 0 <= seg < total_segmentos for seg in mapa)

    def _atribuir_auxiliares_por_mapa(
        self,
        cantos: list[QPointF],
        segmentos: list[tuple[int, int]],
        auxiliares: list[QPointF],
        mapa: list[int],
    ) -> dict[int, list[QPointF]]:
        saida: dict[int, list[tuple[float, int, QPointF]]] = {i: [] for i in range(len(segmentos))}
        for aux_idx, aux in enumerate(auxiliares):
            seg_ordem = int(mapa[aux_idx])
            a_idx, b_idx = segmentos[seg_ordem]
            t = self._parametro_no_segmento(aux, cantos[a_idx], cantos[b_idx])
            saida[seg_ordem].append((t, aux_idx, QPointF(aux)))
        return {
            idx: [pt for _t, _aux_idx, pt in sorted(valores, key=lambda item: (item[0], item[1]))]
            for idx, valores in saida.items()
        }

    def _alinhar_auxiliares_por_mapa(
        self,
        cantos: list[QPointF],
        segmentos: list[tuple[int, int]],
        auxiliares: list[QPointF],
        mapa: list[int],
        preservar_idx: int | None = None,
        auxiliares_retos=None,
    ) -> list[QPointF]:
        ajustados = [QPointF(p) for p in auxiliares]
        contagem: dict[int, int] = {}
        for seg_ordem in mapa:
            contagem[int(seg_ordem)] = contagem.get(int(seg_ordem), 0) + 1
        for aux_idx, aux in enumerate(auxiliares):
            if preservar_idx is not None and aux_idx == int(preservar_idx):
                continue
            seg_ordem = int(mapa[aux_idx])
            if contagem.get(seg_ordem, 0) != 1:
                continue
            if not self._auxiliar_deve_alinhar_reta(aux_idx, aux, cantos, segmentos[seg_ordem], auxiliares_retos):
                continue
            a_idx, b_idx = segmentos[seg_ordem]
            a = cantos[a_idx]
            b = cantos[b_idx]
            t = self._parametro_no_segmento(aux, a, b)
            ajustados[aux_idx] = QPointF(a.x() + ((b.x() - a.x()) * t), a.y() + ((b.y() - a.y()) * t))
        return ajustados

    def _molde_fechado_por_pontos_ou_controles(self, canvas, el: dict, pontos: list, cantos: list[QPointF]) -> bool:
        if bool(el.get("fechado")):
            return True
        if len(pontos) >= 3:
            p0 = self._ponto_qt(pontos[0])
            pn = self._ponto_qt(pontos[-1])
            if p0 is not None and pn is not None and canvas._dist(p0, pn) <= 1e-6:
                return True
        return len(cantos) >= 3

    def _segmentos_cantos(self, cantos: list[QPointF], fechado: bool) -> list[tuple[int, int]]:
        if len(cantos) < 1:
            return []
        if len(cantos) == 1:
            return [(0, 0)] if fechado else []
        if fechado:
            return [(i, (i + 1) % len(cantos)) for i in range(len(cantos))]
        return [(i, i + 1) for i in range(len(cantos) - 1)]

    def _atribuir_auxiliares_a_segmentos(
        self,
        cantos: list[QPointF],
        segmentos: list[tuple[int, int]],
        auxiliares: list[QPointF],
        preferir_ordem: bool = False,
    ) -> dict[int, list[QPointF]]:
        if preferir_ordem and self._ordem_auxiliares_compativel(cantos, segmentos, auxiliares):
            return {idx: [QPointF(auxiliares[idx])] for idx in range(len(segmentos))}
        saida: dict[int, list[tuple[float, QPointF]]] = {i: [] for i in range(len(segmentos))}
        for aux in auxiliares:
            melhor_seg = None
            melhor_dist = float("inf")
            melhor_t = 0.0
            for seg_ordem, (a_idx, b_idx) in enumerate(segmentos):
                a = cantos[a_idx]
                b = cantos[b_idx]
                t = self._parametro_no_segmento(aux, a, b)
                proj = QPointF(a.x() + ((b.x() - a.x()) * t), a.y() + ((b.y() - a.y()) * t))
                dist = self._dist_pontos_local(aux, proj)
                if dist < melhor_dist:
                    melhor_seg = seg_ordem
                    melhor_dist = dist
                    melhor_t = t
            if melhor_seg is not None:
                saida[melhor_seg].append((melhor_t, QPointF(aux)))
        return {idx: [pt for _t, pt in sorted(valores, key=lambda item: item[0])] for idx, valores in saida.items()}

    def _auxiliares_por_segmento_indexados(
        self,
        cantos: list[QPointF],
        segmentos: list[tuple[int, int]],
        auxiliares: list[QPointF],
        preferir_ordem: bool = False,
    ) -> dict[int, list[tuple[int, float, QPointF]]]:
        saida: dict[int, list[tuple[int, float, QPointF]]] = {i: [] for i in range(len(segmentos))}
        if preferir_ordem and self._ordem_auxiliares_compativel(cantos, segmentos, auxiliares):
            for idx, aux in enumerate(auxiliares):
                a_idx, b_idx = segmentos[idx]
                t = self._parametro_no_segmento(aux, cantos[a_idx], cantos[b_idx])
                saida[idx].append((idx, t, QPointF(aux)))
            return saida
        for aux_idx, aux in enumerate(auxiliares):
            melhor_seg = None
            melhor_dist = float("inf")
            melhor_t = 0.0
            for seg_ordem, (a_idx, b_idx) in enumerate(segmentos):
                a = cantos[a_idx]
                b = cantos[b_idx]
                t = self._parametro_no_segmento(aux, a, b)
                proj = QPointF(a.x() + ((b.x() - a.x()) * t), a.y() + ((b.y() - a.y()) * t))
                dist = self._dist_pontos_local(aux, proj)
                if dist < melhor_dist:
                    melhor_seg = seg_ordem
                    melhor_dist = dist
                    melhor_t = t
            if melhor_seg is not None:
                saida[melhor_seg].append((aux_idx, melhor_t, QPointF(aux)))
        for seg_ordem, itens in list(saida.items()):
            saida[seg_ordem] = sorted(itens, key=lambda item: item[1])
        return saida

    def _ordem_auxiliares_compativel(
        self,
        cantos: list[QPointF],
        segmentos: list[tuple[int, int]],
        auxiliares: list[QPointF],
    ) -> bool:
        if len(auxiliares) != len(segmentos):
            return False
        for aux_idx, aux in enumerate(auxiliares):
            melhor_seg = None
            melhor_dist = float("inf")
            for seg_ordem, (a_idx, b_idx) in enumerate(segmentos):
                a = cantos[a_idx]
                b = cantos[b_idx]
                dist = self._distancia_ponto_segmento_local(aux, a, b)
                if dist < melhor_dist:
                    melhor_seg = seg_ordem
                    melhor_dist = dist
            if melhor_seg != aux_idx:
                return False
        return True

    def _alinhar_auxiliares_unicos_as_retas(
        self,
        cantos: list[QPointF],
        segmentos: list[tuple[int, int]],
        auxiliares: list[QPointF],
        preferir_ordem: bool = False,
        preservar_idx: int | None = None,
        auxiliares_retos=None,
    ) -> list[QPointF]:
        ajustados = [QPointF(p) for p in auxiliares]
        por_segmento = self._auxiliares_por_segmento_indexados(cantos, segmentos, auxiliares, preferir_ordem=preferir_ordem)
        for seg_ordem, itens in por_segmento.items():
            if len(itens) != 1:
                continue
            aux_idx, t, _pt = itens[0]
            if not (0 <= aux_idx < len(ajustados)):
                continue
            if preservar_idx is not None and aux_idx == int(preservar_idx):
                continue
            if not self._auxiliar_deve_alinhar_reta(aux_idx, ajustados[aux_idx], cantos, segmentos[seg_ordem], auxiliares_retos):
                continue
            a_idx, b_idx = segmentos[seg_ordem]
            a = cantos[a_idx]
            b = cantos[b_idx]
            ajustados[aux_idx] = QPointF(a.x() + ((b.x() - a.x()) * t), a.y() + ((b.y() - a.y()) * t))
        return ajustados

    def _auxiliar_deve_alinhar_reta(
        self,
        aux_idx: int,
        aux: QPointF,
        cantos: list[QPointF],
        segmento: tuple[int, int],
        auxiliares_retos,
    ) -> bool:
        if isinstance(auxiliares_retos, list) and 0 <= aux_idx < len(auxiliares_retos):
            return bool(auxiliares_retos[aux_idx])
        a_idx, b_idx = segmento
        if not (0 <= a_idx < len(cantos) and 0 <= b_idx < len(cantos)):
            return False
        a = cantos[a_idx]
        b = cantos[b_idx]
        limite_reta = max(0.02, self._dist_pontos_local(a, b) * 0.002)
        return self._distancia_ponto_segmento_local(aux, a, b) <= limite_reta

    def _densidade_segmentos_molde(
        self,
        canvas,
        pontos: list,
        cantos: list[QPointF],
        segmentos: list[tuple[int, int]],
    ) -> dict[int, int]:
        densidades: dict[int, int] = {}
        pontos_base = list(pontos)
        fechado = len(pontos_base) >= 2 and self._pontos_lista_mesmos(pontos_base[0], pontos_base[-1])
        n = len(pontos_base) - 1 if fechado else len(pontos_base)
        for seg_ordem, (a_idx, b_idx) in enumerate(segmentos):
            if fechado and a_idx == b_idx:
                densidades[seg_ordem] = max(160, min(480, (n * 3) if n > 0 else 240))
                continue
            a_real = self._indice_ponto_mais_proximo(canvas, pontos_base[:n], cantos[a_idx])
            b_real = self._indice_ponto_mais_proximo(canvas, pontos_base[:n], cantos[b_idx])
            if a_real is not None and b_real is not None and a_real != b_real and n > 0:
                densidades[seg_ordem] = max(24, min(220, (len(self._indices_intervalo(a_real, b_real, n, fechado)) - 1) * 2))
                continue
            dist = self._dist_pontos_local(cantos[a_idx], cantos[b_idx])
            densidades[seg_ordem] = max(32, min(180, int(dist * 1.2) + 32))
        return densidades

    def _amostrar_trecho_molde(self, controles: list[QPointF], segmentos: int) -> list[QPointF]:
        pts = [QPointF(p) for p in controles]
        if len(pts) <= 2:
            return pts
        if len(pts) == 3:
            desvio = self._distancia_ponto_segmento_local(pts[1], pts[0], pts[2])
            if desvio <= max(0.02, self._dist_pontos_local(pts[0], pts[2]) * 0.002):
                return [QPointF(pts[0]), QPointF(pts[-1])]
            controle = self._controle_quadratico_passando_por_meio(pts[0], pts[1], pts[2])
            amostras = max(16, min(160, int(segmentos)))
            return [
                self._bezier_quadratica(pts[0], controle, pts[2], i / float(amostras))
                for i in range(amostras + 1)
            ]
        saida: list[QPointF] = []
        total = len(pts)
        for i in range(total - 1):
            p0 = pts[i - 1] if i > 0 else pts[i]
            p1 = pts[i]
            p2 = pts[i + 1]
            p3 = pts[i + 2] if i + 2 < total else p2
            if i == 0:
                saida.append(QPointF(p1))
            amostras = max(10, min(48, int(segmentos / max(1, total - 1))))
            for s in range(1, amostras + 1):
                saida.append(self._catmull_rom_centripeta(p0, p1, p2, p3, s / float(amostras)))
        return self._limitar_trecho_ao_envelope_controles(saida, pts)

    def _limitar_trecho_ao_envelope_controles(self, pontos: list[QPointF], controles: list[QPointF]) -> list[QPointF]:
        if len(pontos) < 3 or len(controles) < 2:
            return pontos
        xs = [p.x() for p in controles]
        ys = [p.y() for p in controles]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        margem_x = max(0.001, (max_x - min_x) * 0.015)
        margem_y = max(0.001, (max_y - min_y) * 0.015)
        saida: list[QPointF] = []
        controles_assinatura = {(round(p.x(), 7), round(p.y(), 7)) for p in controles}
        for p in pontos:
            assinatura = (round(p.x(), 7), round(p.y(), 7))
            if assinatura in controles_assinatura:
                saida.append(QPointF(p))
                continue
            saida.append(
                QPointF(
                    max(min_x - margem_x, min(max_x + margem_x, p.x())),
                    max(min_y - margem_y, min(max_y + margem_y, p.y())),
                )
            )
        return saida

    def _distancia_ponto_segmento_local(self, p: QPointF, a: QPointF, b: QPointF) -> float:
        abx = b.x() - a.x()
        aby = b.y() - a.y()
        den = (abx * abx) + (aby * aby)
        if den <= 1e-12:
            return self._dist_pontos_local(p, a)
        t = max(0.0, min(1.0, (((p.x() - a.x()) * abx) + ((p.y() - a.y()) * aby)) / den))
        proj = QPointF(a.x() + (abx * t), a.y() + (aby * t))
        return self._dist_pontos_local(p, proj)

    def _parametro_no_segmento(self, p: QPointF, a: QPointF, b: QPointF) -> float:
        abx = b.x() - a.x()
        aby = b.y() - a.y()
        den = (abx * abx) + (aby * aby)
        if den <= 1e-12:
            return 0.0
        t = (((p.x() - a.x()) * abx) + ((p.y() - a.y()) * aby)) / den
        return max(0.0, min(1.0, t))

    def _redistribuir_molde_por_deslocamentos(
        self,
        canvas,
        el: dict,
        pontos_base: list,
        deslocamentos_principais: dict[int, tuple[float, float]],
    ) -> bool:
        if len(pontos_base) < 4 or not deslocamentos_principais:
            return False
        fechado = len(pontos_base) >= 2 and canvas._dist(
            QPointF(float(pontos_base[0][0]), float(pontos_base[0][1])),
            QPointF(float(pontos_base[-1][0]), float(pontos_base[-1][1])),
        ) <= 1e-6
        n = len(pontos_base) - 1 if fechado else len(pontos_base)
        if n < 2:
            return False

        principais = sorted(i for i in self._indices_pontos_principais_molde(canvas, el) if 0 <= i < n)
        if len(principais) < 2:
            return False
        deslocamentos = {idx: disp for idx, disp in deslocamentos_principais.items() if idx in principais}
        if not deslocamentos:
            return False

        novos = list(pontos_base)
        for idx, (dx, dy) in deslocamentos.items():
            x, y = pontos_base[idx]
            nx = float(x) + dx
            ny = float(y) + dy
            if self._modo_discreto():
                nx = round(nx, 2)
                ny = round(ny, 2)
            novos[idx] = (nx, ny)

        pares: list[tuple[int, int]] = []
        if fechado:
            for i, a in enumerate(principais):
                pares.append((a, principais[(i + 1) % len(principais)]))
        else:
            pares.extend((a, b) for a, b in zip(principais, principais[1:]))

        for a, b in pares:
            indices = self._indices_intervalo(a, b, n, fechado)
            if len(indices) <= 2:
                continue
            dxa, dya = deslocamentos.get(a, (0.0, 0.0))
            dxb, dyb = deslocamentos.get(b, (0.0, 0.0))
            if abs(dxa) <= 1e-9 and abs(dya) <= 1e-9 and abs(dxb) <= 1e-9 and abs(dyb) <= 1e-9:
                continue
            denom = max(1, len(indices) - 1)
            for pos, idx_local in enumerate(indices[1:-1], start=1):
                t = max(0.0, min(1.0, pos / float(denom)))
                ddx = (dxa * (1.0 - t)) + (dxb * t)
                ddy = (dya * (1.0 - t)) + (dyb * t)
                x, y = pontos_base[idx_local]
                nx = float(x) + ddx
                ny = float(y) + ddy
                if self._modo_discreto():
                    nx = round(nx, 2)
                    ny = round(ny, 2)
                novos[idx_local] = (nx, ny)

        if fechado and len(novos) >= 2:
            novos[-1] = novos[0]
        el["pontos"] = novos
        self._sincronizar_curva_suave(el)
        return True

    def _recravar_auxiliares_no_perimetro(self, el: dict) -> None:
        cantos = [p for p in (self._ponto_qt(item) for item in el.get("controle_cantos", [])) if p is not None]
        if len(cantos) < 2:
            return
        auxiliares: list[tuple[float, float]] = []
        limite = len(cantos) if len(cantos) >= 3 else len(cantos) - 1
        for i in range(max(0, limite)):
            a = cantos[i]
            b = cantos[(i + 1) % len(cantos)]
            auxiliares.append(((a.x() + b.x()) / 2.0, (a.y() + b.y()) / 2.0))
        el["controle_auxiliares"] = auxiliares
        el["pontos_auxiliares"] = [{"x": x, "y": y} for x, y in auxiliares]

    def _atualizar_espelho_controle(self, el: dict, chave: str, idx: int, destino: QPointF) -> None:
        itens = el.get(chave)
        if not isinstance(itens, list) or not (0 <= idx < len(itens)):
            return
        item = itens[idx]
        if isinstance(item, dict):
            item["x"] = destino.x()
            item["y"] = destino.y()
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            itens[idx] = (destino.x(), destino.y())

    def _segmento_controle_mais_proximo(self, cantos: list, ponto: QPointF) -> tuple[int | None, int | None]:
        if len(cantos) < 2:
            return None, None
        fechado = len(cantos) >= 3
        melhor_a: int | None = None
        melhor_b: int | None = None
        melhor_dist = float("inf")
        limite = len(cantos) if fechado else len(cantos) - 1
        for i in range(max(limite, 0)):
            j = (i + 1) % len(cantos)
            if not fechado and j <= i:
                continue
            a = self._ponto_qt(cantos[i])
            b = self._ponto_qt(cantos[j])
            if a is None or b is None:
                continue
            dist = self._dist_ponto_segmento(ponto, a, b)
            if dist < melhor_dist:
                melhor_dist = dist
                melhor_a, melhor_b = i, j
        return melhor_a, melhor_b

    def _dist_ponto_segmento(self, p: QPointF, a: QPointF, b: QPointF) -> float:
        abx = b.x() - a.x()
        aby = b.y() - a.y()
        apx = p.x() - a.x()
        apy = p.y() - a.y()
        den = (abx * abx) + (aby * aby)
        if den <= 1e-12:
            return ((p.x() - a.x()) ** 2 + (p.y() - a.y()) ** 2) ** 0.5
        t = ((apx * abx) + (apy * aby)) / den
        t = max(0.0, min(1.0, t))
        px = a.x() + (abx * t)
        py = a.y() + (aby * t)
        return ((p.x() - px) ** 2 + (p.y() - py) ** 2) ** 0.5

    def _reajustar_fio_no_molde(self, el: dict):
        pontos = [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]
        if not pontos:
            return
        base = pontos[:-1] if len(pontos) >= 2 and pontos[0] == pontos[-1] else pontos
        if not base:
            return
        xs = [p.x() for p in base]
        ys = [p.y() for p in base]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        largura = max(max_x - min_x, 1e-6)
        margem = largura * 0.12
        y_fio = min_y + ((max_y - min_y) * 0.24)
        el["fio_origem"] = (min_x + margem, y_fio)
        el["fio_fim"] = (max_x - margem, y_fio)

    def _desenhar_guia(self, canvas, painter):
        return

    def _desenhar_guia_eixo(self, canvas, painter):
        return

    def _desenhar_guia_angular_arraste(self, canvas, painter):
        if self._guia_eixo is None:
            return
        origem, destino = self._guia_eixo
        dx = destino.x() - origem.x()
        dy = destino.y() - origem.y()
        comp = sqrt((dx * dx) + (dy * dy))
        if comp <= 1e-9:
            return
        ang = degrees(atan2(-dy, dx)) % 360.0
        origem_tela = canvas._cena_para_tela(origem)
        destino_tela = canvas._cena_para_tela(destino)
        cor = QColor(self._cor_guia_arraste(canvas))
        if not cor.isValid():
            cor = QColor("#d0d0d0")
        painter.save()
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(cor, 1.0, Qt.DotLine))
        painter.drawLine(origem_tela, destino_tela)

        raio = 30.0
        painter.drawEllipse(origem_tela, raio, raio)
        ref_tela = QPointF(origem_tela.x() + raio, origem_tela.y())
        painter.drawLine(origem_tela, ref_tela)

        arco = []
        passos = max(8, int(abs(ang) / 6.0))
        for i in range(passos + 1):
            atual = radians((ang * i) / max(1, passos))
            arco.append(QPointF(origem_tela.x() + (raio * cos(atual)), origem_tela.y() - (raio * sin(atual))))
        for a, b in zip(arco, arco[1:]):
            painter.drawLine(a, b)

        painter.setPen(QPen(cor, 1.0))
        painter.drawText(int(origem_tela.x() + raio + 5), int(origem_tela.y() - 4), f"{ang:.0f}°")
        painter.restore()

    def _cor_guia_arraste(self, canvas) -> str:
        idx = None
        if self._arrastando_controle_molde is not None:
            idx = self._arrastando_controle_molde[0]
        elif self._arrastando_ponto_poly is not None:
            idx = self._arrastando_ponto_poly[0]
        elif self._hover_molde_idx is not None:
            idx = self._hover_molde_idx
        if idx is not None and 0 <= idx < len(canvas.cena.elementos):
            el = canvas.cena.elementos[idx]
            for chave in ("cor", "linha_cor", "cor_linha", "stroke"):
                cor = el.get(chave)
                if isinstance(cor, str) and cor.strip():
                    return cor.strip()
        return "#d0d0d0"

    def _desenhar_controles_molde_hover(self, canvas, painter):
        idx = self._hover_molde_idx
        if idx is None or not (0 <= idx < len(canvas.cena.elementos)):
            return
        el = canvas.cena.elementos[idx]
        if not el.get("molde"):
            return

        controles = [
            (pt, "#ff3030", 3)
            for pt in (self._ponto_qt(item) for item in el.get("controle_cantos", []))
            if pt is not None
        ]
        controles.extend(
            (pt, "#ff3030", 2)
            for pt in (self._ponto_qt(item) for item in el.get("controle_auxiliares", []))
            if pt is not None
        )
        for pt, cor, raio in controles:
            tela = canvas._cena_para_tela(pt)
            painter.setPen(QPen(QColor(cor), 1.0))
            painter.setBrush(QColor(cor))
            painter.drawEllipse(tela, float(raio), float(raio))

    def _desenhar_molde_em_manipulacao(self, canvas, painter):
        idx = None
        if self._arrastando_controle_molde is not None:
            idx = self._arrastando_controle_molde[0]
        elif self._arrastando_ponto_poly is not None:
            idx = self._arrastando_ponto_poly[0]
        if idx is None or not (0 <= idx < len(canvas.cena.elementos)):
            return
        el = canvas.cena.elementos[idx]
        if el.get("tipo") != "polyline":
            return
        pontos = [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]
        if len(pontos) < 2:
            return
        painter.save()
        painter.setBrush(Qt.NoBrush)
        cor = "#ff2020"
        esp = max(1.8, float(el.get("espessura", 1.0)) + 0.6)
        if self._elemento_curva_suave(el) and hasattr(canvas, "_desenhar_curva_suave_por_pontos"):
            canvas._desenhar_curva_suave_por_pontos(painter, pontos, cor=cor, espessura=esp, estilo="solid")
        else:
            canvas._desenhar_polilinha(painter, pontos, cor=cor, espessura=esp, estilo="solid", amplitude=1.0)
        painter.restore()

    def _desenhar_hover(self, canvas, painter):
        if self._hover_ponto_poly is not None:
            idx, p_idx = self._hover_ponto_poly
            if 0 <= idx < len(canvas.cena.elementos):
                el = canvas.cena.elementos[idx]
                pontos = self._pontos_controle_curva(el) if self._curva_tracado_real(el) else el.get("pontos", [])
                if 0 <= p_idx < len(pontos):
                    ponto = self._ponto_qt(pontos[p_idx])
                    if ponto is None:
                        return
                    pt = canvas._cena_para_tela(ponto)
                    painter.setPen(QPen(QColor("#ff3030"), 1.4))
                    painter.setBrush(Qt.NoBrush)
                    painter.drawEllipse(int(pt.x() - 9), int(pt.y() - 9), 18, 18)

        if self._ponto_selecionado is not None:
            idx, p_idx = self._ponto_selecionado
            if 0 <= idx < len(canvas.cena.elementos):
                el = canvas.cena.elementos[idx]
                pontos = self._pontos_controle_curva(el) if self._curva_tracado_real(el) else el.get("pontos", [])
                if 0 <= p_idx < len(pontos):
                    ponto = self._ponto_qt(pontos[p_idx])
                    if ponto is None:
                        return
                    pt = canvas._cena_para_tela(ponto)
                    painter.setPen(QPen(QColor("#ff3030"), 2.0))
                    painter.setBrush(Qt.NoBrush)
                    painter.drawEllipse(int(pt.x() - 11), int(pt.y() - 11), 22, 22)

        if self._hover_controle_molde is not None:
            idx, tipo, c_idx = self._hover_controle_molde
            if 0 <= idx < len(canvas.cena.elementos):
                el = canvas.cena.elementos[idx]
                chave = "controle_cantos" if tipo == "canto" else "controle_auxiliares"
                controles = el.get(chave, [])
                if 0 <= c_idx < len(controles):
                    controle = self._ponto_qt(controles[c_idx])
                    if controle is None:
                        return
                    pt = canvas._cena_para_tela(controle)
                    painter.setPen(QPen(QColor("#ff3030"), 1.4))
                    painter.setBrush(Qt.NoBrush)
                    painter.drawEllipse(int(pt.x() - 8), int(pt.y() - 8), 16, 16)

        for idx, tipo, c_idx in self._controles_selecionados:
            if not (0 <= idx < len(canvas.cena.elementos)):
                continue
            el = canvas.cena.elementos[idx]
            chave = "controle_cantos" if tipo == "canto" else "controle_auxiliares"
            controles = el.get(chave, [])
            if not (0 <= c_idx < len(controles)):
                continue
            controle = self._ponto_qt(controles[c_idx])
            if controle is None:
                continue
            pt = canvas._cena_para_tela(controle)
            painter.setPen(QPen(QColor("#ff3030"), 2.0))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(int(pt.x() - 11), int(pt.y() - 11), 22, 22)

    def _atualizar_info_angulo(self, canvas, idx: int, p_idx: int, atual: QPointF):
        self._angulo_info = None
        if idx < 0 or idx >= len(canvas.cena.elementos):
            return
        el = canvas.cena.elementos[idx]
        if el.get("tipo") != "polyline":
            return
        pts = [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]
        if len(pts) < 3:
            return
        fechado = canvas._dist(pts[0], pts[-1]) <= 1e-6
        if fechado and p_idx == len(pts) - 1:
            p_idx = 0
        prev_idx = p_idx - 1
        next_idx = p_idx + 1
        if fechado:
            if prev_idx < 0:
                prev_idx = len(pts) - 2
            if next_idx >= len(pts) - 1:
                next_idx = 1
        if not (0 <= prev_idx < len(pts)) or not (0 <= next_idx < len(pts)):
            return
        p_prev = pts[prev_idx]
        p_next = pts[next_idx]
        ang = self._angulo_interno(p_prev, atual, p_next)
        self._angulo_info = (atual, p_prev, p_next, ang)
        if getattr(canvas, "lbl_status", None) is not None:
            canvas.lbl_status.setText(f"Ângulo: {ang:.0f}°")

    def _atualizar_info_angulo_controle_molde(
        self,
        canvas,
        idx: int,
        tipo: str,
        controle_idx: int,
        atual: QPointF,
    ) -> None:
        self._angulo_info = None
        if idx < 0 or idx >= len(canvas.cena.elementos):
            return
        el = canvas.cena.elementos[idx]
        if not el.get("molde"):
            return
        cantos = [p for p in (self._ponto_qt(item) for item in el.get("controle_cantos", []) or []) if p is not None]
        if tipo == "canto":
            if len(cantos) < 3 or not (0 <= controle_idx < len(cantos)):
                return
            fechado = self._molde_fechado_por_pontos_ou_controles(canvas, el, el.get("pontos", []) or [], cantos)
            prev_idx = controle_idx - 1
            next_idx = controle_idx + 1
            if fechado:
                prev_idx %= len(cantos)
                next_idx %= len(cantos)
            if not (0 <= prev_idx < len(cantos)) or not (0 <= next_idx < len(cantos)):
                return
            p_prev = cantos[prev_idx]
            p_next = cantos[next_idx]
        else:
            auxiliares = [p for p in (self._ponto_qt(item) for item in el.get("controle_auxiliares", []) or []) if p is not None]
            if len(cantos) < 2 or not (0 <= controle_idx < len(auxiliares)):
                return
            a_idx, b_idx = self._segmento_controle_mais_proximo(cantos, atual)
            if a_idx is None or b_idx is None:
                return
            p_prev = cantos[int(a_idx)]
            p_next = cantos[int(b_idx)]
        ang = self._angulo_interno(p_prev, atual, p_next)
        self._angulo_info = (QPointF(atual), QPointF(p_prev), QPointF(p_next), ang)
        if getattr(canvas, "lbl_status", None) is not None:
            canvas.lbl_status.setText(f"Angulo: {ang:.0f} graus")

    def _angulo_interno(self, a: QPointF, c: QPointF, b: QPointF) -> float:
        v1x, v1y = a.x() - c.x(), a.y() - c.y()
        v2x, v2y = b.x() - c.x(), b.y() - c.y()
        ang1 = atan2(v1y, v1x)
        ang2 = atan2(v2y, v2x)
        deg = abs(degrees(ang2 - ang1))
        while deg > 360.0:
            deg -= 360.0
        if deg > 180.0:
            deg = 360.0 - deg
        return max(0.0, min(360.0, deg))

    @staticmethod
    def _ponto_qt(p) -> QPointF | None:
        try:
            if isinstance(p, QPointF):
                return QPointF(p)
            if isinstance(p, dict):
                return QPointF(float(p["x"]), float(p["y"]))
            if isinstance(p, (list, tuple)) and len(p) >= 2:
                return QPointF(float(p[0]), float(p[1]))
        except Exception:
            return None
        return None

    def _desenhar_angulo(self, canvas, painter):
        return
