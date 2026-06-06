class Stage:
    """流水线阶段基类。子类设置 name / manual，并实现 run()。"""

    name = "Stage"
    manual = False

    def run(self, config, emit):
        """执行阶段。emit(str) 推送进度。抛异常表示失败。"""
        raise NotImplementedError

    def validate_resume(self, config):
        """手动阶段在 continue 恢复前的前置校验。默认无校验。

        子类可重写，校验不通过时抛 ValueError。
        """
        return


class BRStage(Stage):
    name = "BR"
    manual = True  # 手动阶段：工具开 Bridge 指向文件夹，用户全选+⌘R 进 ACR 手调

    def run(self, config, emit):
        from pipeline import launcher
        emit("BR 阶段：正在打开 Adobe Bridge…")
        try:
            launcher.open_in_app(launcher.BRIDGE_APP, config.raw_folder)
            emit("BR 阶段：Bridge 已打开 RAW 文件夹，请全选并按 ⌘R 进 Camera Raw 调整透视/镜头配置/色差，完成后点继续")
        except Exception as exc:
            emit(f"BR 阶段：无法自动打开 Bridge（{exc}），请手动打开 {config.raw_folder} 调整后点继续")


class LRTStage(Stage):
    name = "LRT"
    manual = True  # 手动阶段：runner 跑到这里会暂停等用户

    def run(self, config, emit):
        from pipeline import launcher
        emit("LRT 阶段：正在打开 LRTimelapse…")
        try:
            launcher.open_in_app(launcher.LRT_APP, config.raw_folder)
            emit("LRT 阶段：请在 LRTimelapse 中完成关键帧/去闪/自动过渡/圣光（写入 XMP），完成后点继续，无需导出")
        except Exception as exc:
            emit(f"LRT 阶段：无法自动打开 LRTimelapse（{exc}），请手动打开 {config.raw_folder} 操作后点继续")


class AEStage(Stage):
    name = "AE"
    manual = False

    def run(self, config, emit):
        from pipeline import ae
        chunks = ae.render_sequence(
            seq_folder=config.raw_folder,
            output_dir=config.output_path,
            fps=config.fps,
            resolution=config.resolution,
            stabilize=config.stabilize,
            emit=emit,
        )
        # 把分块片段无损拼成 _ae_intermediate.mov，供 PR 阶段消费
        ae.merge_chunks(chunks, config.output_path, emit)


class ExportStage(Stage):
    name = "导出"
    manual = False

    def run(self, config, emit):
        from pipeline import ae, export
        intermediate = ae.intermediate_path(config.output_path)
        export.render_exports(
            intermediate_video=str(intermediate),
            output_dir=config.output_path,
            social=config.social,
            emit=emit,
        )


def default_stages():
    return [BRStage(), LRTStage(), AEStage(), ExportStage()]
