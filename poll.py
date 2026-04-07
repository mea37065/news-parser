from credentials import load_credentials

load_credentials()

from bot import handle_callbacks


def main() -> None:
    handle_callbacks()


if __name__ == "__main__":
    main()
