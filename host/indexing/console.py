"""Console output utilities for the indexing module."""


class Colors:
    GREEN = '\033[92m'
    GREY = '\033[90m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    ENDC = '\033[0m'


def log_info(msg: str) -> None:
    print(f"{Colors.BLUE}[INFO]{Colors.ENDC} {msg}")

def log_warn(msg: str) -> None:
    print(f"{Colors.YELLOW}[WARN]{Colors.ENDC} {msg}")

def log_error(msg: str) -> None:
    print(f"{Colors.RED}[ERROR]{Colors.ENDC} {msg}")

def log_success(msg: str) -> None:
    print(f"{Colors.GREEN}[INFO]{Colors.ENDC} {msg}")
