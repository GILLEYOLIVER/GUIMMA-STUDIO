from __future__ import annotations

import os
import unittest
from copy import deepcopy
from importlib.util import find_spec
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if find_spec("PySide6") is None:
    QApplication = None
    QPointF = None
    Qt = SimpleNamespace(LeftButton=1, RightButton=2)
    QWidget = object
    FerramentaCortar = None
    CortarDialog = None
    FerramentaUnir = None
    UnirDialog = None
else:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QPainterPath
    from PySide6.QtWidgets import QApplication, QWidget

    from tools.cortar_tool import CortarDialog, Ferramenta as FerramentaCortar
    from tools.unir_tool import Ferramenta as FerramentaUnir
    from tools.unir_tool import UnirDialog


class _FakeEvent:
    def __init__(self, pos, button=Qt.LeftButton):
        self._pos = QPointF(pos)
        self._button = button
        self.accepted = False

    def position(self):
        return QPointF(self._pos)

    def button(self):
        return self._button

    def accept(self):
        self.accepted = True


class _FakeCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self.zoom = 10.0
        self.historico = 0
        self.atualizou = 0
        self._selecionados = set()
        self.cena = SimpleNamespace(elementos=[self._molde(), self._linha()])

    def _molde(self):
        pontos = [(0.0, 0.0), (10.0, 0.0), (10.0, 8.0), (0.0, 8.0), (0.0, 0.0)]
        valores = {
            str(idx): {
                "indice": idx,
                "numero": idx + 1,
                "ponto": ponto,
                "valores": {
                    "P": {"dx": -1.0, "dy": 0.0},
                    "M": {"dx": 0.0, "dy": 0.0},
                    "G": {"dx": 2.0, "dy": 0.0},
                },
            }
            for idx, ponto in enumerate(pontos[:-1])
        }
        return {
            "tipo": "polyline",
            "molde": True,
            "molde_id": "m1",
            "nome_molde": "N46",
            "pontos": pontos,
            "controle_cantos": pontos[:-1],
            "pontos_controle_principais": [{"x": x, "y": y} for x, y in pontos[:-1]],
            "graduacao_tamanhos": [
                {"tamanho": "P", "ativo": True, "base": False},
                {"tamanho": "M", "ativo": True, "base": True},
                {"tamanho": "G", "ativo": True, "base": False},
            ],
            "graduacao_tabela": {"modo": "dx_dy", "pontos": valores},
            "graduacao_pontos": values_copy(valores),
            "piques_config": [{"tipo": "T", "ponto": (2.0, 0.0), "segmentos": []}],
        }

    @staticmethod
    def _linha():
        return {
            "tipo": "polyline",
            "molde": False,
            "pontos": [(5.0, -2.0), (5.0, 10.0)],
            "cor": "#ff00ff",
        }

    def _ponto_com_snap(self, pos):
        return QPointF(pos)

    def _tela_para_cena(self, pos):
        return QPointF(pos)

    def _indices_elementos_em_ponto(self, pos):
        p = QPointF(pos)
        if 0.0 <= p.x() <= 10.0 and 0.0 <= p.y() <= 8.0:
            return [0]
        if abs(p.x() - 5.0) <= 0.5 and -2.0 <= p.y() <= 10.0:
            return [1]
        return []

    def _registrar_historico(self):
        self.historico += 1

    def _cena_para_tela(self, pos):
        return QPointF(pos)

    def update(self):
        self.atualizou += 1


class _FakeCanvasSnapRuim(_FakeCanvas):
    def _ponto_com_snap(self, _pos):
        return QPointF(999.0, 999.0)


class _FakeCanvasLinhaCurva(_FakeCanvas):
    @staticmethod
    def _linha():
        return {
            "tipo": "polyline",
            "molde": False,
            "pontos": [(5.0, -2.0), (7.0, 4.0), (5.0, 10.0)],
            "cor": "#ff00ff",
        }


