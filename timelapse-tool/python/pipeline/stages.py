from pathlib import Path

# LRT 导出的图像序列可能的扩展名
SEQUENCE_EXTS = {".tif", ".tiff", ".jpg", ".jpeg", ".png"}


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
    manual = True  # 手动阶段：工具开 Bridge+全选+调出 ACR，用户手动调

    def run(self, config, emit):
        # 真实实现（Bridge 打开文件夹/全选/调出 Camera Raw）由后续计划替换
        emit("BR 阶段：在 Adobe Bridge 中打开 RAW 文件夹并全选，进入 Camera Raw 手动调整透视/镜头配置/色差")


class LRTStage(Stage):
    name = "LRT"
    manual = True  # 手动阶段：runner 跑到这里会暂停等用户

    def run(self, config, emit):
        # 打开 LRT 的逻辑由后续计划补充
        emit("LRT 阶段：请在 LRTimelapse 中手动完成关键帧/去闪/导出序列")

    def validate_resume(self, config):
        # 恢复前校验：LRT 导出文件夹必须已有图像序列
        folder = Path(config.lrt_export_folder)
        has_image = any(p.suffix.lower() in SEQUENCE_EXTS for p in folder.iterdir())
        if not has_image:
            raise ValueError("LRT 导出文件夹里没有图像序列，请先在 LRTimelapse 中导出")


class AEStage(Stage):
    name = "AE"
    manual = False

    def run(self, config, emit):
        from pipeline import ae
        ae.render_sequence(
            seq_folder=config.lrt_export_folder,
            output_dir=config.output_path,
            fps=config.fps,
            stabilize=config.stabilize,
            emit=emit,
        )


class PRStage(Stage):
    name = "PR"
    manual = False

    def run(self, config, emit):
        # 桩：真实实现（Premiere 导出）由后续计划替换
        emit("PR 阶段（桩）：导入、增稳、按规格导出成片")


def default_stages():
    return [BRStage(), LRTStage(), AEStage(), PRStage()]
