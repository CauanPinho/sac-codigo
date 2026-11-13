import argparse
import os

from extracao import diagnosticar, extrair_ppc


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnóstico e extração de um PPC.")
    parser.add_argument("pdf", help="caminho do PDF (ex: dados/ppc_tads.pdf)")
    parser.add_argument("--inicio", type=int, default=None, help="página inicial (diagnóstico)")
    parser.add_argument("--fim", type=int, default=None, help="página final (diagnóstico)")
    parser.add_argument(
        "--candidatas",
        action="store_true",
        help="mostrar apenas linhas maiúsculas e curtas (diagnóstico)",
    )
    parser.add_argument(
        "--extrair",
        action="store_true",
        help="rodar a extração completa e salvar o CSV em saida/ppc_disciplinas.csv",
    )
    args = parser.parse_args()

    if args.extrair:
        df = extrair_ppc(args.pdf)
        os.makedirs("saida", exist_ok=True)
        saida_csv = "saida/ppc_disciplinas.csv"
        df.to_csv(saida_csv, index=False)

        print(f"\nArquivo: {args.pdf}")
        print(f"Disciplinas extraídas: {len(df)}")
        if not df.empty:
            print(f"Confiança média: {df['confianca'].mean():.2f}")
            print("\n10 disciplinas com menor confiança:")
            piores = df.sort_values("confianca").head(10)
            for _, linha in piores.iterrows():
                print(
                    f"  [{linha['confianca']:.2f}] {linha['disciplina']} "
                    f"(pág {linha['pagina_inicio']}-{linha['pagina_fim']}) "
                    f"avisos={linha['avisos']}"
                )
        print(f"\nCSV salvo em: {saida_csv}")
        return

    diagnosticar(
        args.pdf,
        pagina_inicio=args.inicio,
        pagina_fim=args.fim,
        so_candidatas=args.candidatas,
    )


if __name__ == "__main__":
    main()