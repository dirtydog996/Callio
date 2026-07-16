import sys

from callio.app import main


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("setup", "init"):
        from callio.cli.setup_wizard import run_setup_wizard

        run_setup_wizard()
    else:
        main()
