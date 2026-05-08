from dadosbr.cli.admin import parse_args


def test_parse_cnpj_status() -> None:
    args = parse_args(["cnpj", "status"])
    assert args.entity == "cnpj"
    assert args.action == "status"


def test_parse_cnpj_sync_groups() -> None:
    args = parse_args(["cnpj", "sync", "--period", "2026-01", "--groups", "empresas,estabelecimentos"])
    assert args.period == "2026-01"
    assert args.groups == "empresas,estabelecimentos"
