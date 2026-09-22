from pathlib import Path
import sys

from PySide6.QtWidgets import QApplication
from app.gui.theme import apply_light_theme

from app.gui.window import MainWindow


def main():
    app = QApplication(sys.argv)
    apply_light_theme(app)
    root = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    if root.name == "DigitalTextbookMaker" and root.parent.name.startswith("dist") and (root.parent.parent / "config/models.yaml").is_file():
        root = root.parent.parent
    if '--verify-review-flow' in sys.argv:
        from app.review_verification import run
        return run(app, root)
    if '--verify-structure' in sys.argv:
        from app.structure_verification import run
        return run(app, root)
    if '--verify-local' in sys.argv:
        from app.verification import run_verification
        return run_verification(app, root)
    window = MainWindow(root)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
