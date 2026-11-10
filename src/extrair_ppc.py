import argparse

from extracao import diagnosticar


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnóstico estrutural de um PPC.")
    parser.add_argument("pdf", help="caminho do PDF (ex: dados/ppc_tads.pdf)")
    parser.add_argument("--inicio", type=int, default=None, help="página inicial")
    parser.add_argument("--fim", type=int, default=None, help="página final")
    parser.add_argument(
        "--candidatas",
        action="store_true",
        help="mostrar apenas linhas maiúsculas e curtas",
    )
    args = parser.parse_args()

    diagnosticar(
        args.pdf,
        pagina_inicio=args.inicio,
        pagina_fim=args.fim,
        so_candidatas=args.candidatas,
    )


if __name__ == "__main__":
    main()