class _FakeCanvasContornoDenso(_FakeCanvas):
    def _molde(self):
        pontos = []
        for i in range(41):
            pontos.append((i * 0.25, 0.0))
        for i in range(1, 33):
            pontos.append((10.0, i * 0.25))
        for i in range(1, 41):
            pontos.append((10.0 - (i * 0.25), 8.0))
        for i in range(1, 32):
            pontos.append((0.0, 8.0 - (i * 0.25)))
        pontos.append(pontos[0])
        controles = [(0.0, 0.0), (10.0, 0.0), (10.0, 8.0), (0.0, 8.0)]
        valores = {
            str(idx): {
                "indice": idx,
                "numero": idx + 1,
                "ponto": ponto,
                "valores": {
                    "P": {"dx": -1.0, "dy": 0.0},
                    "M": {"dx": 0.0, "dy": 0.0},
                    "G": {"dx": 2.0, "dy": 0.0},
                },
            }
            for idx, ponto in enumerate(pontos[:-1])
        }
        return {
            "tipo": "polyline",
            "molde": True,
            "molde_id": "m1",
            "nome_molde": "K1",
            "pontos": pontos,
            "controle_cantos": controles,
            "pontos_controle_principais": [{"x": x, "y": y} for x, y in controles],
            "graduacao_tamanhos": [
                {"tamanho": "P", "ativo": True, "base": False},
                {"tamanho": "M", "ativo": True, "base": True},
                {"tamanho": "G", "ativo": True, "base": False},
            ],
            "graduacao_tabela": {"modo": "dx_dy", "pontos": valores},
            "graduacao_pontos": values_copy(valores),
        }


def values_copy(valor):
    return {
        chave: {
            **cfg,
            "valores": {nome: dict(dados) for nome, dados in cfg.get("valores", {}).items()},
        }
        for chave, cfg in valor.items()
    }


