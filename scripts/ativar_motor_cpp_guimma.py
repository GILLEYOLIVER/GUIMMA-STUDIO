from __future__ import annotations

"""
Script seguro para ativar gradualmente o motor C++ no GUIMMA STUDIO.

Uso recomendado, a partir da raiz do projeto:

    python scripts/ativar_motor_cpp_guimma.py

O script altera apenas imports conhecidos e mantém fallback para Python.
Ele NÃO remove os motores Python antigos.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PATCHES = [
    {
        "path": ROOT / "tools" / "extrair_molde_tool.py",
        "old": "from core.geometry_bridge import (",
        "new": "from core.geometry_bridge_accelerated import (",
        "description": "Ativar bridge acelerado no Extrair Molde",
    },
]


def aplicar_patch(path: Path, old: str, new: str, description: str) -> bool:
    if not path.exists():
        print(f"[IGNORADO] {description}: arquivo não encontrado: {path}")
        return False

    text = path.read_text(encoding="utf-8")
    if new in text:
        print(f"[OK] {description}: já estava aplicado.")
        return True

    if old not in text:
        print(f"[AVISO] {description}: trecho antigo não encontrado em {path}")
        return False

    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"[APLICADO] {description}: {path.relative_to(ROOT)}")
    return True


def main() -> None:
    print("GUIMMA STUDIO - Ativação gradual do motor C++")
    print(f"Raiz: {ROOT}")
    print()

    total = 0
    aplicados = 0
    for patch in PATCHES:
        total += 1
        if aplicar_patch(**patch):
            aplicados += 1

    print()
    print(f"Concluído: {aplicados}/{total} ajustes aplicados.")
    print()
    print("Próximos passos:")
    print("1. Rode: git diff")
    print("2. Verifique se apenas o import do Extrair Molde foi alterado.")
    print("3. Compile o C++ se ainda não compilou.")
    print("4. Teste a ferramenta Extrair Molde.")
    print("5. Se estiver tudo correto: git add -A && git commit -m 'Ativa motor C++ no Extrair Molde' && git push origin main")


if __name__ == "__main__":
    main()
