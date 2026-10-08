"""GUI entry point — launchable via `videocaptioner` (no args) or `python -m videocaptioner.ui.main`."""

import os
import platform
import sys


def main():
    import traceback

    # FFmpeg must be on PATH before pydub / yt-dlp import side effects
    try:
        from videocaptioner.core.utils.download_helper import ensure_ffmpeg_on_path

        ensure_ffmpeg_on_path()
    except Exception:
        pass

    from PyQt5.QtCore import Qt, QLocale, QTranslator
    from PyQt5.QtWidgets import QApplication

    from videocaptioner.config import TRANSLATIONS_PATH
    from videocaptioner.core.utils.cache import disable_cache, enable_cache
    from videocaptioner.core.utils.logger import setup_logger

    # Suppress qfluentwidgets ad
    with open(os.devnull, "w") as _devnull:
        sys.stdout, _stdout = _devnull, sys.stdout
        from qfluentwidgets import FluentTranslator
        sys.stdout = _stdout

    from videocaptioner.ui.common.config import Language, cfg
    from videocaptioner.ui.view.main_window import MainWindow

    # Qt platform plugin path
    lib_folder = "Lib" if platform.system() == "Windows" else "lib"
    plugin_path = os.path.join(
        sys.prefix, lib_folder, "site-packages", "PyQt5", "Qt5", "plugins"
    )
    os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = plugin_path

    # Logger + global exception hook
    logger = setup_logger("VideoCaptioner")

    def exception_hook(exctype, value, tb):
        logger.error("".join(traceback.format_exception(exctype, value, tb)))
        sys.__excepthook__(exctype, value, tb)

    sys.excepthook = exception_hook

    # Cache
    if cfg.get(cfg.cache_enabled):
        enable_cache()
    else:
        disable_cache()

    # DPI scaling
    if cfg.get(cfg.dpiScale) == "Auto":
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough  # type: ignore
        )
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)  # type: ignore
    else:
        os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
        os.environ["QT_SCALE_FACTOR"] = str(cfg.get(cfg.dpiScale))
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)  # type: ignore

    app = QApplication(sys.argv)
    app.setAttribute(Qt.AA_DontCreateNativeWidgetSiblings, True)  # type: ignore

    # i18n — mặc định tiếng Việt
    lang_cfg = cfg.get(cfg.language)
    if lang_cfg == Language.AUTO:
        locale = QLocale(QLocale.Vietnamese, QLocale.Vietnam)
    else:
        locale = lang_cfg.value

    app.installTranslator(FluentTranslator(locale))

    # Prefer compiled .qm when available; otherwise load .ts at runtime
    from videocaptioner.ui.common.ts_translator import TsTranslator

    qm_path = TRANSLATIONS_PATH / f"VideoCaptioner_{locale.name()}.qm"
    ts_path = TRANSLATIONS_PATH / f"VideoCaptioner_{locale.name()}.ts"
    # Fallback aliases
    if not qm_path.exists() and not ts_path.exists():
        name = locale.name()
        if name.startswith("vi"):
            qm_path = TRANSLATIONS_PATH / "VideoCaptioner_vi_VN.qm"
            ts_path = TRANSLATIONS_PATH / "VideoCaptioner_vi_VN.ts"
        elif name.startswith("en"):
            qm_path = TRANSLATIONS_PATH / "VideoCaptioner_en_US.qm"
            ts_path = TRANSLATIONS_PATH / "VideoCaptioner_en_US.ts"
        elif name.startswith("zh"):
            # Traditional vs simplified
            if "HK" in name or "TW" in name or "Hant" in name:
                qm_path = TRANSLATIONS_PATH / "VideoCaptioner_zh_HK.qm"
                ts_path = TRANSLATIONS_PATH / "VideoCaptioner_zh_HK.ts"
            else:
                qm_path = TRANSLATIONS_PATH / "VideoCaptioner_zh_CN.qm"
                ts_path = TRANSLATIONS_PATH / "VideoCaptioner_zh_CN.ts"

    my_translator = QTranslator()
    loaded = False
    if qm_path.exists() and qm_path.stat().st_size > 32:
        loaded = my_translator.load(str(qm_path))
    if not loaded and ts_path.exists():
        ts_translator = TsTranslator()
        if ts_translator.load_ts(ts_path):
            my_translator = ts_translator
            loaded = True
    if loaded:
        app.installTranslator(my_translator)

    w = MainWindow()
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