@unittest.skipIf(FerramentaCortar is None, "PySide6 nao disponivel neste ambiente")
class CortarUnirToolTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_dialogos_tem_opcoes_referencia(self):
        cortar = CortarDialog()
        unir = UnirDialog()
        self.addCleanup(cortar.close)
        self.addCleanup(unir.close)

        self.assertEqual([cortar.cmb_contorno.itemText(i) for i in range(cortar.cmb_contorno.count())], ["Automatico", "Manual"])
        self.assertEqual([cortar.cmb_modo.itemText(i) for i in range(cortar.cmb_modo.count())], ["Linha", "Reta"])
        self.assertIn("T", [cortar.cmb_pique.itemText(i) for i in range(cortar.cmb_pique.count())])
        self.assertTrue(cortar.chk_costura.isChecked())
        self.assertTrue(cortar.chk_manter_base.isChecked())
        self.assertEqual([unir.cmb_giro.itemText(i) for i in range(unir.cmb_giro.count())], ["Igual tamanho", "Igual base"])

    def test_cortar_fluxo_molde_linha_confirma_e_interpola_graduacao(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaCortar()
        ferramenta.on_activate(canvas)
        ferramenta._obter_dialog(canvas).chk_costura.setChecked(False)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(2.0, 2.0))))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(5.0, -1.0))))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(5.0, -1.0))))

        self.assertEqual(canvas.historico, 1)
        self.assertEqual(len(canvas.cena.elementos), 3)
        partes = canvas.cena.elementos[:2]
        self.assertTrue(all(parte.get("molde") for parte in partes))
        self.assertTrue(all(parte.get("metadados", {}).get("corte_id") for parte in partes))
        self.assertTrue(all(parte.get("pontos_controle_principais") for parte in partes))
        self.assertTrue(any(parte.get("piques_config") for parte in partes))
        pique_corte = next(
            cfg
            for parte in partes
            for cfg in parte.get("piques_config", [])
            if abs(cfg.get("ponto", (0.0, 0.0))[0] - 5.0) <= 1e-6
        )
        self.assertEqual(pique_corte["tipo"], "T - forma T")
        self.assertEqual(len(pique_corte["segmentos"]), 2)

        pontos_cfg = partes[0]["graduacao_tabela"]["pontos"]
        inter = next(cfg for cfg in pontos_cfg.values() if abs(cfg["ponto"][0] - 5.0) <= 1e-6)
        self.assertEqual(inter["valores"]["P"], {"dx": -1.0, "dy": 0.0})
        self.assertEqual(inter["valores"]["G"], {"dx": 2.0, "dy": 0.0})

    def test_cortar_ignora_cache_runtime_qpainterpath_do_molde(self):
        canvas = _FakeCanvas()
        canvas.cena.elementos[0]["_runtime_path_polilinha_tela_cache"] = {
            "path": QPainterPath(QPointF(0.0, 0.0))
        }
        ferramenta = FerramentaCortar()
        ferramenta.on_activate(canvas)
        ferramenta._obter_dialog(canvas).chk_costura.setChecked(False)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(2.0, 2.0))))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(5.0, -1.0))))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(5.0, -1.0))))

        self.assertEqual(canvas.historico, 1)
        self.assertEqual(len(canvas.cena.elementos), 3)
        self.assertNotIn("_runtime_path_polilinha_tela_cache", canvas.cena.elementos[0])
        self.assertNotIn("_runtime_path_polilinha_tela_cache", canvas.cena.elementos[1])

    def test_cortar_adiciona_costura_no_segmento_novo_do_corte(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaCortar()
        ferramenta.on_activate(canvas)
        dialog = ferramenta._obter_dialog(canvas)
        dialog.chk_costura.setChecked(True)
        dialog.sp_costura.setValue(1.5)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(2.0, 2.0))))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(5.0, -1.0))))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(5.0, -1.0))))

        for parte in canvas.cena.elementos[:2]:
            self.assertFalse(parte.get("mostrar_margem", False))
            self.assertNotIn("margens_molde", parte)
        costuras = [el for el in canvas.cena.elementos if el.get("subtipo_audaces") == "costura"]
        self.assertEqual(len(costuras), 2)
        ids_partes = {str(parte.get("molde_id")) for parte in canvas.cena.elementos[:2]}
        self.assertEqual({str(el.get("costura_de_molde_id")) for el in costuras}, ids_partes)
        self.assertTrue(all(el.get("costura_parcial") for el in costuras))
        self.assertTrue(all(el.get("margem_costura_cm") == 1.5 for el in costuras))
        self.assertTrue(all(el.get("estilo") == "dash" for el in costuras))
        self.assertTrue(all(len(el.get("pontos", [])) >= 2 for el in costuras))
        for costura in costuras:
            xs = [float(x) for x, _y in costura.get("pontos", [])]
            self.assertTrue(xs)
            self.assertGreaterEqual(min(xs), 3.49)
            self.assertLessEqual(max(xs), 6.51)
            self.assertLessEqual(len(costura.get("pontos", [])), 4)

    def test_cortar_nao_adiciona_costura_quando_desmarcada(self):
        canvas = _FakeCanvas()
        ferramenta = FerramentaCortar()
        ferramenta.on_activate(canvas)
        dialog = ferramenta._obter_dialog(canvas)
        dialog.chk_costura.setChecked(False)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(2.0, 2.0))))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(5.0, -1.0))))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(5.0, -1.0))))

        for parte in canvas.cena.elementos[:2]:
            self.assertFalse(parte.get("mostrar_margem", False))
            self.assertNotIn("margens_molde", parte)
        self.assertFalse([el for el in canvas.cena.elementos if el.get("subtipo_audaces") == "costura"])

    def test_cortar_modo_linha_segue_o_caminho_desenhado(self):
        canvas = _FakeCanvasLinhaCurva()
        ferramenta = FerramentaCortar()
        ferramenta.on_activate(canvas)
        dialog = ferramenta._obter_dialog(canvas)
        dialog.chk_costura.setChecked(False)
        dialog.cmb_modo.setCurrentText("Linha")

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(2.0, 2.0))))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(7.0, 4.0))))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(7.0, 4.0))))

        partes = canvas.cena.elementos[:2]
        self.assertTrue(
            any(
                any(abs(x - 7.0) <= 1e-6 and abs(y - 4.0) <= 1e-6 for x, y in parte["pontos"])
                for parte in partes
            )
        )

    def test_cortar_modo_reta_ignora_ponto_intermediario_da_linha(self):
        canvas = _FakeCanvasLinhaCurva()
        ferramenta = FerramentaCortar()
        ferramenta.on_activate(canvas)
        dialog = ferramenta._obter_dialog(canvas)
        dialog.chk_costura.setChecked(False)
        dialog.cmb_modo.setCurrentText("Reta")

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(2.0, 2.0))))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(7.0, 4.0))))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(7.0, 4.0))))

        partes = canvas.cena.elementos[:2]
        self.assertFalse(
            any(
                any(abs(x - 7.0) <= 1e-6 and abs(y - 4.0) <= 1e-6 for x, y in parte["pontos"])
                for parte in partes
            )
        )

    def test_cortar_usa_clique_exato_mesmo_com_snap_puxando_para_longe(self):
        canvas = _FakeCanvasSnapRuim()
        ferramenta = FerramentaCortar()
        ferramenta.on_activate(canvas)
        ferramenta._obter_dialog(canvas).chk_costura.setChecked(False)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(2.0, 2.0))))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(5.0, -1.0))))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(5.0, -1.0))))

        self.assertEqual(canvas.historico, 1)
        self.assertEqual(len(canvas.cena.elementos), 3)
        self.assertTrue(all(parte.get("molde") for parte in canvas.cena.elementos[:2]))

    def test_cortar_contorno_denso_nao_transforma_amostras_em_controles(self):
        canvas = _FakeCanvasContornoDenso()
        ferramenta = FerramentaCortar()
        ferramenta.on_activate(canvas)
        ferramenta._obter_dialog(canvas).chk_costura.setChecked(False)

        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(2.0, 2.0))))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(5.0, -1.0))))
        self.assertTrue(ferramenta.on_mouse_press(canvas, _FakeEvent(QPointF(5.0, -1.0))))

        self.assertEqual(canvas.historico, 1)
        partes = canvas.cena.elementos[:2]
        for parte in partes:
            self.assertGreater(len(parte["pontos"]), 30)
            self.assertLessEqual(len(parte["controle_cantos"]), 6)
            self.assertLessEqual(len(parte["pontos_controle_principais"]), 6)
            self.assertTrue(parte.get("graduacao_tabela_apenas_pontos_principais"))
            self.assertTrue(any(abs(x - 5.0) <= 1e-6 for x, _y in parte["controle_cantos"]))
            self.assertGreater(len(parte["graduacao_tabela"]["pontos"]), len(parte["controle_cantos"]))

    def test_unir_restura_original_de_corte(self):
        canvas = _FakeCanvas()
        cortar = FerramentaCortar()
        cortar.on_activate(canvas)
        cortar._obter_dialog(canvas).chk_costura.setChecked(True)
        self.assertTrue(cortar.on_mouse_press(canvas, _FakeEvent(QPointF(2.0, 2.0))))
        self.assertTrue(cortar.on_mouse_press(canvas, _FakeEvent(QPointF(5.0, -1.0))))
        self.assertTrue(cortar.on_mouse_press(canvas, _FakeEvent(QPointF(5.0, -1.0))))
        self.assertEqual(len(canvas.cena.elementos), 5)

        unir = FerramentaUnir()
        self.assertTrue(unir._unir_indices(canvas, 0, 1))

        self.assertEqual(len(canvas.cena.elementos), 2)
        molde = canvas.cena.elementos[0]
        self.assertEqual(molde["pontos"], [(0.0, 0.0), (10.0, 0.0), (10.0, 8.0), (0.0, 8.0), (0.0, 0.0)])
        self.assertEqual(molde["nome_molde"], "N46")
        self.assertEqual(molde["piques_config"][0]["tipo"], "T")
        self.assertEqual(canvas.historico, 2)

    def test_unir_usa_clique_exato_mesmo_com_snap_puxando_para_longe(self):
        canvas = _FakeCanvasSnapRuim()
        cortar = FerramentaCortar()
        cortar.on_activate(canvas)
        cortar._obter_dialog(canvas).chk_costura.setChecked(False)
        self.assertTrue(cortar.on_mouse_press(canvas, _FakeEvent(QPointF(2.0, 2.0))))
        self.assertTrue(cortar.on_mouse_press(canvas, _FakeEvent(QPointF(5.0, -1.0))))
        self.assertTrue(cortar.on_mouse_press(canvas, _FakeEvent(QPointF(5.0, -1.0))))

        unir = FerramentaUnir()
        unir.on_activate(canvas)
        self.assertTrue(unir.on_mouse_press(canvas, _FakeEvent(QPointF(2.0, 2.0))))
        self.assertTrue(unir.on_mouse_press(canvas, _FakeEvent(QPointF(8.0, 2.0))))
        self.assertTrue(unir.on_mouse_press(canvas, _FakeEvent(QPointF(8.0, 2.0))))

        self.assertEqual(len(canvas.cena.elementos), 2)
        self.assertEqual(canvas.cena.elementos[0]["nome_molde"], "N46")
        self.assertEqual(canvas.historico, 2)

    def test_unir_fallback_nao_transforma_amostras_em_controles(self):
        canvas = _FakeCanvasContornoDenso()
        molde_a = canvas._molde()
        molde_b = deepcopy(molde_a)
        molde_b["molde_id"] = "m2"
        molde_b["nome_molde"] = "K2"
        for chave in ("pontos", "controle_cantos"):
            molde_b[chave] = [(x + 14.0, y) for x, y in molde_b[chave]]
        molde_b["pontos_controle_principais"] = [
            {"x": ponto["x"] + 14.0, "y": ponto["y"]}
            for ponto in molde_b["pontos_controle_principais"]
        ]
        canvas.cena.elementos = [molde_a, molde_b]

        unir = FerramentaUnir()
        self.assertTrue(unir._unir_contornos_fallback(canvas, 0, 1))

        unido = canvas.cena.elementos[0]
        self.assertGreater(len(unido["pontos"]), 80)
        self.assertLessEqual(len(unido["controle_cantos"]), 8)
        self.assertEqual(len(unido["pontos_controle_principais"]), len(unido["controle_cantos"]))


if __name__ == "__main__":
    unittest.main()
